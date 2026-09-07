#!/bin/zsh
# Run under Apple /bin/zsh and /usr/bin/python3 so brew zsh/python can be uninstalled.
set -euo pipefail

if [[ -z "${BREW_TO_PORTS_SYS_ZSH:-}" ]]; then
  export BREW_TO_PORTS_SYS_ZSH=1
  exec /bin/zsh "$0" "$@"
fi

# Apple system PATH only. gnubin / keg / ports bins are not this process's
# runtime. brew and port are invoked by absolute path. Stash the launch PATH
# so the planner can still report what the user's shell uses.
unsetopt aliases
unalias -m '*' 2>/dev/null || true
export BREW_TO_PORTS_USER_PATH="${BREW_TO_PORTS_USER_PATH:-$PATH}"
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
hash -r

ROOT="${0:A:h}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$(/usr/bin/id -u)" -eq 0 ]]; then
  echo "brew-to-ports: run as your login user, not sudo. Homebrew must not run as root." >&2
  exit 1
fi

macos="$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"
major="${macos%%.*}"
if ! [[ "$major" == <-> ]] || (( major < 13 )); then
  echo "brew-to-ports: macOS 13 Ventura or later required (got ${macos:-unknown})." >&2
  exit 1
fi

SYS_PY="/usr/bin/python3"
if [[ ! -x "$SYS_PY" ]]; then
  echo "brew-to-ports: need $SYS_PY (Xcode Command Line Tools)." >&2
  exit 1
fi

# Resolve with system python, never PATH python3 (that may be brew).
resolved="$("$SYS_PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$SYS_PY")"
brew_prefix=""
if [[ -x /usr/local/bin/brew ]]; then
  brew_prefix="$(/usr/local/bin/brew --prefix 2>/dev/null || true)"
fi
if [[ -n "$brew_prefix" && "$resolved" == "$brew_prefix"* ]]; then
  echo "brew-to-ports: $SYS_PY resolves into Homebrew ($resolved). Refusing." >&2
  exit 1
fi

exec "$SYS_PY" -m brew_to_ports "$@"
