"""Read current PATH + rc snippets; propose MacPorts-first PATH. Does not write rc files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, Tuple

from brew_to_ports.adapters.shell_env import sourced_paths
from brew_to_ports.paths import default_path_file
from brew_to_ports.models import PathAdvice, PathLine

INTEL_BREW_BIN = "/usr/local/bin"
INTEL_BREW_SBIN = "/usr/local/sbin"
ARM_BREW_BIN = "/opt/homebrew/bin"

# Apple's own dirs. /usr/local/bin is in /etc/paths on many Macs and is NOT Apple —
# path_helper putting it first is the brew-wins-login-shell trap.
APPLE_PATHS = (
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)
APPLE_PATHS_OPTIONAL = (
    "/System/Cryptexes/App/usr/bin",
    "/Library/Apple/usr/bin",
)

# Real PATH mutation — not fpath=(, not comments.
_PATH_ARRAY_RE = re.compile(r"(?m)^[ \t]*path=\(")
_EXPORT_PATH_RE = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?PATH=")
_BREW_SHELLENV_RE = re.compile(r"brew[ \t]+shellenv")
_ALIAS_BREW_RE = re.compile(
    r"""(?m)^[ \t]*alias[ \t]+\S+=.*(?:/usr/local|/opt/homebrew)"""
)
_LINKER_RE = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?(?:LDFLAGS|CPPFLAGS|PKG_CONFIG_PATH)="
)
_MACPORTS_INSTALLER_RE = re.compile(r"MacPorts Installer addition")
# `eval "$(name init …)"` / `eval "$(name hook …)"` — PATH-dependent hooks.
_EVAL_HOOK_RE = re.compile(
    r"""eval[ \t]+(?:\"\$\(|'\$\()[ \t]*(?P<cmd>[A-Za-z0-9._-]+)[ \t]+(?:init|hook)\b"""
)
_ABS_BREW_CMD_RE = re.compile(r"(?:/usr/local|/opt/homebrew)/bin/([A-Za-z0-9._+-]+)")

# Keg trees before /usr/local/bin so we don't half-rewrite /usr/local/opt/...
# gnubin exists to shadow Apple; suggest /usr/bin, not MacPorts gnubin.
_KEG_GNUBIN_RE = re.compile(
    r"/usr/local/opt/[^/]+/libexec/gnubin(?:/([^\s\"']+))?"
)
_KEG_BIN_RE = re.compile(r"/usr/local/opt/[^/]+/bin")
_KEG_SBIN_RE = re.compile(r"/usr/local/opt/[^/]+/sbin")
_KEG_LIB_RE = re.compile(r"/usr/local/opt/[^/]+/lib")
_KEG_INC_RE = re.compile(r"/usr/local/opt/[^/]+/include")
_KEG_SHARE_RE = re.compile(r"/usr/local/opt/[^/]+/share")


def suggest_path(
    current_path: str,
    rc_files: Sequence[Tuple[Path, str]] | None = None,
    brew_prefix: str = "/usr/local",
    ports_prefix: str = "/opt/local",
    path_file: Path | None = None,
    home: Path | None = None,
    migrated_cmds: Sequence[str] | None = None,
) -> PathAdvice:
    home = home or Path.home()
    entries = [_norm_entry(p) for p in current_path.split(":") if p]
    ports_bin = f"{ports_prefix}/bin"
    ports_sbin = f"{ports_prefix}/sbin"
    brew_bin = f"{brew_prefix}/bin"
    brew_sbin = f"{brew_prefix}/sbin"

    apple = _apple_paths()
    head = [ports_bin, ports_sbin]
    skip = set(head) | set(apple) | {brew_bin, brew_sbin}
    rest = [p for p in entries if p not in skip]
    for brew_item in (brew_bin, brew_sbin):
        if brew_item in entries or Path(brew_item).exists():
            rest.append(brew_item)

    suggested = ":".join(head + apple + rest)
    analysis = _analyze_rc(rc_files or [])

    notes: List[str] = []
    helper = _path_helper_note()
    if helper:
        notes.append(helper)
        analysis["extra_writers"].append("/etc/zprofile: path_helper (login shells; prepends /etc/paths)")
    if analysis["path_owners"]:
        notes.append(f"owner: {', '.join(analysis['path_owners'])} ({analysis['idiom'] or 'unknown'})")
    if analysis["alias_hits"]:
        notes.append("aliases still on brew prefixes: " + ", ".join(analysis["alias_hits"]))
    if analysis["linker_hits"]:
        notes.append("LDFLAGS/CPPFLAGS/PKG_CONFIG_PATH: " + ", ".join(analysis["linker_hits"]))
    if ARM_BREW_BIN in entries:
        notes.append("PATH contains /opt/homebrew/bin on Intel")

    array_entries: List[str] = []
    if analysis["idiom"] == "zsh-array":
        for path, text in rc_files or []:
            if str(path) in analysis["path_owners"]:
                array_entries = _rewrite_zsh_array(
                    text, ports_bin, ports_sbin, brew_bin, brew_sbin, apple
                )
                break
    if not array_entries:
        array_entries = [_zsh_path_entry(p) for p in suggested.split(":") if p]

    dest = path_file or default_path_file(home)
    abs_entries = [
        e
        for e in (_expand_entry(x, home=home) for x in array_entries)
        if _keep_path_entry(e)
    ]
    path_file_contents = _path_file_contents(abs_entries)
    comment_out = _comment_out_lines(rc_files or [], analysis["path_owners"], home=home)
    load_zsh, load_bash = _load_snippets(dest, home=home)
    rewrites = _prefix_rewrites(rc_files or [], ports_prefix, migrated_cmds=migrated_cmds)

    return PathAdvice(
        current_path=current_path,
        suggested=suggested,
        rc_hits=analysis["rc_hits"],
        collisions=[],
        notes=notes,
        path_owners=analysis["path_owners"],
        idiom=analysis["idiom"],
        extra_writers=analysis["extra_writers"],
        alias_hits=analysis["alias_hits"],
        linker_hits=analysis["linker_hits"],
        array_entries=array_entries,
        path_file=str(dest),
        path_file_contents=path_file_contents,
        comment_out=comment_out,
        load_zsh=load_zsh,
        load_bash=load_bash,
        rewrites=rewrites,
    )


