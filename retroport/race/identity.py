"""A registry race's own identity: a race past 32 that the x64 client's race registry adds.

Such a race (Earthen: 33 Alliance, 34 Horde) has no ChrRaces row in the client's tables: the
client's RaceRows (WXL/modules/runtime) copies its template race's rows at start-up, gives it its
ClientFileString (the registry's ``file=``), and draws its character from retail's data as it is.
What it copies only for want of the race's own - its random names, its voice, its racials - this
package brings: NameGen and EmotesTextSound rows of the race's id (RaceRows leaves a table that
has them alone), VocalUISounds (which it never copies) and the racials' tables. And the create
screen's pieces keyed by that file string: the race's icon, its select scene, music and texts.

Output (``out_dir``), installed with ``retroport install`` as a race package is:

* ``client\\`` - DBFilesClient (NameGen, EmotesTextSound, VocalUISounds, SoundEntries and the
  racials' Spell, SpellIcon, SkillLine, SkillLineAbility, SkillRaceClassInfo...), the voice's
  sounds, the racials' icons, Interface\\GlueXML (CharacterCreate.lua's icon block, GlueParent.lua's
  music, GlueStrings.lua's texts), the race's icon file and its select scene;
* ``server\\dbc\\`` - EmotesTextSound and the racials' tables;
* ``server\\<file>_identity.sql`` / ``_identity_undo.sql`` (world database) and
  ``<file>_racials_characters.sql`` (characters: the template races' racials off characters made
  before the race had its own);
* ``package.json``, ``INSTALL.txt``.

Racials: the race's retail racial skill line (Earthen's 2895), ported as a race package's are
(racials.py), then made what 3.3.5 can do where retail's own effects can't be (``OVERRIDES``, the
user's picks of 2026-11-03), with spells of its own beside them (``EXTRA_SPELLS``). Its
SkillRaceClassInfo row takes race bit 32, which no playable race has, and its SkillLineAbility rows
no race: the server's RaceMgr gives a race past 32 its own racial line by its id (``racials=`` in
mod_retroport_appearance.conf) and no other racial line, whatever the line's race mask says. The
spells' server half is mod-retroport-racials (retroport-tool\\native).
"""

from __future__ import annotations

import json
import os
import shutil
import struct
from dataclasses import dataclass
from typing import Callable

from PIL import Image

from ..character.convert import BfaInstall, _find_listfile_paths, _find_race
from ..dbc import DBCError, DBCFile
from ..dbclayout import DbcLayout, LayoutError
from ..formats import blp
from ..mpq import ClientData
from ..safeio import write_verified
from . import glue, icons, racials, sounds, sql
from .build import (GLUE, RACIAL_CLIENT_TABLES, RACIAL_SERVER_TABLES, RACIALS_DB2, SEXES, VOICE_DB2,
                    RaceBuildResult, _add_visuals, _is_inside, _NotOurs, _parse, _port_visuals, _previous_owns,
                    _save_tables, _select_scene, _template_racial_line, sha256)
from .spells import APPLY_AURA, ONE, BfaSpells, _f, _u, cast_time_index, duration_index, radius_index
from .tables import add_names

CLIENT_TABLES = ["NameGen", "EmotesTextSound", "VocalUISounds", "SoundEntries", "SkillLineAbility",
                 "SkillRaceClassInfo"] + RACIAL_CLIENT_TABLES
SERVER_TABLES = ["EmotesTextSound", "SkillLineAbility", "SkillRaceClassInfo"] + RACIAL_SERVER_TABLES
RACE_ROW_TABLES = ("NameGen", "EmotesTextSound", "VocalUISounds")     # column 2 is the race in each
NO_PLAYABLE_RACE = 0x80000000           # race bit 32: a SkillRaceClassInfo row no stock race matches
ICON_FILE = "Interface\\Glues\\CharacterCreate\\Retroport\\RaceIcons-{}"
ICON_CELL = 128                         # as the glue package's RaceIcons atlas (glue/build.py)
SCENES = "Interface\\Glues\\Models\\UI_{}\\"

# Spell.dbc effect columns, cleared before an override's effects are set
EFFECT_COLUMNS = ("Effect", "EffectDieSides", "EffectRealPointsPerLevel", "EffectBasePoints", "EffectMechanic",
                  "ImplicitTargetA", "ImplicitTargetB", "EffectRadiusIndex", "EffectAura", "EffectAuraPeriod",
                  "EffectAmplitude", "EffectChainTargets", "EffectItemType", "EffectMiscValue", "EffectMiscValueB",
                  "EffectTriggerSpell", "EffectPointsPerCombo", "EffectSpellClassMaskA", "EffectSpellClassMaskB",
                  "EffectSpellClassMaskC")
SCHOOL_DAMAGE, DUMMY, HEAL = 2, 3, 10
CASTER, SRC_CASTER, SRC_AREA_ENEMY, SRC_AREA_ALLY = 1, 22, 15, 30
FIRE = 4
ITEM_CLASS_GEM, GEM_COLOURS = 3, 0x1FF  # every gem subclass: red .. prismatic
TARGET_FLAG_ITEM = 0x10
ATTR0_ABILITY, ATTR0_NO_LOG, ATTR0_CANT_CANCEL = 0x10, 0x100, 0x80000000
ATTR3_DEATH_PERSISTENT = 0x100000
INFINITE = -1
RATING_PCT = "spell_retroport_rating_pct"
CRIT_RATINGS, HASTE_RATINGS, HIT_RATINGS = 0x700, 0xE0000, 0xE0     # melee, ranged, spell
STAMINA = 2


