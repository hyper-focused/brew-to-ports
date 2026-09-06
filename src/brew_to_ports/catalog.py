"""Normalize MacPorts adapter output into a name/homepage index."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from brew_to_ports.models import KIND_FORMULA, ORIGIN_MACPORTS, Package


class Catalog:
    def __init__(self, packages: Iterable[Package], source: str = ""):
        self.source = source
        self.by_name: Dict[str, Package] = {}
        self.by_homepage: Dict[str, List[Package]] = {}
        for pkg in packages:
            key = pkg.name.lower()
            self.by_name[key] = pkg
            home = normalize_homepage(pkg.homepage)
            if home:
                self.by_homepage.setdefault(home, []).append(pkg)

    def get(self, name: str) -> Optional[Package]:
        return self.by_name.get(name.lower())

    def by_home(self, homepage: str) -> List[Package]:
        return list(self.by_homepage.get(normalize_homepage(homepage), []))

    def __len__(self) -> int:
        return len(self.by_name)


def normalize_homepage(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix) :]
            break
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def from_portindex_text(text: str, source: str = "portindex") -> Catalog:
    packages: List[Package] = []
    i = 0
    n = len(text)
    while i < n:
        nl = text.find("\n", i)
        if nl < 0:
            break
        header = text[i:nl].strip()
        i = nl + 1
        if not header:
            continue
        parts = header.split()
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        length = int(parts[1])
        body = text[i : i + length]
        i += length
        if i < n and text[i] == "\n":
            i += 1
        fields = _tcl_list(body)
        info = {}
        for k in range(0, len(fields) - 1, 2):
            info[fields[k]] = fields[k + 1]
        name = info.get("name") or parts[0]
        cats = _tcl_list(info.get("categories", ""))
        packages.append(
            Package(
                name=name,
                version=info.get("version") or "",
                kind=KIND_FORMULA,
                origin=ORIGIN_MACPORTS,
                homepage=info.get("homepage") or "",
                categories=cats,
                replaced_by=info.get("replaced_by") or "",
                description=info.get("description") or "",
            )
        )
    return Catalog(packages, source=source)


def from_dicts(rows: Iterable[dict], source: str = "dict") -> Catalog:
    packages = []
    for row in rows:
        packages.append(
            Package(
                name=row["name"],
                version=str(row.get("version") or ""),
                kind=KIND_FORMULA,
                origin=ORIGIN_MACPORTS,
                homepage=row.get("homepage") or "",
                categories=list(row.get("categories") or []),
                replaced_by=row.get("replaced_by") or "",
                description=row.get("description") or "",
            )
        )
    return Catalog(packages, source=source)


def format_portindex(rows: Iterable[dict]) -> str:
    """Build a PortIndex blob (for fixtures)."""
    chunks: List[str] = []
    for row in rows:
        pairs: List[Tuple[str, str]] = [
            ("name", row["name"]),
            ("version", str(row.get("version") or "")),
            ("homepage", row.get("homepage") or ""),
            ("description", row.get("description") or ""),
        ]
        cats = row.get("categories") or []
        if cats:
            pairs.append(("categories", " ".join(cats)))
        if row.get("replaced_by"):
            pairs.append(("replaced_by", row["replaced_by"]))
        body_parts = []
        for key, val in pairs:
            if val == "" or any(ch in val for ch in " \t{}"):
                body_parts.append(f"{key} {{{val}}}")
            else:
                body_parts.append(f"{key} {val}")
        body = " ".join(body_parts) + "\n"
        chunks.append(f"{row['name']} {len(body)}\n{body}")
    return "".join(chunks)


def _tcl_list(s: str) -> List[str]:
    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        if s[i] == "{":
            depth = 1
            i += 1
            start = i
            while i < n and depth:
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                i += 1
            out.append(s[start : i - 1])
        elif s[i] == '"':
            i += 1
            start = i
            buf = []
            while i < n and s[i] != '"':
                if s[i] == "\\" and i + 1 < n:
                    buf.append(s[i + 1])
                    i += 2
                    continue
                buf.append(s[i])
                i += 1
            out.append("".join(buf) if buf else s[start:i])
            i += 1
        else:
            start = i
            while i < n and s[i] not in " \t\n\r":
                i += 1
            out.append(s[start:i])
    return out
