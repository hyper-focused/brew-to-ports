"""Generate migrate.zsh. Defaults to dry-run. Does not execute it."""

from __future__ import annotations

from brew_to_ports.models import Plan
from brew_to_ports.select import format_select_block

HEADER = r'''#!/bin/zsh
# brew-to-ports migrate.zsh — dry-run unless --apply. Does not copy configs.
# Interpreter is /bin/zsh so brew zsh can be uninstalled mid-run.
set -euo pipefail

if [[ -z "${BREW_TO_PORTS_SYS_ZSH:-}" ]]; then
  export BREW_TO_PORTS_SYS_ZSH=1
  exec /bin/zsh "$0" "$@"
fi

# Apple system PATH only. gnubin / keg / ports bins cannot shadow ls/head/sed.
# brew and port are invoked by absolute path.
unsetopt aliases
unalias -m '*' 2>/dev/null || true
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
hash -r

HERE="${0:A:h}"
APPLY=0
APPLY_LOG=""
DUMPED_LOG=0
typeset -a ACKED
ACKED=()

usage() {
  echo "usage: $0 [--apply] [--config-ack <formula>]..." >&2
  echo "  default is dry-run (prints commands)." >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --config-ack)
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

# Never `sudo brew`. Port writes /opt/local (root). If this script was
# started with sudo, drop brew back to $SUDO_USER.
typeset -a BREW_AS PORT_AS
BREW_AS=()
PORT_AS=()
if [[ "$(/usr/bin/id -u)" -eq 0 ]]; then
  if [[ -z "${SUDO_USER:-}" || "$SUDO_USER" == "root" ]]; then
    echo "brew-to-ports: do not run this script as root. Run as your login user; the script sudo's port only." >&2
    exit 1
  fi
  BREW_OWNER="$SUDO_USER"
  BREW_AS=(/usr/bin/sudo -u "$BREW_OWNER" -H --)
else
  BREW_OWNER="$(/usr/bin/id -un)"
  PORT_AS=(/usr/bin/sudo)
fi

# One sudo password. Compile stays root for that `port install`; keepalive
# covers the gap before the next one. sudo -n after: dead ticket fails closed.
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
      /bin/sleep 30
    done
  ) &
  SUDO_KEEP_PID=$!
  trap '[[ -n "${SUDO_KEEP_PID:-}" ]] && /bin/kill "$SUDO_KEEP_PID" 2>/dev/null || true' EXIT
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
    run_logged "$@"
  fi
}

if [[ "$APPLY" -eq 0 ]]; then
  echo "DRY-RUN (pass --apply to execute). No packages will be installed or uninstalled."
else
  echo "APPLY: installs MacPorts ports and uninstalls brew kegs."
  echo "This script does not back up Homebrew. Time Machine, or a copy of /usr/local/{Cellar,Caskroom,Homebrew,etc,var} plus brew bundle dump, first. bin/sbin are mostly symlinks."
  APPLY_LOG="${HERE}/logs/report-$(/bin/date +%Y-%m-%d).txt"
  /bin/mkdir -p "${HERE}/logs"
  {
    echo ""
    echo "===== brew-to-ports apply $(/bin/date '+%Y-%m-%d %H:%M:%S %z') pid=$$ ====="
  } >> "$APPLY_LOG"
  echo "log: $APPLY_LOG"
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
        + (path_file or "logs/zsh_path")
        + " (see scan report). This script does not edit rc files."
    )
    lines.append("")
    installs = [op for op in plan.ops if op.action == "port_install"]
    tries = [op for op in plan.ops if op.action == "try_source"]
    uninstalls = [op for op in plan.ops if op.action == "brew_uninstall"]

    if plan.configs:
        lines.append("# custom brew config (not copied — adjust the MacPorts file)")
        for cfg in plan.configs:
            lines.append(f"#   {cfg.brew_package}: {cfg.brew_path} -> {cfg.guessed_ports_path}")
        lines.append("")

    if plan.cutover:
        lines.append("# cutover (plan-time)")
        for ch in plan.cutover:
            lines.append(f"#   {ch.runtime}: {ch.action}" + (f" drop {', '.join(ch.drop)}" if ch.drop else ""))
        lines.append("")

    n_inst = len(installs) + len(tries)
    n_un = len(uninstalls)

    lines.append("echo '--> port selfupdate'")
    lines.append("port_sudo -N selfupdate")
    lines.append("")
    if n_inst:
        lines.append(f"echo '--> install phase: {n_inst} ports'")
        lines.append("")

    for i, op in enumerate(installs, 1):
        lines.append(
            f"echo '--> install {_ascii_bar(i, n_inst)} port {op.port_name} (brew {op.brew_name})'"
        )
        lines.append(f'install_port {op.port_name}')
        lines.append("")

    for j, op in enumerate(tries, 1):
        i = len(installs) + j
        lines.append(
            f"echo '--> install {_ascii_bar(i, n_inst)} try-source {op.port_name} overlay {op.overlay_dir}'"
        )
        lines.append(f'try_source_port {_sh_single(op.port_name)} {_sh_single(op.overlay_dir)}')
        lines.append("")

    if uninstalls:
        lines.append("ensure_sudo")
        lines.append("")
        lines.append(f"echo '--> remove phase: {n_un} brew kegs'")
        lines.append("")

    for i, op in enumerate(uninstalls, 1):
        kind = op.kind or "formula"
        tag = f"remove {_ascii_bar(i, n_un)}"
        if op.hold_uninstall:
            lines.append(
                f"echo '--> {tag} brew {op.brew_name} (held until --config-ack {op.brew_name})'"
            )
            lines.append(f'if acked "{op.brew_name}"; then')
            lines.append(f'  uninstall_brew {op.brew_name} {kind}')
            lines.append("else")
            lines.append(
                f'  echo "HOLD: {op.brew_name} has config/state; pass --config-ack {op.brew_name} to uninstall brew copy"'
            )
            lines.append("fi")
        elif op.comment.startswith("drop:"):
            lines.append(f"echo '--> {tag} DROP {op.brew_name} (no MacPorts equivalent)'")
            lines.append(f"uninstall_brew {op.brew_name} {kind}")
        elif op.comment == "try_source":
            lines.append(
                f"echo '--> {tag} brew {op.brew_name} (only if overlay port installed)'"
            )
            lines.append(f"uninstall_brew_if_port {op.brew_name} {kind} {op.port_name}")
        elif op.port_name:
            lines.append(
                f"echo '--> {tag} brew {op.brew_name} (only if port {op.port_name} is installed)'"
            )
            lines.append(f"uninstall_brew_if_port {op.brew_name} {kind} {op.port_name}")
        else:
            lines.append(f"echo '--> {tag} brew {op.brew_name}'")
            lines.append(f"uninstall_brew {op.brew_name} {kind}")
        lines.append("")

    lines.append('echo "--> brew autoremove (unrequested leaves brew still sees)"')
    lines.append("autoremove_brew")
    lines.append("")
    lines.extend(_apply_done_banner(plan))
    lines.append("")
    return "\n".join(lines)


def _apply_done_banner(plan: Plan) -> list:
    """Parent TTY cannot be repaired in-place. Say so, with the PATH cutover."""
    body = [
        "done.",
        "",
        "Open a new terminal. This session still hashes brew binaries.",
        "hash -r here is not enough if login rc still prepends kegs",
        "or evals brew shellenv.",
    ]
    advice = plan.path_advice
    if advice and advice.path_file:
        body.append(f"PATH file: {advice.path_file}")
    if advice and advice.comment_out:
        body.append("Comment these writers, then restart (or source the PATH file):")
        for item in advice.comment_out:
            body.append(f"  {item.path}:{item.lineno}  {item.text}")
    if advice and advice.load_zsh:
        body.append("zsh load (after path_helper):")
        body.extend(advice.load_zsh.rstrip().splitlines())
    if plan.select_links:
        body.append("")
        body.append("Link unversioned runtimes (after the ports are installed):")
        body.extend(format_select_block(plan.select_links, indent=""))
    # zsh builtin — never `cat` (user rc often aliases cat to bat).
    return [f"print -r -- {_sh_single(line)}" for line in body]


def _ascii_bar(i: int, n: int, width: int = 20) -> str:
    if n <= 0:
        filled = 0
    else:
        filled = min(width, (width * i) // n)
    return f"[{'#' * filled}{'-' * (width - filled)}] {i}/{n}"


def _sh_single(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


HELPERS = r'''
# Port/brew mutator stdout+stderr → APPLY_LOG. TTY keeps dialogs, the
# progress bar, and one "dep: name" line when MacPorts starts a dependency.
# Halt (nonzero exit, INT/TERM, or a skipped failed install) dumps 40 log lines.

