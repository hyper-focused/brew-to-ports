"""Human-readable report from a Plan."""

from __future__ import annotations

from brew_to_ports.models import (
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    Plan,
)
from brew_to_ports.path_suggest import snippet


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
    lines.append(f"counts: migrate={len(migrate)} keep={len(keep)} exception={len(exc)}")
    lines.append("")
    lines.extend(_section("MIGRATE", migrate))
    lines.extend(_section("KEEP ON BREW", keep))
    lines.extend(_section("EXCEPTIONS", exc))
    if plan.keep_set:
        lines.append("KEEP-SET (brew deps pinned by leftovers)")
        lines.append("---------------------------------------")
        for name in plan.keep_set:
            lines.append(f"  {name}")
        lines.append("")
    if plan.configs:
        lines.append("CONFIG / STATE (will not be copied)")
        lines.append("----------------------------------")
        for cfg in plan.configs:
            lines.append(
                f"  {cfg.brew_package}: {cfg.brew_path} -> {cfg.guessed_ports_path} "
                f"[{cfg.kind}] brew-paths={cfg.contains_brew_paths} — {cfg.note}"
            )
        lines.append("")
    if plan.path_advice:
        lines.append("PATH ADVICE (not applied)")
        lines.append("-------------------------")
        advice = plan.path_advice
        if advice.path_owners:
            lines.append(f"  owner: {', '.join(advice.path_owners)}  idiom={advice.idiom or 'unknown'}")
        for note in advice.notes:
            lines.append(f"  {note}")
        if advice.rc_hits:
            lines.append("  rc files that touch PATH / brew prefixes:")
            for hit in advice.rc_hits:
                lines.append(f"    {hit}")
        lines.append("")
        lines.append(snippet(advice).rstrip())
        lines.append("")
    for note in plan.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines).rstrip() + "\n"


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