def snippet(advice: PathAdvice) -> str:
    """Comment listed writers; load the generated path file as an array."""
    dest = advice.path_file or str(default_path_file())
    lines = [
        f"# PATH file: {dest}",
        "# Comment:",
    ]
    if advice.comment_out:
        current = None
        for item in advice.comment_out:
            if item.path != current:
                lines.append(f"#   {item.path}")
                current = item.path
            lines.append(f"#     {item.lineno}: {item.text}")
    else:
        lines.append("#   (none)")
    lines.append("# zsh — .zshenv and .zprofile (after path_helper):")
    for raw in (advice.load_zsh or "").splitlines():
        lines.append(raw)
    lines.append("# bash — .profile / .bash_profile:")
    for raw in (advice.load_bash or "").splitlines():
        lines.append(raw)
    if advice.rewrites:
        lines.append("# prefix swap (best-effort; GNU names/kegs/variants will still surprise you):")
        current = None
        for item in advice.rewrites:
            if item.path != current:
                lines.append(f"#   {item.path}")
                current = item.path
            lines.append(f"#     {item.lineno}: {item.text}")
            if item.suggested and item.suggested != item.text:
                lines.append(item.suggested)
    return "\n".join(lines) + "\n"


def _analyze_rc(rc_files: Sequence[Tuple[Path, str]]) -> dict:
    path_owners: List[str] = []
    extra_writers: List[str] = []
    alias_hits: List[str] = []
    linker_hits: List[str] = []
    rc_hits: List[str] = []
    owner_idioms = set()
    names = {p.name for p, _ in rc_files}
    path_helper = ".zshenv" in names and ".zprofile" in names
    dedicated = {".zsh_path", ".path", ".env"}

    for path, text in rc_files:
        has_array = bool(_PATH_ARRAY_RE.search(text))
        has_export = bool(_EXPORT_PATH_RE.search(text))
        has_shellenv = bool(_BREW_SHELLENV_RE.search(text))
        installer = bool(_MACPORTS_INSTALLER_RE.search(text))
        aliases = _ALIAS_BREW_RE.findall(text)
        linker = bool(_LINKER_RE.search(text)) and (
            "/usr/local" in text or "/opt/homebrew" in text
        )

        if has_array:
            path_owners.append(str(path))
            owner_idioms.add("zsh-array")
        elif has_export and path.name in dedicated and not installer:
            path_owners.append(str(path))
            owner_idioms.add("export-path")
        elif has_export and installer:
            extra_writers.append(
                f"{path}: MacPorts installer prepended export PATH= (duplicate writer; prefer the path owner file)"
            )
        elif has_export:
            extra_writers.append(f"{path}: export PATH=")

        if has_shellenv:
            extra_writers.append(f"{path}: eval brew shellenv (rewrites PATH on login)")
        if aliases:
            alias_hits.append(f"{path} ({len(aliases)} alias(es))")
        if linker:
            linker_hits.append(str(path))
        if has_array or has_export or has_shellenv or aliases or linker or installer:
            rc_hits.append(str(path))

    if "zsh-array" in owner_idioms:
        idiom = "zsh-array"
    elif owner_idioms == {"export-path"}:
        idiom = "export-path"
    elif owner_idioms:
        idiom = "mixed"
    else:
        idiom = "unknown"

    return {
        "path_owners": path_owners,
        "extra_writers": extra_writers,
        "alias_hits": alias_hits,
        "linker_hits": linker_hits,
        "rc_hits": rc_hits,
        "idiom": idiom,
        "path_helper": path_helper,
    }


