"""Runtime family grouping. Does not write Decision.status."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from brew_to_ports.classify import AUTO_CONFIDENCE
from brew_to_ports.models import (
    DELTA_OLDER_MAJOR,
    DELTA_OLDER_SAME_MAJOR,
    KIND_FORMULA,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    Decision,
    Package,
)

@dataclass
class RuntimeFamily:
    runtime: str
    members: List[str] = field(default_factory=list)
    can: List[str] = field(default_factory=list)
    drop: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)


def is_python_runtime(name: str) -> bool:
    n = name.lower()
    return n == "python" or n.startswith("python@")


def is_cutover_runtime(name: str) -> bool:
    """python, php, node (and @version). Not ruby — left as a brew dep."""
    n = name.lower()
    if n == "ruby" or n.startswith("ruby@"):
        return False
    return (
        n == "python"
        or n.startswith("python@")
        or n == "php"
        or n.startswith("php@")
        or n == "node"
        or n.startswith("node@")
    )


def cutover_families(
    packages: Sequence[Package],
    decisions: Sequence[Decision],
    *,
    allow_older_same_major: bool = False,
) -> List[RuntimeFamily]:
    """Families for python/php/node that have a viable candidate port."""
    by_name: Dict[str, Package] = {p.name: p for p in packages}
    dmap: Dict[str, Decision] = {d.brew_name: d for d in decisions}
    dependents: Dict[str, List[str]] = {}
    for pkg in packages:
        if pkg.kind != KIND_FORMULA:
            continue
        for dep in pkg.runtime_deps:
            dependents.setdefault(dep, []).append(pkg.name)

    out: List[RuntimeFamily] = []
    for pkg in packages:
        if not is_cutover_runtime(pkg.name):
            continue
        d = dmap.get(pkg.name)
        if d is None or d.category != "runtime":
            continue
        if not _runtime_cutover_ok(d, allow_older_same_major=allow_older_same_major):
            continue
        members = sorted({n for n in dependents.get(pkg.name, []) if n in by_name and n != pkg.name})
        fam = RuntimeFamily(runtime=pkg.name, members=members)
        for name in members:
            md = dmap.get(name)
            if md is None:
                fam.blocked.append(name)
                continue
            bucket = _member_bucket(md)
            if bucket == "can":
                fam.can.append(name)
            elif bucket == "drop":
                fam.drop.append(name)
            else:
                fam.blocked.append(name)
        out.append(fam)
    return out


def python_families(
    packages: Sequence[Package],
    decisions: Sequence[Decision],
    *,
    allow_older_same_major: bool = False,
) -> List[RuntimeFamily]:
    return [
        fam
        for fam in cutover_families(
            packages, decisions, allow_older_same_major=allow_older_same_major
        )
        if is_python_runtime(fam.runtime)
    ]


def _runtime_cutover_ok(d: Decision, *, allow_older_same_major: bool) -> bool:
    m = d.match
    if m is None or not m.port_name or m.confidence not in AUTO_CONFIDENCE:
        return False
    if m.version_delta == DELTA_OLDER_MAJOR:
        return False
    if m.version_delta == DELTA_OLDER_SAME_MAJOR and not allow_older_same_major:
        return False
    return True


def _member_bucket(d: Decision) -> str:
    """already-MIGRATE → can; no port → drop; else blocked."""
    if d.status == STATUS_MIGRATE:
        return "can"
    no_port = (
        d.match is None
        or not d.match.port_name
        or d.match.rule_id in ("no_match", "no_catalog")
        or d.category == "no_equivalent"
    )
    if no_port:
        return "drop"
    if d.status in (STATUS_KEEP, STATUS_EXCEPTION) and d.category in ("version", "runtime", "toolchain", "service"):
        return "blocked"
    if d.match and d.match.confidence not in AUTO_CONFIDENCE:
        return "drop"
    return "blocked"
