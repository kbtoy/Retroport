"""Retail's new passives for the stock races, beside every 3.3.5 racial they have.

The user's pick (2026-11-03, docs/racial-passives-plan.md): six passives retail gave the classic
races after 3.3.5, each taught by its race's own 3.3.5 racial skill line (a SkillLineAbility row),
so every character of the race - new or made before - learns it at login:

* Undead - Touch of the Grave: attacks and damaging spells sometimes (20%, at most every 15 sec)
  drain the target, Shadow damage and as much healing, from attack or spell power (retail's own
  proc and leech spells; 3.3.5 keeps Underwater Breathing as its own racial);
* Blood Elf - Arcane Acuity: +1% critical strike chance;
* Dwarf - Might of the Mountain and Tauren - Brawn: critical strikes deal and heal 2% more;
* Gnome - Nimble Fingers: +1% haste (attacks and casts);
* Night Elf - Touch of Elune: +1% haste at night, +1% critical strike by day (server time: the
  module puts on the day or the night spell).

Retail spell ids are kept where 3.3.5 has no spell of that id; retail reused two 3.3.5 ids
(5227 Underwater Breathing, 59224 Mace Specialization), so those two are given ids in the
package's block (``NEW_IDS``). Icons 3.3.5 already has are used as they are.

Output, installed with ``retroport install`` (server) and into the client's patch: client\\
(DBFilesClient Spell, SpellIcon, SkillLineAbility; retail icons 3.3.5 lacks), server\\dbc\\, the
world SQL (procs, bonus coefficients) and package.json. Build it on each client that plays; the
server tables come out the same each time.
"""

from __future__ import annotations

import json
import os
from typing import Callable

from ..character.convert import BfaInstall, _find_listfile_paths
from ..dbc import DBCError
from ..dbclayout import DbcLayout, LayoutError
from ..formats import blp
from ..mpq import ClientData
from ..safeio import write_verified
from . import racials, sounds
from .build import RACIAL_CLIENT_TABLES, RACIAL_SERVER_TABLES, RaceBuildResult, _is_inside, _parse, _save_tables, sha256
from .identity import Effect, Override, _drop_spells, _texts, apply_overrides
from .spells import BfaSpells

TOUCH_OF_THE_GRAVE, GRAVE_DRAIN = 5227, 127802
ARCANE_ACUITY, MIGHT_OF_THE_MOUNTAIN, BRAWN, NIMBLE_FINGERS = 154742, 59224, 154743, 92680
TOUCH_OF_ELUNE, ELUNE_DAY, ELUNE_NIGHT = 154748, 154796, 154797
BLOCK = 40                                       # its id block (racials.block_base): 240000-240999
NEW_IDS = {TOUCH_OF_THE_GRAVE: 240001, MIGHT_OF_THE_MOUNTAIN: 240002}
# race -> (its 3.3.5 racial skill line, the passives it learns)
RACES = {"Undead": (220, [TOUCH_OF_THE_GRAVE]), "Blood Elf": (756, [ARCANE_ACUITY]),
         "Dwarf": (101, [MIGHT_OF_THE_MOUNTAIN]), "Tauren": (124, [BRAWN]), "Gnome": (753, [NIMBLE_FINGERS]),
         "Night Elf": (126, [TOUCH_OF_ELUNE])}
HELPERS = [GRAVE_DRAIN, ELUNE_DAY, ELUNE_NIGHT]   # cast, not learned
CRIT_MORE = (Effect(aura=163, value=2, misc=127), Effect(aura=50, value=2))
OVERRIDES = {
    # retail's proc aura keeps its trigger; its water breathing is 3.3.5's own racial already
    TOUCH_OF_THE_GRAVE: Override(
        (Effect(aura=42, trigger=GRAVE_DRAIN),),
        "Your attacks and damaging spells have a chance to drain the target, dealing Shadow damage and healing "
        "you for the same amount."),
    # retail's damage: ${$max($AP*1.25,$SPH)*0.25} - attack power and spell power coefficients (AzerothCore adds both)
    GRAVE_DRAIN: Override(
        (Effect(effect=9, value=1, a=6, amplitude=1.0),),
        "Drains the target, dealing Shadow damage and healing you for the same amount.",
        fields={"SchoolMask": 32}, sp_bonus=0.25, ap_bonus=0.3125),
    MIGHT_OF_THE_MOUNTAIN: Override(CRIT_MORE, "Your critical strikes deal and heal $s1% more."),
    BRAWN: Override(CRIT_MORE, "Your critical strikes deal and heal $s1% more."),
    NIMBLE_FINGERS: Override((Effect(aura=193, value=1),), "Attack and casting speed increased by $s1%."),
    ARCANE_ACUITY: Override((Effect(aura=290, value=1, misc=127),), "Increases critical strike chance by $s1%."),
    # a dummy the module reads; the day and night spells are retail's, without their swap effect
    TOUCH_OF_ELUNE: Override((Effect(aura=4, value=1),),
                             "Increases your haste by 1% during the night, and your critical strike chance by 1% "
                             "during the day."),
    ELUNE_DAY: Override((Effect(aura=290, value=1),), "Increases your critical strike chance by 1% during the day.",
                        aura="Critical strike chance increased by 1%."),
    ELUNE_NIGHT: Override((Effect(aura=193, value=1),), "Increases your haste by 1% during the night.",
                          aura="Haste increased by 1%."),
}
PROC = {TOUCH_OF_THE_GRAVE: {"flags": 2429268, "chance": 20, "cooldown": 15000}}   # retail's SpellAuraOptions
CLIENT_TABLES = ["SkillLineAbility"] + [t for t in RACIAL_CLIENT_TABLES
                                        if t not in ("SpellVisual", "SpellVisualKit", "SpellVisualEffectName")]