@dataclass(frozen=True)
class IdentityRace:
    race_id: int                        # client race (33)
    faction: str                        # Alliance / Horde
    template: int                       # its mask race (3 Dwarf): the racial line it no longer learns


@dataclass(frozen=True)
class Effect:
    """One Spell.dbc effect slot."""
    aura: int = 0                       # with effect APPLY_AURA (the default)
    value: int = 0
    misc: int = 0
    effect: int = APPLY_AURA
    per_level: float = 0.0              # EffectRealPointsPerLevel: value + per_level * (level - spell level)
    a: int = CASTER
    b: int = 0
    radius: float = 0.0
    period: int = 0                     # EffectAuraPeriod (ms)


@dataclass
class Override:
    """What a racial does on 3.3.5 in place of what retail's own effects say."""
    effects: tuple[Effect, ...]
    description: str
    aura: str = ""
    fields: dict | None = None          # other Spell.dbc columns
    cast_ms: int | None = None          # cast time (0: instant)
    duration_ms: int | None = None      # duration (0: none, INFINITE)
    script: str = ""                    # the module script the SQL binds
    sp_bonus: float = 0.0               # spell_bonus_data
    ap_bonus: float = 0.0
    ability: str = ""                   # its line on the create screen's racial text


@dataclass
class ExtraSpell:
    """A spell of the race's own beside its retail racials (Earthen's Ingest Gem and Well Fed
    buffs), made from a 3.3.5 spell's row (``template``) with the overrides' fields."""
    spell_id: int
    name: str
    template: int
    override: Override
    learned: bool = False               # taught with the racial line (a SkillLineAbility row)
    icon_of: int = 0                    # the retail racial whose icon it shows (0: the template's)


# --------------------------------------------------------------------------- Earthen (the user's picks)

AZERITE_SURGE, TITAN_WROUGHT_FRAME, HYPER_PRODUCTIVE = 436344, 436340, 436339
WIDE_EYED_WONDER, INGEST_MINERALS, QUIET_CONTEMPLATION = 448924, 436341, 461063
INGEST_GEM = 233901
FED = {"crit": 233910, "haste": 233911, "stamina": 233912, "versatility": 233913, "hit": 233914,
       "attack": 233915, "spell": 233916}
FED_TEMPLATE = 57367                    # a 3.3.5 Well Fed buff (Stamina and Spirit): its icon, flags
GEM_TEMPLATE = 31252                    # Prospecting: an item-target ability
FOOD_TEMPLATE = 433                     # Food: sitting, not in combat, ends on standing

OVERRIDES = {
    # retail: an empowered spell; the user's pick: one instant cast, Fire damage to enemies and a heal
    # on allies around (8 yards), level scaled with a share of spell power and attack power
    AZERITE_SURGE: Override(
        (Effect(effect=SCHOOL_DAMAGE, value=10, per_level=8.0, a=SRC_CASTER, b=SRC_AREA_ENEMY, radius=8.0),
         Effect(effect=HEAL, value=10, per_level=8.0, a=SRC_CASTER, b=SRC_AREA_ALLY, radius=8.0)),
        "Release the azerite in your body in a surge, dealing $s1 Fire damage to enemies within $a1 yards and "
        "healing allies within $a2 yards for $s2.",
        fields={"Attributes": 0, "AttributesEx": 0, "SchoolMask": FIRE, "RangeIndex": 1, "SpellLevel": 1,
                "BaseLevel": 1, "MaxLevel": 80, "RecoveryTime": 120000, "CategoryRecoveryTime": 0,
                "StartRecoveryTime": 1500, "StartRecoveryCategory": 133, "PowerType": 0, "ManaCost": 0,
                "ManaCostPct": 0, "InterruptFlags": 0, "ChannelInterruptFlags": 0, "AuraInterruptFlags": 0,
                "ProcTypeMask": 0, "ProcChance": 101},
        cast_ms=0, duration_ms=0, sp_bonus=0.4, ap_bonus=0.3, ability="Damages enemies and heals allies around you."),
    # retail's own aura (base armor %), which 3.3.5 has under the same id
    TITAN_WROUGHT_FRAME: Override((Effect(aura=142, value=10, misc=1),), "Armor from items increased by $s1%.",
                                  ability="Armor from items increased by 10%."),
    # retail: Finesse; the user's pick: +15 to the gathering skills
    HYPER_PRODUCTIVE: Override(
        (Effect(aura=30, value=15, misc=182), Effect(aura=30, value=15, misc=186), Effect(aura=30, value=15, misc=393)),
        "Herbalism, Mining and Skinning skills increased by $s1.",
        ability="Herbalism, Mining and Skinning skills increased."),
    # a dummy aura the module reads: exploration experience (XPSOURCE_EXPLORE) up by its amount
    WIDE_EYED_WONDER: Override((Effect(aura=4, value=200),),
                               "Experience gained from discovering new areas increased by $s1%.",
                               ability="Three times the experience for discovering new areas."),
    # a dummy aura: the module keeps a Well Fed buff on, keeps food away, and Ingest Gem picks the buff
    INGEST_MINERALS: Override(
        (Effect(aura=4),),
        "You are always Well Fed, but cannot eat food. Ingest Gem consumes a gem to change what your Well Fed "
        "gives by its color: red critical strike, yellow Stamina, blue damage and healing done, green haste, "
        "purple hit, orange attack power, meta spell power, any other Stamina.",
        ability="Always Well Fed; eat gems to choose what it gives. Cannot eat food."),
    # seated restore: health a % of the maximum a second (the module's script), mana 3.3.5's own % aura
    QUIET_CONTEMPLATION: Override(
        (Effect(aura=20, value=5, period=1000), Effect(aura=21, value=5, misc=0, period=1000)),
        "Draws upon your inner energy, restoring $s1% of your maximum health and $s2% of your maximum mana "
        "every sec for $d. Must remain seated during contemplation.",
        aura="Restoring $s1% of maximum health and $s2% of maximum mana every sec.",
        fields="food", duration_ms=20000, cast_ms=0, script="spell_retroport_quiet_contemplation",
        ability="Restores health and mana while seated."),
}


