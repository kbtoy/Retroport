"""Every item and display id given out for a look or a mount - so none is given twice.

The earlier Workbench's backport projects numbered their items from 900000 and their displays above
the client's highest, and kept every id they gave here (``<data>/item-ids.json``); the server still
has those item rows, and players still carry them. Install's mount items take their entries from
990000 and reserve them here too (``remember``), so no number one gave is given again:

* ``reserved`` - every id given out;
* ``item`` / ``display`` - the ids each look (or ``mount:<id>``) was first given.
"""

from __future__ import annotations

import json
import os

NAME = "item-ids.json"


def path(data_dir: str) -> str:
    return os.path.join(data_dir, NAME)


def load(file: str) -> dict:
    try:
        with open(file, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    got = got if isinstance(got, dict) else {}
    for k in ("item", "display"):
        got[k] = {str(d): int(v) for d, v in (got.get(k) or {}).items()}
    res = got.get("reserved") or {}
    got["reserved"] = {k: sorted({int(x) for x in res.get(k) or []}) for k in ("item", "display")}
    got["projects"] = list(got.get("projects") or [])
    return got


def remember(file: str, ids: dict, project: str = "") -> bool:
    """A project's ``ids.json`` added: its ids reserved, the first ids of each look kept. True when
    anything was new."""
    reg = load(file)
    before = json.dumps(reg, sort_keys=True)
    for k in ("item", "display"):
        mine = {str(d): int(v) for d, v in ((ids or {}).get(k) or {}).items()}
        for d, v in mine.items():
            reg[k].setdefault(d, v)
        reg["reserved"][k] = sorted(set(reg["reserved"][k]) | set(mine.values()))
    if project and project not in reg["projects"]:
        reg["projects"].append(project)
    if json.dumps(reg, sort_keys=True) == before:
        return False
    os.makedirs(os.path.dirname(file) or ".", exist_ok=True)
    with open(file + ".part", "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=1, sort_keys=True)
    os.replace(file + ".part", file)
    return True
