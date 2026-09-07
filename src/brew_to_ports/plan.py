"""Ordered install/uninstall lists. Owns the keep-set graph and cutover overlay."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from brew_to_ports.models import (
    CUTOVER_MIGRATE,
    CUTOVER_SKIP,
    DELTA_EQUAL,
    KIND_CASK,
    KIND_FORMULA,
    STATUS_DROP,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    CutoverChoice,
    Decision,
    Match,
    Package,
    Plan,
    PlanOp,
)
from brew_to_ports.source_try import recipe_for, write_overlay


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
    try_source_root: Optional[Path] = None,
) -> Plan:
    by_name: Dict[str, Package] = {p.name: p for p in packages}
    work: List[Decision] = [replace(d, reasons=list(d.reasons)) for d in decisions]
    notes: List[str] = []
    applied = _apply_cutover(packages, work, list(cutover or []), notes)
    overlay_map = _apply_try_source(packages, work, try_source_root, notes)

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
        if decision.match and decision.match.rule_id == "try_source":
            ops.append(
                PlanOp(
                    action="try_source",
                    brew_name=pkg.name,
                    port_name=port,
                    hold_uninstall=decision.hold_uninstall,
                    kind=pkg.kind,
                    overlay_dir=str(overlay_map.get(pkg.name, "")),
                    comment="try_source",
                )
            )
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

    ops, node_kept, node_skipped = _collapse_nodejs_installs(ops)
    if node_skipped:
        notes.append(
            "MacPorts nodejs majors conflict (one active); installing "
            f"{node_kept} only (skipped {', '.join(node_skipped)})"
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
        elif decision.match and decision.match.rule_id == "try_source":
            comment = "try_source"
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
        try_source_root=str(try_source_root) if try_source_root else "",
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


def _apply_try_source(
    packages: Sequence[Package],
    decisions: List[Decision],
    root: Optional[Path],
    notes: List[str],
) -> Dict[str, Path]:
    written: Dict[str, Path] = {}
    if root is None:
        return written
    dmap: Dict[str, Decision] = {d.brew_name: d for d in decisions}
    for pkg in packages:
        if not pkg.requested or pkg.kind != KIND_FORMULA:
            continue
        if pkg.bottle:
            continue
        d = dmap.get(pkg.name)
        if d is None or d.status != STATUS_KEEP:
            continue
        if d.match and d.match.port_name:
            continue
        rec = recipe_for(pkg)
        if rec is None:
            continue
        portdir = write_overlay(pkg, root)
        if portdir is None:
            continue
        d.status = STATUS_MIGRATE
        d.category = "try_source"
        d.reasons = list(d.reasons) + [f"try_source {rec.shape}"]
        d.match = Match(
            brew_name=pkg.name,
            port_name=rec.port_name,
            confidence="try_source",
            rule_id="try_source",
            version_delta=DELTA_EQUAL,
            brew_version=pkg.version,
            port_version=pkg.version,
            reasons=[f"overlay {rec.shape}"],
        )
        written[pkg.name] = portdir
        notes.append(f"try-source {pkg.name} ({rec.shape}) -> {portdir}")
    return written


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


def _nodejs_major(port_name: str) -> Optional[int]:
    if not port_name.startswith("nodejs"):
        return None
    rest = port_name[6:]
    if rest.isdigit():
        return int(rest)
    return None


def _collapse_nodejs_installs(
    ops: List[PlanOp],
) -> Tuple[List[PlanOp], str, List[str]]:
    """MacPorts nodejs majors conflict; keep one port_install — the newest."""
    majors: List[Tuple[int, str]] = []
    seen: Set[str] = set()
    for op in ops:
        if op.action != "port_install":
            continue
        n = _nodejs_major(op.port_name)
        if n is None or op.port_name in seen:
            continue
        seen.add(op.port_name)
        majors.append((n, op.port_name))
    if len(majors) < 2:
        return ops, "", []
    majors.sort()
    kept = majors[-1][1]
    skipped = [name for _, name in majors[:-1]]
    skipset = set(skipped)
    out = [
        op
        for op in ops
        if not (op.action == "port_install" and op.port_name in skipset)
    ]
    return out, kept, skipped