dump_log_tail() {
  [[ "${DUMPED_LOG:-0}" -eq 1 ]] && return 0
  [[ -n "${APPLY_LOG:-}" && -f "$APPLY_LOG" ]] || return 0
  DUMPED_LOG=1
  echo "" >&2
  echo "----- last 40 lines of $APPLY_LOG -----" >&2
  /usr/bin/tail -n 40 "$APPLY_LOG" >&2
  echo "----- end log tail -----" >&2
}

on_exit() {
  local rc="$1"
  [[ -n "${SUDO_KEEP_PID:-}" ]] && /bin/kill "$SUDO_KEEP_PID" 2>/dev/null || true
  if [[ "$rc" -ne 0 && "$APPLY" -eq 1 ]]; then
    dump_log_tail
  fi
}

trap 'on_exit $?' EXIT
trap 'echo "brew-to-ports: interrupted." >&2; exit 130' INT
trap 'echo "brew-to-ports: terminated." >&2; exit 143' TERM

TTY_PORT_SHOWN=""
TTY_PORT_TARGET=""

tty_port_line() {
  local line="$1"
  local pkg=""
  case "$line" in
    "---> Fetching archive for "*|\
    "---> Fetching distfiles for "*|\
    "---> Computing dependencies for "*|\
    "---> Verifying checksums for "*|\
    "---> Applying patches to "*|\
    "---> Extracting "*|\
    "---> Configuring "*|\
    "---> Building "*|\
    "---> Cleaning "*)
      pkg="${line##* }"
      ;;
    "---> Installing "*)
      pkg="${line#---> Installing }"
      pkg="${pkg%% *}"
      pkg="${pkg%%@*}"
      ;;
    "---> Activating "*)
      pkg="${line#---> Activating }"
      pkg="${pkg%% *}"
      pkg="${pkg%%@*}"
      ;;
    "---> Staging "*)
      pkg="${${line#---> Staging }%% *}"
      ;;
    *)
      return 0
      ;;
  esac
  [[ -n "$pkg" ]] || return 0
  [[ "$pkg" != "$TTY_PORT_SHOWN" ]] || return 0
  TTY_PORT_SHOWN="$pkg"
  if [[ -n "$TTY_PORT_TARGET" && "$pkg" == "$TTY_PORT_TARGET" ]]; then
    return 0
  fi
  if [[ -n "$TTY_PORT_TARGET" && "$pkg" != "$TTY_PORT_TARGET" ]]; then
    echo "    dep: $pkg"
  else
    echo "    $pkg"
  fi
}

