"""Dumb edge: Homebrew CLI / JSON dump → dict. Does not classify."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class BrewError(RuntimeError):
    pass


def brew_prefix() -> str:
    brew = shutil.which("brew")
    if not brew:
        return "/usr/local"
    try:
        out = subprocess.check_output([brew, "--prefix"], text=True, stderr=subprocess.DEVNULL)
        return out.strip() or "/usr/local"
    except (OSError, subprocess.CalledProcessError):
        return "/usr/local"


def load_installed_json(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    brew = shutil.which("brew")
    if not brew:
        raise BrewError("Homebrew not found on PATH. Need `brew info --json=v2 --installed`.")
    try:
        out = subprocess.check_output(
            [brew, "info", "--json=v2", "--installed"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or "").strip()
        raise BrewError(f"`brew info --json=v2 --installed` failed: {err or exc}") from exc
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise BrewError("brew JSON schema/parse error from `brew info --json=v2 --installed`") from exc


def python_is_from_brew(python: str, prefix: Optional[str] = None) -> bool:
    prefix = prefix or brew_prefix()
    try:
        resolved = os.path.realpath(python)
    except OSError:
        resolved = python
    return resolved.startswith(os.path.realpath(prefix) + os.sep)
