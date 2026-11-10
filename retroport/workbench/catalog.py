"""What the workbench browses: the items and sets of a modern client, read from a local install.

A *source* is one CASC install (BfA 8.3.7, a retail install - a partial one fetches what it does
not store from Blizzard's CDN into a cache it keeps). Its *catalog* is built once per build from
its own tables and kept on disk:

* items - every item with a look (armour slots, weapons, shields, off-hands) that has a search
  name: its name, quality, expansion, class / subclass / slot, the appearance it shows by
  default (ItemModifiedAppearance modifier 0, else its first) with that appearance's icon and
  ItemDisplayInfo, required level, item level and the classes that may use it, and every other
  appearance it has (heroic, mythic, ...);
* transmog sets - TransmogSet with its pieces (TransmogSetItem -> ItemModifiedAppearance), its
  group (raid, PvP season) and label (ItemNameDescription: "Mythic", "Elite"), and its family:
  the sets that share a root through ParentTransmogSetID (one set in four difficulties, one PvP
  set in its seasons' colours);
* item sets - ItemSet: the classic tier sets, by item id.

Ids are the game's own.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

CATALOG_VERSION = 4

# InventoryType values that show on a character or in its hands
LOOK_SLOTS = {1, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23, 25, 26}
SLOT_NAMES = {1: "Head", 3: "Shoulder", 4: "Shirt", 5: "Chest", 6: "Waist", 7: "Legs", 8: "Feet", 9: "Wrist",
              10: "Hands", 13: "One-Hand", 14: "Shield", 15: "Ranged", 16: "Back", 17: "Two-Hand", 19: "Tabard",
              20: "Chest (robe)", 21: "Main Hand", 22: "Off Hand", 23: "Held In Off-hand", 25: "Thrown",
              26: "Ranged"}
# slot names (the item filter's) -> InventoryType
SLOT_GROUPS = {"head": {1}, "shoulder": {3}, "back": {16}, "chest": {5, 20}, "shirt": {4}, "tabard": {19},
               "wrist": {9}, "hands": {10}, "waist": {6}, "legs": {7}, "feet": {8},
               "mainhand": {13, 17, 21}, "offhand": {14, 22}, "held": {23}, "ranged": {15, 25, 26}}
ARMOUR, WEAPON = 4, 2
ARMOUR_TYPES = {"cloth": 1, "leather": 2, "mail": 3, "plate": 4, "cosmetic": 5, "shield": 6, "misc": 0}
WEAPON_TYPES = {0: "Axe", 1: "Two-Handed Axe", 2: "Bow", 3: "Gun", 4: "Mace", 5: "Two-Handed Mace",
                6: "Polearm", 7: "Sword", 8: "Two-Handed Sword", 9: "Warglaive", 10: "Staff", 11: "Bear Claws",
                12: "Cat Claws", 13: "Fist Weapon", 14: "Miscellaneous", 15: "Dagger", 16: "Thrown",
                17: "Spear", 18: "Crossbow", 19: "Wand", 20: "Fishing Pole"}
ARMOUR_NAMES = {0: "Miscellaneous", 1: "Cloth", 2: "Leather", 3: "Mail", 4: "Plate", 5: "Cosmetic", 6: "Shield"}
EXPANSIONS = {0: "Classic", 1: "The Burning Crusade", 2: "Wrath of the Lich King", 3: "Cataclysm",
              4: "Mists of Pandaria", 5: "Warlords of Draenor", 6: "Legion", 7: "Battle for Azeroth",
              8: "Shadowlands", 9: "Dragonflight", 10: "The War Within", 11: "Midnight", 12: "The Last Titan"}
CLASSES = {1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest", 6: "Death Knight", 7: "Shaman",
           8: "Mage", 9: "Warlock", 10: "Monk", 11: "Druid", 12: "Demon Hunter", 13: "Evoker"}
QUALITIES = {0: ("Poor", "#9d9d9d"), 1: ("Common", "#ffffff"), 2: ("Uncommon", "#1eff00"), 3: ("Rare", "#0070dd"),
             4: ("Epic", "#a335ee"), 5: ("Legendary", "#ff8000"), 6: ("Artifact", "#e6cc80"),
             7: ("Heirloom", "#00ccff"), 8: ("WoW Token", "#00ccff")}
# ItemAppearanceModifierID -> what the appearance is the item's
MODIFIERS = {0: "Normal", 1: "Heroic", 3: "Mythic", 4: "Raid Finder", 5: "Warforged", 6: "Heroic Warforged",
             7: "Mythic Warforged", 153: "Timewalking"}

TABLES = ("Item", "ItemSearchName", "ItemAppearance", "ItemModifiedAppearance", "TransmogSet", "TransmogSetItem",
          "TransmogSetGroup", "ItemNameDescription", "ItemSet")

# item row: the fields the browser lists, in this order (a list keeps the catalog small)
ITEM_FIELDS = ("id", "name", "quality", "expansion", "cls", "sub", "slot", "icon", "appearance", "display",
               "req_level", "item_level", "classes")
F = {name: k for k, name in enumerate(ITEM_FIELDS)}


class SourceError(RuntimeError):
    pass


# Blizzard's test and placeholder items ("[DNT] Test Legs", "[PH] ...", "zzOLD...") - hidden unless asked
_JUNK = re.compile(r"^\s*\[(dnt|ph|nyi|tbd|test)\]|^zz|^(test|qa|deprecated|unused)\b|\((test|old|deprecated)\)",
                   re.IGNORECASE)


def is_junk(name: str) -> bool:
    return bool(_JUNK.search(name))


def _class_bit(cls: int) -> int:
    return 1 << (cls - 1)


def db2_ids(listfile: str, cache_path: str | None = None) -> dict[str, int]:
    """Every ``dbfilesclient/*.db2`` the listfile names -> its FileDataID (one pass, then cached)."""
    stamp = f"{os.path.abspath(listfile)}|{os.path.getmtime(listfile)}"
    if cache_path and os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as fh:
                cached = json.load(fh)
            if cached.get("stamp") == stamp:
                return cached["ids"]
        except (OSError, ValueError, KeyError):
            pass
    found: dict[str, int] = {}
    with open(listfile, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            sep = ";" if ";" in line else ","
            fdid, _sep, path = line.strip().partition(sep)
            path = path.lower().replace("\\", "/")
            if path.startswith("dbfilesclient/") and path.endswith(".db2") and fdid.isdigit():
                found[path[len("dbfilesclient/"):-len(".db2")]] = int(fdid)
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump({"stamp": stamp, "ids": found}, fh)
    return found


@dataclass
class SourceSpec:
    key: str                         # "bfa", "retail"
    label: str
    path: str = ""                   # a local install's folder (holds .build.info and Data\)
    product: str | None = None       # .build.info product: "wow" for retail; None: the active one
    cdn: bool = False                # fetch what a partial install does not store
    kind: str = "local"              # "local": the install at path; "wago": wago.tools
    build: str = ""                  # wago: the build ("": the newest live one)
    browse: bool = True              # its items in the workbench (False: BfA read for its bodies only)


def make_source(spec: SourceSpec, dbd_dir: str, listfile: str, cache_dir: str):
    """A source's reader: the local install, or wago.tools (``wago.WagoSource``)."""
    if spec.kind == "wago":
        from .wago import WagoSource
        return WagoSource(spec, cache_dir)
    return Source(spec, dbd_dir, listfile, cache_dir)


class Source:
    """One local install: its DB2 tables by name and its files by FileDataID. CASC reads go one at
    a time (the storage keeps shared archive handles)."""

    def __init__(self, spec: SourceSpec, dbd_dir: str, listfile: str, cache_dir: str):
        self.spec = spec
        self.dbd_dir = dbd_dir
        self.listfile = listfile
        self.cache_dir = cache_dir
        self._casc = None
        self._defs = None
        self._db2: dict[str, int] | None = None
        self._lock = threading.Lock()
        self._open_lock = threading.Lock()

    @property
    def key(self) -> str:
        return self.spec.key

    def open(self):
        if self._casc is not None:
            return self._casc
        with self._open_lock:                          # icon requests arrive in parallel: open once
            if self._casc is not None:
                return self._casc
            from wotlkconv.casc import CascStorage
            from wotlkconv.db.dbd import DbdIndex
            if not os.path.isfile(os.path.join(self.spec.path, ".build.info")):
                raise SourceError(f"{self.spec.label}: {self.spec.path} is not a game install (no .build.info)")
            cdn = os.path.join(self.cache_dir, "cdn") if self.spec.cdn else None
            casc = CascStorage.open(self.spec.path, product=self.spec.product, cdn_cache=cdn)
            self._defs = DbdIndex(self.dbd_dir)
            self._db2 = db2_ids(self.listfile, os.path.join(self.cache_dir, "db2-ids.json"))
            self._casc = casc
        return self._casc

    @property
    def build(self) -> str:
        """The install's build, from .build.info alone (a cached catalog loads without opening CASC)."""
        from pathlib import Path
        from wotlkconv.casc.config import BuildInfo
        b = self._casc.build if self._casc is not None else BuildInfo.load(Path(self.spec.path), self.spec.product)
        return b.version or b.build_name or b.build_key[:8]

    def table(self, name: str) -> list[tuple[int, dict]]:
        from wotlkconv.db.db2 import parse_db2
        self.open()
        fdid = self._db2.get(name.lower())
        if fdid is None:
            raise SourceError(f"{name}.db2 is not in the listfile")
        with self._lock:
            data = self._casc.read_file_id(fdid, zero_encrypted=True)
        return list(parse_db2(data, name, definitions=self._defs, table_name=name))

    def read(self, fdid: int) -> bytes:
        casc = self.open()
        with self._lock:
            return casc.read_file_id(fdid)

    def raw_table(self, name: str) -> bytes:
        """A table's file as it is (its encrypted sections, unreleased rows, zeroed)."""
        self.open()
        fdid = self._db2.get(name.lower())
        if fdid is None:
            raise SourceError(f"{name}.db2 is not in the listfile")
        with self._lock:
            return self._casc.read_file_id(fdid, zero_encrypted=True)

    def parse(self, name: str, data: bytes) -> list[tuple[int, dict]]:
        """``data`` (``name``'s file) read into rows."""
        from wotlkconv.db.db2 import parse_db2
        self.open()
        return list(parse_db2(data, name, definitions=self._defs, table_name=name))

    def try_read(self, fdid: int) -> tuple[bytes | None, str]:
        """A file by id, or (None, why) - not in this build, not stored here, or encrypted."""
        casc = self.open()
        with self._lock:
            return casc.try_read_file_id(fdid)

    def size_of(self, fdid: int) -> int | None:
        casc = self.open()
        ckey = casc.root.ckey_for(fdid)
        return casc.encoding.size_for(ckey) if ckey else None


@dataclass
class Catalog:
    source: str
    build: str
    items: list[list]                                   # ITEM_FIELDS rows
    appearances: dict[int, list[list]]                  # item id -> [[modifier, appearance, icon, display, label]]
    sets: list[dict]                                    # transmog sets
    item_sets: list[dict]
    item_to_sets: dict[int, list[int]] = field(default_factory=dict)
    by_id: dict[int, list] = field(default_factory=dict)
    set_by_id: dict[int, dict] = field(default_factory=dict)
    item_set_by_id: dict[int, dict] = field(default_factory=dict)
    in_client: set[int] = field(default_factory=set)    # item ids the 3.3.5 client already has

    def __post_init__(self):
        fold_variants(self.sets)
        self.by_id = {r[0]: r for r in self.items}
        self.set_by_id = {s["id"]: s for s in self.sets}
        self.item_set_by_id = {s["id"]: s for s in self.item_sets}
        self._names = [r[F["name"]].lower() for r in self.items]
        self._junk = [is_junk(r[F["name"]]) for r in self.items]
        if not self.item_to_sets:
            reverse: dict[int, list[int]] = defaultdict(list)
            for s in self.sets:
                for p in s["pieces"]:
                    if s["id"] not in reverse[p["item"]]:
                        reverse[p["item"]].append(s["id"])
            self.item_to_sets = dict(reverse)

    # -- items ------------------------------------------------------------------
    def search_items(self, q: str = "", slot: str = "", armour: str = "", weapon: int | None = None,
                     expansion: int | None = None, quality: int | None = None, cls: int | None = None,
                     looks: bool = False, sort: str = "", page: int = 0, per: int = 120,
                     junk: bool = False) -> tuple[int, list[list]]:
        words = q.lower().split()
        exact_id = int(q) if q.strip().isdigit() else None
        slots = SLOT_GROUPS.get(slot)
        armour_sub = ARMOUR_TYPES.get(armour)
        bit = _class_bit(cls) if cls else 0
        hits = []
        for r, name, bad in zip(self.items, self._names, self._junk):
            if bad and not junk and exact_id is None:
                continue
            if exact_id is not None:
                if r[0] != exact_id and r[F["appearance"]] != exact_id and r[F["display"]] != exact_id:
                    continue
            elif words and not all(w in name for w in words):
                continue
            if slots and r[F["slot"]] not in slots:
                continue
            if armour_sub is not None and (r[F["cls"]] != ARMOUR or r[F["sub"]] != armour_sub):
                continue
            if weapon is not None and (r[F["cls"]] != WEAPON or r[F["sub"]] != weapon):
                continue
            if expansion is not None and r[F["expansion"]] != expansion:
                continue
            if quality is not None and r[F["quality"]] < quality:
                continue
            if bit and r[F["classes"]] != -1 and not (r[F["classes"]] & bit):
                continue
            hits.append(r)
        q_low = q.lower().strip()
        if sort == "name":
            hits.sort(key=lambda r: r[F["name"]].lower())
        elif sort == "quality":
            hits.sort(key=lambda r: (-r[F["quality"]], -r[F["expansion"]], r[F["name"]].lower()))
        elif sort == "id":
            hits.sort(key=lambda r: r[0])
        elif q_low and exact_id is None:
            hits.sort(key=lambda r: (r[F["name"]].lower() != q_low, not r[F["name"]].lower().startswith(q_low),
                                     -r[F["expansion"]], r[F["name"]].lower()))
        else:
            hits.sort(key=lambda r: (-r[F["expansion"]], -r[0]))
        if looks:
            seen, unique = set(), []
            for r in hits:
                if r[F["appearance"]] not in seen:
                    seen.add(r[F["appearance"]])
                    unique.append(r)
            hits = unique
        return len(hits), hits[page * per:(page + 1) * per]

    def item_detail(self, item_id: int) -> dict | None:
        r = self.by_id.get(item_id)
        if r is None:
            return None
        out = dict(zip(ITEM_FIELDS, r))
        out["appearances"] = [dict(zip(("modifier", "appearance", "icon", "display", "label"), a))
                              for a in self.appearances.get(item_id, [])]
        out["sets"] = [self.set_summary(self.set_by_id[s]) for s in self.item_to_sets.get(item_id, [])
                       if s in self.set_by_id and not self.set_by_id[s].get("covered_by")
                       and not is_junk(self.set_by_id[s].get("name") or "")]     # not Blizzard's "[DNT]" sets
        out["item_sets"] = [{"id": s["id"], "name": s["name"]} for s in self.item_sets if item_id in s["items"]]
        out["in_client"] = item_id in self.in_client
        same = [o[0] for o in self.items if o[F["appearance"]] == r[F["appearance"]] and o[0] != item_id]
        out["same_look"] = [self.row_dict(self.by_id[i]) for i in same[:24]]
        return out

    def row_dict(self, r: list) -> dict:
        d = dict(zip(ITEM_FIELDS, r))
        d["in_client"] = r[0] in self.in_client
        return d

    # -- sets -------------------------------------------------------------------
    def set_summary(self, s: dict) -> dict:
        return {k: s[k] for k in ("id", "name", "label", "group", "expansion", "classes", "armour", "root",
                                  "icon", "patch")} | {"pieces": len(s["pieces"])}

    def family(self, s: dict) -> list[dict]:
        """The set's versions: its family's sets, without the fragments folded into others."""
        return [self.set_summary(o) for o in self.sets if o["root"] == s["root"] and (not o.get("covered_by") or o is s)]

    def search_sets(self, q: str = "", expansion: int | None = None, cls: int | None = None, armour: str = "",
                    families: bool = True, page: int = 0, per: int = 60, junk: bool = False) -> tuple[int, list[dict]]:
        """Sets matching the search, one card per family; a fragment folded into another set (see
        fold_fragments) only by its id."""
        words = q.lower().split()
        exact_id = int(q) if q.strip().isdigit() else None
        bit = _class_bit(cls) if cls else 0
        armour_sub = ARMOUR_TYPES.get(armour)
        hits = []
        for s in self.sets:
            text = f"{s['name']} {s['label']} {s['group']}".lower()
            if not junk and exact_id is None and is_junk(s["name"]):
                continue
            if exact_id is not None:
                if s["id"] != exact_id:
                    continue
            elif s.get("covered_by") or (words and not all(w in text for w in words)):
                continue
            if expansion is not None and s["expansion"] != expansion:
                continue
            if bit and s["classes"] and not (s["classes"] & bit):
                continue
            if armour_sub is not None and s["armour"] != armour_sub:
                continue
            hits.append(s)
        if families and exact_id is None:
            roots: dict[int, dict] = {}
            for s in hits:                                   # one card per family: its root, else its first
                cur = roots.get(s["root"])
                if cur is None or s["id"] == s["root"] or (cur["id"] != cur["root"] and s["ui_order"] < cur["ui_order"]):
                    roots[s["root"]] = s
            hits = list(roots.values())
        hits.sort(key=lambda s: (-s["expansion"], -s["patch"], s["name"].lower(), s["ui_order"]))
        out = []
        for s in hits[page * per:(page + 1) * per]:
            d = self.set_summary(s)
            if families and s.get("family_name"):
                d["name"] = s["family_name"]                 # one set in many colours: the card is all of them
            d["piece_icons"] = [p["icon"] for p in looks_of(s["pieces"])][:12]
            d["variants"] = sum(1 for o in self.sets if o["root"] == s["root"] and not o.get("covered_by")) \
                if families else 1
            out.append(d)
        return len(hits), out

    def set_detail(self, set_id: int) -> dict | None:
        s = self.set_by_id.get(set_id)
        if s is None:
            return None
        out = self.set_summary(s)
        out["pieces"] = []
        for p in looks_of(s["pieces"]):
            piece = dict(p)
            names = []
            for q in [p, *p["also"]]:
                r = self.by_id.get(q["item"])
                names.append(r[F["name"]] if r is not None else f"Item {q['item']}")
                if q is p and r is not None:
                    piece.update(name=r[F["name"]], quality=r[F["quality"]], cls=r[F["cls"]], sub=r[F["sub"]])
            piece["also"] = names[1:]                    # the other items with this look (a Helm and a Faceguard)
            piece["in_client"] = p["item"] in self.in_client
            out["pieces"].append(piece)
        out["pieces"].sort(key=lambda p: SLOT_ORDER.get(p["slot"], 99))
        out["family"] = self.family(s)
        return out

    def item_set_detail(self, set_id: int) -> dict | None:
        s = self.item_set_by_id.get(set_id)
        if s is None:
            return None
        pieces = [self.row_dict(self.by_id[i]) if i in self.by_id else {"id": i, "name": f"Item {i}", "icon": 0}
                  for i in s["items"]]
        return {"id": s["id"], "name": s["name"], "pieces": pieces}

    def search_item_sets(self, q: str = "", page: int = 0, per: int = 60) -> tuple[int, list[dict]]:
        words = q.lower().split()
        hits = [s for s in self.item_sets if all(w in s["name"].lower() for w in words) or
                (q.strip().isdigit() and s["id"] == int(q))]
        hits.sort(key=lambda s: -s["id"])
        out = []
        for s in hits[page * per:(page + 1) * per]:
            icons = [self.by_id[i][F["icon"]] for i in s["items"] if i in self.by_id]
            out.append({"id": s["id"], "name": s["name"], "pieces": len(s["items"]), "piece_icons": icons[:12],
                        "items": s["items"],
                        "expansion": max((self.by_id[i][F["expansion"]] for i in s["items"] if i in self.by_id),
                                         default=0)})
        return len(hits), out

    # -- what Install builds -------------------------------------------------------
    def display_items(self) -> dict[int, list[int]]:
        """display id -> the items that show it (by their default look first, then their versions)."""
        idx = getattr(self, "_display_items", None)
        if idx is None:
            idx = defaultdict(list)
            for r in self.items:
                if r[F["display"]]:
                    idx[r[F["display"]]].append(r[0])
            for iid, versions in self.appearances.items():
                for v in versions:
                    if v[3] and iid not in idx[v[3]]:
                        idx[v[3]].append(iid)
            self._display_items = idx = dict(idx)
        return idx

    def looks_for(self, entry: dict) -> tuple[list[dict], list[int]]:
        """A basket entry's looks as Install makes them (one per display) and its items: a set's
        pieces, an item's every version, an item set's items' versions."""
        kind, eid = entry.get("kind"), entry.get("id")
        if kind == "look":                              # one display
            iid = (self.display_items().get(int(eid or 0)) or [None])[0]
            r = self.by_id.get(iid) if iid else None
            if r is None:
                return [{"display": int(eid or 0), "item": 0, "slot": 0, "icon": entry.get("icon") or 0,
                         "name": entry.get("name") or f"Look {eid}", "quality": entry.get("quality"), "label": "",
                         "also": 0}], []
            return [{"display": int(eid), "item": iid, "slot": r[F["slot"]], "icon": r[F["icon"]], "name": r[F["name"]],
                     "quality": r[F["quality"]], "label": "", "also": 0}], [iid]
        if kind == "set":
            s = self.set_by_id.get(eid)
            if s is None:
                return [], []
            looks, items = [], []
            for p in sorted(looks_of(s["pieces"]), key=lambda p: SLOT_ORDER.get(p["slot"], 99)):
                r = self.by_id.get(p["item"])
                looks.append({"display": p.get("display") or 0, "item": p["item"], "slot": p["slot"], "icon": p["icon"],
                              "name": r[F["name"]] if r is not None else f"Item {p['item']}",
                              "quality": r[F["quality"]] if r is not None else None, "label": "",
                              "also": len(p["also"])})
                items += [p["item"], *(a["item"] for a in p["also"])]
            return looks, list(dict.fromkeys(items))
        ids = [eid] if kind == "item" else list(entry.get("items") or (self.item_set_by_id.get(eid) or {}).get("items", []))
        looks, items = [], []
        for iid in ids:
            r = self.by_id.get(iid)
            if r is None:
                continue
            items.append(iid)
            versions = self.appearances.get(iid) or [[0, r[F["appearance"]], r[F["icon"]], r[F["display"]], ""]]
            for _m, _a, ic, display, label in versions:
                looks.append({"display": display or 0, "item": iid, "slot": r[F["slot"]], "icon": ic, "name": r[F["name"]],
                              "quality": r[F["quality"]], "label": label if len(versions) > 1 else "", "also": 0})
        return looks, items

    # -- storage ----------------------------------------------------------------
    def to_json(self) -> dict:
        return {"version": CATALOG_VERSION, "source": self.source, "build": self.build, "items": self.items,
                "appearances": {str(k): v for k, v in self.appearances.items()}, "sets": self.sets,
                "item_sets": self.item_sets}

    @classmethod
    def from_json(cls, d: dict) -> "Catalog":
        return cls(d["source"], d["build"], d["items"], {int(k): v for k, v in d["appearances"].items()},
                   d["sets"], d["item_sets"])


SLOT_ORDER = {1: 0, 3: 1, 16: 2, 5: 3, 20: 3, 4: 4, 19: 5, 9: 6, 10: 7, 6: 8, 7: 9, 8: 10,
              13: 11, 17: 11, 21: 11, 14: 12, 22: 12, 23: 12, 15: 13, 25: 13, 26: 13}


def looks_of(pieces: list[dict]) -> list[dict]:
    """A set's pieces one per look: the items that look the same - one display (a Helm and a
    Faceguard for two armour types; three world drops with one model) - under the one the set marks
    primary (TransmogSetItem flag 1), the others in its ``also``."""
    out: dict[tuple, dict] = {}                        # by look, in the order the looks first come
    for p in pieces:
        key = ("d", p["display"]) if p.get("display") else ("a", p["appearance"] or -p["item"])
        cur = out.get(key)
        if cur is None:
            out[key] = dict(p, also=[])
        elif p.get("flags", 0) & 1 and not cur.get("flags", 0) & 1:
            out[key] = dict(p, also=[{k: v for k, v in cur.items() if k != "also"}, *cur["also"]])
        else:
            cur["also"].append(p)
    return list(out.values())


def entry_key(e: dict) -> str:
    return f"{e.get('kind')}:{e.get('source')}:{e.get('id')}"


def plan_basket(catalogs: dict[str, Catalog], basket: list[dict], installed: list[dict] | None = None) -> dict:
    """What installing the basket builds: each entry's looks, the entries whose looks all come with
    an earlier one anyway, and - ``installed``: the basket of the install in the client, None when
    it isn't known - what's new since then and what the next install drops."""
    entries, first = [], {}                             # display -> the entry that brings it first
    displays, items, mounts = set(), set(), set()
    for e in basket:
        if e.get("kind") == "mount":                    # a mount (mounts.py): its own entry, no looks
            entries.append({k: e.get(k) for k in ("kind", "source", "id", "name", "icon", "quality", "sub")} | {
                "key": entry_key(e), "looks": [], "left_out": [], "items": 0, "state": "ready", "shares": [],
                "covered": False, "mount": {"id": e.get("id"), "display": e.get("display"), "kind": e.get("mount_kind")}})
            mounts.add((e.get("source"), e.get("id")))
            continue
        cat = catalogs.get(e.get("source", ""))
        looks, ids = cat.looks_for(e) if cat else ([], [])
        skip = {str(d) for d in e.get("leave_out") or []}             # pieces the user left out of it
        left = [l for l in looks if str(l.get("display")) in skip]
        looks = [l for l in looks if str(l.get("display")) not in skip]
        out = {k: e.get(k) for k in ("kind", "source", "id", "name", "icon", "quality", "sub")} | {
            "key": entry_key(e), "looks": looks, "left_out": left, "items": len(ids),
            "state": "loading" if cat is None else "ready" if looks or left else "missing"}
        mine = list(dict.fromkeys(l["display"] for l in looks if l["display"]))
        others = list(dict.fromkeys(first[d] for d in mine if d in first))
        out["shares"] = [entries[i]["name"] for i in others]
        out["covered"] = bool(mine) and all(d in first for d in mine)   # nothing of its own
        for d in mine:
            first.setdefault(d, len(entries))
        displays.update(mine)
        items.update((e.get("source"), i) for i in ids)
        entries.append(out)
    plan = {"entries": entries, "looks": len(displays), "items": len(items), "mounts": len(mounts),
            "known": installed is not None, "removed": []}
    if installed is not None:
        had = {entry_key(e) for e in installed}
        now = {o["key"] for o in entries}
        for o in entries:
            o["new"] = o["key"] not in had
        plan["removed"] = [e for e in installed if entry_key(e) not in now]
    return plan


def build_catalog(src: Source, log: Callable[[str], None] = lambda m: None) -> Catalog:
    """The catalog of ``src`` from its own tables (see the module doc)."""
    t0 = time.time()
    tables = {}
    for name in TABLES:
        log(f"{src.spec.label}: reading {name}")
        try:
            tables[name] = src.table(name)
        except Exception as e:                        # a table this build lacks leaves its part empty
            log(f"{src.spec.label}: {name}: {e}")
            tables[name] = []
    names = {i: r for i, r in tables["ItemSearchName"]}
    apps = {i: r for i, r in tables["ItemAppearance"]}
    inv_of = {i: r["InventoryType"] for i, r in tables["Item"]}
    by_item: dict[int, list[tuple]] = defaultdict(list)
    ima: dict[int, tuple[int, int]] = {}
    for i, r in tables["ItemModifiedAppearance"]:
        by_item[r["ItemID"]].append((r["ItemAppearanceModifierID"], r.get("OrderIndex", 0), r["ItemAppearanceID"], i))
        ima[i] = (r["ItemID"], r["ItemAppearanceID"])
    groups = {i: r["Name_lang"] for i, r in tables["TransmogSetGroup"]}
    labels = {i: r["Description_lang"] for i, r in tables["ItemNameDescription"]}
    raw_sets = {i: r for i, r in tables["TransmogSet"]}
    # what a modified appearance is called, by the set that uses it ("Gladiator", "Elite"): PvP and
    # newer modifiers have no name of their own. Blizzard's internal sets ("[DNT] 12.0 Mythic VFX Unlock")
    # name nothing; ``in_real_set``: the modified appearances a set players see uses
    ima_label: dict[int, str] = {}
    in_real_set: set[int] = set()
    for _i, r in tables["TransmogSetItem"]:
        s = raw_sets.get(r["TransmogSetID"])
        if not s or is_junk(s.get("Name_lang") or ""):
            continue
        in_real_set.add(r["ItemModifiedAppearanceID"])
        name = labels.get(s["ItemNameDescriptionID"]) or groups.get(s["TransmogSetGroupID"])
        if name and r["ItemModifiedAppearanceID"] not in ima_label:
            ima_label[r["ItemModifiedAppearanceID"]] = name

    def look(appearance: int, fallback_icon: int) -> tuple[int, int]:
        a = apps.get(appearance)
        if a is None:
            return fallback_icon, 0
        return a["DefaultIconFileDataID"] or fallback_icon, a["ItemDisplayInfoID"]

    def wearable(appearance: int) -> bool | None:
        """False for an appearance behind a player condition (ItemAppearance.TransmogPlayerConditionID):
        with no name and in no set players see, it's one of Blizzard's locked variants - the 12.0 "Mythic
        VFX unlock" looks (modifiers 154-158, ~2,300 of them, most only in "[DNT]" sets) - not a version a
        player wears. None when the appearance isn't known."""
        a = apps.get(appearance)
        return None if a is None else not a.get("TransmogPlayerConditionID")

    items, appearances = [], {}
    for iid, r in tables["Item"]:
        if r["ClassID"] not in (ARMOUR, WEAPON) or r["InventoryType"] not in LOOK_SLOTS:
            continue
        n = names.get(iid)
        if n is None or not n.get("Display_lang"):
            continue
        variants = sorted(by_item.get(iid, []), key=lambda v: (v[0] != 0, v[1], v[0]))
        default_app = variants[0][2] if variants else 0
        icon, display = look(default_app, r.get("IconFileDataID", 0))
        items.append([iid, n["Display_lang"], n.get("OverallQualityID", 1), n.get("ExpansionID", 0), r["ClassID"],
                      r["SubclassID"], r["InventoryType"], icon, default_app, display, n.get("RequiredLevel", 0),
                      n.get("ItemLevel", 0), n.get("AllowableClass", -1)])
        # one version per look: several modifiers often share one appearance (a PvP piece's four)
        versions: dict[int, list] = {}
        for m, _o, a, i in variants:
            label = MODIFIERS.get(m) or ima_label.get(i, "")
            if a != default_app and not label and i not in in_real_set and wearable(a) is False:
                continue                                 # a version no player wears (see ``wearable``)
            if a in versions:
                versions[a][4] = versions[a][4] or label
            else:
                versions[a] = [m, a, *look(a, icon), label]
        if len(versions) > 1:
            for k, v in enumerate(versions.values(), 1):
                v[4] = v[4] or f"Version {k}"
            appearances[iid] = list(versions.values())
    item_row = {r[0]: r for r in items}

    pieces_of: dict[int, list[dict]] = defaultdict(list)
    for _i, r in tables["TransmogSetItem"]:
        hit = ima.get(r["ItemModifiedAppearanceID"])
        if hit is None:
            continue
        item_id, appearance = hit
        it = item_row.get(item_id)
        icon, display = look(appearance, it[F["icon"]] if it else 0)
        pieces_of[r["TransmogSetID"]].append({"item": item_id, "appearance": appearance, "icon": icon,
                                             "display": display, "slot": it[F["slot"]] if it else inv_of.get(item_id, 0),
                                             "flags": r.get("Flags", 0)})

    def root_of(sid: int) -> int:
        seen = set()
        while raw_sets.get(sid, {}).get("ParentTransmogSetID") and sid not in seen:
            seen.add(sid)
            parent = raw_sets[sid]["ParentTransmogSetID"]
            if parent not in raw_sets:
                break
            sid = parent
        return sid

    sets = []
    for sid, r in raw_sets.items():
        pieces = pieces_of.get(sid, [])
        subs = [item_row[p["item"]][F["sub"]] for p in pieces
                if p["item"] in item_row and item_row[p["item"]][F["cls"]] == ARMOUR and p["slot"] not in (16, 4, 19)]
        armour = max(set(subs), key=subs.count) if subs else -1
        chest = next((p["icon"] for p in pieces if p["slot"] in (5, 20)), pieces[0]["icon"] if pieces else 0)
        sets.append({"id": sid, "name": r["Name_lang"] or f"Set {sid}", "label": labels.get(r["ItemNameDescriptionID"], ""),
                     "group": groups.get(r["TransmogSetGroupID"], ""), "expansion": r["ExpansionID"],
                     "classes": r["ClassMask"] if r["ClassMask"] not in (-1, 0xFFFFFFFF) else 0, "armour": armour,
                     "root": root_of(sid), "icon": chest, "patch": r.get("PatchIntroduced", 0),
                     "ui_order": r.get("UiOrder", 0), "flags": r.get("Flags", 0), "pieces": pieces})
    fold_fragments(sets)
    # an item set's pieces with a look (rings and trinkets are no backport's business); a set with none
    # - trinket pairs, and the old PvP sets whose ItemID columns BfA left empty - is left out
    item_sets = [{"id": i, "name": r["Name_lang"], "items": looks}
                 for i, r in tables["ItemSet"]
                 if r["Name_lang"] and (looks := [x for x in r["ItemID"] if x in item_row])]
    log(f"{src.spec.label}: {len(items)} items, {len(sets)} transmog sets, {len(item_sets)} item sets "
        f"({time.time() - t0:.0f} s)")
    return Catalog(src.key, src.build, items, appearances, sets, item_sets)


# words a set's colour version is named by (The War Within's dyes, and plain colours)
COLOR_WORDS = {w.lower() for w in """Aquatic Azure Brick Camo Carrot Cloudy Crimson Deep Faded Grassy Icy Lively Midnight
    Pink Plum Rosy Sepia Snowy Sunny Violet Red Blue Green Yellow Black White Purple Orange Gold Golden Silver Bronze
    Copper Dark Light Teal Brown Gray Grey Cyan Magenta Scarlet Emerald Sapphire Ruby Amber Ivory Ebony Jade Indigo
    Lavender Maroon Navy Olive Rose Tan Turquoise Umber Verdant Vermilion Cerulean Cobalt Crimsonic Onyx Pearl
    Obsidian Platinum Sable Slate Bright Pale Rusty Mossy Sandy Stormy Fiery Frosty Shadowy Dusky""".split()}


def fold_variants(sets: list[dict]) -> None:
    """Sets that are one set in other colours but aren't linked as its versions (Aquatic, Azure,
    Brick... Sweatsuit; Prowler's Aquatic, Azure... Headgear): one family each, its root the first
    of them, each set's label the word that differs, ``family_name`` the name without it (the
    card's). Only sets of no family and no label of their own, three or more with the same name
    but for one word - a colour (``COLOR_WORDS``: another word is another set, a race's heritage
    armour or a season's plate) - the same slots and the same expansion. Running it again changes
    nothing."""
    in_family = {s["root"] for s in sets if s["root"] != s["id"]}
    alone = [s for s in sets if s["root"] == s["id"] and s["id"] not in in_family and not s["label"]
             and not s.get("covered_by") and s["pieces"]]

    def keys(s):
        words = s["name"].split()
        sig = (s["expansion"], tuple(sorted({p["slot"] for p in s["pieces"]})))
        return [(" ".join(words[:i] + ["*"] + words[i + 1:]), sig, i) for i in range(len(words))
                if words[i].lower().strip(",:") in COLOR_WORDS] if len(words) > 1 else []
    count: dict = defaultdict(int)
    for s in alone:
        for k, sig, _i in keys(s):
            count[(k, sig)] += 1
    groups: dict = defaultdict(list)
    for s in alone:
        best = max(keys(s), key=lambda t: (count[(t[0], t[1])], t[2]), default=None)
        if best and count[(best[0], best[1])] >= 3:
            groups[(best[0], best[1])].append((s, s["name"].split()[best[2]]))
    for (pattern, _sig), members in groups.items():
        if len(members) < 3:
            continue
        members.sort(key=lambda m: (m[0]["ui_order"], m[0]["id"]))
        root, name = members[0][0]["id"], " ".join(w for w in pattern.split() if w != "*")
        seen: dict = defaultdict(int)
        for s, word in members:
            seen[word] += 1                                  # two sets in one colour: Snowy, Snowy 2
            s.update(root=root, label=word if seen[word] == 1 else f"{word} {seen[word]}", family_name=name)


def fold_fragments(sets: list[dict]) -> None:
    """Mark the sets that are a fragment of another set of the same name: no version label or group of
    their own, and every appearance of theirs in the other (a PvP season's elite pieces sold two slots
    at a time, a set listed twice). ``covered_by`` names the set that shows them; the rest are left
    as they are (a set's versions are labelled, so none is folded)."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for s in sets:
        by_name[s["name"]].append(s)
    for group in by_name.values():
        if len(group) < 2:
            continue
        looks = {s["id"]: {p["appearance"] for p in s["pieces"]} for s in group}
        for s in group:
            mine = looks[s["id"]]
            if not mine or s["label"] or s["group"]:
                continue
            # the biggest set holding them all; between equals, a labelled one, else the oldest
            holders = [t for t in group if t is not s and mine <= looks[t["id"]] and
                       (len(looks[t["id"]]) > len(mine) or t["label"] or t["group"] or t["id"] < s["id"])]
            if holders:
                best = max(holders, key=lambda t: (len(looks[t["id"]]), bool(t["label"] or t["group"]), -t["id"]))
                s["covered_by"] = best["id"]


def load_catalog(src: Source, log: Callable[[str], None] = lambda m: None) -> Catalog:
    """The source's catalog from the cache when it was built for this build, else built and cached."""
    path = os.path.join(src.cache_dir, f"catalog-{src.key}-{src.build}-v{CATALOG_VERSION}.json.gz")
    if os.path.isfile(path):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                return Catalog.from_json(json.load(fh))
        except (OSError, ValueError, KeyError) as e:
            log(f"{src.spec.label}: cached catalog unreadable ({e}); rebuilding")
    cat = build_catalog(src, log)
    os.makedirs(src.cache_dir, exist_ok=True)
    tmp = path + ".part"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(cat.to_json(), fh, separators=(",", ":"))
    os.replace(tmp, path)
    return cat


def client_item_ids(client_dir: str) -> set[int]:
    """The item ids a 3.3.5 client's Item.dbc has (every patch, as the game sees it)."""
    from ..dbc import DBCFile
    from ..mpq import ClientData
    cd = ClientData(client_dir)
    try:
        return {r[0] for r in DBCFile.from_bytes(cd.read("DBFilesClient\\Item.dbc")).records}
    finally:
        cd.close()
