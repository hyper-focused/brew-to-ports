"""Test helpers."""

from __future__ import annotations

import json
from pathlib import Path

from brew_to_ports.catalog import Catalog, format_portindex, from_dicts, from_portindex_text

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def brew_payload():
    return json.loads((FIXTURES / "brew_installed.json").read_text(encoding="utf-8"))


def catalog() -> Catalog:
    rows = json.loads((FIXTURES / "portindex_rows.json").read_text(encoding="utf-8"))
    text = format_portindex(rows)
    parsed = from_portindex_text(text, source="fixture-portindex")
    # sanity: dict path should agree
    alt = from_dicts(rows, source="fixture-dicts")
    assert len(parsed) == len(alt)
    return parsed


def write_portindex_sample() -> Path:
    rows = json.loads((FIXTURES / "portindex_rows.json").read_text(encoding="utf-8"))
    path = FIXTURES / "PortIndex.sample"
    path.write_text(format_portindex(rows), encoding="utf-8")
    return path
