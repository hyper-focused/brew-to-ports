"""Generate migrate.sh. Defaults to dry-run. Does not execute it."""

from __future__ import annotations

from brew_to_ports.models import Plan

HEADER = r'''#!/bin/zsh
# brew-to-ports migrate.sh — dry-run unless --apply. Does not copy configs.
# Interpreter is /bin/zsh so brew zsh can be uninstalled mid-run.
set -euo pipefail

if [[ -z "${BREW_TO_PORTS_SYS_ZSH:-}" ]]; then
  export BREW_TO_PORTS_SYS_ZSH=1
  exec /bin/zsh "$0" "$@"
fi

APPLY=0
typeset -a ACKED
ACKED=()

usage() {
  echo "usage: $0 [--apply] [--i-acked-config <formula>]..." >&2
  echo "  default is dry-run (prints commands)." >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --i-acked-config)
      [[ $# -ge 2 ]] || usage
      ACKED+=("$2")
      shift
      ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
  shift
done

arch="$(/usr/bin/uname -m)"
if [[ "$arch" != "x86_64" ]]; then
  echo "brew-to-ports: Intel x86_64 macOS only (got $arch)." >&2
  exit 1
fi

acked() {
  local name="$1"
  local x
  for x in "${ACKED[@]+${ACKED[@]}}"; do
    [[ "$x" == "$name" ]] && return 0
  done
  return 1
}

run() {
  if [[ "$APPLY" -eq 0 ]]; then
    printf 'DRY-RUN: '
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

if [[ "$APPLY" -eq 0 ]]; then
  echo "DRY-RUN (pass --apply to execute). No packages will be installed or uninstalled."
fi
'''


def render_script(plan: Plan) -> str:
    brew = f"{plan.brew_prefix.rstrip('/')}/bin/brew"
    port = f"{plan.ports_prefix.rstrip('/')}/bin/port"
    sudo = "/usr/bin/sudo"
    lines = [HEADER.rstrip(), ""]
    lines.append(f"BREW={_sh_single(brew)}")
    lines.append(f"PORT={_sh_single(port)}")
    lines.append(f"SUDO={_sh_single(sudo)}")
    lines.append("")
    installs = [op for op in plan.ops if op.action == "port_install"]
    uninstalls = [op for op in plan.ops if op.action == "brew_uninstall"]

    if plan.configs:
        lines.append("# config/state on brew prefix (not copied)")
        for cfg in plan.configs:
            extra = " brew-paths" if cfg.contains_brew_paths else ""
            lines.append(f"#   {cfg.brew_package}: {cfg.brew_path} -> {cfg.guessed_ports_path}{extra}")
        lines.append("")

    lines.append('run "$SUDO" "$PORT" selfupdate')
    lines.append("")

    for op in installs:
        lines.append(f"echo '--> port install {op.port_name} (from brew {op.brew_name})'")
        lines.append(f'run "$SUDO" "$PORT" install {op.port_name}')
        lines.append(f'run "$PORT" -q installed {op.port_name}')
        lines.append("")

    for op in uninstalls:
        if op.hold_uninstall:
            lines.append(f"echo '--> brew uninstall {op.brew_name} (held until --i-acked-config {op.brew_name})'")
            lines.append(f'if acked "{op.brew_name}"; then')
            lines.append(f'  run "$BREW" uninstall {op.brew_name}')
            lines.append("else")
            lines.append(
                f'  echo "HOLD: {op.brew_name} has config/state; pass --i-acked-config {op.brew_name} to uninstall brew copy"'
            )
            lines.append("fi")
        else:
            lines.append(f"echo '--> brew uninstall {op.brew_name}'")
            lines.append(f'run "$BREW" uninstall {op.brew_name}')
        lines.append("")

    lines.append('echo "done."')
    lines.append("")
    return "\n".join(lines)


def _sh_single(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