def _fed(key: str, effects: tuple[Effect, ...], aura: str, script: str = "") -> ExtraSpell:
    return ExtraSpell(FED[key], "Well Fed", FED_TEMPLATE, Override(
        effects, aura, aura=aura, duration_ms=INFINITE, script=script,
        fields={"SpellLevel": 1, "BaseLevel": 1, "MaxLevel": 80, "RecoveryTime": 0, "CategoryRecoveryTime": 0}))


EXTRA_SPELLS = [
    ExtraSpell(INGEST_GEM, "Ingest Gem", GEM_TEMPLATE, Override(
        (Effect(effect=DUMMY),),
        "Consume a gem, changing what your Well Fed gives by the gem's color.",
        fields={"Attributes": ATTR0_ABILITY | ATTR0_NO_LOG, "AttributesExB": 0, "Targets": TARGET_FLAG_ITEM,
                "EquippedItemClass": ITEM_CLASS_GEM, "EquippedItemSubclass": GEM_COLOURS, "SpellVisualID": 0,
                "Reagent": 0, "ReagentCount": 0},
        cast_ms=0, script="spell_retroport_ingest_gem"), learned=True, icon_of=INGEST_MINERALS),
    # the percents are ratings the module makes worth that percent at the player's level (as Ancestral
    # Call's); the flat stats grow with level to a 3.3.5 feast's at 80
    _fed("crit", (Effect(aura=189, value=1, misc=CRIT_RATINGS),), "Critical strike chance increased by $s1%.",
         RATING_PCT),
    _fed("haste", (Effect(aura=189, value=1, misc=HASTE_RATINGS),), "Haste increased by $s1%.", RATING_PCT),
    _fed("stamina", (Effect(aura=29, value=2, per_level=0.6, misc=STAMINA),), "Stamina increased by $s1."),
    # 3.3.5 has no Versatility: damage and healing done, the damage-taken half the module's (Brush It Off's)
    _fed("versatility", (Effect(aura=79, value=1, misc=127), Effect(aura=136, value=1)),
         "Damage and healing done increased by $s1%, damage taken reduced by 0.5%."),
    _fed("hit", (Effect(aura=189, value=1, misc=HIT_RATINGS),), "Chance to hit increased by $s1%.", RATING_PCT),
    _fed("attack", (Effect(aura=99, value=1, per_level=1.0), Effect(aura=124, value=1, per_level=1.0)),
         "Attack power and ranged attack power increased by $s1."),
    _fed("spell", (Effect(aura=13, value=1, per_level=0.57, misc=126), Effect(aura=135, value=1, per_level=0.57)),
         "Spell damage and healing increased by $s1."),
]
# the Earthen's: file string, display name, races, the racial id block, the voice's sound block
EARTHEN = {"file": "EarthenDwarf", "name": "Earthen", "block": 33, "voice_block": 34,
           "races": (IdentityRace(33, "Alliance", 3), IdentityRace(34, "Horde", 2))}


# --------------------------------------------------------------------------- spell rows

def _set_effects(L: DbcLayout, row: list[int], effects: tuple[Effect, ...], radii: list) -> None:
    for col in EFFECT_COLUMNS:
        for j in range(3):
            L.set(row, col, 0, j)
    for j in range(3):
        L.set(row, "EffectChainAmplitude", ONE, j)
        L.set(row, "EffectBonusCoefficient", ONE, j)
    for j, e in enumerate(effects):
        L.set(row, "Effect", e.effect, j)
        L.set(row, "EffectDieSides", 1, j)
        L.set(row, "EffectBasePoints", _u(e.value - 1), j)
        L.set(row, "EffectRealPointsPerLevel", _f(e.per_level), j)
        L.set(row, "ImplicitTargetA", e.a, j)
        L.set(row, "ImplicitTargetB", e.b, j)
        if e.radius:
            L.set(row, "EffectRadiusIndex", radius_index(radii, e.radius), j)
        if e.effect == APPLY_AURA:
            L.set(row, "EffectAura", e.aura, j)
        L.set(row, "EffectAuraPeriod", e.period, j)
        L.set(row, "EffectMiscValue", _u(e.misc), j)


