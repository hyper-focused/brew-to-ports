"""Plan-time runtime cutover. Writer of CutoverChoice. No keep-set, no script."""

from __future__ import annotations

import sys
from typing import Iterable, List, Optional, Sequence, TextIO

from brew_to_ports.family import RuntimeFamily
from brew_to_ports.models import CUTOVER_MIGRATE, CUTOVER_SKIP, CutoverChoice


class CutoverAbort(SystemExit):
    """q / Ctrl-C: write nothing."""

    def __init__(self, message: str = "brew-to-ports: cutover aborted; wrote nothing.") -> None:
        super().__init__(message)


def decide_cutover(
    families: Sequence[RuntimeFamily],
    *,
    migrate_runtime: Optional[Iterable[str]] = None,
    acked_drop: Optional[Iterable[str]] = None,
    interactive: bool = False,
    stdin: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> List[CutoverChoice]:
    """Default: skip all. TTY prompts when interactive. Flags for non-TTY."""
    want = {n.lower() for n in (migrate_runtime or [])}
    acked = {n.lower() for n in (acked_drop or [])}
    err = stderr if stderr is not None else sys.stderr
    inf = stdin if stdin is not None else sys.stdin
    choices: List[CutoverChoice] = []
    for fam in families:
        flagged = fam.runtime.lower() in want
        if interactive:
            choice = _prompt_family(fam, inf, err)
        elif flagged:
            if fam.drop and fam.runtime.lower() not in acked:
                choices.append(
                    CutoverChoice(
                        runtime=fam.runtime,
                        action=CUTOVER_SKIP,
                        can=list(fam.can),
                        drop=list(fam.drop),
                        blocked=list(fam.blocked),
                        note="missing --i-acked-drop; skipped",
                    )
                )
                continue
            choice = CutoverChoice(
                runtime=fam.runtime,
                action=CUTOVER_MIGRATE,
                can=list(fam.can),
                drop=list(fam.drop),
                blocked=list(fam.blocked),
            )
        else:
            choice = CutoverChoice(
                runtime=fam.runtime,
                action=CUTOVER_SKIP,
                can=list(fam.can),
                drop=list(fam.drop),
                blocked=list(fam.blocked),
            )
        choices.append(choice)
    return choices


def _prompt_family(fam: RuntimeFamily, stdin: TextIO, err: TextIO) -> CutoverChoice:
    _print_family(fam, err)
    while True:
        err.write(f"[m]igrate  [s]kip  [q]uit  {fam.runtime}: ")
        err.flush()
        raw = _readline(stdin)
        if raw is None:
            raise CutoverAbort()
        key = raw.strip().lower()
        if key in ("q", "quit"):
            raise CutoverAbort()
        if key in ("s", "skip"):
            err.write(f"skipping {fam.runtime}\n")
            err.flush()
            return CutoverChoice(
                runtime=fam.runtime,
                action=CUTOVER_SKIP,
                can=list(fam.can),
                drop=list(fam.drop),
                blocked=list(fam.blocked),
            )
        if key in ("m", "migrate"):
            if fam.drop and not _confirm_drop(fam, stdin, err):
                err.write(f"skipping {fam.runtime} (confirm was not 'yes')\n")
                err.flush()
                return CutoverChoice(
                    runtime=fam.runtime,
                    action=CUTOVER_SKIP,
                    can=list(fam.can),
                    drop=list(fam.drop),
                    blocked=list(fam.blocked),
                    note="confirm was not yes",
                )
            return CutoverChoice(
                runtime=fam.runtime,
                action=CUTOVER_MIGRATE,
                can=list(fam.can),
                drop=list(fam.drop),
                blocked=list(fam.blocked),
            )
        err.write("type m, s, or q\n")
        err.flush()


def _confirm_drop(fam: RuntimeFamily, stdin: TextIO, err: TextIO) -> bool:
    err.write(
        f"\nThese brew packages have no MacPorts equivalent.\n"
        f"They will be uninstalled and not replaced:\n\n"
    )
    for name in fam.drop:
        err.write(f"  {name}\n")
    err.write(
        f"\nType 'yes' to continue, or anything else to skip {fam.runtime}.\n"
        f"site-packages / venvs of this interpreter are out of scope.\n"
        f"yes: "
    )
    err.flush()
    raw = _readline(stdin)
    if raw is not None and raw.strip() == "yes":
        return True
    err.write(f"type 'yes' to confirm, anything else skips {fam.runtime}: ")
    err.flush()
    raw = _readline(stdin)
    return raw is not None and raw.strip() == "yes"


def _print_family(fam: RuntimeFamily, err: TextIO) -> None:
    err.write(f"\nRuntime family: {fam.runtime}\n")
    err.write("Can migrate to MacPorts:\n")
    if fam.can:
        for name in fam.can:
            err.write(f"  {name}\n")
    else:
        err.write("  (none)\n")
    err.write("No MacPorts equivalent (removed and not replaced if you migrate):\n")
    if fam.drop:
        for name in fam.drop:
            err.write(f"  {name}\n")
    else:
        err.write("  (none)\n")
    if fam.blocked:
        err.write("Blocked (older/unparseable — stay on brew):\n")
        for name in fam.blocked:
            err.write(f"  {name}\n")
    err.write("\n")
    err.flush()


def _readline(stdin: TextIO) -> Optional[str]:
    try:
        line = stdin.readline()
    except KeyboardInterrupt:
        raise CutoverAbort() from None
    if line == "":
        return None
    return line
