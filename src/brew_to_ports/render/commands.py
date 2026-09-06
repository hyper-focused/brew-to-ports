"""Copy/paste command blocks from a Plan."""

from __future__ import annotations

from brew_to_ports.models import Plan
from brew_to_ports.path_suggest import snippet


def render_commands(plan: Plan) -> str:
    installs = [op for op in plan.ops if op.action == "port_install"]
    uninstalls = [op for op in plan.ops if op.action == "brew_uninstall"]
    lines = [
        "# brew-to-ports",
        "sudo port selfupdate",
        "",
    ]
    if installs:
        lines.append("# Install MacPorts equivalents (MacPorts will pull its own deps)")
        for op in installs:
            lines.append(f"sudo port install {op.port_name}   # replaces brew {op.brew_name}")
        lines.append("")
        lines.append("# Validate (examples)")
        for op in installs:
            lines.append(f"port -q installed {op.port_name}")
        lines.append("")
    else:
        lines.append("# No MacPorts installs recommended.")
        lines.append("")

    if uninstalls:
        lines.append("# Remove brew formulae only after the matching port validates")
        for op in uninstalls:
            if op.hold_uninstall:
                lines.append(
                    f"# HOLD {op.brew_name}: ack config/state first "
                    f"(./migrate.sh --apply --i-acked-config {op.brew_name})"
                )
            else:
                lines.append(f"brew uninstall {op.brew_name}")
        lines.append("")
    if plan.path_advice:
        for raw in snippet(plan.path_advice).splitlines():
            lines.append(raw)
        lines.append("")
    if plan.configs:
        lines.append("# config/state left on brew prefix (not copied)")
        for cfg in plan.configs:
            extra = " brew-paths" if cfg.contains_brew_paths else ""
            lines.append(f"#   {cfg.brew_package}: {cfg.brew_path} -> {cfg.guessed_ports_path}{extra}")
        lines.append("")
    return "\n".join(lines)