def _set_fields(L: DbcLayout, row: list[int], o: Override, index_tables: dict, food: list[int] | None) -> None:
    fields = o.fields
    if fields == "food":
        # 3.3.5's Food: sits the caster, not in combat, ends on standing (AzerothCore sits the player
        # for an aura with the not-seated interrupt)
        fields = {k: L.get(food, k) for k in ("Attributes", "AuraInterruptFlags", "InterruptFlags")} | {
            "ChannelInterruptFlags": 0, "RecoveryTime": 0, "CategoryRecoveryTime": 0, "Category": 0,
            "ProcTypeMask": 0}
    for k, v in (fields or {}).items():
        if k in ("Reagent", "ReagentCount"):
            for j in range(8):
                L.set(row, k, v, j)
        else:
            L.set(row, k, _u(v))
    if o.cast_ms is not None:
        L.set(row, "CastingTimeIndex", cast_time_index(index_tables["SpellCastTimes"], o.cast_ms))
    if o.duration_ms is not None:
        L.set(row, "DurationIndex", duration_index(index_tables["SpellDuration"], o.duration_ms)
              if o.duration_ms else 0)


def apply_overrides(plan: racials.RacialPlan, layout: DbcLayout, index_tables: dict, food: list[int] | None,
                    overrides: dict[int, Override]) -> list[str]:
    """Each overridden racial's row made the override's (its companions gone: one row holds it)."""
    notes = []
    for s, o in overrides.items():
        p = plan.ported.get(s)
        if p is None:
            notes.append(f"{s}: not among the racials; its override is unused")
            continue
        row = p.rows[0]
        _set_effects(layout, row, o.effects, index_tables["SpellRadius"])
        _set_fields(layout, row, o, index_tables, food)
        p.rows, p.pet_rows, p.pet_auras = [row], [], []
        p.dropped, p.translated, p.scripted = [], [], []
        p.effects = {j: ("slot", 0, j) for j in range(len(o.effects))}
        p.proc_flags, p.ap_bonus, p.script = 0, o.ap_bonus, o.script
        notes.append(f"{p.name}: made the 3.3.5 form the user picked ({len(o.effects)} effect(s))")
    return notes


def extra_rows(extras: list[ExtraSpell], spell_table, layout: DbcLayout, index_tables: dict, food: list[int] | None,
               icon_ids: dict[int, int], icon_of: dict[int, int]) -> list[tuple[ExtraSpell, list[int]]]:
    """Each extra spell's Spell.dbc row from its template's in ``spell_table`` (the client's or
    server's), without texts."""
    out = []
    for x in extras:
        tpl = spell_table.find_by_id(x.template)
        if tpl is None:
            raise DBCError(f"Spell.dbc has no spell {x.template} ({x.name}'s template)")
        row = list(spell_table.row(tpl) if not isinstance(tpl, list) else tpl)
        row[0] = x.spell_id
        _set_effects(layout, row, x.override.effects, index_tables["SpellRadius"])
        _set_fields(layout, row, x.override, index_tables, food)
        if x.spell_id in FED.values():
            layout.set(row, "Attributes", layout.get(row, "Attributes") | ATTR0_CANT_CANCEL)
            layout.set(row, "AttributesExC", layout.get(row, "AttributesExC") | ATTR3_DEATH_PERSISTENT)
        if x.icon_of and icon_ids.get(icon_of.get(x.icon_of, 0)):
            layout.set(row, "SpellIconID", icon_ids[icon_of[x.icon_of]])
        out.append((x, row))
    return out


def _drop_spells(table, ids: set[int]) -> int:
    packed = {struct.pack("<I", i) for i in ids}
    before = len(table.records)
    table.records = [r for r in table.records
                     if (r[:4] if isinstance(r, (bytes, bytearray)) else struct.pack("<I", r[0])) not in packed]
    return before - len(table.records)


def _add_extras(table, layout: DbcLayout, rows: list[tuple[ExtraSpell, list[int]]]) -> int:
    for x, row in rows:
        if table.find_by_id(row[0]) is not None:
            raise DBCError(f"Spell.dbc already has spell {row[0]} ({x.name})")
        row = list(row)
        for col, text in (("Name_lang", x.name), ("NameSubtext_lang", ""), ("Description_lang", x.override.description),
                          ("AuraDescription_lang", x.override.aura)):
            layout.set_text(table, row, col, text)
        table.add_row(row)
    return len(rows)


# --------------------------------------------------------------------------- the build

def _texts(overrides: dict[int, Override]) -> dict[int, dict[str, str]]:
    return {s: {"description": o.description, "aura": o.aura or o.description} for s, o in overrides.items()}