SERVER_TABLES = ["SkillLineAbility"] + RACIAL_SERVER_TABLES


def _icon_ids(client: ClientData, icons, plan: racials.RacialPlan, bfa: BfaInstall, client_out: str, work: str,
              res: RaceBuildResult) -> dict[int, int]:
    """fdid -> SpellIcon id: 3.3.5's own row for an icon it has, else a new row in the block (and the
    icon from retail, when the client has no such file)."""
    have = {icons.get_string(r[1]).lower(): r[0] for r in icons.records}
    out, k = {}, 0
    for fdid, path in sorted(plan.icons.items()):
        if path.lower() in have:
            out[fdid] = have[path.lower()]
            continue
        new = racials.block_base(BLOCK) + k
        k += 1
        icons.add_record([new, icons.add_string(path)])
        out[fdid] = new
        rel = path + ".blp"
        if not client.exists(rel):
            src = write_verified(os.path.join(work, f"icon_{fdid}.blp"), bfa.read(fdid))
            img = blp.decode(src)
            res.files.append(write_verified(os.path.join(client_out, *rel.split("\\")), blp.encode_dxt(img),
                                            lambda p, size=img.size: blp.verify_blp(p, size)))
            res.owns.append(rel.lower())
    return out


def build_passives(*, install_dir: str, client_dir: str, out_dir: str, listfile: str, dbd_dir: str,
                   server_dbc_dir: str, product: str | None = "wow", patch: str = "patch-H.MPQ",
                   on_log: Callable[[str], None] | None = None) -> RaceBuildResult:
    log = on_log or (lambda m: None)
    for p in (client_dir, server_dbc_dir):
        if _is_inside(out_dir, p):
            raise ValueError(f"output folder {out_dir} is inside {p} - pick a separate folder")
    client_out = os.path.join(out_dir, "client")
    os.makedirs(client_out, exist_ok=True)
    res = RaceBuildResult(race="", name="Stock racial passives")
    log(f"Reading {client_dir} ...")
    client = ClientData(client_dir, top=patch)
    layouts = {t: DbcLayout(t, dbd_dir) for t in set(RACIAL_CLIENT_TABLES + RACIAL_SERVER_TABLES)}
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
        with open(path, "rb") as fh:
            data = fh.read()
        res.bases[f"server/dbc/{t}.dbc"] = {"source": path, "sha256": sha256(data)}
        stables[t] = _parse(t, data, layouts)

    bfa = BfaInstall(install_dir, dbd_dir, listfile, product=product)
    spells = BfaSpells(bfa, lambda paths: _find_listfile_paths(listfile, paths))
    learned = [s for _line, ss in RACES.values() for s in ss]
    plan = racials.RacialPlan(0, "Stock racial passives", learned, list(HELPERS))
    index_tables = {t: [ctables[t], stables[t]] for t in ("SpellCastTimes", "SpellDuration", "SpellRange", "SpellRadius")}
    try:
        notes = racials.port_racials(plan, spells, layout=layouts["Spell"], index_tables=index_tables,
                                     range_layout=layouts["SpellRange"], block=BLOCK,
                                     listfile_names=lambda fdids: sounds.listfile_names(listfile, fdids))
    except (racials.RacialsError, LayoutError) as e:
        raise ValueError(f"passives: {e}") from e
    plan.source = spells
    L = layouts["Spell"]
    apply_overrides(plan, L, index_tables, None, OVERRIDES)
    for old, new in NEW_IDS.items():
        plan.ported[old].rows[0][0] = new                       # retail reused a 3.3.5 id
    log("  passives: " + ", ".join(f"{plan.ported[s].name} {plan.ported[s].rows[0][0]}" for s in learned))

    # an earlier build's rows go first: its spells, and its block (icons, skill line rows)
    ids = {i for p in plan.ported.values() for i in p.all_ids}
    lo, hi = racials.block_base(BLOCK), racials.block_base(BLOCK) + racials.BLOCK_SIZE
    for tables in (ctables, stables):
        _drop_spells(tables["Spell"], ids)
        for t in ("SkillLineAbility", "SpellIcon"):
            if t in tables:
                tables[t].records = [r for r in tables[t].records if not lo <= r[0] < hi]

    work = os.path.join(out_dir, "_work")
    os.makedirs(work, exist_ok=True)
    icon_ids = _icon_ids(client, ctables["SpellIcon"], plan, bfa, client_out, work, res)
    res.rows = {"client": {}, "server": {}}
    texts = _texts(OVERRIDES)
    for side, tables in (("client", ctables), ("server", stables)):
        res.rows[side]["Spell"] = racials.add_spells(tables["Spell"], L, plan, spells, icon_ids, None, texts)
        n = 0
        for race, (line, passives) in RACES.items():
            tpl = next((r for r in tables["SkillLineAbility"].records if r[1] == line), None)
            if tpl is None:
                raise DBCError(f"SkillLineAbility has no row of {race}'s racial line {line}")
            for s in passives:
                row = list(tpl)
                row[0], row[2] = lo + n, plan.ported[s].rows[0][0]
                row[4] = 0                                      # every class; the line's own race mask
                row[8], row[9] = 0, 2                           # superseded by none; learned with the skill
                tables["SkillLineAbility"].add_record(row)
                n += 1
        res.rows[side]["SkillLineAbility"] = n
    res.rows["client"]["SpellIcon"] = sum(1 for r in ctables["SpellIcon"].records if lo <= r[0] < hi)
    res.racials = {"spells": {str(p.rows[0][0]): p.name for p in plan.ported.values()}, "notes": notes}
    overridden = {plan.ported[s].name for s in OVERRIDES if s in plan.ported}
    res.warnings += [f"passives: {n}" for n in notes if n.split(":", 1)[0] not in overridden]
    dbc_out = os.path.join(client_out, "DBFilesClient")
    sdir = os.path.join(out_dir, "server", "dbc")
    os.makedirs(dbc_out, exist_ok=True)
    os.makedirs(sdir, exist_ok=True)
    _save_tables(ctables, dbc_out, "client/DBFilesClient", res)
    _save_tables(stables, sdir, "server/dbc", res)

    install, undo = passives_sql(plan)
    sroot = os.path.join(out_dir, "server")
    res.files.append(write_verified(os.path.join(sroot, "stock_racial_passives.sql"), install.encode("utf-8")))
    res.files.append(write_verified(os.path.join(sroot, "stock_racial_passives_undo.sql"), undo.encode("utf-8")))
    manifest = res.model_dump()
    manifest["owns"] = sorted(set(res.owns))
    manifest["kind"] = "passives"
    write_verified(os.path.join(out_dir, "package.json"), json.dumps(manifest, indent=1).encode("utf-8"))
    log(f"Done: {out_dir}")
    return res


