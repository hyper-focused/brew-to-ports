"""Apply migrate/keep/exception policy. Owns the Decision enum."""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from brew_to_ports.catalog import Catalog
from brew_to_ports.match import load_aliases, match_package
from brew_to_ports.models import (
    DELTA_EQUAL,
    DELTA_OLDER_MAJOR,
    DELTA_OLDER_SAME_MAJOR,
    DELTA_PORT_NEWER,
    DELTA_UNPARSEABLE,
    KIND_CASK,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    Decision,
    Match,
    Package,
)
from brew_to_ports.paths import data_file

AUTO_CONFIDENCE = {
    "exact",
    "alias",
    "versioned",
    "stem",
    "separator",
    "homepage",
    "homepage_family",
}
AQUA_HINTS = {"aqua"}


def load_exceptions(path: Optional[Path] = None) -> dict:
    return json.loads((path or data_file("exceptions.json")).read_text(encoding="utf-8"))


def classify_all(
    packages: Sequence[Package],
    catalog: Catalog,
    allow_older_same_major: bool = False,
    aliases: Optional[Dict[str, str]] = None,
    exceptions: Optional[dict] = None,
) -> List[Decision]:
    aliases = aliases if aliases is not None else load_aliases()
    exceptions = exceptions if exceptions is not None else load_exceptions()
    return [
        classify_one(
            pkg,
            catalog,
            allow_older_same_major=allow_older_same_major,
            aliases=aliases,
            exceptions=exceptions,
        )
        for pkg in packages
    ]


def classify_one(
    pkg: Package,
    catalog: Catalog,
    allow_older_same_major: bool = False,
    aliases: Optional[Dict[str, str]] = None,
    exceptions: Optional[dict] = None,
) -> Decision:
    aliases = aliases if aliases is not None else load_aliases()
    exceptions = exceptions if exceptions is not None else load_exceptions()
    match = match_package(pkg, catalog, aliases=aliases)
    category = _exception_category(pkg.name, exceptions)
    stateful = _name_matches(pkg.name, exceptions.get("stateful") or [])

    if pkg.kind == KIND_CASK:
        return _cask_decision(pkg, match, catalog, category, stateful)

    if pkg.tap and not _core_tap(pkg.tap):
        return Decision(
            brew_name=pkg.name,
            status=STATUS_EXCEPTION,
            match=match,
            reasons=[f"third-party tap {pkg.tap}"],
            category="tap",
            hold_uninstall=False,
            requested=pkg.requested,
            kind=pkg.kind,
        )

    if category in ("toolchain", "runtime", "service"):
        reasons = [f"exception category {category}"]
        if match.port_name:
            reasons.append(f"candidate port {match.port_name} @{match.port_version} not auto-migrated")
        return Decision(
            brew_name=pkg.name,
            status=STATUS_EXCEPTION,
            match=match,
            reasons=reasons,
            category=category,
            hold_uninstall=stateful,
            requested=pkg.requested,
            kind=pkg.kind,
        )

    if match.port_name is None or match.confidence not in AUTO_CONFIDENCE:
        return Decision(
            brew_name=pkg.name,
            status=STATUS_KEEP,
            match=match,
            reasons=["no equivalent above match threshold"],
            category="no_equivalent",
            hold_uninstall=stateful,
            requested=pkg.requested,
            kind=pkg.kind,
        )

    return _version_gate(
        pkg,
        match,
        allow_older_same_major=allow_older_same_major,
        category=category,
        stateful=stateful,
    )


def _cask_decision(pkg, match: Match, catalog: Catalog, category: str, stateful: bool) -> Decision:
    if match.port_name and match.confidence in {"exact", "alias"}:
        port = catalog.get(match.port_name)
        cats = {c.lower() for c in (port.categories if port else [])}
        if "aqua" in cats or match.confidence == "alias":
            gated = _version_gate(
                pkg,
                match,
                allow_older_same_major=False,
                category=category or "cask",
                stateful=stateful,
            )
            if gated.status == STATUS_MIGRATE:
                gated.reasons.insert(0, "cask mapped to MacPorts aqua/app port")
            return gated
    return Decision(
        brew_name=pkg.name,
        status=STATUS_KEEP,
        match=match,
        reasons=["cask: default keep on Homebrew"],
        category="cask",
        hold_uninstall=False,
        requested=True,
        kind=KIND_CASK,
    )


def _version_gate(
    pkg: Package,
    match: Match,
    allow_older_same_major: bool,
    category: str,
    stateful: bool,
) -> Decision:
    delta = match.version_delta
    if delta in (DELTA_EQUAL, DELTA_PORT_NEWER):
        reasons = [f"{match.rule_id}", f"version {delta} brew={match.brew_version} port={match.port_version}"]
        if stateful:
            reasons.append("stateful: brew uninstall held until config is acked")
        return Decision(
            brew_name=pkg.name,
            status=STATUS_MIGRATE,
            match=match,
            reasons=reasons,
            category=category,
            hold_uninstall=stateful,
            requested=pkg.requested,
            kind=pkg.kind,
        )
    if delta == DELTA_OLDER_SAME_MAJOR:
        if allow_older_same_major:
            return Decision(
                brew_name=pkg.name,
                status=STATUS_MIGRATE,
                match=match,
                reasons=[
                    f"older same major allowed by flag brew={match.brew_version} port={match.port_version}"
                ],
                category=category,
                hold_uninstall=stateful,
                requested=pkg.requested,
                kind=pkg.kind,
            )
        return Decision(
            brew_name=pkg.name,
            status=STATUS_KEEP,
            match=match,
            reasons=[
                f"MacPorts older same major brew={match.brew_version} port={match.port_version}; "
                "pass --allow-older-same-major to opt in"
            ],
            category="version",
            hold_uninstall=stateful,
            requested=pkg.requested,
            kind=pkg.kind,
        )
    if delta == DELTA_OLDER_MAJOR:
        return Decision(
            brew_name=pkg.name,
            status=STATUS_EXCEPTION,
            match=match,
            reasons=[
                f"MacPorts older major brew={match.brew_version} port={match.port_version}"
            ],
            category="version",
            hold_uninstall=stateful,
            requested=pkg.requested,
            kind=pkg.kind,
        )
    if delta == DELTA_UNPARSEABLE:
        return Decision(
            brew_name=pkg.name,
            status=STATUS_EXCEPTION,
            match=match,
            reasons=[
                f"unparseable versions brew={match.brew_version} port={match.port_version}"
            ],
            category="version",
            hold_uninstall=stateful,
            requested=pkg.requested,
            kind=pkg.kind,
        )
    return Decision(
        brew_name=pkg.name,
        status=STATUS_KEEP,
        match=match,
        reasons=["version delta not eligible"],
        category=category or "version",
        hold_uninstall=stateful,
        requested=pkg.requested,
        kind=pkg.kind,
    )


def _core_tap(tap: str) -> bool:
    t = tap.lower()
    return t in ("homebrew/core", "homebrew/cask", "homebrew/cask-versions", "")


def _exception_category(name: str, exceptions: dict) -> str:
    cats = exceptions.get("categories") or {}
    for category, patterns in cats.items():
        if _name_matches(name, patterns):
            return category
    return ""


def _name_matches(name: str, patterns: List[str]) -> bool:
    lower = name.lower()
    for pat in patterns:
        if fnmatch(lower, pat.lower()):
            return True
    return False
