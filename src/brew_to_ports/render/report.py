"""Human-readable report from a Plan. TTY is a summary; the file is the dump."""

from __future__ import annotations

from brew_to_ports.models import (
    STATUS_DROP,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    Decision,
    Plan,
)
from brew_to_ports.path_suggest import snippet
from brew_to_ports.select import format_select_block


def render_summary(plan: Plan, *, log_path: str = "") -> str:
    """What a human should read on the TTY. Details live in the scan log."""
    migrate = [d for d in plan.decisions if d.status == STATUS_MIGRATE]
    keep = [d for d in plan.decisions if d.status == STATUS_KEEP]
    exc = [d for d in plan.decisions if d.status == STATUS_EXCEPTION]
    drop = [d for d in plan.decisions if d.status == STATUS_DROP]
    requested_keep = [d for d in keep if d.requested]
    pinned = len(keep) - len(requested_keep)
    lines = [
        "brew-to-ports scan",
        f"  {plan.arch}  macOS {plan.macos}",
        f"  brew {plan.brew_prefix}  ports {plan.ports_prefix}",
        f"  catalog {plan.catalog_source or '(none)'}",
        "",
        f"  migrate {len(migrate)}   keep {len(keep)}   exception {len(exc)}   drop {len(drop)}",
        "",
    ]
    tries = [op for op in plan.ops if op.action == "try_source"]
    if tries:
        lines.append(f"TRY-SOURCE  {len(tries)} overlay(s)")
        for op in tries:
            lines.append(f"  {op.brew_name} -> {op.port_name}")
        lines.append("")
    if plan.cutover:
        lines.append("CUTOVER")
        for ch in plan.cutover:
            extra = f"  drop {', '.join(ch.drop)}" if ch.drop else ""
            lines.append(f"  {ch.runtime}: {ch.action}{extra}")
        lines.append("")
    lines.extend(_short_section("MIGRATE", migrate))
    lines.extend(_short_section("DROP", drop))
    lines.extend(_short_section("EXCEPTION", exc))
    lines.append(
        f"KEEP ON BREW  {len(keep)} ({len(requested_keep)} requested, {pinned} pinned deps)"
    )
    if requested_keep:
        for d in requested_keep:
            lines.append(f"  {_one_line(d)}")
        if pinned:
            lines.append(f"  + {pinned} brew deps pinned by keep/exception (see log)")
    else:
        lines.append("  (none requested)")
    lines.append("")
    if plan.configs:
        lines.append(f"CUSTOM CONFIG  {len(plan.configs)} file(s), not copied (see log)")
        lines.append("")
    if plan.select_links:
        lines.append("PORT SELECT  (after install; makes unversioned php/python3/pip3)")
        lines.extend(format_select_block(plan.select_links))
        lines.append("")
    if plan.path_advice:
        lines.append("PATH")
        for note in plan.path_advice.notes:
            lines.append(f"  {note}")
        if plan.path_advice.path_file:
            lines.append(f"  file {plan.path_advice.path_file}")
        lines.append("  comment-out / load snippet / alias rewrites: see log")
        lines.append("")
    for note in plan.notes:
        lines.append(f"note: {note}")
    if log_path:
        lines.append(f"log: {log_path}")
    return "\n".join(lines).rstrip() + "\n"


