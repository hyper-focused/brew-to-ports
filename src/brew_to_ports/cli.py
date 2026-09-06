"""Parse args, pick mode, print errors. No matching logic."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from brew_to_ports.adapters.brew import BrewError, brew_prefix, load_installed_json, python_is_from_brew
from brew_to_ports.adapters.macports import load_catalog, ports_prefix
from brew_to_ports.adapters.shell_env import current_path, read_rc_files
from brew_to_ports.catalog import Catalog, from_portindex_text
from brew_to_ports.classify import classify_all
from brew_to_ports.config_scan import scan_configs
from brew_to_ports.cutover import CutoverAbort, decide_cutover
from brew_to_ports.family import python_families
from brew_to_ports.inventory import from_brew_json
from brew_to_ports.path_suggest import default_path_file, suggest_path
from brew_to_ports.plan import build_plan
from brew_to_ports.render.commands import render_commands
from brew_to_ports.render.report import render_report
from brew_to_ports.render.script import render_script


# Ventura: Apple CLT /usr/bin/python3 is 3.9.6; MacPorts current tree targets 13+.
# Intel Tahoe is productVersion 26 — floor only; 27+ is Apple Silicon and fails require_intel.
MIN_MACOS = (13, 0)
MIN_PYTHON = (3, 9)

INTEL_ONLY = "brew-to-ports: Intel x86_64 macOS only (got {arch}). Homebrew is still Tier 1 on Apple Silicon."
TOO_OLD_MACOS = (
    "brew-to-ports: macOS 13 Ventura or later required (got {version}). "
    "Apple CLT /usr/bin/python3 is 3.9 from Ventura on, and the current MacPorts tree targets Ventura+."
)
TOO_OLD_PYTHON = (
    "brew-to-ports: Python 3.9+ required (got {version}). "
    "Install Xcode Command Line Tools so /usr/bin/python3 is 3.9.6+."
)


def require_intel(arch: Optional[str] = None) -> str:
    machine = arch if arch is not None else os.uname().machine
    if machine != "x86_64":
        raise SystemExit(INTEL_ONLY.format(arch=machine))
    return machine


def macos_version() -> str:
    try:
        return subprocess.check_output(["/usr/bin/sw_vers", "-productVersion"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def require_not_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise SystemExit("brew-to-ports: run as your login user, not sudo. Homebrew must not run as root.")


def parse_macos_version(raw: str) -> Optional[Tuple[int, ...]]:
    """Parse sw_vers -productVersion. Non-numeric (including 'unknown') → None."""
    chunks: List[int] = []
    for part in raw.strip().split("."):
        if not part.isdigit():
            return None if not chunks else tuple(chunks)
        chunks.append(int(part))
    return tuple(chunks) if chunks else None


def macos_meets_min(raw: str, minimum: Tuple[int, ...] = MIN_MACOS) -> bool:
    parsed = parse_macos_version(raw)
    if parsed is None:
        return False
    n = max(len(parsed), len(minimum))
    left = parsed + (0,) * (n - len(parsed))
    right = minimum + (0,) * (n - len(minimum))
    return left >= right


def require_macos(version: Optional[str] = None) -> str:
    raw = version if version is not None else macos_version()
    if not macos_meets_min(raw):
        raise SystemExit(TOO_OLD_MACOS.format(version=raw))
    return raw


def require_python(version_info: Optional[Sequence[int]] = None) -> Tuple[int, ...]:
    info = tuple(version_info) if version_info is not None else sys.version_info[:3]
    if info < MIN_PYTHON:
        shown = ".".join(str(p) for p in info[:3]) if version_info is not None else sys.version.split()[0]
        raise SystemExit(TOO_OLD_PYTHON.format(version=shown))
    return info[:3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brew-to-ports",
        description="Inventory Homebrew on Intel Macs and plan a conservative MacPorts migration.",
    )
    parser.add_argument("--dump", action="store_true", help="write inventory JSON to stdout")
    parser.add_argument(
        "--script",
        nargs="?",
        const="migrate.sh",
        metavar="FILE",
        help="write migrate.sh (default path migrate.sh). Script still defaults to dry-run.",
    )
    parser.add_argument("--report", metavar="FILE", help="also write the human report to FILE")
    parser.add_argument("--brew-json", metavar="FILE", help="read brew info --json=v2 from FILE instead of live brew")
    parser.add_argument("--portindex", metavar="FILE", help="read MacPorts PortIndex from FILE")
    parser.add_argument(
        "--allow-older-same-major",
        action="store_true",
        help="opt in to MacPorts ports that are older but same major as the brew formula",
    )
    parser.add_argument(
        "--allow-brew-python",
        action="store_true",
        help="allow running under Homebrew's Python (not recommended)",
    )
    parser.add_argument("--commands", action="store_true", help="print copy/paste commands after the report")
    parser.add_argument(
        "--path-file",
        nargs="?",
        const=str(default_path_file()),
        metavar="FILE",
        help="write generated PATH file (default ~/.zsh_path.brew-to-ports). Also written with --script.",
    )
    parser.add_argument(
        "--migrate-runtime",
        action="append",
        default=[],
        metavar="FORMULA",
        help="non-TTY: cut over this python runtime (repeatable). TTY prompts instead.",
    )
    parser.add_argument(
        "--i-acked-drop",
        action="append",
        default=[],
        metavar="FORMULA",
        help="non-TTY: ack dropping unmatched children of this runtime (repeatable).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    require_not_root()
    require_intel()
    host_macos = require_macos()
    _check_runtime_python(allow_brew=args.allow_brew_python)

    try:
        payload = load_installed_json(Path(args.brew_json) if args.brew_json else None)
    except BrewError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.dump:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    portindex = Path(args.portindex) if args.portindex else None
    if portindex is not None:
        catalog = from_portindex_text(portindex.read_text(encoding="utf-8", errors="replace"), source=str(portindex))
    else:
        catalog = load_catalog()

    dest = Path(args.path_file).expanduser() if args.path_file else default_path_file()
    try:
        plan = run_scan(
            payload,
            catalog,
            allow_older_same_major=args.allow_older_same_major,
            arch=os.uname().machine,
            macos=host_macos,
            brew_pfx=brew_prefix(),
            ports_pfx=ports_prefix(),
            path_file=dest,
            migrate_runtime=args.migrate_runtime,
            acked_drop=args.i_acked_drop,
            interactive_cutover=sys.stdin.isatty() and not args.migrate_runtime,
        )
    except CutoverAbort as exc:
        print(str(exc) or "brew-to-ports: cutover aborted; wrote nothing.", file=sys.stderr)
        return 2
    report = render_report(plan)
    sys.stdout.write(report)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    if args.commands or args.script:
        sys.stdout.write("\n")
        sys.stdout.write(render_commands(plan))
    if args.script:
        script_path = Path(args.script)
        script_path.write_text(render_script(plan), encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | 0o111)
        print(f"\nwrote {script_path} (dry-run by default; pass --apply to mutate)", file=sys.stderr)
    if args.script or args.path_file:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(plan.path_advice.path_file_contents if plan.path_advice else "", encoding="utf-8")
        print(f"wrote {dest} (PATH data file — comment rc writers and load it)", file=sys.stderr)
    return 0


def run_scan(
    payload: dict,
    catalog: Catalog,
    *,
    allow_older_same_major: bool = False,
    arch: str = "x86_64",
    macos: str = "unknown",
    brew_pfx: str = "/usr/local",
    ports_pfx: str = "/opt/local",
    path_env: Optional[str] = None,
    rc_files=None,
    path_file: Optional[Path] = None,
    migrate_runtime: Optional[List[str]] = None,
    acked_drop: Optional[List[str]] = None,
    interactive_cutover: bool = False,
) -> "Plan":
    packages = from_brew_json(payload)
    decisions = classify_all(packages, catalog, allow_older_same_major=allow_older_same_major)
    families = python_families(packages, decisions, allow_older_same_major=allow_older_same_major)
    choices = decide_cutover(
        families,
        migrate_runtime=migrate_runtime,
        acked_drop=acked_drop,
        interactive=interactive_cutover,
    )
    plan = build_plan(
        packages,
        decisions,
        arch=arch,
        macos=macos,
        brew_prefix=brew_pfx,
        ports_prefix=ports_pfx,
        catalog_source=catalog.source,
        allow_older_same_major=allow_older_same_major,
        cutover=choices,
    )
    plan.configs = scan_configs(packages, plan.decisions, brew_pfx, ports_pfx)
    plan.path_advice = suggest_path(
        path_env if path_env is not None else current_path(),
        rc_files if rc_files is not None else read_rc_files(),
        brew_prefix=brew_pfx,
        ports_prefix=ports_pfx,
        path_file=path_file,
    )
    return plan


def _check_runtime_python(allow_brew: bool) -> None:
    require_python()
    exe = sys.executable
    if python_is_from_brew(exe) and not allow_brew:
        raise SystemExit(
            f"brew-to-ports: refusing Homebrew Python as runtime ({exe}). "
            "Use /usr/bin/python3 or pass --allow-brew-python."
        )
