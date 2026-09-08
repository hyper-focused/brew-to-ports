# Status

Intel Homebrew → MacPorts planner. Entry: `./brew-to-ports.zsh`. Scan is read-only. `migrate.zsh --apply` is the only mutator. Waves: scan → dry-run → apply → new terminal → scan again. User guide: [README.md](README.md). Flags and waves: [DETAILS.md](DETAILS.md).

## Shipped

- Intel x86_64 only; macOS 13 Ventura through 26 Tahoe (`sw_vers` 26 is valid)
- Wrapper `brew-to-ports.zsh`: Apple `/bin/zsh` + `/usr/bin/python3`; process PATH is `/usr/bin:/bin:/usr/sbin:/sbin`; aliases off; brew/port by absolute path
- Matcher: exact, aliases, `@version` compact, stem maps, homepage **with shared non-generic stem**, family pick
- Keep-set: requested keep/exception + casks pin brew runtime deps; leftover unrequested deps of migrators can go
- Exceptions: runtime, toolchain, **service** (httpd/nginx/unbound stay). **MySQL/MariaDB/Percona are radioactive** — server, `mysql-client`, connectors; no migrate, no try-source overlay
- Python / php / node family cutover (TTY `[m]/[s]/[q]` then `yes`; non-TTY `--migrate-runtime` + `--i-acked-drop`). Ruby is not offered. MacPorts nodejs: only the newest major is installed (they conflict)
- HOLD uninstall is apply-only: `migrate.zsh --apply --config-ack FORMULA` (php.ini). `--i-acked-drop` is a **planner** flag, not `migrate.zsh`
- `--try-source` / `--allow-try-source`: overlay Portfiles for **source-built** unmatched kegs (github noarch, Go, autoreconf); `port -D` install; brew keg stays on failure; bottled unmatched stay on brew
- `--allow-older-same-major`
- Privileges: never `sudo brew`; one `sudo -v` for MacPorts; keepalive + `sudo -n`
- `--apply` reminds: Time Machine or a copy of Cellar/Homebrew/etc/var first (not just bin/sbin)
- Quiet apply TTY: bar + package/`dep:`; port/brew stdout in `logs/report-YYYY-MM-DD.txt`; 40-line dump on halt
- Scan TTY is a summary; full dump in `logs/scan-YYYY-MM-DD.txt`. Default writes `migrate.zsh` and offers dry-run; `--no-script` skips
- `port select --set` lines for php / python / python3 / pip / pip3 (newest)
- Artifacts in **cwd** `logs/` (`scan-`, `report-`, `zsh_path`, `overlay/`) — not `$HOME/.zsh_path.brew-to-ports`
- PATH file includes Apple `/usr/bin` `/bin` `/usr/sbin` `/sbin`; notes `/etc/zprofile` path_helper. Does not edit rc or `/etc/zprofile`
- gnubin alias suggestions → `/usr/bin/<cmd>`; zsh `print` not `cat`
- Custom brew confs listed with paths (vendor baseline vs live; bottle owns the file); not copied
- Tests: `PYTHONPATH=src python3 -m unittest discover -s tests -q` (CI installs zsh)

## Not doing

- Apple Silicon
- `--allow-older-major` (HandBrake 0.10 vs 1.11, ImageMagick 6 vs 7)
- Translating brew Ruby `install {}` into Portfiles
- Storing a sudo password
- Editing `sources.conf`, user rc, or `/etc/zprofile`
- Copying nginx.conf / databases / TLS keys
- Touching brew MySQL / MariaDB / Percona (install, overlay, or uninstall)
- Cellar-specific `aliases.json` entries
- `path_helper` as migrate teardown (it prepends `/usr/local/bin`; it is not undo)

## Next (when we say go)

1. **try-source shapes we skipped** — cmake, rust/PyPI (only if a destroot strategy is boring). MySQL/MariaDB are not on this list; they stay radioactive
2. **Cask Aqua cutover** — iTerm/Audacity already match; default is still keep-on-brew

Remaining keep-set after python + same-major + try-source on the author’s cellar was mostly casks, ImageMagick/HandBrake (older major), pyenv/pydantic (no equivalent), and leftover brew deps of keepers. That is policy, not unnamed packages.

## Module owners

| Module | Owns |
|---|---|
| `brew-to-ports.zsh` | Apple zsh wrapper; pins OS PATH; execs `/usr/bin/python3` |
| `match.py` | brew → port name (no migrate/keep) |
| `classify.py` | initial Decision (runtime/toolchain/service stay exception) |
| `family.py` | runtime + direct dependents; can/drop/blocked (python/php/node) |
| `cutover.py` | `CutoverChoice`; TTY + planner flags (`--migrate-runtime`, `--i-acked-drop`) |
| `select.py` | `port select --set` for php/python/pip (newest) |
| `source_try.py` | overlay Portfile text + shape (skips mysql/mariadb/percona) |
| `plan.py` | keep-set, cutover overlay, try-source overlay, ops |
| `config_scan.py` | brew conf inventory; custom vs vendor baseline; never copies |
| `path_suggest.py` | PATH file + rc *advice* (does not write rc) |
| `paths.py` | cwd `logs/` locations |
| `adapters/os_tools.py` | Apple PATH for migrator subprocesses |
| `render/report.py` | TTY summary + full scan dump |
| `render/script.py` | migrate.zsh (dry-run default; `--apply`; `--config-ack`) |