def render_report(plan: Plan) -> str:
    lines = [
        "brew-to-ports scan",
        "==================",
        f"arch:          {plan.arch}",
        f"macos:         {plan.macos}",
        f"brew prefix:   {plan.brew_prefix}",
        f"ports prefix:  {plan.ports_prefix}",
        f"catalog:       {plan.catalog_source or '(none)'}",
        "",
    ]
    migrate = [d for d in plan.decisions if d.status == STATUS_MIGRATE]
    keep = [d for d in plan.decisions if d.status == STATUS_KEEP]
    exc = [d for d in plan.decisions if d.status == STATUS_EXCEPTION]
    drop = [d for d in plan.decisions if d.status == STATUS_DROP]
    lines.append(
        f"counts: migrate={len(migrate)} keep={len(keep)} exception={len(exc)} drop={len(drop)}"
    )
    lines.append("")
    tries = [op for op in plan.ops if op.action == "try_source"]
    if tries:
        lines.append("TRY-SOURCE (overlay Portfile; port -D install; brew stays if it fails)")
        lines.append("---------------------------------------------------------------------")
        if plan.try_source_root:
            lines.append(f"  overlay: {plan.try_source_root}")
        for op in tries:
            lines.append(f"  {op.brew_name} -> {op.port_name}  {op.overlay_dir}")
        lines.append("")
    if plan.cutover:
        lines.append("CUTOVER")
        lines.append("-------")
        for ch in plan.cutover:
            extra = f" drop={','.join(ch.drop)}" if ch.drop else ""
            pin = f" pins={','.join(ch.pins)}" if ch.pins else ""
            note = f" {ch.note}" if ch.note else ""
            lines.append(f"  {ch.runtime}: {ch.action}{extra}{pin}{note}")
        lines.append("")
    lines.extend(_section("MIGRATE", migrate))
    lines.extend(_section("DROP (uninstalled, not replaced)", drop))
    lines.extend(_section("KEEP ON BREW", keep))
    lines.extend(_section("EXCEPTIONS", exc))
    if plan.keep_set:
        lines.append("KEEP-SET (brew runtime graph of requested keep/exception + casks)")
        lines.append("---------------------------------------------------------------")
        for name in plan.keep_set:
            lines.append(f"  {name}")
        lines.append("")
    if plan.configs:
        lines.append("CUSTOM CONFIG (not copied — adjust the MacPorts file)")
        lines.append("----------------------------------------------------")
        for cfg in plan.configs:
            lines.append(f"  {cfg.brew_package}: {cfg.brew_path}")
            lines.append(f"      ports: {cfg.guessed_ports_path}")
            if cfg.note:
                lines.append(f"      {cfg.note}")
        lines.append("")
    if plan.select_links:
        lines.append("PORT SELECT (unversioned php / python3 / pip3 after install)")
        lines.append("-----------------------------------------------------------")
        lines.extend(format_select_block(plan.select_links))
        lines.append("")
    if plan.path_advice:
        lines.append("PATH")
        lines.append("----")
        advice = plan.path_advice
        for note in advice.notes:
            lines.append(f"  {note}")
        lines.append("")
        lines.append(snippet(advice).rstrip())
        lines.append("")
    for note in plan.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines).rstrip() + "\n"


def _one_line(d: Decision) -> str:
    port = ""
    if d.match and d.match.port_name:
        port = f" -> {d.match.port_name} ({d.match.version_delta})"
    hold = " [HOLD]" if d.hold_uninstall else ""
    return f"{d.brew_name}{port}{hold}"


def _short_section(title: str, decisions: list) -> list:
    lines = [title]
    if not decisions:
        lines.append("  (none)")
        lines.append("")
        return lines
    for d in decisions:
        lines.append(f"  {_one_line(d)}")
    lines.append("")
    return lines


def _section(title: str, decisions) -> list:
    lines = [title, "-" * len(title)]
    if not decisions:
        lines.append("  (none)")
        lines.append("")
        return lines
    for d in decisions:
        port = ""
        if d.match and d.match.port_name:
            port = f" -> {d.match.port_name} @{d.match.port_version} ({d.match.version_delta})"
        hold = " [HOLD UNINSTALL]" if d.hold_uninstall else ""
        req = " requested" if d.requested else " dep"
        lines.append(f"  {d.brew_name}{port}{hold} ({d.kind}{req} {d.category or d.status})")
        for reason in d.reasons:
            lines.append(f"      {reason}")
    lines.append("")
    return lines
