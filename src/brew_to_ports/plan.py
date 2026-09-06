"""Ordered install/uninstall lists. Owns the keep-set graph and cutover overlay."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Set

from brew_to_ports.models import (
    CUTOVER_MIGRATE,
    CUTOVER_SKIP,
    KIND_CASK,
    KIND_FORMULA,
    STATUS_DROP,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    CutoverChoice,
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
    cutover: Optional[Sequence[CutoverChoice]] = None,
) -> Plan:
    by_name: Dict[str, Package] = {p.name: p for p in packages}
    work: List[Decision] = [replace(d, reasons=list(d.reasons)) for d in decisions]
    notes: List[str] = []
    applied = _apply_cutover(packages, work, list(cutover or []), notes)

    keep_set = _expand_keep_set(packages, work)
    decision_map: Dict[str, Decision] = {d.brew_name: d for d in work}
    for decision in work:
        pkg = by_name.get(decision.brew_name)
        if decision.status == STATUS_MIGRATE and decision.brew_name in keep_set:
            decision.status = STATUS_KEEP
            decision.reasons.append("keep_because_dep_of_keeper")
        elif (
            pkg is not None
            and not pkg.requested
            and pkg.kind == KIND_FORMULA
            and decision.brew_name not in keep_set
            and decision.status != STATUS_EXCEPTION
        ):
            decision.reasons.append("leftover_brew_dep_no_remaining_keeper")

    ops: List[PlanOp] = []
    for decision in work:
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
                kind=pkg.kind,
            )
        )

    uninstallable = _uninstall_order(packages, keep_set, decision_map)
    for name in uninstallable:
        decision = decision_map[name]
        pkg = by_name.get(name)
        comment = ""
        if decision.hold_uninstall:
            comment = "held: ack config/state first"
        elif decision.status == STATUS_DROP:
            comment = "drop: no MacPorts equivalent"
        ops.append(
            PlanOp(
                action="brew_uninstall",
                brew_name=name,
                port_name=(decision.match.port_name if decision.match else ""),
                hold_uninstall=decision.hold_uninstall,
                comment=comment,
                kind=pkg.kind if pkg else KIND_FORMULA,
            )
        )

    if catalog_source in ("", "missing"):
        notes.append("MacPorts catalog missing; no migrate recommendations.")

    return Plan(
        arch=arch,
        macos=macos,
        brew_prefix=brew_prefix,
        ports_prefix=ports_prefix,
        decisions=work,
        keep_set=sorted(keep_set),
        ops=ops,
        catalog_source=catalog_source,
        allow_older_same_major=allow_older_same_major,
        notes=notes,
        cutover=applied,
    )


def _apply_cutover(
    packages: Sequence[Package],
    decisions: List[Decision],
    choices: Sequence[CutoverChoice],
    notes: List[str],
) -> List[CutoverChoice]:
    dmap: Dict[str, Decision] = {d.brew_name: d for d in decisions}
    applied: List[CutoverChoice] = []
    for ch in choices:
        if ch.action != CUTOVER_MIGRATE:
            applied.append(ch)
            continue
        affected = [ch.runtime] + list(ch.drop) + list(ch.can)
        snap = {n: (dmap[n].status, list(dmap[n].reasons)) for n in affected if n in dmap}
        rt = dmap.get(ch.runtime)
        if rt is None:
            applied.append(replace(ch, action=CUTOVER_SKIP, note="runtime missing"))
            continue
        rt.status = STATUS_MIGRATE
        rt.reasons = list(rt.reasons) + ["cutover migrate runtime"]
        for name in ch.can:
            d = dmap.get(name)
            if d is not None and d.status != STATUS_MIGRATE:
                d.status = STATUS_MIGRATE
                d.reasons = list(d.reasons) + ["cutover with runtime"]
        for name in ch.drop:
            d = dmap.get(name)
            if d is not None:
                d.status = STATUS_DROP
                d.reasons = list(d.reasons) + ["cutover drop: no MacPorts equivalent"]
        ks = _expand_keep_set(packages, decisions)
        pinned = [n for n in [ch.runtime, *ch.drop] if n in ks]
        if pinned:
            for n, (st, rs) in snap.items():
                dmap[n].status = st
                dmap[n].reasons = rs
            notes.append(
                f"cutover {ch.runtime} skipped: still pinned ({', '.join(pinned)})"
            )
            applied.append(
                replace(
                    ch,
                    action=CUTOVER_SKIP,
                    pins=pinned,
                    note="keep-set preflight",
                )
            )
            continue
        notes.append(f"cutover {ch.runtime}: migrate; drop {', '.join(ch.drop) or '(none)'}")
        applied.append(ch)
    return applied


def _expand_keep_set(packages: Sequence[Package], decisions: Sequence[Decision]) -> Set[str]:
    """Seed from packages that *remain on brew by choice* (requested keep/exception, casks).

    Unrequested formulae are not seeds. DROP is never a seed.
    """
    by_name: Dict[str, Package] = {p.name: p for p in packages}
    deps: Dict[str, List[str]] = {p.name: list(p.runtime_deps) for p in packages}
    keep: Set[str] = set()
    for d in decisions:
        if d.status not in (STATUS_KEEP, STATUS_EXCEPTION):
            continue
        pkg = by_name.get(d.brew_name)
        if pkg is None:
            continue
        if pkg.requested or pkg.kind == KIND_CASK:
            keep.add(d.brew_name)
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
    """Leaves first. DROP, requested migrators, leftover non-exception deps."""
    remaining = {p.name for p in packages if p.name not in keep_set}
    eligible: Set[str] = set()
    for p in packages:
        if p.name not in remaining:
            continue
        d = decision_map.get(p.name)
        if d is None:
            continue
        if d.status == STATUS_DROP:
            eligible.add(p.name)
        elif d.status == STATUS_MIGRATE:
            eligible.add(p.name)
        elif not p.requested and d.status != STATUS_EXCEPTION:
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
