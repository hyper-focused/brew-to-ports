# Contributing

PRs welcome. Keep the matcher conservative: a false migrate is worse than a keep.

## Where to put a mapping

1. **Systematic pattern** (many names, same rule) → `src/brew_to_ports/match.py` stem / `@version` / homepage family. Examples: `php@8.5` → `php85`, `python-foo` → `py314-foo`, `node@22` → `nodejs22`, `ruby-foo` → `rb33-foo`, `perl-foo` → `p5.34-foo`, `r-ggplot2` → `r-ggplot2`.
2. **One-off, no pattern** → `data/aliases.json`. Examples: `pkgconf` → `pkgconfig`, `gnu-sed` → `gsed`.
3. **Dangerous class** → `data/exceptions.json` (runtime, toolchain, **service**, stateful). Do not special-case a single formula in classify.

Do **not** add `port search` / substring matching. `python-yq` is not `py-pyqt4`. Unique homepage requires a shared non-generic stem (or an alias); `xquartz` is not `quartz-wm`. `gcc` is not `riscv32-none-elf-gcc`.

Do **not** put cellar-specific aliases in `aliases.json` (e.g. `node` → `nodejs22`). Use `node@N` → `nodejsN`.

## Tests

Every matcher change needs a fixture case in `tests/test_match.py` (including a negative: the thing it must not map to).

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

No live `brew` / `port` required for CI.

## New behavior (where it lives)

- Runtime grouping → `family.py`. Cutover prompts/flags → `cutover.py` (writes `CutoverChoice` only). Eligibility: python, php, node (not ruby).
- Overlay Portfiles → `source_try.py`. Plan applies them; `migrate.zsh` uses `port -D`. Failed install must not uninstall brew.
- `STATUS_DROP` is uninstall-without-port, not a fake migrate. `--i-acked-drop` is a **planner** flag, not `migrate.zsh`.
- Unique homepage / family pick: shared non-generic stem, or `aliases.json`.

## Scope

Intel x86_64, macOS 13 Ventura through 26 Tahoe (`sw_vers` 26 is valid; do not treat majors >15 as invalid). Generated `migrate.zsh` must stay dry-run unless `--apply`. Never `sudo brew`; sudo only `port`. Do not write user rc files or `/etc/zprofile`. Do not copy config/state. Migrator process PATH is Apple `/usr/bin:/bin:/usr/sbin:/sbin` only; call brew/port by absolute path; no bare `cat`/`ls`/`sed`. Tests may use `bat`/starship as **fixtures** (a fake user's rc). Product code must not call those. Scoreboard: [STATUS.md](STATUS.md). Operator flags and waves: [DETAILS.md](DETAILS.md).