_PATH_ARRAY_BODY_RE = re.compile(r"(?ms)^[ \t]*path=\((.*?)\)")


def _apple_paths() -> List[str]:
    out = list(APPLE_PATHS)
    for item in APPLE_PATHS_OPTIONAL:
        if Path(item).is_dir():
            out.append(item)
    return out


def _path_helper_note() -> str:
    zprofile = Path("/etc/zprofile")
    try:
        text = zprofile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if "path_helper" not in text:
        return ""
    return (
        "/etc/zprofile runs path_helper on login shells and prepends /etc/paths "
        "(/usr/local/bin is first on many Macs). Re-load logs/zsh_path in .zprofile "
        "AFTER that. Do not edit /etc/zprofile."
    )


def _rewrite_zsh_array(
    text: str,
    ports_bin: str,
    ports_sbin: str,
    brew_bin: str,
    brew_sbin: str,
    apple: Sequence[str],
) -> List[str]:
    """User bins, MacPorts, Apple system dirs, leftovers, brew last. No $path — file is complete."""
    match = _PATH_ARRAY_BODY_RE.search(text)
    if not match:
        return [ports_bin, ports_sbin, *apple]
    cleaned: List[str] = []
    skip = {
        ports_bin,
        ports_sbin,
        brew_bin,
        brew_sbin,
        *(p.rstrip("/") for p in apple),
    }
    for line in match.group(1).splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry or entry in ("$path", "path"):
            continue
        norm = _norm_entry(entry) if entry.startswith("/") else entry
        if norm in skip or entry.rstrip("/") in skip:
            continue
        cleaned.append(norm if entry.startswith("/") else entry)
    insert_at = 0
    for i, entry in enumerate(cleaned):
        if entry.startswith("$HOME") or entry.startswith("~"):
            insert_at = i + 1
            continue
        break
    user = cleaned[:insert_at]
    middle = cleaned[insert_at:]
    brew = []
    if Path(brew_bin).exists() or brew_bin in text:
        brew.append(brew_bin)
    if Path(brew_sbin).exists() or brew_sbin in text:
        brew.append(brew_sbin)
    return user + [ports_bin, ports_sbin] + list(apple) + middle + brew


def _keep_path_entry(entry: str) -> bool:
    """Keep reserved user dirs even if missing. Drop vanished brew keg trees."""
    if "/usr/local/opt/" in entry or "/opt/homebrew/opt/" in entry:
        return Path(entry).is_dir()
    return True


def _path_file_contents(abs_entries: List[str]) -> str:
    lines = [
        "# brew-to-ports PATH — one directory per line; load via scan report one-liners",
        "# Login shells: /etc/zprofile path_helper prepends /etc/paths first.",
        "# Load this file again in ~/.zprofile after that so MacPorts stays ahead of brew.",
        "",
    ]
    seen = set()
    for entry in abs_entries:
        if not entry or entry in seen:
            continue
        seen.add(entry)
        lines.append(entry)
    return "\n".join(lines) + "\n"


def _load_snippets(dest: Path, home: Path | None = None) -> tuple:
    loc = str(dest)
    home_s = str(home or Path.home())
    if loc.startswith(home_s + "/"):
        display = "$HOME/" + loc[len(home_s) + 1 :]
    else:
        display = loc
    zsh = (
        'path=( ${(f)"$(< ' + display + ')"} $path )\n'
        "typeset -gU path\n"
        "path=( ${^path}(N-/) )\n"
    )
    bash = (
        'PATH="$(grep -v \'^[[:space:]]*#\' '
        + display
        + ' | grep -v \'^[[:space:]]*$\' | paste -sd: -)${PATH:+:$PATH}"\n'
        "export PATH\n"
    )
    return zsh, bash


