"""MacPorts `port select` links for language runtimes. Not keep-set, not PATH."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from brew_to_ports.models import SelectLink

# group -> (option, rank)
_PHP = re.compile(r"^php(\d+)$")
_PYTHON = re.compile(r"^python(\d{3})$")
_PIP = re.compile(r"^pip(\d{3})$")


def runtime_select_links(
    port_names: Iterable[str],
    summary: Optional[Sequence[Tuple[str, str, Sequence[str]]]] = None,
) -> List[SelectLink]:
    """Newest php / python / python3 / pip / pip3 option among planned + live names."""
    names = {n.strip() for n in port_names if n and n.strip()}
    selected_by_group: Dict[str, str] = {}
    for group, selected, options in summary or []:
        selected_by_group[group] = selected
        for opt in options:
            if opt and opt != "none":
                names.add(opt)

    best: Dict[str, Tuple[int, str]] = {}
    for name in names:
        for group, option, rank in _groups_for_port(name):
            prev = best.get(group)
            if prev is None or rank > prev[0]:
                best[group] = (rank, option)

    order = ("php", "python", "python3", "pip", "pip3")
    links: List[SelectLink] = []
    for group in order:
        hit = best.get(group)
        if hit is None:
            continue
        _rank, option = hit
        links.append(
            SelectLink(
                group=group,
                option=option,
                selected=selected_by_group.get(group, ""),
            )
        )
    return links


def format_select_block(links: Sequence[SelectLink], *, indent: str = "  ") -> List[str]:
    lines: List[str] = []
    for link in links:
        extra = ""
        if link.selected and link.selected == link.option:
            extra = "  # already"
        elif link.selected and link.selected != "none":
            extra = f"  # currently {link.selected}"
        lines.append(f"{indent}{link.command}{extra}")
    return lines


def _groups_for_port(name: str) -> List[Tuple[str, str, int]]:
    n = name.strip()
    m = _PHP.match(n)
    if m:
        return [("php", n, int(m.group(1)))]
    m = _PYTHON.match(n)
    if m:
        rank = int(m.group(1))
        return [
            ("python", n, rank),
            ("python3", n, rank),
            ("pip", f"pip{rank}", rank),
            ("pip3", f"pip{rank}", rank),
        ]
    m = _PIP.match(n)
    if m:
        rank = int(m.group(1))
        return [("pip", n, rank), ("pip3", n, rank)]
    return []
