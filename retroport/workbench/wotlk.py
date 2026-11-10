"""WotLK's own item numbers, for the Stats step - from Wrath Classic's tables on wago.tools.

Install makes every item a level-1 cosmetic copy. The Stats step gives them real stats, and the
numbers it suggests are WotLK's: Wrath Classic (3.4.5) carries every WotLK item as it was, and the
tables its items were made with. From them, once (cached):

* **every equippable WotLK item** with its stats, armour, damage, speed, sockets, durability and
  price - to copy one onto a piece, and to measure the rest from;
* **the stat budget** by item level, quality and slot group (RandPropPoints - the 3.3.5 client
  has the same table);
* **weapon damage per second** by item level and quality (ItemDamageOneHand, TwoHand, Ranged,
  Wand and the caster tables);
* **armour, durability, speed and sell price** as the real items of the same slot, type and quality
  have them: the median at each item level (a curve to interpolate along).

Checked against real items: an epic plate chest at item level 264 gets 308 budget points, and
Sanctified Scourgelord Battleplate's 169 Strength, 185 Stamina, 108 crit and 92 armour penetration
cost 314 (WotLK's costs: a point of Stamina 2/3, attack power 1/2, spell power 6/7, the 1.5-power sum).
"""

from __future__ import annotations

import gzip
import json
import os
import statistics
import threading
from collections import defaultdict

from .catalog import SourceSpec

BUILD = "3.4.5.63697"                      # Wrath Classic, the build these numbers were checked at
VERSION = 1
DPS_TABLES = ("ItemDamageOneHand", "ItemDamageTwoHand", "ItemDamageRanged", "ItemDamageWand",
              "ItemDamageOneHandCaster", "ItemDamageTwoHandCaster")
WEAPON, ARMOUR = 2, 4
_lock = threading.Lock()


def _rows(src, name: str) -> list[dict]:
    return [r for _i, r in src.table(name)]


def build(src, log=lambda m: None) -> dict:
    """The reference from Wrath Classic's tables (``src``: a reader of that build)."""
    log("WotLK reference: reading Wrath Classic's items")
    base = {r["ID"]: r for r in _rows(src, "Item")}
    items, curves = [], defaultdict(list)
    for r in _rows(src, "ItemSparse"):
        b = base.get(r["ID"])
        inv = r["InventoryType"]
        if b is None or not inv or inv in (18, 24, 27) or r["OverallQualityID"] < 1 or r["ItemLevel"] < 5:
            continue                                      # bags, ammo, quivers, junk
        cls, sub = b["ClassID"], b["SubclassID"]
        if cls not in (WEAPON, ARMOUR):
            continue
        stats = [[t, v] for t, v in zip(r["StatModifier_bonusStat"], r["StatModifier_bonusAmount"]) if t > 0 and v]
        sockets = [s for s in r["SocketType"] if s]
        rec = [r["ID"], r["Display_lang"], r["ItemLevel"], r["RequiredLevel"], r["OverallQualityID"], inv, cls, sub,
               stats, r["Resistances"][0], r["MinDamage"][0], r["MaxDamage"][0], r["ItemDelay"], sockets,
               r["Socket_match_enchantment_ID"], r["MaxDurability"], r["SellPrice"], r["Bonding"], r["AllowableClass"],
               r["ItemSet"], b.get("Material", 0)]
        items.append(rec)
        key = f"{cls}:{sub}:{inv}:{r['OverallQualityID']}"
        curves[key].append((r["ItemLevel"], r["Resistances"][0], r["MaxDurability"], r["SellPrice"], r["ItemDelay"]))
    ref = {"version": VERSION, "build": BUILD, "items": items, "rpp": {}, "dps": {},
           "armor": {}, "durability": {}, "price": {}, "delay": {}}
    for r in _rows(src, "RandPropPoints"):
        ref["rpp"][r["ID"]] = [*r["Epic"], *r["Superior"], *r["Good"]]
    for name in DPS_TABLES:
        try:
            ref["dps"][name] = {r["ItemLevel"]: list(r["Quality"]) for r in _rows(src, name)}
        except Exception as e:                            # a table this build lacks: no suggestion from it
            log(f"WotLK reference: {name}: {e}")
    for key, pts in curves.items():
        by_level = defaultdict(list)
        for p in pts:
            by_level[p[0]].append(p)
        ref["armor"][key] = _curve(by_level, 1)
        ref["price"][key] = _curve(by_level, 3)
        dur = [p[2] for p in pts if p[2] > 0]
        ref["durability"][key] = int(statistics.median(dur)) if dur else 0
        delay = [p[4] for p in pts if p[4] > 0]
        if delay:
            ref["delay"][key] = int(statistics.median(delay))
    log(f"WotLK reference: {len(items)} items")
    return ref


def _curve(by_level: dict, k: int) -> list[list[int]]:
    """[[item level, median value], ...] where the value is set (0 armour: a piece without)."""
    out = []
    for lvl in sorted(by_level):
        vals = [p[k] for p in by_level[lvl] if p[k] > 0]
        if vals:
            out.append([lvl, int(statistics.median(vals))])
    return out


def load(cache_dir: str, log=lambda m: None, make_source=None) -> dict:
    """The reference, from the cache or built (and cached) from wago.tools."""
    path = os.path.join(cache_dir, f"wotlk-reference-v{VERSION}-{BUILD}.json.gz")
    with _lock:
        if os.path.isfile(path):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                pass
        if make_source is None:
            from .wago import WagoSource
            make_source = lambda: WagoSource(SourceSpec("wotlk", "Wrath Classic", kind="wago", product="wow_classic",
                                                        build=BUILD, browse=False), cache_dir)
        ref = build(make_source(), log)
        os.makedirs(cache_dir, exist_ok=True)
        with gzip.open(path + ".part", "wt", encoding="utf-8") as fh:
            json.dump(ref, fh, separators=(",", ":"))
        os.replace(path + ".part", path)
        return ref


ITEM_FIELDS = ("id", "name", "ilvl", "req", "quality", "inv", "cls", "sub", "stats", "armor", "dmg_min", "dmg_max",
               "delay", "sockets", "socket_bonus", "durability", "sell", "bonding", "classes", "itemset", "material")


def search(ref: dict, q: str = "", inv: int = 0, cls: int = 0, sub: int = -1, limit: int = 60) -> list[dict]:
    """WotLK items to copy from: by name, the same slot (a robe answers for a chest) and type first."""
    words = q.lower().split()
    same_slot = {5: (5, 20), 20: (5, 20), 13: (13, 21, 22), 21: (13, 21), 22: (13, 22), 15: (15, 26), 26: (15, 26)}
    slots = same_slot.get(inv, (inv,)) if inv else None
    hits = []
    for r in ref["items"]:
        if slots and r[5] not in slots:
            continue
        if cls and r[6] != cls:
            continue
        if words and not all(w in r[1].lower() for w in words):
            continue
        hits.append(r)
    hits.sort(key=lambda r: (sub >= 0 and r[7] != sub, -r[2], -r[4], r[1]))
    return [dict(zip(ITEM_FIELDS, r)) for r in hits[:limit]]


def tables(ref: dict) -> dict:
    """What the page needs to suggest numbers on its own: budgets, damage, the curves."""
    return {k: ref[k] for k in ("build", "rpp", "dps", "armor", "durability", "price", "delay")}