def build_identity(*, install_dir: str, client_dir: str, out_dir: str, listfile: str, dbd_dir: str,
                   server_dbc_dir: str, race: str = EARTHEN["file"], name: str = EARTHEN["name"],
                   races: tuple[IdentityRace, ...] = EARTHEN["races"], block: int = EARTHEN["block"],
                   voice_block: int = EARTHEN["voice_block"], product: str | None = "wow",
                   patch: str = "patch-H.MPQ", overrides: dict[int, Override] | None = None,
                   extras: list[ExtraSpell] | None = None,
                   on_log: Callable[[str], None] | None = None) -> RaceBuildResult:
    """The identity package of the registry race ``race`` (a retail ClientFileString) for
    ``races`` (ids past 32, their mask races the templates). Rebuilds over its own earlier install."""
    log = on_log or (lambda m: None)
    overrides = OVERRIDES if overrides is None else overrides
    extras = EXTRA_SPELLS if extras is None else extras
    for p in (client_dir, server_dbc_dir):
        if p and _is_inside(out_dir, p):
            raise ValueError(f"output folder {out_dir} is inside {p} - pick a separate folder")
    if not all(r.race_id > 32 for r in races):
        raise ValueError("an identity package is for registry races past 32; `retroport race` builds 1-32")
    client_out = os.path.join(out_dir, "client")
    os.makedirs(client_out, exist_ok=True)
    key = race.upper()
    ids = [r.race_id for r in races]
    res = RaceBuildResult(race=race, name=name, races=[r.__dict__ for r in races])

    # --- tables, as the client and the server load them ---
    log(f"Reading {client_dir} ...")
    client = ClientData(client_dir, top=patch)
    layouts = {t: DbcLayout(t, dbd_dir) for t in set(RACIAL_CLIENT_TABLES + RACIAL_SERVER_TABLES + ["SoundEntries"])}
    ctables, stables = {}, {}
    for t in CLIENT_TABLES:
        hit = client.find(f"DBFilesClient\\{t}.dbc")
        if hit is None:
            raise DBCError(f"{t}.dbc is not in any archive of the client")
        res.client_sources[t] = hit[0]
        res.bases[f"client/DBFilesClient/{t}.dbc"] = {"source": hit[0], "sha256": sha256(hit[1])}
        ctables[t] = _parse(t, hit[1], layouts)
    for t in SERVER_TABLES:
        path = os.path.join(server_dbc_dir, f"{t}.dbc")
        if not os.path.isfile(path):
            raise DBCError(f"{path} not found - is this the server's DBC folder?")
        with open(path, "rb") as fh:
            data = fh.read()
        res.bases[f"server/dbc/{t}.dbc"] = {"source": path, "sha256": sha256(data)}
        stables[t] = _parse(t, data, layouts)
    bfa = BfaInstall(install_dir, dbd_dir, listfile, product=product)
    bfa.fdids.update(_find_listfile_paths(listfile, {f"dbfilesclient/{t}.db2" for t in
                                                     ("uitextureatlas", "uitextureatlasmember", "globalstrings",
                                                      "chrraces", "namegen") + VOICE_DB2 + RACIALS_DB2}))
    source_race, _row = _find_race(bfa, race)

    # --- its racials, ported and made 3.3.5's (before anything is taken out: their ids say what to) ---
    spells = BfaSpells(bfa, lambda paths: _find_listfile_paths(listfile, paths))
    plan = racials.plan_racials(bfa, spells, source_race)
    if plan is None:
        raise ValueError(f"retail has no racial skill line for {race}")
    index_tables = {t: [ctables[t], stables[t]] for t in ("SpellCastTimes", "SpellDuration", "SpellRange",
                                                          "SpellRadius")}
    try:
        notes = racials.port_racials(plan, spells, layout=layouts["Spell"], index_tables=index_tables,
                                     range_layout=layouts["SpellRange"], block=block,
                                     listfile_names=lambda fdids: sounds.listfile_names(listfile, fdids),
                                     skills={r[0] for r in ctables["SkillLine"].records}
                                     & {r[0] for r in stables["SkillLine"].records})
    except (racials.RacialsError, LayoutError) as e:
        raise ValueError(f"racials: {e}") from e
    plan.source = spells
    L = layouts["Spell"]
    food = ctables["Spell"].find_by_id(FOOD_TEMPLATE)
    food = ctables["Spell"].row(food) if food is not None and not isinstance(food, list) else food
    notes = [n for n in notes if n.split(":", 1)[0] not in {plan.ported[s].name for s in overrides if s in plan.ported}]
    notes += apply_overrides(plan, L, index_tables, food, overrides)
    log(f"  racials: retail's {plan.name} ({plan.skill_line}): "
        + ", ".join(plan.ported[a].name for a in plan.abilities)
        + (f"; and {', '.join(sorted({x.name for x in extras}))} of its own" if extras else ""))

    # --- what an earlier build of the package added goes first ---
    extra_ids = {x.spell_id for x in extras}
    for label, tables in (("client", ctables), ("server", stables)):
        gone = racials.strip_racials(tables, plan)
        n = _drop_spells(tables["Spell"], extra_ids)
        if n:
            gone["Spell"] = gone.get("Spell", 0) + n
        for t in RACE_ROW_TABLES:
            if t in tables:
                before = len(tables[t].records)
                tables[t].records = [r for r in tables[t].records if r[2] not in ids]
                if len(tables[t].records) != before:
                    gone[t] = before - len(tables[t].records)
        if "SoundEntries" in tables:
            lo = racials.block_base(voice_block)
            before = len(tables["SoundEntries"].records)
            tables["SoundEntries"].records = [r for r in tables["SoundEntries"].records
                                              if not lo <= r[0] < lo + racials.BLOCK_SIZE]
            if len(tables["SoundEntries"].records) != before:
                gone["SoundEntries"] = gone.get("SoundEntries", 0) + before - len(tables["SoundEntries"].records)
        if gone:
            log(f"  {label}: took out the earlier build's rows: {gone}")

    res.rows = {"client": {}, "server": {}}

    def bump(side: str, t: str, n: int) -> None:
        if n:
            res.rows[side][t] = res.rows[side].get(t, 0) + n

    # --- random names ---
    names = [(str(r["Name"]), int(r["Sex"])) for _i, r in sorted(bfa.table("NameGen"), key=lambda t: t[0])
             if r["RaceID"] == source_race and int(r["Sex"]) in (0, 1) and r["Name"]]
    if names:
        for rid in ids:
            bump("client", "NameGen", add_names(ctables["NameGen"], rid, names))
        log(f"  random names: retail's, {sum(1 for _n, s in names if s == 0)} male and "
            f"{sum(1 for _n, s in names if s == 1)} female")
    else:
        res.warnings.append("random names: retail has none for the race; it keeps its template's")

    # --- voice: emote sounds and spoken errors (combat sounds go by display: its template's) ---
    try:
        hit = client.find("DBFilesClient\\EmotesText.dbc")
        if hit is None:
            raise DBCError("EmotesText.dbc is not in any archive of the client")
        voice = sounds.collect_voice(bfa.table, source_race, race, emotes={r[0] for r in DBCFile.from_bytes(hit[1]).records},
                                     vocal_enums={r[1] for r in ctables["VocalUISounds"].records},
                                     names=lambda fdids: sounds.listfile_names(listfile, fdids))
        used = set(voice.emotes.values()) | {k for pair in voice.vocal.values() for k in pair if k}
        voice.kits = {k: v for k, v in voice.kits.items() if k in used}
        voice.creature = {}
        files = sounds.write_voice_files(bfa.read, voice, client_out)
        res.files += files
        res.owns += [os.path.relpath(f, client_out).lower() for f in files]
        res.warnings += [f"voice: {s}" for s in voice.skipped if "combat sounds" not in s and "Player" not in s]
        sound_ids = {kit: racials.block_base(voice_block) + i for i, kit in enumerate(sorted(voice.kits))}
        if len(sound_ids) >= racials.BLOCK_SIZE:
            raise ValueError(f"{len(sound_ids)} sounds: more than the voice block holds")
        bump("client", "SoundEntries", sounds.add_sound_entries(ctables["SoundEntries"], voice, sound_ids))
        for rid in ids:
            if voice.emotes:
                bump("client", "EmotesTextSound", sounds.add_emote_sounds(ctables["EmotesTextSound"], voice, rid, sound_ids))
                bump("server", "EmotesTextSound", sounds.add_emote_sounds(stables["EmotesTextSound"], voice, rid, sound_ids))
            if voice.vocal:
                bump("client", "VocalUISounds", sounds.add_vocal_sounds(ctables["VocalUISounds"], voice, rid, sound_ids))
        log(f"  voice: {len(voice.kits)} sounds ({len(files)} files): {len(voice.emotes)} emote sounds, "
            f"{len(voice.vocal)} spoken errors")
    except (ValueError, KeyError) as e:
        res.warnings.append(f"voice: {e}; the race speaks with its template's voice")

    # --- racials: icons, visuals, spells, skill line, who learns it ---
    notes += _port_visuals(bfa, plan, race, listfile, client, client_out, out_dir, ctables, layouts, res, log)
    work = os.path.join(out_dir, "_work")
    os.makedirs(work, exist_ok=True)
    plan.icon_ids = racials.add_icons(ctables["SpellIcon"], plan)
    bump("client", "SpellIcon", len(plan.icon_ids))
    for fdid, path in plan.icons.items():
        rel = path + ".blp"
        src = write_verified(os.path.join(work, f"icon_{fdid}.blp"), bfa.read(fdid))
        img = blp.decode(src)
        out = os.path.join(client_out, *rel.split("\\"))
        res.files.append(write_verified(out, blp.encode_dxt(img), lambda p, size=img.size: blp.verify_blp(p, size)))
        res.owns.append(rel.lower())
    visual_ids = {bfa_id: pv.visual[0] for bfa_id, pv in plan.visuals.items()}
    if plan.visuals:
        for k, v in _add_visuals(ctables, plan, layouts, client_out, bfa,
                                 _NotOurs(client, _previous_owns(out_dir)), res).items():
            bump("client", k, v)
    icon_of = {s: p.icon_fdid for s, p in plan.ported.items()}
    texts = _texts(overrides)
    for side, tables in (("client", ctables), ("server", stables)):
        template_line = _template_racial_line(tables, layouts, races[0].template)
        bump(side, "Spell", racials.add_spells(tables["Spell"], L, plan, spells, plan.icon_ids, visual_ids, texts))
        bump(side, "Spell", _add_extras(tables["Spell"], L, extra_rows(extras, tables["Spell"], L, index_tables, food,
                                                                        plan.icon_ids, icon_of)))
        racials.add_skill_line(tables["SkillLine"], layouts["SkillLine"], template_line, plan)
        bump(side, "SkillLine", 1)
        bump(side, "SkillRaceClassInfo", racials.add_race_class_info(tables["SkillRaceClassInfo"], template_line, plan,
                                                                     NO_PLAYABLE_RACE))
        bump(side, "SkillLineAbility", racials.add_abilities(tables["SkillLineAbility"], template_line, plan, 0))
        # the extra spells it learns: rows after the racials' in its block
        tpl = next(r for r in tables["SkillLineAbility"].records if r[1] == plan.skill_line)
        for k, x in enumerate(x for x in extras if x.learned):
            row = list(tpl)
            row[0], row[2] = racials.block_base(block) + len(plan.learned) + k, x.spell_id
            tables["SkillLineAbility"].add_record(row)
            bump(side, "SkillLineAbility", 1)
    res.racials = {"skill_line": plan.skill_line, "name": plan.name,
                   "spells": {str(i): spells.names.get(i, "") for i in plan.spell_ids}
                   | {str(x.spell_id): x.name for x in extras}, "notes": notes}
    res.warnings += [f"racials: {n}" for n in notes if "made the 3.3.5 form" not in n]

    dbc_out = os.path.join(client_out, "DBFilesClient")
    sdir = os.path.join(out_dir, "server", "dbc")
    os.makedirs(dbc_out, exist_ok=True)
    os.makedirs(sdir, exist_ok=True)
    _save_tables(ctables, dbc_out, "client/DBFilesClient", res)
    _save_tables(stables, sdir, "server/dbc", res)

    # --- create screen: icon, scene, music, texts (keyed by its ClientFileString) ---
    def read_base(rel: str) -> str:
        hit = client.find(rel)
        if hit is None:
            raise DBCError(f"{rel} is not in any archive of the client")
        res.bases["client/" + rel.replace("\\", "/")] = {"source": hit[0], "sha256": sha256(hit[1])}
        return hit[1].decode("utf-8", "replace")

    lua = read_base(GLUE + "CharacterCreate.lua")
    parent = read_base(GLUE + "GlueParent.lua")
    strings = read_base(GLUE + "GlueStrings.lua")
    if not glue.bfa_style(lua):
        raise ValueError("the client's create screen is not the glue package's (retroport glue): a registry "
                         "race's icon needs its RACE_ICON_ATLAS")
    icon_lines = _race_icon(bfa, race, key, client_out, work, res, log)
    lua = glue.put_block(lua, f"icons {key}", "\n".join(icon_lines))
    own_scene = _select_scene(bfa, race, client, client_out, work, listfile, res, log)
    if own_scene:
        res.owns.append((SCENES.format(race)).lower())
    template_file = "DWARF" if races[0].template == 3 else "ORC"
    parent = glue.patch_glue_parent(parent, {} if own_scene else {key: template_file}, key, music={key: template_file})
    gs = {str(r.get("BaseTag", "")): str(r.get("TagText_lang", "")) for _i, r in bfa.table("GlobalStrings")}
    text = {k: v for k, v in gs.items() if k in (f"RACE_INFO_{key}", f"RACE_INFO_{key}_FEMALE")}
    if f"RACE_INFO_{key}" not in text:
        res.warnings.append("no race description in the retail install; wrote a placeholder")
        text[f"RACE_INFO_{key}"] = f"{name}."
    text[f"{key}_DISABLED"] = f"{name} is not available."
    abilities = [a for a in plan.abilities if plan.ported[a].name]
    for n, a in enumerate(abilities, 1):
        o = overrides.get(a)
        text[f"ABILITY_INFO_{key}{n}"] = "- " + (o.ability if o and o.ability else plan.ported[a].name)
    strings = glue.patch_glue_strings(strings, text, key)
    for fname, body in (("CharacterCreate.lua", lua), ("GlueParent.lua", parent), ("GlueStrings.lua", strings)):
        res.files.append(write_verified(os.path.join(client_out, *GLUE.split("\\"), fname), body.encode("utf-8")))
    shutil.rmtree(work, ignore_errors=True)

    # --- server SQL ---
    excluded = sorted(racials.racial_skill_lines(stables["SkillLine"], layouts["SkillLine"]) - {plan.skill_line})
    old_lines = {_template_racial_line(stables, layouts, r.template) for r in races}
    scripts = {s: o.script for s, o in overrides.items() if o.script and s in plan.ported}
    scripts.update({x.spell_id: x.override.script for x in extras if x.override.script})
    racial_sql = sql.RacialSql(
        plan.skill_line, plan.name, excluded,
        ap_bonus={s: o.ap_bonus for s, o in overrides.items() if o.ap_bonus and s in plan.ported},
        sp_bonus={s: o.sp_bonus for s, o in overrides.items() if o.sp_bonus and s in plan.ported},
        scripts=scripts,
        old_spells=sorted({row[2] for row in stables["SkillLineAbility"].records if row[1] in old_lines}))
    install, undo = _identity_sql(name, races, racial_sql)
    sroot = os.path.join(out_dir, "server")
    res.files.append(write_verified(os.path.join(sroot, f"{race}_identity.sql"), install.encode("utf-8")))
    res.files.append(write_verified(os.path.join(sroot, f"{race}_identity_undo.sql"), undo.encode("utf-8")))
    res.files.append(write_verified(os.path.join(sroot, f"{race}_racials_characters.sql"),
                                    sql.characters_cleanup_sql(list(races), name, racial_sql).encode("utf-8")))

    _write_package(out_dir, res, races, client_dir, server_dbc_dir, patch)
    log(f"Done: {out_dir}")
    return res


