"""Dumb edge: locate/parse PortIndex and `port select --summary`. Does not classify."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from brew_to_ports.adapters.os_tools import subprocess_env
from brew_to_ports.catalog import Catalog, from_portindex_text

DEFAULT_PORTS_PREFIX = "/opt/local"
SOURCES_ROOT = "/opt/local/var/macports/sources"


class MacPortsError(RuntimeError):
    pass


def ports_prefix() -> str:
    return os.environ.get("MACPORTS_PREFIX") or DEFAULT_PORTS_PREFIX


def find_portindex(explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit is not None:
        path = Path(explicit)
        return path if path.is_file() else None
    env = os.environ.get("BREW_TO_PORTS_PORTINDEX")
    if env:
        path = Path(env)
        if path.is_file():
            return path
    root = Path(SOURCES_ROOT)
    if not root.is_dir():
        return None
    matches = sorted(p for p in root.rglob("PortIndex") if p.is_file() and p.name == "PortIndex")
    if not matches:
        return None
    # Prefer a tree PortIndex over PortIndex_darwin_* copies if both exist.
    preferred = [p for p in matches if "PortIndex_" not in str(p.parent)]
    return (preferred or matches)[0]


def load_catalog(explicit: Optional[Path] = None) -> Catalog:
    path = find_portindex(explicit)
    if path is None:
        return Catalog([], source="missing")
    text = path.read_text(encoding="utf-8", errors="replace")
    return from_portindex_text(text, source=str(path))


def load_select_summary(port: Optional[str] = None) -> List[Tuple[str, str, Sequence[str]]]:
    """Live `port select --summary` → (group, selected, options). Empty if no port."""
    binary = port or f"{ports_prefix().rstrip('/')}/bin/port"
    if not os.path.isfile(binary):
        return []
    try:
        out = subprocess.check_output(
            [binary, "select", "--summary"],
            text=True,
            stderr=subprocess.DEVNULL,
            env=subprocess_env(),
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return parse_select_summary(out)


def parse_select_summary(text: str) -> List[Tuple[str, str, Sequence[str]]]:
    rows: List[Tuple[str, str, Sequence[str]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("Name") or line.startswith("===="):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        group, selected = parts[0], parts[1]
        options = parts[2].split() if len(parts) > 2 else []
        rows.append((group, selected, options))
    return rows
