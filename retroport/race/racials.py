"""A race's own racials from BfA in place of its faction template's.

BfA's "Racial - <Race>" skill line (a Kul Tiran's 2723) and the abilities it teaches become 3.3.5
spells (spells.py) with BfA's icons, under a 3.3.5 skill line of the same id: its SkillLineAbility
rows teach them to the race's ids, a SkillRaceClassInfo row gives the race the skill, and the
server SQL (sql.py) has every new character of the race learn it - AzerothCore also teaches it
to existing ones at login (Player::LearnDefaultSkills). The template race's racial skill line
(Human's, Orc's) is no longer copied onto the race: tables.add_race_bit skips racial lines.

"Languages" (each BfA race's spell saying which it speaks) is left out: 3.3.5's languages are
skill lines the template already gives.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from ..dbc import DBCError, DBCFile, RawDBC
from ..dbclayout import DbcLayout
from .spells import BfaSpells, PortedSpell, SpellPortError, pet_texts, port_spell, spell_texts

# what BfA does in a server script, mod-retroport-racials (retroport-tool\native) does: the spells
# it scripts (spell -> ScriptName, bound by the race's SQL with a spell_proc row for its procs)
SCRIPTS = {291628: "spell_retroport_brush_it_off",       # Kul Tiran: Brush It Off
           274738: "spell_retroport_ancestral_call"}     # Mag'har Orc: Ancestral Call
# the spells a scripted racial casts, ported with it: Ancestral Call's four clan buffs (crit,
# haste, mastery, versatility; its tooltip names two)
SCRIPT_CASTS = {274738: (274739, 274740, 274741, 274742)}
# spells whose amount the script sets itself (Brush It Off's heal): no spell power on top
SCRIPT_AMOUNTS = {291843}
# tooltips that say what 3.3.5 does where the source's can't: 3.3.5 characters have no mastery
# or versatility to rank, so Ancestral Call grants one of the four at random (BfA's own rule:
# "a random secondary stat"; retail's "one of your two highest")
TEXTS = {274738: {"description": "Invoke the spirits of your ancestors, granting you one of their powers at random "
                                 "for $274739d: $274739s1% critical strike chance, $274740s1% haste, $274741s1% more "
                                 "damage and healing done, or $274742s1% more damage and healing done and less "
                                 "damage taken."}}
# what a racial does to other spells, a module script on those spells does: racial -> (ScriptName,
# the 3.3.5 spells' name it goes on). Pandaren: Epicurean gives every Well Fed buff more. The rest
# of the Pandaren's (Bouncy, Inner Peace) the module does by the racial's aura alone.
BOUND_SCRIPTS = {107072: ("spell_retroport_epicurean", "Well Fed")}
RACIAL_CATEGORY = 9             # 3.3.5 SkillLine.CategoryID of racial lines (and riding, cooking...)
SKIPPED_ABILITIES = {"Languages"}
COMPANION_BLOCK = 100           # companion spell ids: one block per race (after BfA's own ids)
BLOCK_BASE, BLOCK_SIZE = 200000, 1000   # a race's own ids in each table: BLOCK_BASE + race id * BLOCK_SIZE
ICON_DIR = "Interface\\Icons\\"
_SPELL_REF = re.compile(r"\$@?(?:spelldesc)?(\d{4,})")


class RacialsError(ValueError):
    pass


@dataclass
class RacialPlan:
    skill_line: int                                 # BfA's id, kept as the 3.3.5 one
    name: str                                       # "Racial - Kul Tiran"
    abilities: list[int]                            # the spells the skill teaches, in BfA's order
    helpers: list[int] = field(default_factory=list)  # spells they cast or name (a heal they apply)
    ported: dict[int, PortedSpell] = field(default_factory=dict)
    icons: dict[int, str] = field(default_factory=dict)       # BfA icon fdid -> 3.3.5 path (no extension)
    icon_ids: dict[int, int] = field(default_factory=dict)    # BfA icon fdid -> SpellIcon id (the client's)
    source: object = None                                      # the BfaSpells the plan was ported from
    block: int = 0                                             # its id block (block_base): the race's id
    visuals: dict = field(default_factory=dict)                # BfA SpellVisualID -> visuals.PortedVisual
    visual_source: object = None                               # the visuals.BfaVisuals they came from
    anim_ids: dict = field(default_factory=dict)               # BfA animation id -> its 3.3.5 id (anim_slots)

    @property
    def spell_ids(self) -> list[int]:
        return [i for p in self.ported.values() for i in p.all_ids]

    @property
    def learned(self) -> list[int]:
        """Spells the skill teaches: the abilities and their companions (helpers are cast, not known)."""
        return [i for a in self.abilities for i in self.ported[a].ids]


def racial_skill_lines(skill_line: DBCFile, layout: DbcLayout) -> set[int]:
    """3.3.5's racial skill lines: category 9 lines named for a race ("Racial - Human", "Orc Racial")."""
    name = layout.at("DisplayName_lang")
    return {r[0] for r in skill_line.records
            if r[layout.at("CategoryID")] == RACIAL_CATEGORY and "racial" in skill_line.get_string(r[name]).lower()}