def _comment_out_lines(
    rc_files: Sequence[Tuple[Path, str]],
    owners: List[str],
    home: Path | None = None,
) -> List[PathLine]:
    owner_resolved = set()
    for raw in owners:
        try:
            owner_resolved.add(Path(raw).expanduser().resolve())
        except OSError:
            continue
    dedicated = {".zsh_path", ".path", ".env", ".zsh_path.brew-to-ports", "zsh_path"}
    home = home or Path.home()
    found: List[PathLine] = []
    for path, text in rc_files:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path
        if resolved in owner_resolved:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            kind = ""
            replace = False
            if _BREW_SHELLENV_RE.search(line):
                kind = "shellenv"
            elif _EXPORT_PATH_RE.match(line) or _EXPORT_PATH_RE.search(line):
                kind = "export"
            else:
                sourced = sourced_paths(line + "\n", from_file=path, home=home)
                for src in sourced:
                    try:
                        src_res = src.resolve()
                    except OSError:
                        src_res = src
                    if src_res in owner_resolved or src.name in dedicated:
                        kind = "source_owner"
                        replace = True
                        break
            if kind:
                found.append(
                    PathLine(
                        path=str(path),
                        lineno=lineno,
                        text=stripped,
                        kind=kind,
                        replace_with_load=replace,
                    )
                )
    return found


def _apple_gnubin(match: re.Match) -> str:
    rest = match.group(1) or ""
    cmd = rest.rsplit("/", 1)[-1] if rest else ""
    return f"/usr/bin/{cmd}" if cmd else "/usr/bin"


def rewrite_brew_prefix(text: str, ports_prefix: str = "/opt/local") -> str:
    """Map brew prefixes. gnubin aliases → Apple /usr/bin, not ports gnubin."""
    s = text
    s = _KEG_GNUBIN_RE.sub(_apple_gnubin, s)
    s = _KEG_BIN_RE.sub(f"{ports_prefix}/bin", s)
    s = _KEG_SBIN_RE.sub(f"{ports_prefix}/sbin", s)
    s = _KEG_LIB_RE.sub(f"{ports_prefix}/lib", s)
    s = _KEG_INC_RE.sub(f"{ports_prefix}/include", s)
    s = _KEG_SHARE_RE.sub(f"{ports_prefix}/share", s)
    s = s.replace("/usr/local/bin", f"{ports_prefix}/bin")
    s = s.replace("/usr/local/sbin", f"{ports_prefix}/sbin")
    s = s.replace("/opt/homebrew/bin", f"{ports_prefix}/bin")
    s = s.replace("/opt/homebrew/sbin", f"{ports_prefix}/sbin")
    return s


def _migrated_names(migrated_cmds: Sequence[str] | None) -> set:
    names = set()
    for raw in migrated_cmds or []:
        n = raw.strip().lower()
        if not n:
            continue
        names.add(n)
        names.add(n.split("@")[0])
    return names


def _prefix_rewrites(
    rc_files: Sequence[Tuple[Path, str]],
    ports_prefix: str,
    migrated_cmds: Sequence[str] | None = None,
) -> List[PathLine]:
    migrated = _migrated_names(migrated_cmds)
    found: List[PathLine] = []
    for path, text in rc_files:
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _EXPORT_PATH_RE.search(line) or _BREW_SHELLENV_RE.search(line):
                continue
            kind = ""
            suggested = ""
            if _ALIAS_BREW_RE.search(line):
                kind = "alias"
                suggested = rewrite_brew_prefix(stripped, ports_prefix)
            elif _LINKER_RE.search(line) and (
                "/usr/local" in line or "/opt/homebrew" in line
            ):
                kind = "linker"
                suggested = rewrite_brew_prefix(stripped, ports_prefix)
            else:
                hook = _EVAL_HOOK_RE.search(stripped)
                if hook and hook.group("cmd").lower() in migrated:
                    kind = "hook"
                    cmd = hook.group("cmd")
                    suggested = stripped.replace(
                        f"$({cmd} ", f"$({ports_prefix}/bin/{cmd} ", 1
                    )
                else:
                    abs_cmd = _ABS_BREW_CMD_RE.search(stripped)
                    name = abs_cmd.group(1).lower() if abs_cmd else ""
                    if name and name in migrated:
                        kind = "bin"
                        suggested = rewrite_brew_prefix(stripped, ports_prefix)
            if not kind:
                continue
            found.append(
                PathLine(
                    path=str(path),
                    lineno=lineno,
                    text=stripped,
                    kind=kind,
                    suggested=suggested if suggested != stripped else "",
                )
            )
    return found


def _expand_entry(entry: str, home: Path | None = None) -> str:
    home_s = str(home or Path.home())
    if entry.startswith("$HOME"):
        return home_s + entry[len("$HOME") :]
    if entry.startswith("~"):
        return home_s + entry[1:]
    return entry


def _zsh_path_entry(entry: str) -> str:
    home = str(Path.home())
    if entry == home:
        return "$HOME"
    if entry.startswith(home + "/"):
        return "$HOME/" + entry[len(home) + 1 :]
    return entry


def _norm_entry(entry: str) -> str:
    if entry != "/":
        return entry.rstrip("/")
    return entry
