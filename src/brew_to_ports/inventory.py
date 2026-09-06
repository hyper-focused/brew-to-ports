"""Normalize brew adapter output into Package[]. Owns brew-side derived fields."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from brew_to_ports.models import KIND_CASK, KIND_FORMULA, ORIGIN_BREW, Package


def from_brew_json(payload: Dict[str, Any]) -> List[Package]:
    packages: List[Package] = []
    for formula in payload.get("formulae") or []:
        packages.append(_formula(formula))
    for cask in payload.get("casks") or []:
        packages.append(_cask(cask))
    return packages


def requested_names(packages: Iterable[Package]) -> List[str]:
    return [p.name for p in packages if p.requested or p.kind == KIND_CASK]


def _formula(raw: Dict[str, Any]) -> Package:
    installed = raw.get("installed") or []
    inst = installed[-1] if installed else {}
    deps = []
    for dep in inst.get("runtime_dependencies") or []:
        name = dep.get("full_name") or dep.get("name")
        if name:
            deps.append(name)
    version = inst.get("version") or (raw.get("versions") or {}).get("stable") or ""
    linked = raw.get("linked_keg") not in (None, "")
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
        linked=linked,
        runtime_deps=deps,
        description=raw.get("desc") or "",
    )


def _cask(raw: Dict[str, Any]) -> Package:
    installed = raw.get("installed")
    if isinstance(installed, list):
        version = installed[-1] if installed else raw.get("version") or ""
    else:
        version = installed or raw.get("version") or ""
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
        description=raw.get("desc") or "",
    )
