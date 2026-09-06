"""Dumb edge: read PATH and shell rc files, following source/. includes. Does not write them."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Set, Tuple

# zsh: .zshenv runs for every shell (including zsh -c). PATH often lives there.
RC_NAMES = (
    ".zshenv",
    ".zshrc",
    ".zprofile",
    ".zlogin",
    ".bashrc",
    ".bash_profile",
    ".profile",
)
MAX_INCLUDE_DEPTH = 8

# `source file` / `. file` after a newline, `&&`, or `;`
# Also matches inside `[[ -f file ]] && source file`.
_SOURCE_RE = re.compile(
    r"""(?:^|&&|;)\s*(?:source|\.)\s+(?P<path>(?:['\"][^'\"]+['\"]|[^\s;'\"&|<>]+))""",
    re.MULTILINE,
)

_SAFE_VARS = ("HOME", "ZDOTDIR")


def current_path() -> str:
    return os.environ.get("PATH") or ""


def read_rc_files(home: Path | None = None) -> List[Tuple[Path, str]]:
    """Return (path, text) for standard rc files and files they source, depth-limited."""
    home = (home or Path.home()).expanduser()
    found: List[Tuple[Path, str]] = []
    seen: Set[Path] = set()
    for name in RC_NAMES:
        path = home / name
        _collect(path, home, found, seen, depth=0)
    return found


def sourced_paths(text: str, *, from_file: Path, home: Path) -> List[Path]:
    """Parse source/. includes. Conservative: HOME/ZDOTDIR/~ only, no eval."""
    hits: List[Path] = []
    for match in _SOURCE_RE.finditer(text):
        raw = match.group("path").strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
        resolved = _resolve_include(raw, from_file=from_file, home=home)
        if resolved is not None:
            hits.append(resolved)
    return hits


def _collect(
    path: Path,
    home: Path,
    found: List[Tuple[Path, str]],
    seen: Set[Path],
    depth: int,
) -> None:
    try:
        path = path.expanduser().resolve()
    except OSError:
        return
    if path in seen or not path.is_file():
        return
    seen.add(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    found.append((path, text))
    if depth >= MAX_INCLUDE_DEPTH:
        return
    for included in sourced_paths(text, from_file=path, home=home):
        _collect(included, home, found, seen, depth + 1)


def _resolve_include(raw: str, *, from_file: Path, home: Path) -> Path | None:
    if not raw or raw.startswith("(") or raw.startswith("<"):
        return None
    if "${" in raw:
        # Only ${HOME} / ${ZDOTDIR} / ${ZDOTDIR:-$HOME}
        raw = raw.replace("${ZDOTDIR:-$HOME}", str(home))
        raw = raw.replace("${ZDOTDIR:-${HOME}}", str(home))
        raw = raw.replace("${HOME}", str(home))
        zdot = os.environ.get("ZDOTDIR") or str(home)
        raw = raw.replace("${ZDOTDIR}", zdot)
        if "${" in raw or "$(" in raw:
            return None
    raw = raw.replace("$HOME", str(home))
    zdot = os.environ.get("ZDOTDIR") or str(home)
    raw = raw.replace("$ZDOTDIR", zdot)
    if raw.startswith("~"):
        raw = str(home) + raw[1:]
    if "$" in raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        candidate = (from_file.parent / path).resolve()
        if candidate.is_file():
            path = candidate
        else:
            path = (home / path).resolve()
    try:
        path = path.resolve()
    except OSError:
        return None
    # User rc only. Do not follow Homebrew/MacPorts/antidote/plugin trees.
    home_resolved = home.resolve()
    if not _is_relative_to(path, home_resolved):
        return None
    return path if path.is_file() else None


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False
