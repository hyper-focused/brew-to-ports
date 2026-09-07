"""Dumb edge: Homebrew CLI / JSON dump → dict. Does not classify."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from brew_to_ports.adapters.os_tools import INTEL_BREW, INTEL_BREW_BIN, subprocess_env


class BrewError(RuntimeError):
    pass


def brew_prefix() -> str:
    if not os.path.isfile(INTEL_BREW):
        return "/usr/local"
    try:
        out = subprocess.check_output(
            [INTEL_BREW, "--prefix"],
            text=True,
            stderr=subprocess.DEVNULL,
            env=subprocess_env(INTEL_BREW_BIN),
        )
        return out.strip() or "/usr/local"
    except (OSError, subprocess.CalledProcessError):
        return "/usr/local"


def load_installed_json(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if not os.path.isfile(INTEL_BREW):
        raise BrewError(f"Homebrew not found at {INTEL_BREW} (Intel prefix). Need `brew info --json=v2 --installed`.")
    try:
        out = subprocess.check_output(
            [INTEL_BREW, "info", "--json=v2", "--installed"],
            text=True,
            stderr=subprocess.PIPE,
            env=subprocess_env(INTEL_BREW_BIN),
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
