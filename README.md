# Brew to Ports 

**Don't Panic.** 

So there we were, happily updating runtimes and libraries using brew, when suddenly some text appeared on the screen: Homebrew has classified every Intel Mac as [Tier 3](https://docs.brew.sh/Support-Tiers): no new bottles, no CI, and the lights go out around September 2027. The Vogons have arrived. This app is the towel for that trip.

Homebrew's own docs point those machines at [MacPorts](https://www.macports.org), but migrating dozens or hundreds of packages is... a commitment. 

The app initially **plans** a Homebrew → MacPorts move, and generates a migrate.zsh script to execute the change. It does **not** silently take any destructive action. Once you're happy with the plan, have done a dry-run, and are feeling lucky, run the generated script as a normal user `migrate.zsh --apply`. Then, go grab a coffee, or a tea if you can find one.

**Apple Silicon** You don't need this. Homebrew is still Tier 1. Go outside, touch some grass, and enjoy your Mac manufactured **this** decade. Maybe go check out some Norwegian fjords.

---

## Why this exists

Intel Homebrew has become a source-build farm. Compiling `wget` from source on a 2018 MacBook Pro is a lifestyle, not a package manager. Just ask the Gentoo guys, if you can find any who didn't die of old age waiting for Full Chromium to compile. 

MacPorts still ships Intel packages and supports the current tree (Ventura and up). It's not the hero we wanted, but it's the one that understands some people still use hardware that was around when Baby Shark was the latest hit.

However, it became clear pretty quickly we would learn the ultimate question before finishing a manual migration. So we came up with a plan: inventory the cellar, match what has a real equivalent, install those ports, then uninstall the brew kegs **only if** the port is actually there. Make sure the script doesn't do anything stupid - no `sudo brew`. No surprise `php.ini` deletion. No "we copied your nginx.conf and now you have two of them and neither works."

If that sounds like the opposite of a rewrite-in-place, good. That's the idea. We've lived through an accidental db version upgrade. That's a week of our lives we'll never get back.

---

## Too lazy or impatient to read? Here you go. Run the script, follow the prompts, and you're probably good to go. 

So, you're the kind of person who tears the tags off of mattresses, eh? Backup first. Time Machine, **or** a copy of `/usr/local/{Cellar,Caskroom,Homebrew,etc,var}` plus `brew bundle dump`. `bin`/`sbin` are mostly symlinks. They are not a backup. Hitchhiker's Guide rule: know where your towel (and your Cellar) is.


```sh
# install
git clone https://github.com/hyper-focused/brew-to-ports.git
cd brew-to-ports
chmod +x brew-to-ports.zsh

# optional hygiene (probably a good idea, the script intentionally doesn't run them)
brew autoremove --dry-run
brew cleanup --dry-run

# as your login user — never sudo
./brew-to-ports.zsh

# read the summary. then the log. then the dry-run. then:
./migrate.zsh --apply
# if the dry-run HOLDs php.ini (or similar):
# ./migrate.zsh --apply --config-ack php@8.4

# after it finishes: NEW TERMINAL

# then copy-paste the `sudo port select --set …` lines from the summary

# If you aren't concerned with minor version differences, do a second run:
./brew-to-ports.zsh --allow-older-same-major 
./migrate.zsh --apply
```

No pip needed. No venv. Uses Apple `/usr/bin/python3`, `/bin/zsh`, and other utilities / runtimes only.

---

## Requirements - make sure you have these or you might break stuff. 

Homebrew
MacPorts
Xcode 
A good sense of humor

This runs **on the Intel Mac being migrated**.

| Must be | Or we refuse |
|---|---|
| Intel **x86_64** | Apple Silicon. See fjords, above. |
| macOS **13 Ventura through 26 Tahoe** | Monterey and older. MacPorts' *current tree* is Ventura+. |
| Apple `/bin/zsh` | The wrapper re-execs it so brew zsh can die mid-apply without taking us with it |
| Xcode CLT; `/usr/bin/python3` **3.9.6+** | That's what Ventura+ CLT ships. No brew Python, no python.org, no venv. `--allow-brew-python` exists as a fire exit, not a plan. |
| Homebrew at `/usr/local` | Intel prefix. `brew info --json=v2 --installed` has to work |
| MacPorts at `/opt/local` for `--apply` | Optional to *plan* (`--portindex FILE`). Required if you actually want to move anything |

**Tahoe:** four Intel models are still on Apple's list ([support.apple.com/122867](https://support.apple.com/en-us/122867)) — 16" MBP 2019, 13" MBP 2020 (four TB3), 27" iMac 2020, Mac Pro 2019. `sw_vers` says **26**, not 16. 

Ventura is the floor because CLT Python is 3.9 from 13 on (Monterey was 3.8.9) and [MacPorts' current tree](https://www.macports.org) targets 13+. Tahoe is the last Intel macOS. 27+ is Apple Silicon and already fails the Intel gate. If you remember streaming 'Baby Shark' on this machine when the song was new, you're probably good.

This is for people who already live in a terminal. We will not catch every GNU `g-` prefix, homemade rc graph, or keg you installed in 2014 and forgot. Read the log. That's what it's for.

---

## How a wave works

Think of this as one trip through the guide, not a rewrite of the planet.

1. **Scan** (`./brew-to-ports.zsh`) — read-only. Matches cellar → PortIndex. Writes `migrate.zsh`. Offers a dry-run.
2. **Dry-run** (`./migrate.zsh`, no `--apply`) — prints what it *would* run. Installs nothing. This is the "are you feeling lucky" checkpoint.
3. **Apply** (`./migrate.zsh --apply`) — the only thing that mutates packages. `port install`, then `brew uninstall` if the port is actually there, then `brew autoremove`. If a keg is HOLD (php.ini), apply again with `--config-ack php@8.4`.
4. **New terminal.** Then `port select`. Then scan again.

One `migrate.zsh` is a snapshot of **this** cellar. After apply, the cellar changed. Scan again. Repeat until migrate=0, or until you decide leftover brew is a lifestyle choice.

The TTY scan is a **summary** — counts, migrate/drop/exception, requested keep, `port select` lines. The novel goes in `logs/scan-YYYY-MM-DD.txt`. `--apply` hides port/brew spam in `logs/report-YYYY-MM-DD.txt` and keeps a progress bar + current package on screen. If it halts, you get the last 40 log lines. If it succeeds, it just… stops. That's the good ending.

---

## We use Apple's binaries. On purpose.

The planner and `migrate.zsh` pin:

```
PATH=/usr/bin:/bin:/usr/sbin:/sbin
```

Aliases off. `hash -r`. `brew` is `/usr/local/bin/brew`. `port` is `/opt/local/bin/port`. `ls`/`head`/`sed`/`date` are Apple. The done banner is zsh `print`, not `cat`, because your rc may still say `alias cat=bat` after we uninstall bat. `/bin/cat` would have been fine. We still don't want the argument.

**Why:** brew users who wanted Linux put gnubin first and aliased `ls` to `gls`. Then we uninstall coreutils. If our script still said `ls`, it would call a ghost. `/bin/ls` does not ghost.

This is **only** for our process. Your login tab is a child-process problem we cannot fix from in here. `/etc/zprofile` runs `path_helper` on login and prepends `/etc/paths` (often `/usr/local/bin` first). We do **not** edit `/etc/zprofile`. Load `logs/zsh_path` again in `~/.zprofile` **after** that. New terminal. Don't Panic.

Generated `logs/zsh_path` order: your `$HOME` bins, MacPorts, Apple system dirs (`/usr/bin` `/bin` `/usr/sbin` `/sbin` + Cryptexes/Library/Apple if present), leftovers, `/usr/local/bin` **last**.

---

## What we will not migrate (or it's a bad idea)

Some of this is "not yet." Some of this is "we already know how that story ends."

| Leave it | Why |
|---|---|
| **Apple Silicon** | Wrong decade. Go outside. |
| **Casks** (iTerm, fonts, …) | Default keep. Aqua cutover is a later problem |
| **Ruby** | Never in the cutover prompt. Homebrew's own engine is portable-ruby; the `ruby` formula is still in the leftover brew graph. MacPorts `ruby @1.8.7` is not a joke you want to be in |
| **gcc / llvm / clang** | Toolchain exception. Dual-stack. Nobody wants a surprise compiler swap mid-migrate |
| **httpd, nginx, unbound, …** | **Services.** We will not copy `nginx.conf` or TLS keys. You do that, on purpose, with a backup |
| **MySQL / MariaDB / Percona** | Radioactive. Server, `mysql-client`, connectors, the lot. No migrate, no overlay, no uninstall. We've done the accidental db version upgrade. Not again |
| **ImageMagick 7 vs ports 6, HandBrake 1.x vs 0.10, cmake 4 vs 3** | Older **major**. There is no `--allow-older-major`. For good reason. |
| **Bottled unmatched kegs** | Stay on brew. `--try-source` is only for **source-built** unmatched (github noarch, Go, autoreconf). |
| **pyenv, pydantic, bgpq3, …** | No equivalent above version threshold. Keep |
| **`python-yq` vs `yq`** | We do not `port search` and pray. If we have a pattern transformation, great. A false migrate is worse than a keep |

**Runtimes we *will* offer:** python, php, node (`[m]/[s]/[q]`). Unmatched children of a migrate need `yes` / `--i-acked-drop`. MacPorts `nodejsN` majors **conflict** — only the newest is `port install`ed. python313+python314 can both be active. php is `php84`/`php85` binaries until you `port select`.

**HOLD / config:** Config files you don't want broken. For example, php.ini is stateful. Even after php cutover, brew uninstall of `php@8.4` needs `--config-ack php@8.4` on **apply**. Custom brew confs are **listed** (vendor baseline vs live). Stock bottle copies are omitted. Nothing is copied.

**Don't sudo the wrapper.** `sudo brew` is how you get a root-owned cellar. We `sudo` **only** `port`. One `sudo -v`, keepalive, then `sudo -n`. Casks that write `/opt/X11` or `/Applications` make *brew* invoke sudo as you; we still never `sudo brew`.

---

## Commands and flags

If the copy-paste block was enough, you can stop here. This is the rest of the remote.

### `./brew-to-ports.zsh` (planner — read-only)

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

TTY cutover: `[m]igrate` `[s]kip` `[q]uit`, then `yes` if anything would be deleted. `q` writes **nothing**. That's the panic button working as designed.

### `./migrate.zsh` (the only mutator)

Default is **dry-run**. Prints `DRY-RUN:` lines. Installs nothing.

| Flag | What it does |
|---|---|
| `--apply` | Actually `port install` / `brew uninstall`. Needs sudo for **port** only |
| `--config-ack FORMULA` | Uninstall a HOLD keg (config you don't want us to surprise-delete). Repeatable. Example: `--config-ack php@8.4` |
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

Restart-safe: skip if the port is already installed; skip brew uninstall if the mapped port isn't. Re-run `--apply` after a compile failure. That's the whole recovery plan. There is no "undo" button, which is why the dry-run exists.

---

## Files it writes (working directory, not `$HOME`)

We used to dump PATH advice in `$HOME`. That was cute until it wasn't. Everything now lands in the repo's cwd.

| Path | What |
|---|---|
| `migrate.zsh` | Apply script. Dry-run until `--apply` |
| `logs/scan-YYYY-MM-DD.txt` | Full scan (reasons, keep-set, PATH rewrites) |
| `logs/report-YYYY-MM-DD.txt` | `--apply` port/brew log |
| `logs/zsh_path` | PATH data, one directory per line. **You** source it. We don't edit rc |
| `logs/overlay/` | try-source Portfiles |

Gitignores `logs/` and `migrate.zsh`. Don't commit your cellar. The universe has enough of those.

---

## Layout

```
brew-to-ports.zsh      # zsh wrapper (Apple zsh + /usr/bin/python3)
src/brew_to_ports/     # stdlib Python
data/aliases.json      # one-off brew → port names (not your shell aliases)
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
