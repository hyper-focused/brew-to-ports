"""Repo and data locations. Not a dumping ground — path resolution only."""

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_file(name: str) -> Path:
    return repo_root() / "data" / name
