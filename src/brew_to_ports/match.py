"""Name + homepage cascade. Never shells out. Never classifies migrate/keep."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from brew_to_ports.catalog import Catalog, normalize_homepage
from brew_to_ports.models import (
    DELTA_EQUAL,
    DELTA_NA,
    DELTA_OLDER_MAJOR,
    DELTA_OLDER_SAME_MAJOR,
    DELTA_PORT_NEWER,
    DELTA_UNPARSEABLE,
    Match,
    Package,
)
from brew_to_ports.paths import data_file

_VERSION_SPLIT = re.compile(r"[.\-]")


def load_aliases(path: Optional[Path] = None) -> Dict[str, str]:
    raw = json.loads((path or data_file("aliases.json")).read_text(encoding="utf-8"))
    return {str(k).lower(): str(v) for k, v in raw.items()}


def match_package(pkg: Package, catalog: Catalog, aliases: Optional[Dict[str, str]] = None) -> Match:
    aliases = aliases if aliases is not None else load_aliases()
    if not catalog.by_name:
        return Match(
            brew_name=pkg.name,
            port_name=None,
            confidence="none",
            rule_id="no_catalog",
            version_delta=DELTA_NA,
            brew_version=pkg.version,
            reasons=["MacPorts catalog empty or missing"],
        )

    hit = _cascade(pkg, catalog, aliases)
    if hit is None:
        return Match(
            brew_name=pkg.name,
            port_name=None,
            confidence="none",
            rule_id="no_match",
            version_delta=DELTA_NA,
            brew_version=pkg.version,
            reasons=["no port above auto-migrate threshold"],
        )

    port, rule_id, confidence, extra = hit
    if port.replaced_by:
        replacement = catalog.get(port.replaced_by)
        if replacement is not None:
            extra.append(f"replaced_by {port.name} -> {replacement.name}")
            port = replacement
            rule_id = "replaced_by"
    delta = compare_versions(pkg.version, port.version)
    return Match(
        brew_name=pkg.name,
        port_name=port.name,
        confidence=confidence,
        rule_id=rule_id,
        version_delta=delta,
        brew_version=pkg.version,
        port_version=port.version,
        reasons=extra,
    )


def compare_versions(brew_version: str, port_version: str) -> str:
    brew = parse_version(brew_version)
    port = parse_version(port_version)
    if brew is None or port is None:
        return DELTA_UNPARSEABLE
    n = max(len(brew), len(port))
    brew = brew + (0,) * (n - len(brew))
    port = port + (0,) * (n - len(port))
    if port == brew:
        return DELTA_EQUAL
    if port > brew:
        return DELTA_PORT_NEWER
    if port[0] == brew[0]:
        return DELTA_OLDER_SAME_MAJOR
    return DELTA_OLDER_MAJOR


def parse_version(raw: str):
    if not raw:
        return None
    s = raw.strip()
    if s.lower().startswith("v") and len(s) > 1 and s[1].isdigit():
        s = s[1:]
    s = s.split("_", 1)[0]
    s = s.split("+", 1)[0]
    parts = []
    for token in _VERSION_SPLIT.split(s):
        if not token:
            continue
        if token.isdigit():
            parts.append(int(token))
            continue
        m = re.match(r"(\d+)", token)
        if m:
            parts.append(int(m.group(1)))
        elif not parts:
            return None
        else:
            break
    return tuple(parts) if parts else None


def versioned_candidates(name: str) -> List[str]:
    if "@" not in name:
        return []
    base, ver = name.split("@", 1)
    if not base or not ver:
        return []
    compact = ver.replace(".", "")
    major = ver.split(".", 1)[0]
    ordered = [
        f"{base}{compact}",
        f"{base}{ver}",
        f"{base}-{ver}",
        f"{base}-{compact}",
        f"{base}{major}",
        f"{base}-{major}",
    ]
    seen = set()
    out = []
    for item in ordered:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _cascade(pkg, catalog: Catalog, aliases: Dict[str, str]):
    name = pkg.name
    exact = catalog.get(name)
    if exact is not None:
        return exact, "exact_name", "exact", []

    alias = aliases.get(name.lower())
    if alias:
        port = catalog.get(alias)
        if port is not None:
            return port, "alias", "alias", [f"alias {name} -> {alias}"]

    for cand in versioned_candidates(name):
        port = catalog.get(cand)
        if port is not None:
            return port, "versioned_transform", "versioned", [f"transform {name} -> {cand}"]

    swapped = name.replace("_", "-") if "_" in name else name.replace("-", "_")
    if swapped != name:
        port = catalog.get(swapped)
        if port is not None:
            return port, "separator", "separator", [f"separator {name} -> {swapped}"]

    if pkg.homepage:
        homes = catalog.by_home(pkg.homepage)
        if len(homes) == 1:
            return homes[0], "homepage", "homepage", [
                f"homepage {normalize_homepage(pkg.homepage)}"
            ]
        if len(homes) > 1:
            return None
    return None
