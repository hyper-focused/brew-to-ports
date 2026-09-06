"""Inventory brew-side config/state. Never copies files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

from brew_to_ports.classify import load_exceptions, _name_matches
from brew_to_ports.models import ConfigFile, Decision, Package, STATUS_MIGRATE

BREW_PATH_MARKERS = ("/usr/local", "/opt/homebrew", "HOMEBREW_PREFIX", "$(brew --prefix)")
MAX_PEEK_BYTES = 1_000_000
TEXT_SUFFIXES = {".conf", ".cfg", ".ini", ".plist", ".cnf", ".yml", ".yaml", ".json", ".txt", ""}


def scan_configs(
    packages: Sequence[Package],
    decisions: Sequence[Decision],
    brew_prefix: str,
    ports_prefix: str,
    extra_files: Iterable[ConfigFile] | None = None,
) -> List[ConfigFile]:
    prefix = Path(brew_prefix)
    ports = Path(ports_prefix)
    exceptions = load_exceptions()
    migrate = {d.brew_name for d in decisions if d.status == STATUS_MIGRATE}
    findings: List[ConfigFile] = []
    if extra_files:
        findings.extend(extra_files)

    for pkg in packages:
        if pkg.name not in migrate:
            continue
        stateful = _name_matches(pkg.name, exceptions.get("stateful") or [])
        for path in _candidate_paths(prefix, pkg.name):
            if not path.exists():
                continue
            kind = "state" if stateful else ("conf" if path.is_file() else "data")
            contains = False
            if path.is_file():
                contains = _contains_brew_paths(path, str(prefix))
            guessed = str(ports / path.relative_to(prefix)) if _is_relative_to(path, prefix) else str(ports / "etc" / pkg.name)
            findings.append(
                ConfigFile(
                    brew_package=pkg.name,
                    brew_path=str(path),
                    guessed_ports_path=guessed,
                    kind=kind,
                    copy_safe=False,
                    contains_brew_paths=contains,
                    note="edit by hand, do not cp" if contains else "review before any copy; tool will not copy",
                )
            )
    return findings


def _candidate_paths(prefix: Path, name: str) -> List[Path]:
    return [
        prefix / "etc" / name,
        prefix / "etc" / f"{name}.conf",
        prefix / "etc" / f"{name}.cnf",
        prefix / "var" / name,
        prefix / "var" / "db" / name,
        prefix / "var" / "lib" / name,
        prefix / "opt" / name / "etc",
    ]


def _contains_brew_paths(path: Path, brew_prefix: str) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix != "":
        return False
    try:
        if path.stat().st_size > MAX_PEEK_BYTES:
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    markers = list(BREW_PATH_MARKERS) + [brew_prefix]
    return any(marker in text for marker in markers)


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False
