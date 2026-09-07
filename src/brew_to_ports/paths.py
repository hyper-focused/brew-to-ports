"""Repo and data locations. Not a dumping ground — path resolution only."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_file(name: str) -> Path:
    return repo_root() / "data" / name


def workspace_logs_dir(root: Path | None = None) -> Path:
    """Visible logs/ next to where the operator ran the tool."""
    return (root or Path.cwd()) / "logs"


def default_path_file(root: Path | None = None) -> Path:
    return workspace_logs_dir(root) / "zsh_path"


def default_scan_log(today: date | None = None, root: Path | None = None) -> Path:
    day = (today or date.today()).isoformat()
    return workspace_logs_dir(root) / f"scan-{day}.txt"
