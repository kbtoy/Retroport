"""The Stats step: what each installed piece is in game.

Install makes every look a cosmetic copy - any class, level 1, no stats. Here each piece gets
its item level and required level, quality, who may wear it, its armour type, stats, armour,
weapon damage and speed, sockets and socket bonus, durability, price, binding, a description,
and item sets with their set bonuses. The page works the numbers out (WotLK's own rules, see
``wotlk``) and keeps them in ``<data>/item-stats.json``:

    {"global": {field: value},                every piece's value unless its set or the piece says otherwise
     "groups": {"<basket key>": {field: value, "broken": bool}},   a basket set's own values
     "pieces": {"<retail display>": {...}},    a piece's own values (and its worked-out stats)
     "sets":   [{"key", "name", "pieces": [display...], "bonuses": [[pieces needed, spell]]}]}

A basket set's pieces take its values (item level, required level, quality, binding, armour type, the
role its stats are for, classes) over the basket's; a piece's own armour type, role, classes and stats
win over both. Item level, required level, quality and binding a piece sets for itself only once its
set is *broken* (or when it is in no set: an item of its own) - ``SET_FIELDS``. Which set a look is in
is the basket's (``groups_of``: its first set), worked out again at each install.

A piece is Install's item for one look (one item per retail display; ``direct`` says which
entry). Install's item SQL is its item rows, then one UPDATE per piece with its stats
(``updates``). Item sets - ``ItemSet.dbc`` rows (ids from 3000, kept per set: ``set_ids``,
``set_rows``, ``itemset_dbc``), with ``item_template.itemset`` on their pieces - are laid out on the
page; Install doesn't put them in the client's and the server's tables yet.

Set bonuses are spells the 3.3.5 client already has: the bonuses of its own item sets, with
their text, to choose from.
"""

from __future__ import annotations

import json
import os
import re
import threading

# 3.3.5a's classes (id -> name); AllowableClass bit = 1 << (id - 1)
CLASSES = {1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest", 6: "Death Knight", 7: "Shaman",
           8: "Mage", 9: "Warlock", 11: "Druid"}
