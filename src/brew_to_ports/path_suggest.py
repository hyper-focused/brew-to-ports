"""Read current PATH + rc snippets; propose MacPorts-first PATH. Does not write rc files."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from brew_to_ports.models import PathAdvice

INTEL_BREW_BIN = "/usr/local/bin"
INTEL_BREW_SBIN = "/usr/local/sbin"
ARM_BREW_BIN = "/opt/homebrew/bin"
PORTS_BIN = "/opt/local/bin"
PORTS_SBIN = "/opt/local/sbin"

BREW_MARKERS = ("/usr/local/bin", "/usr/local/sbin", "/opt/homebrew/bin", "brew --prefix", "HOMEBREW")
PORTS_MARKERS = ("/opt/local/bin", "/opt/local/sbin")


def suggest_path(
    current_path: str,
    rc_files: Sequence[Tuple[Path, str]] | None = None,
    brew_prefix: str = "/usr/local",
    ports_prefix: str = "/opt/local",
) -> PathAdvice:
    entries = [_norm_entry(p) for p in current_path.split(":") if p]
    ports_bin = f"{ports_prefix}/bin"
    ports_sbin = f"{ports_prefix}/sbin"
    brew_bin = f"{brew_prefix}/bin"
    brew_sbin = f"{brew_prefix}/sbin"

    head = []
    for item in (ports_bin, ports_sbin):
        if item not in head:
            head.append(item)
    rest = [p for p in entries if p not in head]
    # Keep leftover brew after ports even if it was earlier in PATH.
    for brew_item in (brew_bin, brew_sbin):
        if brew_item in rest:
            rest = [p for p in rest if p != brew_item]
            rest.append(brew_item)
        elif brew_item not in rest and Path(brew_item).exists():
            rest.append(brew_item)

    suggested = ":".join(head + rest)

    rc_hits: List[str] = []
    for path, text in rc_files or []:
        if any(marker in text for marker in BREW_MARKERS + PORTS_MARKERS):
            rc_hits.append(str(path))

    collisions: List[str] = []
    notes = [
        "Do not edit rc files automatically. Paste the block if you want it.",
        "PKG_CONFIG_PATH / LDFLAGS / CPPFLAGS that point at $(brew --prefix …) will still see Homebrew libs until you change them.",
        "Includes are followed (source / .), so PATH in ~/.zsh_path still shows up here.",
    ]
    if rc_hits:
        notes.append(
            "PATH-related lines found in: "
            + ", ".join(rc_hits)
            + " — paste the replacement in the file that actually sets PATH, not necessarily .zshrc."
        )
    if ARM_BREW_BIN in entries:
        notes.append("PATH contains /opt/homebrew/bin — unexpected on Intel; leaving it in place but MacPorts still goes first.")
    if INTEL_BREW_BIN in entries and ports_bin:
        notes.append("Dual-stack: MacPorts first, leftover Homebrew after. Name collisions will shadow brew binaries.")

    return PathAdvice(
        current_path=current_path,
        suggested=suggested,
        rc_hits=rc_hits,
        collisions=collisions,
        notes=notes,
    )


def _norm_entry(entry: str) -> str:
    if entry != "/":
        return entry.rstrip("/")
    return entry


def snippet(advice: PathAdvice) -> str:
    return (
        "# brew-to-ports: MacPorts first; leftover Homebrew after\n"
        f'export PATH="{advice.suggested}"\n'
    )
