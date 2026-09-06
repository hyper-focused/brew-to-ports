"""Canonical records. One owner per field is documented on Plan / Decision writers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


KIND_FORMULA = "formula"
KIND_CASK = "cask"
ORIGIN_BREW = "brew"
ORIGIN_MACPORTS = "macports"

STATUS_MIGRATE = "migrate"
STATUS_KEEP = "keep"
STATUS_EXCEPTION = "exception"

DELTA_EQUAL = "equal"
DELTA_PORT_NEWER = "port_newer"
DELTA_OLDER_SAME_MAJOR = "port_older_same_major"
DELTA_OLDER_MAJOR = "port_older_major"
DELTA_UNPARSEABLE = "unparseable"
DELTA_NA = "n/a"


@dataclass
class Package:
    name: str
    version: str
    kind: str
    origin: str
    tap: str = ""
    homepage: str = ""
    requested: bool = False
    as_dependency: bool = False
    bottle: bool = False
    keg_only: bool = False
    linked: bool = True
    runtime_deps: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    replaced_by: str = ""
    description: str = ""


@dataclass
class Match:
    brew_name: str
    port_name: Optional[str]
    confidence: str
    rule_id: str
    version_delta: str
    brew_version: str = ""
    port_version: str = ""
    reasons: List[str] = field(default_factory=list)


@dataclass
class Decision:
    brew_name: str
    status: str
    match: Optional[Match]
    reasons: List[str]
    category: str = ""
    hold_uninstall: bool = False
    requested: bool = False
    kind: str = KIND_FORMULA


@dataclass
class ConfigFile:
    brew_package: str
    brew_path: str
    guessed_ports_path: str
    kind: str
    copy_safe: bool
    contains_brew_paths: bool
    note: str = ""


@dataclass
class PathLine:
    path: str
    lineno: int
    text: str
    kind: str  # source_owner | export | shellenv | alias | linker
    replace_with_load: bool = False
    suggested: str = ""


@dataclass
class PathAdvice:
    current_path: str
    suggested: str
    rc_hits: List[str] = field(default_factory=list)
    collisions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    path_owners: List[str] = field(default_factory=list)
    idiom: str = ""  # zsh-array | export-path | mixed | unknown
    extra_writers: List[str] = field(default_factory=list)
    alias_hits: List[str] = field(default_factory=list)
    linker_hits: List[str] = field(default_factory=list)
    array_entries: List[str] = field(default_factory=list)
    path_file: str = ""
    path_file_contents: str = ""
    comment_out: List[PathLine] = field(default_factory=list)
    load_zsh: str = ""
    load_bash: str = ""
    rewrites: List[PathLine] = field(default_factory=list)


@dataclass
class PlanOp:
    action: str
    brew_name: str = ""
    port_name: str = ""
    hold_uninstall: bool = False
    comment: str = ""
    kind: str = KIND_FORMULA


@dataclass
class Plan:
    arch: str
    macos: str
    brew_prefix: str
    ports_prefix: str
    decisions: List[Decision] = field(default_factory=list)
    keep_set: List[str] = field(default_factory=list)
    ops: List[PlanOp] = field(default_factory=list)
    configs: List[ConfigFile] = field(default_factory=list)
    path_advice: Optional[PathAdvice] = None
    allow_older_same_major: bool = False
    catalog_source: str = ""
    notes: List[str] = field(default_factory=list)
