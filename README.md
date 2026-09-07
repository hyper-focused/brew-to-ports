# brew-to-ports

**Don't Panic.** Homebrew has classified every Intel Mac as [Tier 3](https://docs.brew.sh/Support-Tiers): no new bottles, no CI, and the lights go out around September 2027. Homebrew's own docs point those machines at [MacPorts](https://www.macports.org). This is the towel for that trip.

It **plans** a Homebrew → MacPorts move. It does **not** silently rewrite the machine. The only thing that mutates packages is `migrate.zsh --apply`, which you run on purpose, after a dry-run, after a backup, preferably after coffee.

**Apple Silicon is a hard fail.** Homebrew is still Tier 1 there. You don't need this. Go outside.

---

## Why this exists

Intel Homebrew became a source-build farm. Compiling `wget` from source on a 2019 MacBook Pro is a lifestyle, not a package manager. MacPorts still ships Intel bottles (mostly) and still targets the current tree (Ventura+).

We wanted one conservative pass: inventory the cellar, match what has a real equivalent, install those ports, then uninstall the brew kegs **only if** the port is actually there. Dual-stack until you say otherwise. No `sudo brew`. No surprise `php.ini` deletion. No "we copied your nginx.conf and now you have two of them and neither works."

If that sounds like the opposite of a rewrite-in-place, good. That's the product.

---

## I'm too lazy to read — copy/paste this now

Backup first. Time Machine, **or** a copy of `/usr/local/{Cellar,Caskroom,Homebrew,etc,var}` plus `brew bundle dump`. `bin`/`sbin` are mostly symlinks. They are not a backup. Hitchhiker's Guide rule: know where your towel (and your Cellar) is.

```sh
git clone https://github.com/hyper-focused/brew-to-ports.git
cd brew-to-ports
chmod +x brew-to-ports

# optional hygiene (you run these, not us)
brew autoremove --dry-run
brew cleanup --dry-run

# as your login user — never sudo ./brew-to-ports
./brew-to-ports --allow-older-same-major
# TTY: python/php/node [m]igrate [s]kip [q]uit
# then: Dry-run migrate.zsh now? [Y/n]   ← Enter is yes, still a dry-run

# read the summary. then the log. then the dry-run. then:
./migrate.zsh --apply --i-acked-config php@8.4   # only if php.ini HOLD applies

# after it finishes: NEW TERMINAL
# then copy-paste the `sudo port select --set …` lines from the summary
./brew-to-ports --allow-older-same-major         # wave 2
```

No pip. No venv. Apple `/usr/bin/python3` and `/bin/zsh` only.

---

## Hard requirements (the universe, not our opinion)

This runs **on the Intel Mac being migrated**. Not a Linux CI box pretending. Not your M4.

| Must be | Or we refuse |
|---|---|
| Intel **x86_64** | Apple Silicon (`uname -m` is not a negotiation) |
| macOS **13 Ventura through 26 Tahoe** | Monterey and older. MacPorts' *current tree* is Ventura+. We don't invent a second OS class. |
| Apple `/bin/zsh` | The wrapper re-execs it so brew zsh can die mid-apply |
| Xcode CLT; `/usr/bin/python3` **3.9.6+** | That's what Ventura+ CLT ships. No brew Python, no python.org, no venv. `--allow-brew-python` exists as a fire exit, not a plan. |
| Homebrew at `/usr/local` | Intel prefix. `brew info --json=v2 --installed` must work |
| MacPorts at `/opt/local` for `--apply` | Optional to *plan* (`--portindex FILE`). Required to mutate |

**Tahoe footnote:** four Intel models still on Apple's list ([support.apple.com/122867](https://support.apple.com/en-us/122867)) — 16" MBP 2019, 13" MBP 2020 (four TB3), 27" iMac 2020, Mac Pro 2019. `sw_vers` says **26**, not 16. MacPorts' x86_64-26 bottles are incomplete; more ports compile from source. The planner does not care. Your fans will.

Ventura is the floor because CLT Python is 3.9 from 13 on (Monterey was 3.8.9) and [MacPorts' current tree](https://www.macports.org) targets 13+. Tahoe is the last Intel macOS. 27+ is Apple Silicon and already fails the Intel gate. No extra Tahoe code path.

Audience: people who already live in a terminal. We will not catch every GNU `g-` prefix, homemade rc graph, or keg you installed in 2014 and forgot. Read the log.

---

## How a wave works

1. **Scan** (`./brew-to-ports`) — read-only. Matches cellar → PortIndex. Writes `migrate.zsh`. Offers a dry-run.
2. **Dry-run** (`./migrate.zsh`, no `--apply`) — prints what it *would* run. Installs nothing.
3. **Apply** (`./migrate.zsh --apply`) — the only mutator. `port install`, then `brew uninstall` if the port is actually there, then `brew autoremove`.
4. **New terminal.** Then `port select`. Then scan again.

One `migrate.zsh` is a snapshot of **this** cellar. Keep-set is "who still has a brew reason to live." After apply, the cellar changed. Scan again. Repeat until migrate=0.

TTY scan is a **summary** (counts, migrate/drop/exception, requested keep, `port select` lines). The novel goes in `logs/scan-YYYY-MM-DD.txt`. `--apply` logs port/brew spam to `logs/report-YYYY-MM-DD.txt` and keeps a progress bar + current package on screen. On halt, last 40 log lines dump. Success does not.

---

## We use Apple's binaries. On purpose.

The planner and `migrate.zsh` pin:

```
PATH=/usr/bin:/bin:/usr/sbin:/sbin
```

Aliases off. `hash -r`. `brew` is `/usr/local/bin/brew`. `port` is `/opt/local/bin/port`. `ls`/`head`/`sed`/`date` are Apple. The done banner is zsh `print`, not `cat` (your rc may still say `alias cat=bat` after we uninstall bat).

**Why:** brew users who wanted Linux put gnubin first and aliased `ls` to `gls`. Then we uninstall coreutils. If our script still said `ls`, it would call a ghost. `/bin/ls` does not ghost.

This is **only** for our process. Your login tab is a child-process problem we cannot fix. `/etc/zprofile` runs `path_helper` on login and prepends `/etc/paths` (often `/usr/local/bin` first). We do **not** edit `/etc/zprofile`. Load `logs/zsh_path` again in `~/.zprofile` **after** that. New terminal. Don't Panic.

Generated `logs/zsh_path` order: your `$HOME` bins, MacPorts, Apple system dirs (`/usr/bin` `/bin` `/usr/sbin` `/sbin` + Cryptexes/Library/Apple if present), leftovers, `/usr/local/bin` **last**.

---

## What we will not migrate (or it's a bad idea)

| Leave it | Why |
|---|---|
| **Apple Silicon** | Wrong planet |
| **Casks** (iTerm, fonts, …) | Default keep. Aqua cutover is v2 |
| **Ruby** | Never in the cutover prompt. Homebrew's own engine is portable-ruby; the `ruby` formula is still in the leftover brew graph. MacPorts `ruby @1.8.7` is not a joke you want to be in |
| **gcc / llvm / clang** | Toolchain exception. Dual-stack |
| **httpd, nginx, mysql, unbound, …** | **Services.** We will not copy `nginx.conf`, databases, or TLS keys. You do that |
| **ImageMagick 7 vs ports 6, HandBrake 1.x vs 0.10, cmake 4 vs 3** | Older **major**. There is no `--allow-older-major`. On purpose |
| **Bottled unmatched kegs** | Stay on brew. `--try-source` is only for **source-built** unmatched (github noarch, Go, autoreconf). Not cmake/rust/PyPI/mysql |
| **pyenv, pydantic, bgpq3, …** | No equivalent above threshold. Keep |
| **`python-yq` vs `yq`** | We do not `port search` and pray. False migrate is worse than a keep |

**Runtimes we *will* offer:** python, php, node (`[m]/[s]/[q]`). Unmatched children of a migrate need `yes` / `--i-acked-drop`. MacPorts `nodejsN` majors **conflict** — only the newest is `port install`ed. python313+python314 can both be active. php is `php84`/`php85` binaries until you `port select`.

**HOLD / config:** php.ini is stateful. Even after php cutover, brew uninstall of `php@8.4` needs `--i-acked-config php@8.4` on **apply**. Custom brew confs are **listed** (vendor baseline vs live). Stock bottle copies are omitted. Nothing is copied.

**Don't sudo the wrapper.** `sudo brew` is how you get a root-owned cellar. We `sudo` **only** `port`. One `sudo -v`, keepalive, then `sudo -n`. Casks that write `/opt/X11` or `/Applications` make *brew* invoke sudo as you; we still never `sudo brew`.

---

## Commands and flags

### `./brew-to-ports` (planner — read-only)

Default: scan, write `migrate.zsh` + `logs/zsh_path`, append `logs/scan-YYYY-MM-DD.txt`, offer dry-run on a TTY.

| Flag | What it does |
|---|---|
| `--no-script` | Scan log only. No `migrate.zsh`, no dry-run offer |
| `--script FILE` | Write the apply script somewhere else (default `migrate.zsh`) |
| `--report FILE` | Full dump path (default `logs/scan-YYYY-MM-DD.txt`) |
| `--path-file` / `--path-file FILE` | PATH data file (default `logs/zsh_path`) |
| `--commands` | Also print copy/paste `sudo port` / `brew uninstall` after the summary |
| `--allow-older-same-major` | Opt in to ports that are older but **same major** (tesseract 5.4 vs 5.5). Not older major |
| `--migrate-runtime FORMULA` | Non-TTY: cut over this python/php/node family (repeatable). TTY prompts instead |
| `--i-acked-drop FORMULA` | Non-TTY: ack dropping unmatched children of that runtime |
| `--try-source` / `--allow-try-source` / `--try-source DIR` | Overlay Portfiles for source-built unmatched kegs (`logs/overlay`). Bottled unmatched stay |
| `--brew-json FILE` | Fake cellar (tests / offline) |
| `--portindex FILE` | Fake PortIndex |
| `--dump` | `brew info --json=v2 --installed` to stdout, then exit |
| `--allow-brew-python` | Run the planner under Homebrew's Python. Not the supported path |
| `-h` / `--help` | The short version of this table |

TTY cutover: `[m]igrate` `[s]kip` `[q]uit`, then `yes` if anything would be deleted. `q` writes **nothing**.

### `./migrate.zsh` (the only mutator)

Default is **dry-run**. Prints `DRY-RUN:` lines. Installs nothing.

| Flag | What it does |
|---|---|
| `--apply` | Actually `port install` / `brew uninstall`. Needs sudo for **port** only |
| `--i-acked-config FORMULA` | Allow uninstall of a HOLD keg (php.ini). Example: `--i-acked-config php@8.4` |
| `-h` / `--help` | Usage |

`--apply` TTY: sudo once, progress bar + current package/`dep: zlib`, port/brew stdout in `logs/report-YYYY-MM-DD.txt`. Halt → last 40 lines. Skip-on-conflict leaves the brew keg and continues. `port -N` so MacPorts doesn't hide a `Continue?` in the pipe. Never `port -q` for installs (`-q` is mute, not logged).

After apply: **open a new terminal.** Then:

```sh
sudo port select --set php php84
sudo port select --set python python314
sudo port select --set python3 python314
sudo port select --set pip pip314
sudo port select --set pip3 pip314
```

(Exact lines are in the scan summary; newest option per group. nodejs has no `port select` — the active `nodejsN` *is* `/opt/local/bin/node`.)

Restart-safe: skip if the port is already installed; skip brew uninstall if the mapped port isn't. Re-run `--apply` after a compile failure.

---

## Files it writes (working directory, not `$HOME`)

| Path | What |
|---|---|
| `migrate.zsh` | Apply script. Dry-run until `--apply` |
| `logs/scan-YYYY-MM-DD.txt` | Full scan (reasons, keep-set, PATH rewrites) |
| `logs/report-YYYY-MM-DD.txt` | `--apply` port/brew log |
| `logs/zsh_path` | PATH data, one directory per line. **You** source it. We don't edit rc |
| `logs/overlay/` | try-source Portfiles |

Gitignores `logs/` and `migrate.zsh`. Don't commit your cellar.

---

## Layout

```
brew-to-ports          # zsh wrapper (Apple zsh + /usr/bin/python3)
src/brew_to_ports/     # stdlib Python
data/aliases.json      # one-off brew → port names (not your aliases)
data/exceptions.json   # runtime / toolchain / service / stateful
tests/                 # fixtures; CI does not need live brew
STATUS.md              # shipped / not doing / next
```

---

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

CI: Ubuntu, Python 3.9 + 3.12, installs `zsh` for `/bin/zsh -n`. Matching rules: [CONTRIBUTING.md](CONTRIBUTING.md). Scoreboard: [STATUS.md](STATUS.md).

---

## License

[MIT](LICENSE). Mostly harmless.

Homebrew and MacPorts are separate projects with their own licenses. We only shell out to `brew` / `port` and read their public indexes. We are not those projects. We are the bit in between that tries not to set your cellar on fire.

*Share and Enjoy.*
