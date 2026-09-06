"""Normalize brew adapter output into Package[]. Owns brew-side derived fields."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from brew_to_ports.models import KIND_CASK, KIND_FORMULA, ORIGIN_BREW, Package


def from_brew_json(payload: Dict[str, Any]) -> List[Package]:
    formulae_raw = list(payload.get("formulae") or [])
    casks_raw = list(payload.get("casks") or [])
    installed: Set[str] = {str(f.get("name") or "") for f in formulae_raw}
    installed.discard("")
    packages: List[Package] = []
    for formula in formulae_raw:
        packages.append(_formula(formula, installed))
    for cask in casks_raw:
        packages.append(_cask(cask, installed))
    return packages


def requested_names(packages: Iterable[Package]) -> List[str]:
    return [p.name for p in packages if p.requested or p.kind == KIND_CASK]


def _formula(raw: Dict[str, Any], installed: Set[str]) -> Package:
    installed_kegs = raw.get("installed") or []
    linked = raw.get("linked_keg")
    inst: Dict[str, Any] = {}
    if linked not in (None, ""):
        for keg in installed_kegs:
            if str(keg.get("version") or "") == str(linked):
                inst = keg
                break
    if not inst:
        inst = installed_kegs[-1] if installed_kegs else {}
    deps = _formula_deps(raw, inst, installed)
    version = inst.get("version") or (raw.get("versions") or {}).get("stable") or ""
    linked_flag = linked not in (None, "")
    return Package(
        name=raw.get("name") or "",
        version=str(version),
        kind=KIND_FORMULA,
        origin=ORIGIN_BREW,
        tap=raw.get("tap") or "",
        homepage=raw.get("homepage") or "",
        requested=bool(inst.get("installed_on_request")),
        as_dependency=bool(inst.get("installed_as_dependency")),
        bottle=bool(inst.get("poured_from_bottle")),
        keg_only=bool(raw.get("keg_only")),
        linked=linked_flag,
        runtime_deps=deps,
        description=raw.get("desc") or "",
        source_url=_stable_url(raw),
        sha256=_stable_sha256(raw),
        license=str(raw.get("license") or ""),
        build_deps=[str(x) for x in (raw.get("build_dependencies") or []) if x],
    )


def _stable_url(raw: Dict[str, Any]) -> str:
    urls = raw.get("urls") or {}
    stable = urls.get("stable") if isinstance(urls, dict) else None
    if not isinstance(stable, dict):
        return ""
    return str(stable.get("url") or "")


def _stable_sha256(raw: Dict[str, Any]) -> str:
    urls = raw.get("urls") or {}
    stable = urls.get("stable") if isinstance(urls, dict) else None
    if not isinstance(stable, dict):
        return ""
    return str(stable.get("checksum") or "")


def _formula_deps(raw: Dict[str, Any], inst: Dict[str, Any], installed: Set[str]) -> List[str]:
    """Union keg runtime deps with declared required/recommended/optional that are installed."""
    names: List[str] = []
    seen: Set[str] = set()

    def add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    for dep in inst.get("runtime_dependencies") or []:
        add(str(dep.get("full_name") or dep.get("name") or ""))
    for name in raw.get("dependencies") or []:
        if str(name) in installed:
            add(str(name))
    for name in raw.get("recommended_dependencies") or []:
        if str(name) in installed:
            add(str(name))
    for name in raw.get("optional_dependencies") or []:
        if str(name) in installed:
            add(str(name))
    return names


def _cask(raw: Dict[str, Any], installed: Set[str]) -> Package:
    installed_val = raw.get("installed")
    if isinstance(installed_val, list):
        version = installed_val[-1] if installed_val else raw.get("version") or ""
    else:
        version = installed_val or raw.get("version") or ""
    name = raw.get("token") or ""
    if not name:
        names = raw.get("name") or []
        name = names[0] if names else ""
    return Package(
        name=str(name),
        version=str(version),
        kind=KIND_CASK,
        origin=ORIGIN_BREW,
        tap=raw.get("tap") or "",
        homepage=raw.get("homepage") or "",
        requested=True,
        as_dependency=False,
        bottle=True,
        keg_only=False,
        linked=True,
        runtime_deps=_cask_formula_deps(raw, installed),
        description=raw.get("desc") or "",
    )


def _cask_formula_deps(raw: Dict[str, Any], installed: Set[str]) -> List[str]:
    depends = raw.get("depends_on") or {}
    if not isinstance(depends, dict):
        return []
    formulae = depends.get("formula") or []
    if isinstance(formulae, str):
        formulae = [formulae]
    names: List[str] = []
    seen: Set[str] = set()
    for name in formulae:
        name = str(name)
        if not name or name in seen:
            continue
        if installed and name not in installed:
            continue
        seen.add(name)
        names.append(name)
    return names
