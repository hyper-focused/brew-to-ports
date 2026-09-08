# Brew to Ports

**Don't Panic.**

Homebrew classified every Intel Mac as [Tier 3](https://docs.brew.sh/Support-Tiers): no new bottles, no CI, lights out around September 2027. The Vogons have arrived. Homebrew's own docs point those machines at [MacPorts](https://www.macports.org). This is the towel for that trip.

It **plans** first. It writes `migrate.zsh`. It does **not** silently take anything apart. When you're happy with the plan, have dry-run it, and are feeling lucky:

```sh
./migrate.zsh --apply
```

Then go grab a coffee, or a tea if you can find one.

**Apple Silicon.** You don't need this. Homebrew is still Tier 1. Go outside. The fjords are still there.

---

## Why

Intel Homebrew is a source-build farm. Compiling `wget` on a 2018 MacBook Pro is a lifestyle, not a package manager. Ask the Gentoo crowd, if anyone survived Chromium.

MacPorts still ships Intel bottles and still targets Ventura and up. It's not the hero we wanted. It is the one that remembers hardware from when Baby Shark was new.

A manual cellar-by-cellar move would finish sometime after the Ultimate Question. So the plan is boring on purpose: inventory the cellar, match only real equivalents, install the port, uninstall the brew keg **only if** that port is actually there.

No `sudo brew`. No surprise `php.ini` deletion. No "we copied your `nginx.conf` and now you have two of them and neither works." We've already done the accidental database version upgrade. That week is not coming back.

---

## Before you start

This runs **on the Intel Mac being migrated.** Intel x86_64, macOS 13 Ventura through 26 Tahoe, Homebrew at `/usr/local`, MacPorts at `/opt/local`, Xcode Command Line Tools so `/usr/bin/python3` is 3.9.6+. Login user. No pip, no venv, never sudo the wrapper.

Backup first. Time Machine, **or** a copy of `/usr/local/{Cellar,Caskroom,Homebrew,etc,var}` plus `brew bundle dump`. `bin` and `sbin` are mostly symlinks. They are not a backup. Know where your towel (and your Cellar) is.

Optional hygiene (we will not run these for you):

```sh
brew autoremove --dry-run
brew cleanup --dry-run
```

---

## Wave 1

```sh
git clone https://github.com/hyper-focused/brew-to-ports.git
cd brew-to-ports
chmod +x brew-to-ports.zsh

./brew-to-ports.zsh
```

That writes `migrate.zsh` and `logs/zsh_path` by default. The TTY is a **summary**. The novel is `logs/scan-YYYY-MM-DD.txt`. Read both.

**Runtimes.** If you have python, php, or node on brew, it will ask `[m]igrate` `[s]kip` `[q]uit`. Default is skip if you walk away — brew keeps them. `m` moves that family to MacPorts. If some children have no equivalent, it asks you to type `yes` (they get uninstalled and not replaced). `q` writes **nothing** and exits. That is the panic button.

**Dry-run prompt.** After the scan: `Dry-run migrate.zsh now? [Y/n]`. Enter is yes. Still a dry-run. Don't Panic. It prints `DRY-RUN:` lines and installs nothing. Say `n` if you want to read the log first; run `./migrate.zsh` later yourself.

When it looks right:

```sh
./migrate.zsh --apply
```

Sudo is for **port** only. The TTY is a progress bar plus the current package. Brew/port spam lives in `logs/report-YYYY-MM-DD.txt`. Halt dumps the last 40 lines of that log. Success prints `done.` There is no undo. That is why the dry-run exists.

**`--config-ack`.** php.ini (and similar HOLD kegs) are not uninstalled just because php moved. The dry-run will say HOLD. To actually remove brew's `php@8.4` after you have checked the MacPorts file:

```sh
./migrate.zsh --apply --config-ack php@8.4
```

Without that flag, the port is installed and the brew keg stays. Repeat the flag per HOLD formula.

Open a **new terminal.** This session still hashes brew. Paste the `sudo port select --set …` lines from the summary (php / python / pip). Then load `logs/zsh_path` in `~/.zprofile` **after** `/etc/zprofile` — we do not edit rc for you. Scan again:

```sh
./brew-to-ports.zsh
```

Repeat until migrate=0, or leftover brew is a lifestyle.

---

## Wave 2 — older, same major

Some ports are a notch older than brew but still the same major (tesseract 5.4 vs 5.5). Wave 1 leaves those on brew. If that does not scare you:

```sh
./brew-to-ports.zsh --allow-older-same-major
./migrate.zsh --apply
```

That is **not** ImageMagick 7 vs MacPorts 6, or HandBrake 1.x vs 0.10. There is no `--allow-older-major`. On purpose.

---

## What you should expect to still have on brew

- **Casks** (iTerm, fonts, …) — default keep
- **gcc / llvm / clang** — we will not surprise-swap your compiler
- **Ruby** — never in the cutover prompt
- **httpd / nginx / unbound** — services; we will not copy `nginx.conf` or TLS keys
- **MySQL / MariaDB / Percona** — radioactive. Server, `mysql-client`, connectors. No migrate, no overlay, no uninstall
- Unmatched kegs, pyenv, and leftover deps of the stuff you kept

`--try-source` can attempt overlay Portfiles for **source-built** unmatched kegs (not bottled ones, not cmake/rust, never mysql). Most people never need it.

---

## How we keep it from setting the cellar on fire

- **Plan ≠ apply.** Scan is read-only. `migrate.zsh` is dry-run until `--apply`.
- **Never `sudo brew`.** Login user. We `sudo` only `port`.
- **Uninstall follows install.** Skip-on-conflict leaves the brew keg.
- **We do not copy configs.** Custom brew files are listed. HOLD needs `--config-ack`.
- **Apple binaries only** while we run (`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, aliases off), so `alias ls=gls` cannot ghost us after we uninstall coreutils. We do not edit `/etc/zprofile`.

We will not catch every GNU `g-` prefix or keg you installed in 2014 and forgot. Read the log.

Fake PortIndex, custom prefixes, `--no-script`, non-TTY flags: [DETAILS.md](DETAILS.md). Scoreboard: [STATUS.md](STATUS.md). Matching PRs: [CONTRIBUTING.md](CONTRIBUTING.md).

---

[MIT](LICENSE). Mostly harmless.

Homebrew and MacPorts are separate projects. We are the bit in between that tries not to set your cellar on fire.

*Share and Enjoy.*
