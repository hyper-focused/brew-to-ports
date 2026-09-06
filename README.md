# brew-to-ports

Plan a Homebrew → MacPorts move on **Intel Macs**.

Homebrew treats all Intel x86_64 systems as [Tier 3](https://docs.brew.sh/Support-Tiers): no new bottles, no CI, and Intel support is slated to go away in or after September 2027. Homebrew itself points those machines at [MacPorts](https://www.macports.org). This tool inventories your cellar, matches what it can, and emits a plan. It does not silently rewrite the machine.

**Apple Silicon is a hard fail.** Homebrew is still Tier 1 there.

## Requirements

- Intel x86_64 macOS
- Homebrew (`brew info --json=v2 --installed`)
- Xcode Command Line Tools (`/usr/bin/python3`)
- MacPorts optional (local PortIndex). Without it, pass `--portindex FILE` or you get inventory only.

The wrapper and generated `migrate.sh` run under **`/bin/zsh`** and **`/usr/bin/python3`** so uninstalling brew’s zsh/python cannot kill the migrator. That is not a recommendation to *live* on Apple’s copies.

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

```sh
./brew-to-ports                          # scan (read-only)
./brew-to-ports --script --commands --path-file
./migrate.sh                             # dry-run
./migrate.sh --apply                     # the only mutator
```

`--path-file` writes `~/.zsh_path.brew-to-ports` (one directory per line). The report lists `source` / `export PATH` / `brew shellenv` lines to comment, plus zsh/bash load one-liners. It does not edit rc files.

`--allow-older-same-major` opts in to MacPorts ports that are older but the same major as the brew formula.

`--brew-json FILE` / `--portindex FILE` run against dumps (useful for tests and for machines that cannot talk to the PortIndex).

## What it does

- Formulae and casks: requested vs dependency, bottle vs source, keg-only.
- Match to MacPorts: exact name, aliases, `@version` compact (`php@8.5` → `php85`), stem maps (`python-foo` → `py314-foo`, `node@22` → `nodejs22`, `ruby-`/`perl-`/`r-` modules), homepage family pick (`ffmpeg-full` → `ffmpeg-devel`).
- Keep-set: requested brew survivors (and casks) pin their brew runtime graph. Unrequested leftovers of migrators can go; MacPorts already pulled what it needs.
- PATH advice from `.zshenv` / `.zprofile` / sourced files under `$HOME` (not antidote/Cellar).
- Best-effort `/usr/local` → `/opt/local` rewrites for aliases and `LDFLAGS`/`CPPFLAGS`.
- Generated `migrate.sh`: dry-run default, restart-safe skips, `brew services stop` before uninstall, `brew autoremove` at the end.

## What it will not do

- Run on Apple Silicon or Linuxbrew
- Copy nginx.conf, databases, or TLS keys
- Edit `~/.zshrc` / `~/.zsh_path` for you
- Auto-migrate language runtimes (python/ruby/node/php) or toolchains (gcc/llvm)
- Treat `port search yq` hits as equivalents (`python-yq` is not `py-pyqt4` and not ports `yq`)

## Layout

```
brew-to-ports          # zsh wrapper
src/brew_to_ports/     # stdlib Python
data/aliases.json      # one-off brew → port names
data/exceptions.json   # runtime / toolchain / stateful categories
tests/                 # fixtures, no live brew required
```

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

CI runs that on Ubuntu (fixture-only). Matching rules: see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). Homebrew and MacPorts are separate projects with their own licenses; this tool only shells out to `brew` / `port` and reads their public indexes.
