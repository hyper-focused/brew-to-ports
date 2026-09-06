# Contributing

PRs welcome. Keep the matcher conservative: a false migrate is worse than a keep.

## Where to put a mapping

1. **Systematic pattern** (many names, same rule) → `src/brew_to_ports/match.py` stem / `@version` / homepage family. Examples: `php@8.5` → `php85`, `python-foo` → `py314-foo`, `node@22` → `nodejs22`, `ruby-foo` → `rb33-foo`, `perl-foo` → `p5.34-foo`, `r-ggplot2` → `r-ggplot2`.
2. **One-off, no pattern** → `data/aliases.json`. Examples: `pkgconf` → `pkgconfig`, `gnu-sed` → `gsed`.
3. **Dangerous class** → `data/exceptions.json` (runtime, toolchain, stateful). Do not special-case a single formula in classify.

Do **not** add `port search` / substring matching. `python-yq` is not `py-pyqt4`.

Do **not** put cellar-specific aliases in `aliases.json` (e.g. `node` → `nodejs22`). Use `node@N` → `nodejsN`.

## Tests

Every matcher change needs a fixture case in `tests/test_match.py` (including a negative: the thing it must not map to).

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

No live `brew` / `port` required for CI.

## Scope

Intel x86_64, macOS 13 Ventura through 26 Tahoe (`sw_vers` 26 is valid; do not treat majors >15 as invalid). Generated `migrate.sh` must stay dry-run unless `--apply`. Never `sudo brew`; sudo only `port`. Do not write user rc files. Do not copy config/state.
