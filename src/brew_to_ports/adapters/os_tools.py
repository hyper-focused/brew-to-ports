"""Dumb edge: Apple CLI locations. Migrator never searches user PATH/gnubin."""

from __future__ import annotations

import os
from typing import Dict, Optional

# BSD/Apple tools. No gnubin, no keg, no /opt/local/libexec.
OS_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
INTEL_BREW = "/usr/local/bin/brew"
INTEL_BREW_BIN = "/usr/local/bin"
INTEL_PORTS_BIN = "/opt/local/bin"
USER_PATH_ENV = "BREW_TO_PORTS_USER_PATH"


def migrator_path(*extra_bins: str) -> str:
    """OS dirs first, then extra prefix bins (brew/port). Never gnubin."""
    parts = OS_PATH.split(":")
    seen = set(parts)
    for raw in extra_bins:
        if not raw:
            continue
        for item in raw.split(":"):
            if item and item not in seen:
                parts.append(item)
                seen.add(item)
    return ":".join(parts)


def subprocess_env(*extra_bins: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = migrator_path(*extra_bins)
    return env


def user_path(environ: Optional[Dict[str, str]] = None) -> str:
    """PATH the user launched with (wrapper stashes it before pinning)."""
    env = environ if environ is not None else os.environ
    return env.get(USER_PATH_ENV) or env.get("PATH") or ""
