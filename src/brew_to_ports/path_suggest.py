"""Read current PATH + rc snippets; propose MacPorts-first PATH. Does not write rc files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, Tuple

from brew_to_ports.adapters.shell_env import sourced_paths
from brew_to_ports.models import PathAdvice, PathLine

INTEL_BREW_BIN = "/usr/local/bin"
INTEL_BREW_SBIN = "/usr/local/sbin"
ARM_BREW_BIN = "/opt/homebrew/bin"

# Real PATH mutation — not fpath=(, not comments.
_PATH_ARRAY_RE = re.compile(r"(?m)^[ \t]*path=\(")
_EXPORT_PATH_RE = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?PATH=")
_BREW_SHELLENV_RE = re.compile(r"brew[ \t]+shellenv")
_ALIAS_BREW_RE = re.compile(
    r"""(?m)^[ \t]*alias[ \t]+\S+=.*(?:/usr/local|/opt/homebrew)"""
)
_LINKER_RE = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?(?:LDFLAGS|CPPFLAGS|PKG_CONFIG_PATH)="
)
_MACPORTS_INSTALLER_RE = re.compile(r"MacPorts Installer addition")


def default_path_file(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".zsh_path.brew-to-ports"


def suggest_path(
    current_path: str,
    rc_files: Sequence[Tuple[Path, str]] | None = None,
    brew_prefix: str = "/usr/local",
    ports_prefix: str = "/opt/local",
    path_file: Path | None = None,
    home: Path | None = None,
) -> PathAdvice:
    home = home or Path.home()
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
    for brew_item in (brew_bin, brew_sbin):
        if brew_item in rest:
            rest = [p for p in rest if p != brew_item]
            rest.append(brew_item)
        elif brew_item not in rest and Path(brew_item).exists():
            rest.append(brew_item)

    suggested = ":".join(head + rest)
    analysis = _analyze_rc(rc_files or [])

    notes = [
        "Do not edit rc files automatically. Comment the listed lines yourself; source the generated path file.",
        "PKG_CONFIG_PATH / LDFLAGS / CPPFLAGS that point at brew prefixes will still see Homebrew libs until you change them.",
        "Includes are followed (source / .) under $HOME only — not Homebrew/antidote plugin trees.",
    ]
    if analysis["path_owners"]:
        notes.append(
            "PATH owner(s): "
            + ", ".join(analysis["path_owners"])
            + f" (idiom: {analysis['idiom'] or 'unknown'})."
        )
    if analysis["extra_writers"]:
        notes.append(
            "Extra PATH writers (second opinions — pick one owner): "
            + "; ".join(analysis["extra_writers"])
        )
    if analysis["alias_hits"]:
        notes.append(
            "Hardcoded Homebrew aliases (update if those formulae migrate): "
            + ", ".join(analysis["alias_hits"])
        )
    if analysis["linker_hits"]:
        notes.append(
            "Linker/pkg-config flags still pointing at brew: "
            + ", ".join(analysis["linker_hits"])
        )
    if analysis["path_helper"]:
        notes.append(
            "Login zsh runs /etc/zprofile path_helper BETWEEN .zshenv and .zprofile. "
            "Keep a load of the generated path file in .zprofile (after path_helper), not brew shellenv."
        )
    if ARM_BREW_BIN in entries:
        notes.append("PATH contains /opt/homebrew/bin — unexpected on Intel; leaving it in place but MacPorts still goes first.")
    if INTEL_BREW_BIN in entries and ports_bin:
        notes.append("Dual-stack: MacPorts first, leftover Homebrew after. Name collisions will shadow brew binaries.")

    array_entries: List[str] = []
    if analysis["idiom"] == "zsh-array":
        for path, text in rc_files or []:
            if str(path) in analysis["path_owners"]:
                array_entries = _rewrite_zsh_array(text, ports_bin, ports_sbin)
                break
    if not array_entries:
        array_entries = [_zsh_path_entry(p) for p in suggested.split(":") if p]

    dest = path_file or default_path_file(home)
    abs_entries = [_expand_entry(e, home=home) for e in array_entries]
    path_file_contents = _path_file_contents(abs_entries)
    comment_out = _comment_out_lines(rc_files or [], analysis["path_owners"], home=home)
    load_zsh, load_bash = _load_snippets(dest, home=home)

    notes.append(f"Generated PATH file: {dest} (written with --script or --path-file).")
    notes.append("Comment out the listed source/export/shellenv lines, then load that file from .zshenv and again from .zprofile after path_helper.")

    return PathAdvice(
        current_path=current_path,
        suggested=suggested,
        rc_hits=analysis["rc_hits"],
        collisions=[],
        notes=notes,
        path_owners=analysis["path_owners"],
        idiom=analysis["idiom"],
        extra_writers=analysis["extra_writers"],
        alias_hits=analysis["alias_hits"],
        linker_hits=analysis["linker_hits"],
        array_entries=array_entries,
        path_file=str(dest),
        path_file_contents=path_file_contents,
        comment_out=comment_out,
        load_zsh=load_zsh,
        load_bash=load_bash,
    )


def snippet(advice: PathAdvice) -> str:
    """Human instructions: comment detected PATH writers, load the generated file."""
    lines = [
        f"# brew-to-ports PATH cutover (does not edit rc files for you)",
        f"# 1. Review/write {advice.path_file or default_path_file()}",
        "# 2. Comment out these detected PATH writers:",
    ]
    if advice.comment_out:
        current = None
        for item in advice.comment_out:
            if item.path != current:
                lines.append(f"#    {item.path}")
                current = item.path
            lines.append(f"#      {item.lineno}: {item.text}")
    else:
        lines.append("#    (none detected)")
    lines.append("# 3. In their place, load the generated file:")
    lines.append("#    zsh (.zshenv and again in .zprofile after path_helper):")
    for raw in (advice.load_zsh or "").splitlines():
        lines.append(raw)
    lines.append("#    bash (.profile / .bash_profile):")
    for raw in (advice.load_bash or "").splitlines():
        lines.append(raw)
    lines.append("# Leave the old PATH owner file in place as a backup.")
    return "\n".join(lines) + "\n"


def _analyze_rc(rc_files: Sequence[Tuple[Path, str]]) -> dict:
    path_owners: List[str] = []
    extra_writers: List[str] = []
    alias_hits: List[str] = []
    linker_hits: List[str] = []
    rc_hits: List[str] = []
    owner_idioms = set()
    names = {p.name for p, _ in rc_files}
    path_helper = ".zshenv" in names and ".zprofile" in names
    dedicated = {".zsh_path", ".path", ".env"}

    for path, text in rc_files:
        has_array = bool(_PATH_ARRAY_RE.search(text))
        has_export = bool(_EXPORT_PATH_RE.search(text))
        has_shellenv = bool(_BREW_SHELLENV_RE.search(text))
        installer = bool(_MACPORTS_INSTALLER_RE.search(text))
        aliases = _ALIAS_BREW_RE.findall(text)
        linker = bool(_LINKER_RE.search(text)) and (
            "/usr/local" in text or "/opt/homebrew" in text
        )

        if has_array:
            path_owners.append(str(path))
            owner_idioms.add("zsh-array")
        elif has_export and path.name in dedicated and not installer:
            path_owners.append(str(path))
            owner_idioms.add("export-path")
        elif has_export and installer:
            extra_writers.append(
                f"{path}: MacPorts installer prepended export PATH= (duplicate writer; prefer the path owner file)"
            )
        elif has_export:
            extra_writers.append(f"{path}: export PATH=")

        if has_shellenv:
            extra_writers.append(f"{path}: eval brew shellenv (rewrites PATH on login)")
        if aliases:
            alias_hits.append(f"{path} ({len(aliases)} alias(es))")
        if linker:
            linker_hits.append(str(path))
        if has_array or has_export or has_shellenv or aliases or linker or installer:
            rc_hits.append(str(path))

    if "zsh-array" in owner_idioms:
        idiom = "zsh-array"
    elif owner_idioms == {"export-path"}:
        idiom = "export-path"
    elif owner_idioms:
        idiom = "mixed"
    else:
        idiom = "unknown"

    return {
        "path_owners": path_owners,
        "extra_writers": extra_writers,
        "alias_hits": alias_hits,
        "linker_hits": linker_hits,
        "rc_hits": rc_hits,
        "idiom": idiom,
        "path_helper": path_helper,
    }


_PATH_ARRAY_BODY_RE = re.compile(r"(?ms)^[ \t]*path=\((.*?)\)")


def _rewrite_zsh_array(text: str, ports_bin: str, ports_sbin: str) -> List[str]:
    """Rebuild the owner's path=(...) with MacPorts near the top. Keep $path at the end."""
    match = _PATH_ARRAY_BODY_RE.search(text)
    if not match:
        return [ports_bin, ports_sbin]
    cleaned: List[str] = []
    skip = {ports_bin, ports_sbin, ports_bin + "/", ports_sbin + "/"}
    for line in match.group(1).splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry or entry in ("$path", "path"):
            continue
        if entry.rstrip("/") in skip or entry in skip:
            continue
        if entry.startswith("/"):
            cleaned.append(_norm_entry(entry))
        else:
            cleaned.append(entry)
    insert_at = 0
    for i, entry in enumerate(cleaned):
        if entry.startswith("$HOME") or entry.startswith("~"):
            insert_at = i + 1
            continue
        break
    return cleaned[:insert_at] + [ports_bin, ports_sbin] + cleaned[insert_at:]


