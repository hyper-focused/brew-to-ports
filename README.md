# brew-to-ports

Plan a Homebrew → MacPorts move on **Intel** Macs. Homebrew is Tier 3 on Intel (no new bottles; gone ~Sep 2027).

Scan is read-only. `migrate.sh` is dry-run unless you pass `--apply`. Config/state is inventoried, not copied. Apple Silicon is a hard fail.

Audience: people who already live in a terminal. The scanner does what it can with PATH files, `source`/`export`/`brew shellenv` lines, and a best-effort `/usr/local` → `/opt/local` swap on aliases and linker flags. It will not catch every keg, GNU `g-` prefix, or variant. If your rc graph is weirder than that, you already know to verify it.

## Usage

```sh
./brew-to-ports
./brew-to-ports --script --commands --path-file
./migrate.sh              # dry-run
./migrate.sh --apply
```

`--path-file` writes `~/.zsh_path.brew-to-ports` (one dir per line). The report lists `source` / `export PATH` / `brew shellenv` lines to comment, plus zsh/bash load one-liners.

Requires Intel x86_64, `brew info --json=v2 --installed`, and `/usr/bin/python3` (not Homebrew’s). MacPorts is optional if you pass `--portindex`. The tool runs under `/bin/zsh` and `/usr/bin/python3` so brew’s zsh/python can be uninstalled without killing the migrator. That is not a recommendation to *live* on Apple’s copies.

## Layout

Python 3 stdlib under `src/brew_to_ports/`. Wrapper: `brew-to-ports`. Aliases/exceptions: `data/*.json`.
