# Details

Operator reference: uncommon flags, custom prefixes, files, and why specific bits are shaped the way they are. The migrate path is [README.md](README.md). You do not need this file to move a cellar.

---

## Requirements

Runs **on the Intel Mac being migrated.** Not a Linux CI box. Not Apple Silicon.

| Must be | Or we refuse |
| --- | --- |
| Intel **x86_64** | Apple Silicon. Homebrew is still Tier 1 there. |
| macOS **13 Ventura through 26 Tahoe** | Monterey and older. MacPorts' current tree is Ventura+. |
| Apple `/bin/zsh` | Wrapper and `migrate.zsh` re-exec it so brew zsh can die mid-apply. |
| Xcode **Command Line Tools**; `/usr/bin/python3` **3.9.6+** | Full Xcode.app is optional. `--allow-brew-python` is a fire exit, not a plan. |
| Homebrew at `/usr/local` | Intel prefix. `brew info --json=v2 --installed` must work. |
| MacPorts at `/opt/local` for `--apply` | Optional to *plan* (`--portindex FILE`). Required to move anything. |

**Tahoe:** four Intel models are still on Apple's list ([support.apple.com/122867](https://support.apple.com/en-us/122867)) — 16" MBP 2019, 13" MBP 2020 (four Thunderbolt 3), 27" iMac 2020, Mac Pro 2019. `sw_vers` says **26**, not 16. MacPorts' x86_64-26 bottles are incomplete, so more ports build from source. The planner does not care. Your fans will.

Ventura is the floor because CLT Python became 3.9 there (Monterey was 3.8.9) and MacPorts' current tree targets 13+. Tahoe is the last Intel macOS. 27+ is Apple Silicon and already fails the Intel gate.

**Custom prefixes / offline.** Intel Homebrew is `/usr/local/bin/brew`; that is not configurable. MacPorts prefix defaults to `/opt/local`; set `MACPORTS_PREFIX` if yours lives elsewhere. Fake a cellar with `--brew-json FILE`. Fake a PortIndex with `--portindex FILE` or `BREW_TO_PORTS_PORTINDEX`. Write the apply script somewhere other than `./migrate.zsh` with `--script FILE`. `--no-script` scans without writing `migrate.zsh` (no dry-run offer). These are for tests and odd installs, not the usual migrate.

---

## How a wave works

One `migrate.zsh` is a snapshot of **this** cellar. After apply, the cellar changed. Scan again.

1. **Scan** — `./brew-to-ports.zsh`. Read-only. Matches cellar → PortIndex. Writes `migrate.zsh` and `logs/zsh_path` **by default**. On a TTY, asks `Dry-run migrate.zsh now? [Y/n]` (Enter = yes, still a dry-run). `--no-script` skips the script and that prompt.
2. **Dry-run** — that prompt, or `./migrate.zsh` with no `--apply`. Prints `DRY-RUN:` lines. Installs nothing.
3. **Apply** — `./migrate.zsh --apply`. The only mutator. `port -N selfupdate`, `port install`, then `brew uninstall` if the port is actually there, then `brew autoremove`. HOLD kegs need `--config-ack`.
4. **New terminal.** `port select`. Scan again.

TTY scan is a **summary** (counts, migrate / drop / exception, requested keep, `port select`). Full dump: `logs/scan-YYYY-MM-DD.txt` (append). `--apply` TTY is a progress bar + current package / `dep:`; port/brew stdout is `logs/report-YYYY-MM-DD.txt`. Halt dumps the last 40 log lines. Success prints `done.` plus PATH / `port select`.

`q` at a cutover prompt writes **nothing**.

Restart-safe: skip if the port is already installed; skip brew uninstall if the mapped port isn't. Re-run `--apply` after a compile failure. Skip-on-conflict leaves the brew keg. `port -N` so MacPorts doesn't hide `Continue?` in the pipe. Never `port -q` for installs (`-q` is mute, not logged).

---

## Apple PATH (why the script does not call `ls`)

Planner and `migrate.zsh` pin:

```
PATH=/usr/bin:/bin:/usr/sbin:/sbin
```

Aliases off. `hash -r`. `brew` is `/usr/local/bin/brew`. `port` is `/opt/local/bin/port`. The done banner is zsh `print`, not `cat`, because rc may still say `alias cat=bat` after we uninstall bat.

If the user put gnubin first and aliased `ls` to `gls`, uninstalling coreutils would make a bare `ls` in our script fail. `/bin/ls` does not. gnubin *alias suggestions* in the scan log rewrite to `/usr/bin/<cmd>`, not MacPorts gnubin.

This is **only** for our process. `/etc/zprofile` runs `path_helper` and often puts `/usr/local/bin` first. We do **not** edit `/etc/zprofile`. Load `logs/zsh_path` in `~/.zprofile` **after** that. We do not call `path_helper` as teardown — it prepends `/usr/local/bin`; it is not undo.

Generated `logs/zsh_path` order: `$HOME` bins, MacPorts, Apple (`/usr/bin` `/bin` `/usr/sbin` `/sbin`, plus Cryptexes if present), leftovers, `/usr/local/bin` **last**.

---

## What we will not migrate

Some of this is not yet. Some of this is policy.

