"""Inventory brew-side config. Never copies files.

Reports only files that look customized versus a vendor baseline
(bottle etc, sibling .default / php.ini-production, or keg extension loaders).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from brew_to_ports.classify import load_exceptions, _name_matches
from brew_to_ports.models import ConfigFile, Decision, Package, STATUS_MIGRATE

BREW_PATH_MARKERS = ("/usr/local", "/opt/homebrew", "HOMEBREW_PREFIX", "$(brew --prefix)")
MAX_PEEK_BYTES = 1_000_000
TEXT_SUFFIXES = {".conf", ".cfg", ".ini", ".plist", ".cnf", ".yml", ".yaml", ".json", ".txt", ""}
SKIP_DIR_NAMES = {
    "bash_completion.d",
    "zsh",
    "fish",
    "vendor_completions.d",
    "site-functions",
    "profile.d",
}
SKIP_BASENAMES = {"pear.conf"}
TEMPLATE_ENDINGS = (
    ".default",
    ".sample",
    ".dist",
    ".orig",
    "-production",
    "-development",
    "-recommended",
    "-dist",
)
BARE_CONF_NAMES = {"nanorc", "gitconfig"}
_EXT_LOADER = re.compile(r"^(zend_)?extension\s*=\s*(.*)$", re.I)
_DEV_VALUE = re.compile(r";\s*Development Value:\s*(.*)$", re.I)


def scan_configs(
    packages: Sequence[Package],
    decisions: Sequence[Decision],
    brew_prefix: str,
    ports_prefix: str,
    extra_files: Iterable[ConfigFile] | None = None,
) -> List[ConfigFile]:
    prefix = Path(brew_prefix)
    ports = Path(ports_prefix)
    exceptions = load_exceptions()
    dmap: Dict[str, Decision] = {d.brew_name: d for d in decisions}
    migrate = {d.brew_name for d in decisions if d.status == STATUS_MIGRATE}
    findings: List[ConfigFile] = []
    if extra_files:
        findings.extend(extra_files)

    for pkg in packages:
        if pkg.name not in migrate:
            continue
        stateful = _name_matches(pkg.name, exceptions.get("stateful") or [])
        port_name = ""
        d = dmap.get(pkg.name)
        if d is not None and d.match is not None and d.match.port_name:
            port_name = d.match.port_name
        for path in _iter_conf_files(prefix, pkg):
            if not _pkg_owns_conf(path, pkg, packages, prefix):
                continue
            kind = "conf" if path.is_file() else "data"
            if stateful and kind != "conf":
                kind = "state"
            contains = False
            if path.is_file():
                contains = _contains_brew_paths(path, str(prefix))
            custom, why = _custom_reason(path, pkg, prefix)
            if not custom:
                continue
            findings.append(
                ConfigFile(
                    brew_package=pkg.name,
                    brew_path=str(path),
                    guessed_ports_path=_guess_ports_path(path, prefix, ports, port_name),
                    kind=kind,
                    copy_safe=False,
                    contains_brew_paths=contains,
                    note=why,
                )
            )
    return findings


def _iter_conf_files(prefix: Path, pkg: Package) -> List[Path]:
    seen: Set[Path] = set()
    out: List[Path] = []
    for root in _candidate_roots(prefix, pkg):
        if not root.exists() or root in seen:
            continue
        seen.add(root)
        if root.is_file():
            if _is_conf_file(root):
                out.append(root)
            continue
        if not root.is_dir():
            continue
        out.extend(_walk_conf_dir(root, depth=0))
    unique: List[Path] = []
    seen_files: Set[Path] = set()
    for path in out:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen_files:
            continue
        seen_files.add(key)
        unique.append(path)
    return unique


def _candidate_roots(prefix: Path, pkg: Package) -> List[Path]:
    etc = prefix / "etc"
    name = pkg.name
    roots = [
        etc / name,
        etc / f"{name}.conf",
        etc / f"{name}.cnf",
        etc / f"{name}.ini",
        etc / f"{name}config",
        etc / f"{name}rc",
    ]
    stem, ver = _formula_stem_version(name)
    if ver:
        roots.append(etc / stem / ver)
    elif name != stem:
        roots.append(etc / stem)
    return roots


def _walk_conf_dir(root: Path, depth: int) -> List[Path]:
    if depth > 2:
        return []
    found: List[Path] = []
    try:
        kids = sorted(root.iterdir())
    except OSError:
        return []
    for kid in kids:
        if kid.is_dir():
            if kid.name in SKIP_DIR_NAMES or kid.name.startswith("."):
                continue
            found.extend(_walk_conf_dir(kid, depth + 1))
            continue
        if _is_conf_file(kid):
            found.append(kid)
    return found


def _is_conf_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name
    lower = name.lower()
    if lower in SKIP_BASENAMES or name.startswith("."):
        return False
    if any(lower.endswith(end) for end in TEMPLATE_ENDINGS):
        return False
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES and suffix != "":
        return True
    return lower in BARE_CONF_NAMES


def _formula_stem_version(name: str) -> Tuple[str, str]:
    if "@" not in name:
        return name, ""
    stem, ver = name.split("@", 1)
    return stem, ver


def _pkg_owns_conf(
    path: Path, pkg: Package, packages: Sequence[Package], prefix: Path
) -> bool:
    """Prefer the formula whose bottle shipped this etc path (nano vs nanorc)."""
    bottled = [p for p in packages if _bottle_rel_file(prefix, p, path) is not None]
    if bottled:
        return any(p.name == pkg.name for p in bottled)
    if _bottle_etc(prefix, pkg) is not None:
        return False
    return _under_exclusive_root(path, pkg, prefix, packages)


def _bottle_rel_file(prefix: Path, pkg: Package, path: Path) -> Optional[Path]:
    bottle = _bottle_etc(prefix, pkg)
    if bottle is None:
        return None
    etc = prefix / "etc"
    if not _is_relative_to(path, etc):
        return None
    candidate = bottle / path.relative_to(etc)
    return candidate if candidate.is_file() else None


def _under_exclusive_root(
    path: Path, pkg: Package, prefix: Path, packages: Sequence[Package]
) -> bool:
    etc = prefix / "etc"
    name = pkg.name
    names = {p.name for p in packages}
    exact = [
        etc / f"{name}.conf",
        etc / f"{name}.cnf",
        etc / f"{name}.ini",
        etc / f"{name}config",
    ]
    if f"{name}rc" not in names:
        exact.append(etc / f"{name}rc")
    if path in exact:
        return True
    namedir = etc / name
    if namedir.is_dir() and _is_relative_to(path, namedir):
        return True
    stem, ver = _formula_stem_version(name)
    if ver:
        verdir = etc / stem / ver
        if verdir.is_dir() and _is_relative_to(path, verdir):
            return True
    return False


def _custom_reason(path: Path, pkg: Package, prefix: Path) -> Tuple[bool, str]:
    text = _read_text(path)
    if text is None:
        return False, ""
    if _only_keg_extensions(text, str(prefix)):
        return False, ""
    for baseline in _baselines(path, pkg, prefix):
        other = _read_text(baseline)
        if other is None:
            continue
        if _norm_lines(text, str(prefix)) == _norm_lines(other, str(prefix)):
            return False, ""
        if path.name == "php.ini" and baseline.name == "php.ini-production":
            if _php_ini_matches_prod_or_dev(text, other, str(prefix)):
                return False, ""
    if _has_any_baseline(path, pkg, prefix):
        return True, "differs from vendor baseline; not copied — adjust the MacPorts file"
    return True, "no vendor baseline; not copied — inspect and adjust the MacPorts file"


def _has_any_baseline(path: Path, pkg: Package, prefix: Path) -> bool:
    return any(_read_text(p) is not None for p in _baselines(path, pkg, prefix))


def _baselines(path: Path, pkg: Package, prefix: Path) -> List[Path]:
    found: List[Path] = []
    for suffix in (".default", ".sample", ".dist"):
        found.append(Path(str(path) + suffix))
    if path.name == "php.ini":
        found.append(path.with_name("php.ini-production"))
        found.append(path.with_name("php.ini-development"))
        found.append(path.with_name("php.ini-dist"))
        found.append(path.with_name("php.ini-recommended"))
    bottle = _bottle_etc(prefix, pkg)
    if bottle is not None:
        etc = prefix / "etc"
        if _is_relative_to(path, etc):
            found.append(bottle / path.relative_to(etc))
    return found


def _bottle_etc(prefix: Path, pkg: Package) -> Optional[Path]:
    cellar = prefix / "Cellar" / pkg.name
    if not cellar.is_dir():
        return None
    exact = cellar / pkg.version / ".bottle" / "etc"
    if exact.is_dir():
        return exact
    matches: List[Path] = []
    try:
        children = list(cellar.iterdir())
    except OSError:
        return None
    for child in children:
        bottle = child / ".bottle" / "etc"
        if bottle.is_dir():
            matches.append(bottle)
    if not matches:
        return None
    return sorted(matches)[-1]


def _guess_ports_path(live: Path, prefix: Path, ports: Path, port_name: str) -> str:
    etc = prefix / "etc"
    if port_name and _is_relative_to(live, etc):
        rel = live.relative_to(etc)
        parts = rel.parts
        if len(parts) >= 2:
            return str(ports / "etc" / port_name / parts[-1])
        return str(ports / "etc" / rel)
    if _is_relative_to(live, prefix):
        return str(ports / live.relative_to(prefix))
    return str(ports / "etc" / live.name)


def _read_text(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > MAX_PEEK_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _contains_brew_paths(path: Path, brew_prefix: str) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix != "":
        return False
    text = _read_text(path)
    if text is None:
        return False
    markers = list(BREW_PATH_MARKERS) + [brew_prefix]
    return any(marker in text for marker in markers)


def _norm_paths(text: str, brew_prefix: str) -> str:
    prefixes = [p for p in (brew_prefix, "/usr/local", "/opt/homebrew") if p]
    prefixes.sort(key=len, reverse=True)
    for p in prefixes:
        text = text.replace(p, "${PREFIX}")
    text = re.sub(r"\$\{PREFIX\}/Cellar/[^/\s\"']+/[^/\s\"']+", "${KEG}", text)
    text = re.sub(r"\$\{PREFIX\}/opt/[^/\s\"']+", "${KEG}", text)
    return text


def _norm_lines(text: str, brew_prefix: str) -> List[str]:
    out: List[str] = []
    for line in _norm_paths(text, brew_prefix).splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        out.append(re.sub(r"\s+", " ", s))
    return out


def _only_keg_extensions(text: str, brew_prefix: str) -> bool:
    lines = _norm_lines(text, brew_prefix)
    lines = [ln for ln in lines if not (ln.startswith("[") and ln.endswith("]"))]
    if not lines:
        return False
    for line in lines:
        m = _EXT_LOADER.match(line)
        if not m:
            return False
        val = m.group(2).strip().strip("\"'")
        if "${KEG}" not in val and "${PREFIX}" not in val:
            return False
    return True


def _php_ini_matches_prod_or_dev(live: str, production: str, brew_prefix: str) -> bool:
    live_kv = _ini_assignments(_norm_paths(live, brew_prefix))
    prod_text = _norm_paths(production, brew_prefix)
    prod_kv, dev_kv = _php_ini_prod_and_dev(prod_text)
    if not prod_kv:
        return False
    header_dev = "This is the php.ini-development INI file" in live
    for key, val in live_kv.items():
        if key not in prod_kv and key not in dev_kv:
            return False
        if _ini_val_ok(val, prod_kv.get(key), dev_kv.get(key)):
            continue
        # PHP's development template flips a few booleans with no Development Value comment.
        if (
            header_dev
            and key in prod_kv
            and _boolish(val)
            and _boolish(prod_kv[key])
        ):
            continue
        return False
    return True


_QR_KEY = re.compile(r"^;\s*([a-zA-Z][a-zA-Z0-9._]*)\s*$")


def _php_ini_prod_and_dev(production: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    prod: Dict[str, str] = {}
    dev: Dict[str, str] = {}
    pending_dev: Optional[str] = None
    qr_key: Optional[str] = None
    for raw in production.splitlines():
        s = raw.strip()
        if not s:
            qr_key = None
            continue
        qm = _QR_KEY.match(s)
        if qm and s.startswith(";"):
            qr_key = qm.group(1)
            continue
        m = _DEV_VALUE.match(s)
        if m:
            pending_dev = m.group(1).strip()
            if qr_key:
                dev[qr_key] = pending_dev
            continue
        body = s[1:].strip() if s.startswith(";") else s
        if "=" not in body or body.startswith("["):
            continue
        key, val = body.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key or any(c.isspace() for c in key):
            pending_dev = None
            continue
        if pending_dev is not None:
            dev[key] = pending_dev
            pending_dev = None
        if not s.startswith(";"):
            prod[key] = val
        qr_key = None
    return prod, dev


def _boolish(value: str) -> bool:
    return value.lower() in {"on", "off", "1", "0", "true", "false", "yes", "no"}


def _ini_assignments(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#") or s.startswith("["):
            continue
        if "=" not in s:
            continue
        key, val = s.split("=", 1)
        key = key.strip()
        if not key or any(c.isspace() for c in key):
            continue
        out[key] = val.strip()
    return out


def _ini_val_ok(live: str, prod: Optional[str], dev: Optional[str]) -> bool:
    for allowed in (prod, dev):
        if allowed is None:
            continue
        if live == allowed:
            return True
        token = allowed.split()[0]
        if live == token:
            return True
    return False


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False