def _race_icon(bfa: BfaInstall, race: str, key: str, client_out: str, work: str, res: RaceBuildResult,
               log: Callable[[str], None]) -> list[str]:
    """The race's create-screen icons (retail's raceicon-<name>-<sex>, upscaled as the glue
    package's) in a file of its own, and the icon block's lines naming it."""
    atlases = {i: r for i, r in bfa.table("UiTextureAtlas")}
    members = {str(r["CommittedName"]).lower(): r for _i, r in bfa.table("UiTextureAtlasMember")}
    short = race.lower().removesuffix("dwarf") if f"raceicon-{race.lower()}-male" not in members else race.lower()
    src = {sx: members.get(f"raceicon-{short}-{sx.lower()}") for sx in SEXES}
    if not all(src.values()):
        res.warnings.append(f"race icons: no raceicon-{short}-male/female in retail's atlas list; the create "
                            "screen shows the Human icon")
        return []
    sheet = Image.new("RGBA", (ICON_CELL * 2, ICON_CELL), (0, 0, 0, 0))
    for col, sx in enumerate(SEXES):
        m = src[sx]
        fdid = atlases[m["UiTextureAtlasID"]]["FileDataID"]
        p = os.path.join(work, f"atlas{fdid}.blp")
        if not os.path.isfile(p):
            write_verified(p, bfa.read(fdid))
        cell = icons.crop_atlas_member(blp.decode(p), m).convert("RGBA")
        sheet.paste(cell.resize((ICON_CELL, ICON_CELL), Image.Resampling.LANCZOS), (col * ICON_CELL, 0))
    rel = ICON_FILE.format(race)
    res.files.append(write_verified(os.path.join(client_out, *(rel + ".blp").split("\\")), blp.encode_bgra(sheet),
                                    blp.verify_blp))
    res.owns.append((rel + ".blp").lower())
    log(f"  race icons: retail's raceicon-{short}-male/female, {ICON_CELL} pixels, in {rel}")
    path = glue.lua_string(rel)
    return ["RACE_ICON_ATLAS = RACE_ICON_ATLAS or {};",
            f'RACE_ICON_ATLAS["{key}_MALE"] = {{0, 0.5, 0, 1, {path}}};',
            f'RACE_ICON_ATLAS["{key}_FEMALE"] = {{0.5, 1, 0, 1, {path}}};']


