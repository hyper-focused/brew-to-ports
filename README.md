# brew-to-ports

Plan a Homebrew → MacPorts move on **Intel Macs**.

Homebrew treats all Intel x86_64 systems as [Tier 3](https://docs.brew.sh/Support-Tiers): no new bottles, no CI, and Intel support is slated to go away in or after September 2027. Homebrew itself points those machines at [MacPorts](https://www.macports.org). This tool inventories your cellar, matches what it can, and emits a plan. It does not silently rewrite the machine.

**Apple Silicon is a hard fail.** Homebrew is still Tier 1 there.

## Requirements

This runs on the Intel Mac being migrated. Not Apple Silicon, not Linux, not macOS 12.

**Host**
- Intel x86_64
- macOS **13 Ventura through 26 Tahoe**
  - Ventura, Sonoma, Sequoia: the usual Intel cellar
  - Tahoe: four Intel models still on Apple’s list ([support.apple.com/122867](https://support.apple.com/en-us/122867)) — 16" MacBook Pro 2019, 13" MacBook Pro 2020 (four Thunderbolt 3), 27" iMac 2020, Mac Pro 2019. `sw_vers` reports **26**, not 16.
- `/bin/zsh` (Apple’s copy; the wrapper re-execs it)

**Runtime (Xcode Command Line Tools, not a Python you installed)**
- `xcode-select --install`
- `/usr/bin/python3` **3.9.6** (what Apple CLT ships from Ventura on)
- No pip, no venv, no `python.org` install, no Homebrew Python  
  (`--allow-brew-python` exists; it is not the supported path)
- Full Xcode.app is not required for the planner

**Inventory**
- Homebrew at the Intel prefix (`/usr/local`)
- `brew info --json=v2 --installed` must work

**Catalog**
- MacPorts PortIndex: live install **or** `--portindex FILE`
- MacPorts is optional to *plan*. `migrate.sh --apply` needs MacPorts at `/opt/local` and `sudo` for `port install`.
- Intel Tahoe: MacPorts’ x86_64-26 bottle set is incomplete; more ports will build from source. The planner does not care.

Ventura is the floor because Apple CLT Python is 3.9 from 13 on (Monterey CLT was 3.8.9) and the [current MacPorts tree](https://www.macports.org) targets 13+. Tahoe is Apple’s last Intel macOS; 27+ is Apple Silicon only and already fails the Intel gate. No extra Tahoe code path. The wrapper and generated `migrate.sh` pin `/bin/zsh` and `/usr/bin/python3` so uninstalling brew’s copies cannot kill the migrator. That is not a recommendation to *live* on Apple’s Python.

Audience: people who already live in a terminal. The matcher and PATH scanner do what they can. They will not catch every keg, GNU `g-` prefix, variant, or homemade rc graph. Read the report.

## Install

```sh
git clone https://github.com/hyper-focused/brew-to-ports.git
cd brew-to-ports
chmod +x brew-to-ports
./brew-to-ports --help
```

No pip dependencies. Python 3.9+ stdlib only.

## Usage

The scan is read-only. Do not expect `./brew-to-ports` to `brew uninstall` anything. `migrate.sh --apply` is the only mutator; it already runs `brew autoremove` at the **end**.

Run the planner and `migrate.sh` as **your login user**, never `sudo ./migrate.sh`. Homebrew owns `/usr/local` and your launchd services; `sudo brew` is how you get a root-owned cellar. The script `sudo`s **only** `port` (`selfupdate` / `install`). `--apply` asks for your sudo password **once** (`sudo -v`) and keeps the ticket alive; it does not store the password. Later `port` calls use `sudo -n` (fail if the ticket died, no 76 prompts). If you do `sudo ./migrate.sh` anyway, it drops `brew` back to `$SUDO_USER` and refuses if it cannot tell who that is. A few casks may prompt for sudo on their own — that is brew calling sudo, not us wrapping brew.

**Before you scan** (optional hygiene — you run these, not the planner):

```sh
brew autoremove --dry-run    # orphans: unrequested, nothing still needs them
brew cleanup --dry-run       # old kegs + cache, not installed formulae
```

If that list is junk, run them for real, **then** scan. If it names something you still invoke by PATH, leave it. `installed_on_request` lies. Repeat: scan → apply → scan again. One `migrate.sh` is a snapshot of this cellar; keep-set is computed from who still has a brew reason to live.

```sh
./brew-to-ports                          # scan (read-only)
./brew-to-ports --script --commands --path-file
./migrate.sh                             # dry-run
./migrate.sh --apply                     # the only mutator
./brew-to-ports --script                 # wave 2, after the cellar changed
```

`--path-file` writes `~/.zsh_path.brew-to-ports` (one directory per line). The report lists `source` / `export PATH` / `brew shellenv` lines to comment, plus zsh/bash load one-liners. It does not edit rc files.

`--allow-older-same-major` opts in to MacPorts ports that are older but the same major as the brew formula.

On a TTY, python / `python@*` families get `[m]igrate` / `[s]kip` / `[q]uit` (then `yes` if anything would be deleted). `q` writes nothing. Non-TTY stays dual-stack unless `--migrate-runtime python@3.13` and `--i-acked-drop python@3.13` when unmatched children would be dropped. php/node/ruby are not in this slice.

`--try-source` writes best-effort overlay Portfiles (github noarch, Go, autoreconf) under `~/.brew-to-ports/overlay` and plans `port -D` install. cmake/rust/PyPI/mysql are not attempted. Failed overlay install leaves the brew keg. Does not edit `sources.conf`.

`--brew-json FILE` / `--portindex FILE` run against dumps (useful for tests and for machines that cannot talk to the PortIndex).

## What it does

- Formulae and casks: requested vs dependency, bottle vs source, keg-only.
- Match to MacPorts: exact name, aliases, `@version` compact (`php@8.5` → `php85`), stem maps (`python-foo` → `py314-foo`, `node@22` → `nodejs22`, `ruby-`/`perl-`/`r-` modules), homepage family pick (`ffmpeg-full` → `ffmpeg-devel`) only when names share a non-generic stem.
- Keep-set: requested brew survivors (and casks) pin their brew runtime graph. Unrequested leftovers of migrators can go; MacPorts already pulled what it needs. Service/runtime/toolchain exceptions are not leftover-uninstalled.
- Python family cutover (plan-time). php/node/ruby stay dual-stack until that slice exists.
- `--try-source` overlay Portfiles for some unmatched formulae (not cmake/rust/PyPI).
- PATH advice from `.zshenv` / `.zprofile` / sourced files under `$HOME` (not antidote/Cellar).
- Best-effort `/usr/local` → `/opt/local` rewrites for aliases and `LDFLAGS`/`CPPFLAGS`.
- Generated `migrate.sh`: dry-run default, restart-safe skips, `brew services stop` before uninstall, `brew autoremove` at the end. `sudo` only `port`.

## What it will not do

- Run on Apple Silicon, Linuxbrew, or macOS 12 Monterey and older
- Copy nginx.conf, databases, or TLS keys
- Edit `~/.zshrc` / `~/.zsh_path` for you
- Auto-migrate language runtimes (python/ruby/node/php) or toolchains (gcc/llvm) without a TTY cutover / `--migrate-runtime`
- Treat `port search yq` hits as equivalents (`python-yq` is not `py-pyqt4` and not ports `yq`)

## Layout

```
brew-to-ports          # zsh wrapper
src/brew_to_ports/     # stdlib Python
data/aliases.json      # one-off brew → port names
data/exceptions.json   # runtime / toolchain / service / stateful
tests/                 # fixtures, no live brew required
STATUS.md              # shipped / not doing / next
```

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

CI runs that on Ubuntu (fixture-only). Matching rules: [CONTRIBUTING.md](CONTRIBUTING.md). Progress: [STATUS.md](STATUS.md).

## License

[MIT](LICENSE). Homebrew and MacPorts are separate projects with their own licenses; this tool only shells out to `brew` / `port` and reads their public indexes.