run_logged() {
  setopt localoptions no_errexit
  local rc=0
  if [[ -z "${APPLY_LOG:-}" ]]; then
    "$@"
    return $?
  fi
  {
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
  } >> "$APPLY_LOG"
  TTY_PORT_SHOWN=""
  "$@" 2>&1 | /usr/bin/tee -a "$APPLY_LOG" | while IFS= read -r line || [[ -n "$line" ]]; do
    tty_port_line "$line"
  done
  rc=${pipestatus[1]}
  return $rc
}

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

ensure_sudo() {
  [[ "$APPLY" -eq 1 ]] || return 0
  [[ "$(/usr/bin/id -u)" -eq 0 ]] && return 0
  sudo_refresh && return 0
  echo "Enter your sudo password for MacPorts package installations."
  /usr/bin/sudo -v || {
    echo "brew-to-ports: sudo is required (cask uninstall / port). Aborting." >&2
    exit 1
  }
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
  # Query as the current uid. Do not wrap this with sudo.
  # `port installed NAME` exits 0 even when NAME is not installed; check output.
  local out
  out="$("$PORT" -q installed "$1" 2>/dev/null || true)"
  [[ -n "$out" ]]
}

brew_has_formula() {
  "${BREW_AS[@]}" "$BREW" list --formula "$1" >/dev/null 2>&1
}