def _identity_sql(name: str, races: tuple[IdentityRace, ...], racial: sql.RacialSql) -> tuple[str, str]:
    """(install, undo) world SQL: the racial line every race its SkillRaceClassInfo rows allow learns
    (race mask 0: AzerothCore asks GetSkillRaceClassInfo, which gives a race past 32 its own line
    alone), and the racials' server rows. The races' own rows (start, stats) are the registry's."""
    ids = ", ".join(str(r.race_id) for r in races)
    out = [f"-- {name} (races {ids}): its own racials for AzerothCore (world database), generated by retroport.",
           "-- Needs the core's RaceMgr racial lines (racials= in mod_retroport_appearance.conf) and the module",
           "-- mod-retroport-racials. Re-applying is safe. Undo: the matching *_undo.sql.", ""]
    undo = [f"-- Removes what the {name} identity SQL added.", ""]
    lines, undo_lines = sql.racial_sql_lines(racial, 0)
    return "\n".join(out + lines) + "\n", "\n".join(undo + undo_lines) + "\n"


def _write_package(out_dir: str, res: RaceBuildResult, races: tuple[IdentityRace, ...], client_dir: str,
                   server_dbc_dir: str, patch: str) -> None:
    manifest = res.model_dump()
    manifest["race"] = ""               # no race folders: the files it owns are listed (owns)
    manifest["owns"] = sorted(set(res.owns))
    manifest["kind"] = "identity"
    write_verified(os.path.join(out_dir, "package.json"), json.dumps(manifest, indent=1).encode("utf-8"))
    ids = ", ".join(f"{r.race_id} ({r.faction}, mask race {r.template})" for r in races)
    lines = [f"{res.name} ({res.race}) - a registry race's own names, voice, create screen and racials, built by retroport",
             "", f"Races: {ids}", "",
             "INSTALL: retroport install - it never overwrites a file you changed since this build, backs up",
             "everything it replaces, and writes an undo receipt:",
             f"  retroport install \"{out_dir}\" --client \"{client_dir}\" --patch {patch} --server-dbc \"{server_dbc_dir}\"",
             "  (shows the plan; add --apply to install; undo: retroport uninstall <installs\\...json>)", "",
             "CLIENT: the x64 client's wxl-races.cfg row of each race needs file=" + res.race
             + f" and racials={res.racials.get('skill_line')}.",
             "SERVER",
             f"  1. server\\dbc\\*.dbc go into {server_dbc_dir} (install does this, with backups).",
             f"  2. mod_retroport_appearance.conf: the races' rows need racials={res.racials.get('skill_line')}.",
             f"  3. Apply server\\{res.race}_identity.sql to the world database (undo: {res.race}_identity_undo.sql);",
             f"     optional, for the CHARACTERS database: server\\{res.race}_racials_characters.sql takes the mask",
             "     races' racial spells off characters made before.",
             "  4. The module mod-retroport-racials (retroport-tool\\native) runs the racials' scripts.",
             "  5. Restart worldserver.", "", "Client DBC sources:"]
    lines += [f"  {t}: {src}" for t, src in res.client_sources.items()]
    if res.warnings:
        lines += ["", "Warnings:"] + [f"  - {w}" for w in res.warnings]
    write_verified(os.path.join(out_dir, "INSTALL.txt"), ("\r\n".join(lines) + "\r\n").encode("utf-8"))
