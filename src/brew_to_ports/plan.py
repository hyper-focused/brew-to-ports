"""Ordered install/uninstall lists. Owns the keep-set graph."""

from __future__ import annotations

from typing import Dict, List, Sequence, Set

from brew_to_ports.models import (
    KIND_FORMULA,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    Decision,
    Package,
    Plan,
    PlanOp,
)


def build_plan(
    packages: Sequence[Package],
    decisions: Sequence[Decision],
    *,
    arch: str,
    macos: str,
    brew_prefix: str,
    ports_prefix: str,
    catalog_source: str = "",
    allow_older_same_major: bool = False,
) -> Plan:
    by_name: Dict[str, Package] = {p.name: p for p in packages}
    decision_map: Dict[str, Decision] = {d.brew_name: d for d in decisions}

    keep_set = _expand_keep_set(packages, decisions)
    for decision in decisions:
        if decision.status == STATUS_MIGRATE and decision.brew_name in keep_set:
            decision.status = STATUS_KEEP
            decision.reasons.append("keep_because_dep_of_keeper")

    ops: List[PlanOp] = []
    for decision in decisions:
        pkg = by_name.get(decision.brew_name)
        if pkg is None:
            continue
        if decision.status != STATUS_MIGRATE:
            continue
        if not pkg.requested and pkg.kind != KIND_CASK:
            continue
        port = decision.match.port_name if decision.match else None
        if not port:
            continue
        ops.append(
            PlanOp(
                action="port_install",
                brew_name=pkg.name,
                port_name=port,
                hold_uninstall=decision.hold_uninstall,
            )
        )

    uninstallable = _uninstall_order(packages, keep_set, decision_map)
    for name in uninstallable:
        decision = decision_map[name]
        ops.append(
            PlanOp(
                action="brew_uninstall",
                brew_name=name,
                port_name=(decision.match.port_name if decision.match else ""),
                hold_uninstall=decision.hold_uninstall,
                comment="held: ack config/state first" if decision.hold_uninstall else "",
            )
        )

    notes = []
    if catalog_source in ("", "missing"):
        notes.append("MacPorts catalog missing; no migrate recommendations.")

    return Plan(
        arch=arch,
        macos=macos,
        brew_prefix=brew_prefix,
        ports_prefix=ports_prefix,
        decisions=list(decisions),
        keep_set=sorted(keep_set),
        ops=ops,
        catalog_source=catalog_source,
        allow_older_same_major=allow_older_same_major,
        notes=notes,
    )


def _expand_keep_set(packages: Sequence[Package], decisions: Sequence[Decision]) -> Set[str]:
    deps: Dict[str, List[str]] = {p.name: list(p.runtime_deps) for p in packages}
    keep: Set[str] = {
        d.brew_name
        for d in decisions
        if d.status in (STATUS_KEEP, STATUS_EXCEPTION)
    }
    changed = True
    while changed:
        changed = False
        for name in list(keep):
            for dep in deps.get(name, []):
                if dep not in keep:
                    keep.add(dep)
                    changed = True
    return keep


def _uninstall_order(
    packages: Sequence[Package],
    keep_set: Set[str],
    decision_map: Dict[str, Decision],
) -> List[str]:
    """Leaves first: formulae that migrated (or leftover deps of migrators) and are not keepers."""
    remaining = {
        p.name
        for p in packages
        if p.kind == KIND_FORMULA and p.name not in keep_set
    }
    # Only uninstall if classified migrate, or unrequested leftover of a migrator.
    eligible: Set[str] = set()
    for p in packages:
        if p.name not in remaining:
            continue
        d = decision_map.get(p.name)
        if d is None:
            continue
        if d.status == STATUS_MIGRATE:
            eligible.add(p.name)
        elif not p.requested and d.status != STATUS_EXCEPTION:
            # leftover brew dep after its dependents migrated
            eligible.add(p.name)
    dependents: Dict[str, Set[str]] = {n: set() for n in eligible}
    for p in packages:
        if p.name not in eligible:
            continue
        for dep in p.runtime_deps:
            if dep in dependents:
                dependents[dep].add(p.name)

    ordered: List[str] = []
    leftover = set(eligible)
    while leftover:
        leaves = [n for n in leftover if not (dependents[n] & leftover)]
        if not leaves:
            leaves = sorted(leftover)
        for name in sorted(leaves):
            ordered.append(name)
            leftover.remove(name)
    return ordered