def source_race_bit(row: dict | None, race_id: int) -> int:
    """The race's bit in the source's race masks: retail's ChrRaces.PlayableRaceBit (since 9.0 a
    race's bit is no longer its id: a Mag'har's is 13), else BfA's 1 << (race - 1)."""
    bit = (row or {}).get("PlayableRaceBit")
    return 1 << bit if isinstance(bit, int) and bit >= 0 else 1 << (race_id - 1)


def source_race_mask(r: dict) -> int:
    """A row's race mask: BfA's RaceMask (64 bits), or retail 12.1's RaceMasks[2] (low, high word)."""
    if "RaceMask" in r:
        return int(r["RaceMask"]) & 0xFFFFFFFFFFFFFFFF
    lo, hi = (list(r.get("RaceMasks") or []) + [0, 0])[:2]
    return (int(lo) & 0xFFFFFFFF) | ((int(hi) & 0xFFFFFFFF) << 32)


def find_racial_line(bfa, bfa_race: int) -> tuple[int, str, list[int]] | None:
    """BfA's racial skill line of ``bfa_race``: (id, name, ability spells), or None."""
    bit = source_race_bit(dict(bfa.table("ChrRaces")).get(bfa_race), bfa_race)
    lines = {i: r for i, r in bfa.table("SkillLine") if str(r.get("DisplayName_lang", "")).startswith("Racial")}
    races = {}
    for _i, r in bfa.table("SkillRaceClassInfo"):
        races.setdefault(r["SkillID"], 0)
        races[r["SkillID"]] |= source_race_mask(r)
    abilities: dict[int, list[tuple[int, int]]] = {}
    for i, r in bfa.table("SkillLineAbility"):
        if r["SkillLine"] in lines:
            abilities.setdefault(r["SkillLine"], []).append((i, r))
    for line, rows in abilities.items():
        line_races = races.get(line, 0)
        mine = [r["Spell"] for _i, r in sorted(rows, key=lambda t: t[0])
                if (source_race_mask(r) & bit) or (not source_race_mask(r) and line_races & bit)]
        if mine:
            return line, str(lines[line]["DisplayName_lang"]), mine
    return None


def plan_racials(bfa, spells: BfaSpells, bfa_race: int) -> RacialPlan | None:
    found = find_racial_line(bfa, bfa_race)
    if found is None:
        return None
    line, name, spell_ids = found
    abilities = [s for s in spell_ids if spells.names.get(s) not in SKIPPED_ABILITIES]
    helpers = []
    for s in abilities:
        refs = {e.get("EffectTriggerSpell", 0) for e in spells.effects.get(s, [])}
        refs |= {int(m) for m in _SPELL_REF.findall(str(spells.text.get(s, {}).get("Description_lang", "")))}
        refs |= set(SCRIPT_CASTS.get(s, ()))
        for h in sorted(refs - {0} - set(abilities) - set(helpers)):
            if h in spells.names:
                helpers.append(h)
    return RacialPlan(line, name, abilities, helpers)


def port_racials(plan: RacialPlan, spells: BfaSpells, *, layout: DbcLayout, index_tables: dict,
                 range_layout: DbcLayout, block: int, listfile_names, skills: set[int] | None = None) -> list[str]:
    """Port the plan's spells (rows without texts; ``plan.ported``) and name their icons; returns
    what was dropped or needs a script, for the build's warnings. ``skills``: 3.3.5's skill lines."""
    notes = []
    plan.block = block
    base, used = spells.max_id + 1 + COMPANION_BLOCK * block, 0
    for s in plan.abilities + plan.helpers:
        try:
            p = port_spell(spells, s, layout=layout, index_tables=index_tables, range_layout=range_layout,
                           companion_ids=list(range(base + used, base + used + 8)), skills=skills)
        except SpellPortError as e:
            raise RacialsError(f"{spells.names.get(s, s)}: {e}") from e
        used += len(p.all_ids) - 1
        if used >= COMPANION_BLOCK:
            raise RacialsError(f"more than {COMPANION_BLOCK} companion spells")
        plan.ported[s] = p
        for what, items in (("dropped", p.dropped), ("translated", p.translated), ("needs a server script", p.scripted)):
            if items:
                notes.append(f"{p.name}: {what}: {', '.join(items)}")
    paths = listfile_names({p.icon_fdid for p in plan.ported.values() if p.icon_fdid})
    for fdid, path in paths.items():
        stem = path.replace("/", "\\").rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        plan.icons[fdid] = ICON_DIR + stem
    return notes


# --------------------------------------------------------------------------- tables

def block_base(block: int) -> int:
    """The first id of a race's own block in each table it adds rows to (icons, its skill line's
    rows, its spells' visuals and sounds): the same on every rebuild, whatever other packages add."""
    return BLOCK_BASE + block * BLOCK_SIZE