ALL_CLASSES = sum(1 << (c - 1) for c in CLASSES)
QUALITIES = {0: "Poor", 1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary", 6: "Artifact", 7: "Heirloom"}
BONDING = {0: "No binding", 1: "Binds when picked up", 2: "Binds when equipped", 3: "Binds when used"}
ARMOUR_TYPES = {1: "Cloth", 2: "Leather", 3: "Mail", 4: "Plate"}
MATERIAL = {1: 7, 2: 8, 3: 5, 4: 6}                     # the Material an armour type sounds like
SOCKETS = {1: "Meta", 2: "Red", 4: "Yellow", 8: "Blue", 14: "Prismatic"}
# item_template stat types (ItemModType): name, "base" (white +N line) or "equip" (green Equip: line), cost
STATS = {
    0: ("Mana", "base", 0.5), 1: ("Health", "base", 0.5), 3: ("Agility", "base", 1), 4: ("Strength", "base", 1),
    5: ("Intellect", "base", 1), 6: ("Spirit", "base", 1), 7: ("Stamina", "base", 2 / 3),
    12: ("Defense rating", "equip", 1), 13: ("Dodge rating", "equip", 1), 14: ("Parry rating", "equip", 1),
    15: ("Block rating", "equip", 1), 31: ("Hit rating", "equip", 1), 32: ("Critical strike rating", "equip", 1),
    35: ("Resilience rating", "equip", 1), 36: ("Haste rating", "equip", 1), 37: ("Expertise rating", "equip", 1),
    38: ("Attack power", "equip", 0.5), 39: ("Ranged attack power", "equip", 0.4), 43: ("Mana per 5 sec.", "equip", 2),
    44: ("Armor penetration rating", "equip", 1), 45: ("Spell power", "equip", 6 / 7), 46: ("Health per 5 sec.", "equip", 2),
    47: ("Spell penetration", "equip", 1), 48: ("Block value", "equip", 0.65),
    16: ("Melee hit rating", "equip", 1), 17: ("Ranged hit rating", "equip", 1), 18: ("Spell hit rating", "equip", 1),
    19: ("Melee critical strike rating", "equip", 1), 20: ("Ranged critical strike rating", "equip", 1),
    21: ("Spell critical strike rating", "equip", 1), 28: ("Melee haste rating", "equip", 1),
    29: ("Ranged haste rating", "equip", 1), 30: ("Spell haste rating", "equip", 1),
}
RANGED = {2: 2, 3: 3, 18: 2, 16: 0, 19: 0}               # weapon subclass -> ammo type (bow/crossbow arrows, gun bullets)
SET_ID_START = 3000                                      # the client's own item sets end at 901
_lock = threading.Lock()


SET_FIELDS = ("ilvl", "req", "quality", "bonding")     # a piece's own only once its set is broken
SET_KINDS = ("set", "itemset")                         # the basket entries that are sets of pieces


def empty() -> dict:
    return {"global": {}, "groups": {}, "pieces": {}, "sets": []}


def _clean(d: dict) -> dict:
    return {"global": dict(d.get("global") or {}), "groups": {str(k): dict(v) for k, v in (d.get("groups") or {}).items()},
            "pieces": dict(d.get("pieces") or {}), "sets": list(d.get("sets") or [])}


def load(data_dir: str) -> dict:
    try:
        with open(os.path.join(data_dir, "item-stats.json"), encoding="utf-8") as fh:
            return _clean(json.load(fh))
    except (OSError, ValueError, AttributeError, TypeError):
        return empty()


def save(data_dir: str, edits: dict) -> None:
    if not isinstance(edits, dict) or not isinstance(edits.get("pieces", {}), dict) or \
            not isinstance(edits.get("groups", {}), dict):
        raise ValueError("the stats are an object with global, groups, pieces and sets")
    clean = _clean(edits)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "item-stats.json")
    with open(path + ".part", "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=1)
    os.replace(path + ".part", path)


def groups_of(plan: dict) -> dict[str, str]:
    """retail display -> the basket key of the first set in ``plan`` (catalog.plan_basket) holding it;
    a look in no set (an item of its own) has none."""
    out: dict[str, str] = {}
    for e in plan.get("entries") or []:
        if e.get("kind") in SET_KINDS:
            for look in e.get("looks") or []:
                d = str(look.get("display") or "")
                if d and d != "0":
                    out.setdefault(d, e["key"])
    return out


def effective(edits: dict, display, field: str, default=None, group: str | None = None):
    """A piece's value for ``field``: its own, else its set's (``group``: its basket set's key), else
    every piece's (global), else ``default``. Item level, required level, quality and binding are a
    piece's own only when it is in no set or its set is broken. "" and None mean "not set"."""
    g = ((edits.get("groups") or {}).get(group) or {}) if group else {}
    own = (edits.get("pieces") or {}).get(str(display), {}).get(field)
    if own not in (None, "") and (field not in SET_FIELDS or not group or g.get("broken")):
        return own
    if g.get(field) not in (None, ""):
        return g[field]
    v = (edits.get("global") or {}).get(field)
    return v if v not in (None, "") else default


def touched(edits: dict, display, group: str | None = None) -> bool:
    """Whether a piece has anything to write (otherwise it stays a cosmetic copy)."""
    p = (edits.get("pieces") or {}).get(str(display), {})
    fields = ("ilvl", "req", "quality", "classes", "armor_type", "bonding")
    return bool(p.get("stats") or p.get("armor") or p.get("dmg_max") or
                any(effective(edits, display, f, group=group) not in (None, "") for f in fields))


# -- the item rows ------------------------------------------------------------------------------
_TOKEN = re.compile(r"'((?:[^'\\]|''|\\.)*)'|(-?\d+(?:\.\d+)?)")


def kit_items(sql_text: str) -> dict[int, dict]:
    """An item SQL's item_template rows (entry -> {column: value}) from its INSERT."""
    m = re.search(r"INSERT INTO `item_template` \(([^)]*)\) VALUES\s*(.*?);\s*$", sql_text, re.S | re.M)
    if not m:
        return {}
    cols = [c.strip(" `") for c in m.group(1).split(",")]
    out = {}
    for row in re.findall(r"\((.*?)\)(?=,\s*\(|\s*$)", m.group(2).strip(), re.S):
        vals = []
        for s, n in _TOKEN.findall(row):
            vals.append(s.replace("''", "'") if n == "" else (float(n) if "." in n else int(n)))
        if len(vals) == len(cols):
            rec = dict(zip(cols, vals))
            out[int(rec["entry"])] = rec
    return out


def _q(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"


def piece_sets(edits: dict, set_ids: dict) -> dict[str, int]:
    """retail display -> the item set id its piece belongs to (its first set)."""
    out = {}
    for s in edits.get("sets") or []:
        sid = set_ids.get(s.get("key"))
        if sid:
            for d in s.get("pieces") or []:
                out.setdefault(str(d), sid)
    return out


# AzerothCore's item_template columns, as its worldserver reads them (BuyPrice as int32). MySQL
# refuses an UPDATE with a value outside its column - the whole piece's UPDATE - and the piece stays
# a level-1 copy; so every value is kept inside. (AzerothCore has no StatsCount column: it
# counts the stats it loads.)
INT32, UINT32 = (-2 ** 31, 2 ** 31 - 1), (0, 2 ** 32 - 1)
LIMITS = {"Quality": (0, 7), "ItemLevel": (0, 65535), "RequiredLevel": (0, 255), "bonding": (0, 255),
          "AllowableClass": INT32, "subclass": (0, 255), "Material": (-128, 127), "armor": UINT32, "block": UINT32,
          "MaxDurability": (0, 65535), "SellPrice": UINT32, "BuyPrice": (0, INT32[1]), "dmg_min1": (0, INT32[1]),
          "dmg_max1": (0, INT32[1]), "dmg_type1": (0, 255), "delay": (0, 65535), "ammo_type": (0, 255),
          "maxcount": INT32, "socketBonus": INT32, "itemset": UINT32,
          **{f"stat_type{k}": (0, 255) for k in range(1, 11)}, **{f"stat_value{k}": INT32 for k in range(1, 11)},
          **{f"socketColor_{k}": (-128, 127) for k in range(1, 4)}, **{f"socketContent_{k}": INT32 for k in range(1, 4)}}


def column_value(col: str, v):
    """``v`` kept inside ``col``'s range (text and floats as they are)."""
    lo, hi = LIMITS.get(col, (None, None))
    return min(max(v, lo), hi) if lo is not None and isinstance(v, int) and not isinstance(v, bool) else v


def updates(edits: dict, ids: dict, rows: dict[int, dict], set_ids: dict, names: dict | None = None,
            groups: dict | None = None) -> list[str]:
    """One UPDATE per touched piece (``rows``: the item rows as the SQL inserts them, entry -> {column:
    value}; a row stays as it is otherwise). ``names``: the name each look has in the workbench (the
    item the basket chose) - a row named after another retail item that shares the look gets it (a
    name typed on the Stats page wins over both). ``groups``: each look's basket set (``groups_of``)."""
    out = []
    sets = piece_sets(edits, set_ids)
    for display, entry in sorted(((str(d), e) for d, e in (ids.get("item") or {}).items()), key=lambda t: t[1]):
        row = rows.get(int(entry))
        if row is None:
            continue
        in_set = sets.get(display)
        group = (groups or {}).get(display)
        p = (edits.get("pieces") or {}).get(display, {})
        name = p.get("name") or (names or {}).get(display)
        renamed = bool(name) and name != row.get("name")
        if not (touched(edits, display, group) or in_set):
            if renamed:                                     # nothing else to give it: its name only
                out.append(f"UPDATE `item_template` SET `name` = {_q(name)} WHERE `entry` = {int(entry)};")
            continue
        cls, sub, inv = row.get("class", 0), row.get("subclass", 0), row.get("InventoryType", 0)
        set_ = {}
        if renamed:
            set_["name"] = _q(name)
        for col, field in (("Quality", "quality"), ("ItemLevel", "ilvl"), ("RequiredLevel", "req"), ("bonding", "bonding")):
            v = effective(edits, display, field, group=group)
            if v not in (None, ""):
                set_[col] = int(v)
        classes = effective(edits, display, "classes", group=group)
        if classes not in (None, ""):
            classes = int(classes)
            set_["AllowableClass"] = -1 if classes in (0, -1) or classes & ALL_CLASSES == ALL_CLASSES else classes
        at = effective(edits, display, "armor_type", group=group)
        if at and cls == 4 and sub in ARMOUR_TYPES and inv != 16 and int(at) in ARMOUR_TYPES:
            set_["subclass"], set_["Material"] = int(at), MATERIAL[int(at)]
        stats = [(int(t), int(v)) for t, v in (p.get("stats") or []) if int(t) in STATS and int(v)][:10]
        for k in range(10):
            t, v = stats[k] if k < len(stats) else (0, 0)
            set_[f"stat_type{k + 1}"], set_[f"stat_value{k + 1}"] = t, v
        for col, field in (("armor", "armor"), ("block", "block"), ("MaxDurability", "durability"), ("SellPrice", "sell")):
            v = p.get(field)
            if v not in (None, ""):
                set_[col] = max(0, int(v))
        if "SellPrice" in set_:
            set_["BuyPrice"] = set_["SellPrice"] * 4
        if cls == 2 and p.get("dmg_max"):
            set_["dmg_min1"], set_["dmg_max1"] = int(p.get("dmg_min") or 0), int(p["dmg_max"])
            set_["dmg_type1"] = 0
            set_["delay"] = int(p.get("delay") or 2000)
            if sub in RANGED:
                set_["RangedModRange"] = 100
                set_["ammo_type"] = RANGED[sub]
        if effective(edits, display, "unique", group=group):
            set_["maxcount"] = 1
        sockets = [int(c) for c in (p.get("sockets") or []) if int(c) in SOCKETS][:3]
        for k in range(3):
            set_[f"socketColor_{k + 1}"] = sockets[k] if k < len(sockets) else 0
            set_[f"socketContent_{k + 1}"] = 0
        set_["socketBonus"] = int(p.get("socket_bonus") or 0) if sockets else 0
        set_["itemset"] = in_set or 0
        if p.get("description") is not None:
            set_["description"] = _q(p.get("description") or "")
        out.append("UPDATE `item_template` SET " + ", ".join(f"`{k}` = {column_value(k, v)}" for k, v in set_.items()) +
                   f" WHERE `entry` = {int(entry)};")
    return out


# -- item sets ----------------------------------------------------------------------------------
def set_ids(data_dir: str, sets: list[dict]) -> dict[str, int]:
    """Each set's ItemSet id, kept per set key (a set keeps its id when it's renamed or changed)."""
    path = os.path.join(data_dir, "item-set-ids.json")
    with _lock:
        known = _json(path, {})
        nxt = max([SET_ID_START - 1, *known.values()]) + 1
        for s in sets:
            k = s.get("key")
            if k and k not in known:
                known[k], nxt = nxt, nxt + 1
        with open(path + ".part", "w", encoding="utf-8") as fh:
            json.dump(known, fh, indent=1)
        os.replace(path + ".part", path)
        return known


def set_rows(edits: dict, ids: dict, sids: dict) -> list[dict]:
    """The sets as ItemSet rows: {id, name, items (entries, 17 at most), bonuses [(needed, spell)]}."""
    entries = {str(d): int(e) for d, e in (ids.get("item") or {}).items()}
    out = []
    for s in edits.get("sets") or []:
        sid = sids.get(s.get("key"))
        items = [entries[str(d)] for d in s.get("pieces") or [] if str(d) in entries][:17]
        if not sid or not items:
            continue
        bonuses = sorted(((int(n), int(sp)) for n, sp in (s.get("bonuses") or []) if int(n) > 0 and int(sp) > 0))[:8]
        out.append({"id": sid, "name": s.get("name") or f"Set {sid}", "items": items, "bonuses": bonuses})
    return out


def itemset_dbc(base: bytes, rows: list[dict], owned: set[int]) -> bytes:
    """``base`` (an ItemSet.dbc) with ``rows`` in it - rows of ids in ``owned`` (ours, from before)
    replaced, every other row kept."""
    from ..dbc import DBCFile
    dbc = DBCFile.from_bytes(base)
    if dbc.field_count != 53:
        raise ValueError(f"ItemSet.dbc has {dbc.field_count} fields, not 3.3.5a's 53")
    flags = dbc.records[0][17] if dbc.records else 0
    dbc.records = [r for r in dbc.records if r[0] not in owned and r[0] not in {x["id"] for x in rows}]
    for x in rows:
        name = dbc.add_string(x["name"])
        rec = [x["id"]] + [name] * 16 + [flags]
        rec += (x["items"] + [0] * 17)[:17]
        rec += ([sp for _n, sp in x["bonuses"]] + [0] * 8)[:8]
        rec += ([n for n, _sp in x["bonuses"]] + [0] * 8)[:8]
        rec += [0, 0]
        dbc.records.append(rec)
    dbc.records.sort(key=lambda r: r[0])
    return dbc.to_bytes()


# -- what the 3.3.5 client offers ---------------------------------------------------------------
_SUB = re.compile(r"\$(\d*)(s|m)([1-3])|\$(\d*)h|\$(\d*)d")


def _duration(ms: int) -> str:
    if ms <= 0:
        return "until cancelled"
    sec = ms // 1000
    if sec >= 3600 and sec % 3600 == 0:
        return f"{sec // 3600} hour" + ("s" if sec >= 7200 else "")
    if sec >= 60 and sec % 60 == 0:
        return f"{sec // 60} min"
    return f"{sec} sec"


def spell_text(text: str, row: list[int], spells: dict | None = None, durations: dict | None = None) -> str:
    """A spell's description with its numbers in: $s1/$m1 (its effects' points), $h (its proc
    chance), $d (its duration), and $12345s1 (another spell's) - other placeholders are left."""
    def num(m):
        if m.group(5) is not None:                          # $d / $12345d: duration
            r = (spells or {}).get(int(m.group(5))) if m.group(5) else row
            ms = (durations or {}).get(r[40]) if r else None
            return _duration(ms) if ms is not None else m.group(0)
        if m.group(4) is not None:                          # $h / $12345h: proc chance
            r = (spells or {}).get(int(m.group(4))) if m.group(4) else row
            return str(r[35]) if r else m.group(0)
        r = (spells or {}).get(int(m.group(1))) if m.group(1) else row
        if r is None:
            return m.group(0)
        k = int(m.group(3)) - 1
        base, dice = _signed(r[80 + k]), r[74 + k]
        lo = base + 1
        return f"{lo} to {base + dice}" if dice > 1 else str(abs(lo))
    return _SUB.sub(num, text or "")


def _signed(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


def client_options(client_dir: str, socket_bonus_ids: set[int] | None = None) -> dict:
    """Set bonus spells (every bonus of the client's own item sets, with its text and the sets that
    have it) and socket bonuses (the enchantments WotLK items use as one)."""
    from ..dbc import DBCFile
    from ..mpq import ClientData
    cd = ClientData(client_dir)
    try:
        sets = DBCFile.from_bytes(cd.read("DBFilesClient\\ItemSet.dbc"))
        spells = DBCFile.from_bytes(cd.read("DBFilesClient\\Spell.dbc"))
        enchants = DBCFile.from_bytes(cd.read("DBFilesClient\\SpellItemEnchantment.dbc"))
        durations = {r[0]: _signed(r[1]) for r in DBCFile.from_bytes(cd.read("DBFilesClient\\SpellDuration.dbc")).records}
    finally:
        cd.close()
    by_spell = {r[0]: r for r in spells.records}
    bonus: dict[int, dict] = {}
    for r in sets.records:
        set_name = sets.get_string(r[1])
        for k in range(8):
            sp, need = r[35 + k], r[43 + k]
            row = by_spell.get(sp)
            if not sp or row is None:
                continue
            b = bonus.setdefault(sp, {"spell": sp, "name": spells.get_string(row[136]),
                                      "text": spell_text(spells.get_string(row[170]), row, by_spell, durations),
                                      "sets": [], "pieces": need})
            if len(b["sets"]) < 4:
                b["sets"].append(set_name)
    sockets = []
    for r in enchants.records:
        if socket_bonus_ids is not None and r[0] not in socket_bonus_ids:
            continue
        name = enchants.get_string(r[14])
        if name:
            sockets.append({"id": r[0], "name": name})
    return {"bonuses": sorted(bonus.values(), key=lambda b: b["text"].lower()),
            "socket_bonuses": sorted(sockets, key=lambda s: s["name"].lower())}


def spell_lookup(client_dir: str, spell_id: int) -> dict | None:
    from ..dbc import DBCFile
    from ..mpq import ClientData
    cd = ClientData(client_dir)
    try:
        spells = DBCFile.from_bytes(cd.read("DBFilesClient\\Spell.dbc"))
        durations = {r[0]: _signed(r[1]) for r in DBCFile.from_bytes(cd.read("DBFilesClient\\SpellDuration.dbc")).records}
    finally:
        cd.close()
    row = spells.find_by_id(spell_id)
    if row is None:
        return None
    by_spell = {r[0]: r for r in spells.records}
    return {"spell": spell_id, "name": spells.get_string(row[136]),
            "text": spell_text(spells.get_string(row[170]), row, by_spell, durations)}


def _json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default
