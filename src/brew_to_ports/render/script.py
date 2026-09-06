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

macos="$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"
major="${macos%%.*}"
if ! [[ "$major" == <-> ]] || (( major < 13 )); then
  echo "brew-to-ports: macOS 13 Ventura or later required (got ${macos:-unknown})." >&2
  exit 1
fi

# Homebrew must run as the login user (it owns /usr/local and launchd services).
# MacPorts writes /opt/local and needs root. Never `sudo brew`.
# If this script was started with sudo, drop brew back to $SUDO_USER.
typeset -a BREW_AS PORT_AS
BREW_AS=()
PORT_AS=()
if [[ "$(/usr/bin/id -u)" -eq 0 ]]; then
  if [[ -z "${SUDO_USER:-}" || "$SUDO_USER" == "root" ]]; then
    echo "brew-to-ports: do not run migrate.sh as root. Run as your login user; the script sudo's port only." >&2
    exit 1
  fi
  BREW_OWNER="$SUDO_USER"
  BREW_AS=(/usr/bin/sudo -u "$BREW_OWNER" -H --)
else
  BREW_OWNER="$(/usr/bin/id -un)"
  PORT_AS=(/usr/bin/sudo)
fi

# One sudo password for the whole --apply. A single `sudo port install` stays
# root for the entire compile; the ticket only matters *between* packages.
# Keepalive + pre-command refresh on this TTY (macOS tty_tickets). Never store a password.
# sudo -n after that: ticket dead → fail closed, no prompt storm.
SUDO_KEEP_PID=""
if [[ "$APPLY" -eq 1 && "$(/usr/bin/id -u)" -ne 0 ]]; then
  echo "Enter your sudo password for MacPorts package installations."
  /usr/bin/sudo -v || {
    echo "brew-to-ports: sudo is required for port install (once). Aborting." >&2
    exit 1
  }
  (
    if [[ -e /dev/tty ]]; then
      exec </dev/tty
    fi
    while /usr/bin/sudo -n -v >/dev/null 2>&1; do
      sleep 30
    done
  ) &
  SUDO_KEEP_PID=$!
  trap '[[ -n "${SUDO_KEEP_PID:-}" ]] && kill "$SUDO_KEEP_PID" 2>/dev/null || true' EXIT INT TERM
  PORT_AS=(/usr/bin/sudo -n)
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
    lines.append(HELPERS.rstrip())
    lines.append("")
    path_file = ""
    if plan.path_advice and plan.path_advice.path_file:
        path_file = plan.path_advice.path_file
    lines.append(
        "# PATH still prefers brew until you load "
        + (path_file or "~/.zsh_path.brew-to-ports")
        + " (see scan report). This script does not edit rc files."
    )
    lines.append("")
    installs = [op for op in plan.ops if op.action == "port_install"]
    uninstalls = [op for op in plan.ops if op.action == "brew_uninstall"]

    if plan.configs:
        lines.append("# config/state on brew prefix (not copied)")
        for cfg in plan.configs:
            extra = " brew-paths" if cfg.contains_brew_paths else ""
            lines.append(f"#   {cfg.brew_package}: {cfg.brew_path} -> {cfg.guessed_ports_path}{extra}")
        lines.append("")

    lines.append("port_sudo selfupdate")
    lines.append("")

    for op in installs:
        lines.append(f"echo '--> port install {op.port_name} (from brew {op.brew_name})'")
        lines.append(f'install_port {op.port_name}')
        lines.append("")

    for op in uninstalls:
        kind = op.kind or "formula"
        if op.hold_uninstall:
            lines.append(f"echo '--> brew uninstall {op.brew_name} (held until --i-acked-config {op.brew_name})'")
            lines.append(f'if acked "{op.brew_name}"; then')
            lines.append(f'  uninstall_brew {op.brew_name} {kind}')
            lines.append("else")
            lines.append(
                f'  echo "HOLD: {op.brew_name} has config/state; pass --i-acked-config {op.brew_name} to uninstall brew copy"'
            )
            lines.append("fi")
        else:
            lines.append(f"echo '--> brew uninstall {op.brew_name}'")
            lines.append(f"uninstall_brew {op.brew_name} {kind}")
        lines.append("")

    lines.append('echo "--> brew autoremove (unrequested leaves brew still sees)"')
    lines.append("autoremove_brew")
    lines.append("")
    lines.append('echo "done."')
    lines.append("")
    return "\n".join(lines)


def _sh_single(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


HELPERS = r'''
sudo_refresh() {
  if [[ "$(/usr/bin/id -u)" -eq 0 ]]; then
    return 0
  fi
  if [[ -e /dev/tty ]]; then
    /usr/bin/sudo -n -v </dev/tty >/dev/null 2>&1
  else
    /usr/bin/sudo -n -v >/dev/null 2>&1
  fi
}

port_sudo() {
  if [[ "$APPLY" -eq 1 && "$(/usr/bin/id -u)" -ne 0 ]]; then
    if ! sudo_refresh; then
      echo "brew-to-ports: sudo ticket expired. Re-run --apply (restart-safe)." >&2
      exit 1
    fi
  fi
  run "${PORT_AS[@]}" "$PORT" "$@"
}

port_has() {
  "$PORT" -q installed "$1" >/dev/null 2>&1
}

brew_has_formula() {
  "${BREW_AS[@]}" "$BREW" list --formula "$1" >/dev/null 2>&1
}

brew_has_cask() {
  "${BREW_AS[@]}" "$BREW" list --cask "$1" >/dev/null 2>&1
}

stop_brew_service() {
  local name="$1"
  local st
  st="$("${BREW_AS[@]}" "$BREW" services list 2>/dev/null | awk -v n="$name" '$1==n {print $2; exit}')" || return 0
  [[ "$st" == "started" || "$st" == "error" ]] || return 0
  run "${BREW_AS[@]}" "$BREW" services stop "$name" || true
}

install_port() {
  local name="$1"
  if [[ "$APPLY" -eq 1 ]] && port_has "$name"; then
    echo "skip: port $name already installed"
    return 0
  fi
  port_sudo install "$name"
  if [[ "$APPLY" -eq 1 ]]; then
    port_has "$name"
  else
    run "$PORT" -q installed "$name"
  fi
}

uninstall_brew() {
  local name="$1"
  local kind="${2:-formula}"
  if [[ "$kind" == "cask" ]]; then
    if [[ "$APPLY" -eq 1 ]] && ! brew_has_cask "$name"; then
      echo "skip: brew cask $name not installed"
      return 0
    fi
    run "${BREW_AS[@]}" "$BREW" uninstall --cask "$name"
    return 0
  fi
  if [[ "$APPLY" -eq 1 ]] && ! brew_has_formula "$name"; then
    echo "skip: brew $name not installed"
    return 0
  fi
  stop_brew_service "$name"
  run "${BREW_AS[@]}" "$BREW" uninstall "$name"
}

autoremove_brew() {
  if [[ "$APPLY" -eq 1 ]]; then
    run "${BREW_AS[@]}" "$BREW" autoremove || true
  else
    run "${BREW_AS[@]}" "$BREW" autoremove
  fi
}
'''