brew_has_cask() {
  "${BREW_AS[@]}" "$BREW" list --cask "$1" >/dev/null 2>&1
}

typeset -A BREW_SVC
BREW_SVC_LOADED=0

brew_services_load() {
  [[ "$BREW_SVC_LOADED" -eq 1 ]] && return 0
  BREW_SVC_LOADED=1
  local line name st
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == Name* ]] && continue
    name="${${=line}[1]}"
    st="${${=line}[2]}"
    BREW_SVC[$name]="$st"
  done < <("${BREW_AS[@]}" "$BREW" services list 2>/dev/null || true)
}

stop_brew_service() {
  local name="$1"
  local st
  brew_services_load
  st="${BREW_SVC[$name]:-}"
  [[ "$st" == "started" || "$st" == "error" ]] || return 0
  run "${BREW_AS[@]}" "$BREW" services stop "$name" || true
}

port_is_active() {
  local out
  out="$("$PORT" -q installed "$1" 2>/dev/null || true)"
  [[ "$out" == *"(active)"* ]]
}

port_deactivate_conflicts() {
  local name="$1"
  local raw conf
  raw="$("$PORT" info --conflicts "$name" 2>/dev/null || true)"
  raw="${raw##*conflicts:}"
  raw="${raw//,/ }"
  for conf in ${=raw}; do
    [[ -n "$conf" && "$conf" != "$name" ]] || continue
    if port_is_active "$conf"; then
      echo "deactivate active $conf (conflicts with $name)"
      port_sudo -N deactivate "$conf" || true
    fi
  done
}

install_port() {
  local name="$1"
  TTY_PORT_TARGET="$name"
  TTY_PORT_SHOWN=""
  if [[ "$APPLY" -eq 1 ]] && port_has "$name"; then
    echo "skip: port $name already installed"
    TTY_PORT_TARGET=""
    return 0
  fi
  if ! port_sudo -N install "$name"; then
    echo "install $name failed; deactivating MacPorts conflicts and retrying"
    dump_log_tail
    DUMPED_LOG=0
    port_deactivate_conflicts "$name"
    if ! port_sudo -N install "$name"; then
      echo "skip: could not install $name (MacPorts conflict); leaving brew keg"
      dump_log_tail
      DUMPED_LOG=0
      TTY_PORT_TARGET=""
      return 0
    fi
  fi
  TTY_PORT_TARGET=""
  if [[ "$APPLY" -eq 1 ]]; then
    port_has "$name"
  else
    run "$PORT" -q installed "$name"
  fi
}

try_source_port() {
  local name="$1"
  local dir="$2"
  TTY_PORT_TARGET="$name"
  TTY_PORT_SHOWN=""
  if [[ "$APPLY" -eq 1 ]] && port_has "$name"; then
    echo "skip: port $name already installed"
    TTY_PORT_TARGET=""
    return 0
  fi
  if [[ "$APPLY" -eq 1 ]]; then
    if ! port_sudo -N -D "$dir" install; then
      echo "try-source failed for $name; leaving brew keg in place"
      dump_log_tail
      DUMPED_LOG=0
      TTY_PORT_TARGET=""
      return 0
    fi
  else
    run "${PORT_AS[@]}" "$PORT" -D "$dir" install
  fi
  TTY_PORT_TARGET=""
}

uninstall_brew_if_port() {
  local name="$1"
  local kind="${2:-formula}"
  local portname="${3:-$1}"
  if [[ "$APPLY" -eq 1 ]] && ! port_has "$portname"; then
    echo "skip: port $portname not installed; leaving brew $name"
    return 0
  fi
  uninstall_brew "$name" "$kind"
}

uninstall_brew() {
  local name="$1"
  local kind="${2:-formula}"
  if [[ "$kind" == "cask" ]]; then
    if [[ "$APPLY" -eq 1 ]] && ! brew_has_cask "$name"; then
      echo "skip: brew cask $name not installed"
      return 0
    fi
    ensure_sudo
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
