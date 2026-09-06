# brew-to-ports

Inventory Homebrew on **Intel Macs** and plan a conservative migration to MacPorts.

Homebrew classifies all Intel x86_64 Macs as Tier 3 (no new bottles, no CI) and will stop running on Intel in or after September 2027. Homebrew itself points those machines at MacPorts. This tool tells you what can move, what should stay, and what will bite you.

It does **not** silently rewrite your machine.

## What it does

- Lists installed Homebrew formulae and casks (bottle vs source, requested vs dependency).
- Matches them to MacPorts ports (name cascade + version compare).
- Classifies each package: **migrate** / **keep on brew** / **exception**.
- Prints copy/paste commands, a PATH suggestion, and config/state files that will **not** come along.
- Can write `migrate.sh`. That script **defaults to dry-run**. `--apply` is the only mutator.

## What it will not do (v1)

- Run on Apple Silicon (hard fail; Homebrew is still Tier 1 there).
- Copy or merge config/data files (`nginx.conf`, database dirs, TLS keys, …).
- Edit `~/.zshrc` / `~/.bashrc`.
- Uninstall leftover Homebrew, or yank a brew library still needed by a package you are keeping.
- Auto-migrate a MacPorts port that is an older major (or older same-major unless you pass `--allow-older-same-major`).

## Requirements

- Intel x86_64 macOS
- Homebrew (`brew info --json=v2 --installed`)
- `/usr/bin/python3` (Command Line Tools). Do not use Homebrew’s Python as the runtime.
- MacPorts optional for a local PortIndex; otherwise a PortIndex is fetched and cached.

## Usage

```sh
./brew-to-ports                  # scan (no changes)
./brew-to-ports --script         # also write migrate.sh (still dry-run)
./migrate.sh                     # print what would happen
./migrate.sh --apply             # actually install ports / uninstall brew formulae
```

## Layout

Python 3 stdlib core under `src/brew_to_ports/`. Thin zsh wrapper `brew-to-ports`. Curated name aliases and exception categories live in `data/`, not as one function per formula.

## License

Not yet declared. Treat as source-available until a license file lands.