def passives_sql(plan: racials.RacialPlan) -> tuple[str, str]:
    """(install, undo) world SQL: Touch of the Grave's proc (retail's chance and cooldown) and its
    drain's coefficients. The passives are learned through their races' racial lines."""
    out = ["-- Retail's new passives for the stock races (retroport): procs and coefficients, world database.",
           "-- The spells are in the server's Spell.dbc and SkillLineAbility.dbc; re-applying is safe.", ""]
    undo = ["-- Removes what stock_racial_passives.sql added.", ""]
    for s, p in PROC.items():
        sid = plan.ported[s].rows[0][0]
        out += [f"DELETE FROM `spell_proc` WHERE `SpellId` = {sid};",
                "INSERT INTO `spell_proc` (`SpellId`, `ProcFlags`, `SpellTypeMask`, `SpellPhaseMask`, `Chance`, `Cooldown`) "
                f"VALUES ({sid}, {p['flags']}, 1, 2, {p['chance']}, {p['cooldown']});"]
        undo.append(f"DELETE FROM `spell_proc` WHERE `SpellId` = {sid};")
    bonus = {s: o for s, o in OVERRIDES.items() if o.sp_bonus or o.ap_bonus}
    for s, o in bonus.items():
        sid = plan.ported[s].rows[0][0]
        out += [f"DELETE FROM `spell_bonus_data` WHERE `entry` = {sid};",
                "INSERT INTO `spell_bonus_data` (`entry`, `direct_bonus`, `dot_bonus`, `ap_bonus`, `ap_dot_bonus`, "
                f"`comments`) VALUES ({sid}, {o.sp_bonus:g}, 0, {o.ap_bonus:g}, 0, '{plan.ported[s].name} (retroport)');"]
        undo.append(f"DELETE FROM `spell_bonus_data` WHERE `entry` = {sid};")
    return "\n".join(out) + "\n", "\n".join(undo) + "\n"