BLOCK_TABLES = ("SpellIcon", "SkillLineAbility", "SkillRaceClassInfo", "SpellVisual", "SpellVisualKit",
                "SpellVisualEffectName", "SoundEntries")


def add_icons(icons: DBCFile, plan: RacialPlan) -> dict[int, int]:
    """SpellIcon rows for the plan's icons: fdid -> id."""
    out = {}
    for k, (fdid, path) in enumerate(sorted(plan.icons.items())):
        new = block_base(plan.block) + k
        icons.add_record([new, icons.add_string(path)])
        out[fdid] = new
    return out


def add_spells(table: RawDBC, layout: DbcLayout, plan: RacialPlan, spells: BfaSpells, icon_ids: dict[int, int],
               visual_ids: dict[int, int] | None = None, texts_for: dict[int, dict[str, str]] | None = None) -> int:
    """The plan's Spell.dbc rows, texts, icons and visuals set, in one table (client or server).
    ``texts_for``: tooltips in place of TEXTS' (a registry race's own picks, race/identity.py)."""
    added = 0
    for s, p in plan.ported.items():
        texts = spell_texts(spells, plan.ported, s, (TEXTS if texts_for is None else texts_for).get(s))
        for k, row in enumerate(p.rows + p.pet_rows):
            row = list(row)
            if table.find_by_id(row[0]) is not None:
                raise DBCError(f"Spell.dbc already has spell {row[0]} ({p.name}) - rebuild with --replace")
            pet = k >= len(p.rows)
            for col, text in (pet_texts(spells, plan.ported, s, row, layout) if pet else texts).items():
                layout.set_text(table, row, col, text)
            if k == 0 or pet:                       # the pet's buff shows the racial's icon
                layout.set(row, "SpellIconID", icon_ids.get(p.icon_fdid, 0))
            if k == 0 and visual_ids and p.visual_id in visual_ids:
                layout.set(row, "SpellVisualID", visual_ids[p.visual_id], 0)
            table.add_row(row)
            added += 1
    return added


def add_skill_line(lines: DBCFile, layout: DbcLayout, template_line: int, plan: RacialPlan) -> None:
    tpl = lines.find_by_id(template_line)
    if tpl is None:
        raise DBCError(f"SkillLine has no template racial line {template_line}")
    if lines.find_by_id(plan.skill_line):
        raise DBCError(f"SkillLine already has {plan.skill_line} - rebuild with --replace")
    row = list(tpl)
    row[0] = plan.skill_line
    layout.set_text(lines, row, "DisplayName_lang", plan.name)
    layout.set_text(lines, row, "Description_lang", "")
    lines.add_record(row)


def add_race_class_info(info: DBCFile, template_line: int, plan: RacialPlan, race_mask: int) -> int:
    tpl = next((r for r in info.records if r[1] == template_line), None)
    if tpl is None:
        raise DBCError(f"SkillRaceClassInfo has no row for template racial line {template_line}")
    row = list(tpl)
    row[0], row[1], row[2] = block_base(plan.block), plan.skill_line, race_mask
    info.add_record(row)
    return 1


def add_abilities(abilities: DBCFile, template_line: int, plan: RacialPlan, race_mask: int) -> int:
    tpl = next((r for r in abilities.records if r[1] == template_line), None)
    if tpl is None:
        raise DBCError(f"SkillLineAbility has no row for template racial line {template_line}")
    for k, spell in enumerate(plan.learned):
        row = list(tpl)
        row[0], row[1], row[2], row[3], row[4] = block_base(plan.block) + k, plan.skill_line, spell, race_mask, 0
        abilities.add_record(row)
    return len(plan.learned)


def spells_named(spells: RawDBC, layout: DbcLayout, name: str) -> list[int]:
    """The ids of a Spell.dbc's spells with this (enUS) name."""
    at = layout.at("Name_lang", 0)
    return sorted(r[0] for r in map(spells.row, spells.records) if spells.get_string(r[at]) == name)


def strip_racials(tables: dict, plan: RacialPlan) -> dict[str, int]:
    """Remove what an earlier build of the plan added - its spell ids, its skill line, and every
    row in its block (icons, skill line rows, visuals, sounds) - so a rebuild adds them again."""
    removed = {}
    lo, hi = block_base(plan.block), block_base(plan.block) + BLOCK_SIZE

    def drop(name, keep):
        d = tables.get(name)
        if d is None:
            return
        before = len(d.records)
        d.records = [r for r in d.records if keep(r)]
        if len(d.records) != before:
            removed[name] = before - len(d.records)

    ids = {struct.pack("<I", i) for i in plan.spell_ids}
    drop("Spell", lambda r: (r[:4] if isinstance(r, (bytes, bytearray)) else struct.pack("<I", r[0])) not in ids)
    drop("SkillLine", lambda r: r[0] != plan.skill_line)
    for name in BLOCK_TABLES:
        drop(name, lambda r: not lo <= r[0] < hi)
    drop("SkillLineAbility", lambda r: r[1] != plan.skill_line)
    drop("SkillRaceClassInfo", lambda r: r[1] != plan.skill_line)
    return removed