| Leave it | Why |
| --- | --- |
| **Apple Silicon** | Homebrew is still Tier 1. |
| **Casks** (iTerm, fonts, …) | Default keep even if a MacPorts Aqua port exists. |
| **Ruby** | Never in the cutover prompt. Homebrew's engine is portable-ruby; MacPorts `ruby @1.8.7` is not a usable replacement. |
| **gcc / llvm / clang** | Toolchain exception. Dual-stack. |
| **httpd, nginx, unbound, …** | Services. We will not copy `nginx.conf` or TLS keys. |
| **MySQL / MariaDB / Percona** | Radioactive. Server, `mysql-client`, connectors. No migrate, no overlay, no uninstall. |
| **ImageMagick 7 vs ports 6, HandBrake 1.x vs 0.10, cmake 4 vs 3** | Older **major**. There is no `--allow-older-major`. |
| **Bottled unmatched kegs** | Stay on brew. `--try-source` is only for **source-built** unmatched (github noarch, Go, autoreconf). Not cmake / rust / PyPI / mysql. |
| **python-yq vs yq** | We do not `port search` and guess. A false migrate is worse than a keep. |

**Runtimes we offer:** python, php, node (`[m]` / `[s]` / `[q]`). Default on non-TTY is skip. Unmatched children of a migrate need `yes` or `--i-acked-drop`. MacPorts `nodejsN` majors **conflict** — only the newest is installed. `python313` and `python314` can both be active. php is `php84` / `php85` until you `port select`. nodejs has no `port select` — the active `nodejsN` *is* `/opt/local/bin/node`.

**HOLD.** Custom brew confs are listed (vendor baseline vs live). Stock bottle copies omitted. Nothing is copied. php.ini uninstall needs `--config-ack php@8.4` on **apply**. `--i-acked-drop` is a **planner** flag, not `migrate.zsh`.

---

## `./brew-to-ports.zsh` — planner, read-only

Default: scan, write `migrate.zsh` + `logs/zsh_path`, append `logs/scan-YYYY-MM-DD.txt`, then on a TTY ask `Dry-run migrate.zsh now? [Y/n]`. Enter is yes. Non-TTY prints the dry-run command instead of prompting.

| Flag | What it does |
| --- | --- |
| `--no-script` | Scan log only. No `migrate.zsh`, no dry-run offer. No `logs/zsh_path` unless you also pass `--path-file`. |
| `--script FILE` | Write the apply script somewhere else (default is already `migrate.zsh`). |
| `--report FILE` | Full dump path (default `logs/scan-YYYY-MM-DD.txt`). |
| `--path-file` / `--path-file FILE` | PATH data file (default `logs/zsh_path`). Also written with `migrate.zsh`. |
| `--commands` | Also print copy/paste `sudo port` / `brew uninstall` after the summary. |
| `--allow-older-same-major` | Opt in to ports that are older but **same major**. Not older major. |
| `--migrate-runtime FORMULA` | Non-TTY cutover for python / php / node (repeatable). TTY prompts instead. |
| `--i-acked-drop FORMULA` | Non-TTY: ack dropping unmatched children of that runtime. |
| `--try-source` / `--allow-try-source` / `--try-source DIR` | Overlay Portfiles for source-built unmatched kegs (`logs/overlay`). Bottled unmatched stay. |
| `--brew-json FILE` | Fake cellar (tests / offline). |
| `--portindex FILE` | Fake PortIndex. |
| `--dump` | `brew info --json=v2 --installed` to stdout, then exit. |
| `--allow-brew-python` | Run the planner under Homebrew's Python. Not the supported path. |

TTY cutover: `[m]igrate` `[s]kip` `[q]uit`, then `yes` if anything would be deleted.

---

## `./migrate.zsh` — the only mutator

Default is **dry-run**. Prints `DRY-RUN:` lines. Installs nothing.

| Flag | What it does |
| --- | --- |
| `--apply` | `port install` / `brew uninstall`. Sudo for **port** only. |
| `--config-ack FORMULA` | Uninstall a HOLD keg. Repeatable. Example: `--config-ack php@8.4`. |
| `-h` / `--help` | Usage. |

`--apply` reminds: Time Machine or a copy of Cellar/Homebrew/etc/var first (not just bin/sbin). One `sudo -v`, keepalive, then `sudo -n`. Casks that write `/opt/X11` or `/Applications` make *brew* invoke sudo as you. We still never `sudo brew`.

After apply, new terminal, then something like:

```sh
sudo port select --set php php84
sudo port select --set python python314
sudo port select --set python3 python314
sudo port select --set pip pip314
sudo port select --set pip3 pip314
```

Exact lines are in the scan summary (newest option per group).

---

## Files (working directory, not `$HOME`)

| Path | What |
| --- | --- |
| `migrate.zsh` | Apply script. Dry-run until `--apply`. Gitignored. |
| `logs/scan-YYYY-MM-DD.txt` | Full scan (reasons, keep-set, PATH rewrites). |
| `logs/report-YYYY-MM-DD.txt` | `--apply` port/brew log (next to the script: `${0:A:h}/logs`). |
| `logs/zsh_path` | PATH data, one directory per line. **You** source it. We don't edit rc. |
| `logs/overlay/` | try-source Portfiles. |

---

## Layout

```
brew-to-ports.zsh      # wrapper: Apple zsh + /usr/bin/python3
src/brew_to_ports/     # stdlib Python
data/aliases.json      # one-off brew → port names
data/exceptions.json   # runtime / toolchain / service / stateful
tests/                 # fixtures; CI does not need live brew
STATUS.md              # shipped / not doing / next
DETAILS.md             # flags, prefixes, files
```

Module owners and "not doing" live in [STATUS.md](STATUS.md). Matcher rules: [CONTRIBUTING.md](CONTRIBUTING.md).

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

CI: Ubuntu, Python 3.9 + 3.12, installs `zsh` for `/bin/zsh -n`.
