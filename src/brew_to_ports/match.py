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
_PY_DEP_RE = re.compile(r"^python@(\d+)\.(\d+)")
_PY_PORT_RE = re.compile(r"^py(\d{3})-")
_NOISE_STEMS = {
    "full",
    "devel",
    "complete",
    "stable",
    "head",
    "git",
    "py",
    "python",
    "node",
    "js",
}


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
    if base == "node":
        ordered = [
            f"nodejs{compact}",
            f"nodejs{major}",
            f"nodejs-{compact}",
            f"nodejs-{major}",
        ] + ordered
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

    for cand in stem_candidates(pkg):
        port = catalog.get(cand)
        if port is not None:
            return port, "stem_transform", "stem", [f"stem {name} -> {cand}"]

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
            picked = pick_homepage_family(pkg, homes)
            if picked is not None:
                port, why = picked
                return port, "homepage_family", "homepage_family", [
                    f"homepage family {normalize_homepage(pkg.homepage)} -> {port.name} ({why})"
                ]
    return None


def python_series(pkg: Package) -> List[str]:
    """Compact Python versions from brew runtime deps: python@3.14 -> 314."""
    series: List[str] = []
    seen = set()
    for dep in pkg.runtime_deps:
        m = _PY_DEP_RE.match(dep)
        if not m:
            continue
        compact = m.group(1) + m.group(2)
        if compact not in seen:
            seen.add(compact)
            series.append(compact)
    return series


def stem_candidates(pkg: Package) -> List[str]:
    """Systematic brew→ports stem changes. Never substring search."""
    name = pkg.name
    out: List[str] = []

    if name == "node" or name.startswith("node@"):
        ver = name.split("@", 1)[1] if "@" in name else (pkg.version or "")
        compact = ver.replace(".", "")
        major = ver.split(".", 1)[0] if ver else ""
        if compact:
            out.extend([f"nodejs{compact}", f"nodejs-{compact}"])
        if major:
            out.extend([f"nodejs{major}", f"nodejs-{major}"])
        out.append("nodejs")

    if name.startswith("python-"):
        rest = name[len("python-") :].split("@", 1)[0]
        if rest in {"tk", "tkinter"}:
            rest = "tkinter"
        if rest:
            series_list = python_series(pkg) or ("314", "313", "312", "311", "310")
            for series in series_list:
                out.append(f"py{series}-{rest}")
            out.append(f"py-{rest}")

    elif python_series(pkg) and "@" not in name and not name.startswith("python"):
        # pygments, pytest — python-using formulae without a python- prefix
        for series in python_series(pkg):
            out.append(f"py{series}-{name}")
        out.append(f"py-{name}")

    for suffix in ("-full", "-complete"):
        if name.endswith(suffix):
            base = name[: -len(suffix)]
            out.append(f"{base}-devel")
            out.append(base)
            parsed = parse_version(pkg.version)
            if parsed:
                out.append(f"{base}{parsed[0]}")
                out.append(f"{base}-{parsed[0]}")

    return _unique(out)


def name_stems(name: str) -> set:
    n = name.lower()
    n = re.sub(r"^python-", "", n)
    n = re.sub(r"^py\d*-", "", n)
    n = re.sub(r"^nodejs", "node", n)
    stems = set()
    for bit in re.split(r"[-_@.]", n):
        if not bit or bit.isdigit() or bit in _NOISE_STEMS:
            continue
        stems.add(bit)
        stripped = re.sub(r"\d+$", "", bit)
        if stripped and len(stripped) >= 2 and stripped not in _NOISE_STEMS:
            stems.add(stripped)
    return stems


def pick_homepage_family(pkg: Package, homes: List) -> Optional[tuple]:
    """Several ports share a homepage. Pick by related name + version, not substring."""
    brew_stems = name_stems(pkg.name)
    related = [p for p in homes if name_stems(p.name) & brew_stems]
    if not related:
        return None
    series = python_series(pkg)
    scored = []
    rank = {
        DELTA_EQUAL: 0,
        DELTA_PORT_NEWER: 1,
        DELTA_OLDER_SAME_MAJOR: 2,
        DELTA_OLDER_MAJOR: 3,
        DELTA_UNPARSEABLE: 4,
    }
    for port in related:
        delta = compare_versions(pkg.version, port.version)
        r = rank.get(delta, 9)
        bonus = 0
        lname = port.name.lower()
        m = _PY_PORT_RE.match(lname)
        if series:
            if m and m.group(1) in series:
                bonus -= 10 + (len(series) - series.index(m.group(1)))
            elif lname.startswith("py-") and not m:
                bonus -= 1
            elif m:
                bonus += 8
        elif m:
            bonus -= int(m.group(1)) / 1000.0  # prefer newer pyNNN if we don't know
        if pkg.name.endswith("-full") and lname.endswith("-devel"):
            bonus -= 5
        scored.append((r, bonus, len(lname), port, delta))
    scored.sort(key=lambda row: (row[0], row[1], row[2]))
    best = scored[0]
    return best[3], f"delta={best[4]}"


def _unique(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