def _path_file_contents(abs_entries: List[str]) -> str:
    lines = [
        "# brew-to-ports generated PATH — one directory per line.",
        "# Not a script. Load it with the zsh/bash array one-liners from the scan report.",
        "",
    ]
    seen = set()
    for entry in abs_entries:
        if not entry or entry in seen:
            continue
        seen.add(entry)
        lines.append(entry)
    return "\n".join(lines) + "\n"


def _load_snippets(dest: Path, home: Path | None = None) -> tuple:
    loc = str(dest)
    home_s = str(home or Path.home())
    if loc.startswith(home_s + "/"):
        display = "$HOME/" + loc[len(home_s) + 1 :]
    else:
        display = loc
    zsh = (
        'path=( ${(f)"$(< ' + display + ')"} $path )\n'
        "typeset -gU path\n"
        "path=( ${^path}(N-/) )\n"
    )
    bash = (
        'PATH="$(grep -v \'^[[:space:]]*#\' '
        + display
        + ' | grep -v \'^[[:space:]]*$\' | paste -sd: -)${PATH:+:$PATH}"\n'
        "export PATH\n"
    )
    return zsh, bash


def _comment_out_lines(
    rc_files: Sequence[Tuple[Path, str]],
    owners: List[str],
    home: Path | None = None,
) -> List[PathLine]:
    owner_resolved = set()
    for raw in owners:
        try:
            owner_resolved.add(Path(raw).expanduser().resolve())
        except OSError:
            continue
    dedicated = {".zsh_path", ".path", ".env", ".zsh_path.brew-to-ports"}
    home = home or Path.home()
    found: List[PathLine] = []
    for path, text in rc_files:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path
        if resolved in owner_resolved:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            kind = ""
            replace = False
            if _BREW_SHELLENV_RE.search(line):
                kind = "shellenv"
            elif _EXPORT_PATH_RE.match(line) or _EXPORT_PATH_RE.search(line):
                kind = "export"
            else:
                sourced = sourced_paths(line + "\n", from_file=path, home=home)
                for src in sourced:
                    try:
                        src_res = src.resolve()
                    except OSError:
                        src_res = src
                    if src_res in owner_resolved or src.name in dedicated:
                        kind = "source_owner"
                        replace = True
                        break
            if kind:
                found.append(
                    PathLine(
                        path=str(path),
                        lineno=lineno,
                        text=stripped,
                        kind=kind,
                        replace_with_load=replace,
                    )
                )
    return found


def _expand_entry(entry: str, home: Path | None = None) -> str:
    home_s = str(home or Path.home())
    if entry.startswith("$HOME"):
        return home_s + entry[len("$HOME") :]
    if entry.startswith("~"):
        return home_s + entry[1:]
    return entry


def _zsh_path_entry(entry: str) -> str:
    home = str(Path.home())
    if entry == home:
        return "$HOME"
    if entry.startswith(home + "/"):
        return "$HOME/" + entry[len(home) + 1 :]
    return entry


def _norm_entry(entry: str) -> str:
    if entry != "/":
        return entry.rstrip("/")
    return entry
