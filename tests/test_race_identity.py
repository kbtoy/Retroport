"""A registry race's identity package (race/identity.py): racial overrides, its own spells, its SQL."""

import struct

import pytest

from retroport.dbc import DBCFile, RawDBC
from retroport.dbclayout import DbcLayout
from retroport.race import identity, racials
from retroport.race.spells import PortedSpell, _f

DBD = r"I:\WoW Modding\WoWDBDefs\definitions"
pytestmark = pytest.mark.skipif(not __import__("os").path.isdir(DBD), reason="WoWDBDefs not found")


def _index_tables():
    ct, du, rg, ra = DBCFile(4), DBCFile(4), DBCFile(40), DBCFile(4)
    ct.add_record([1, 0, 0, 0])
    du.add_record([21, 0xFFFFFFFF, 0, 0xFFFFFFFF])
    du.add_record([18, 20000, 0, 20000])
    ra.add_record([14, _f(8.0), 0, _f(8.0)])
    return {"SpellCastTimes": [ct], "SpellDuration": [du], "SpellRange": [rg], "SpellRadius": [ra]}


def _row(L: DbcLayout, sid: int, **fields) -> list[int]:
    row = L.blank()
    L.set(row, "ID", sid)
    for k, v in fields.items():
        L.set(row, k, v)
    return row


def test_an_override_puts_its_effects_in_one_row_and_its_references_on_them():
    L = DbcLayout("Spell", DBD)
    main = _row(L, 436344, Attributes=0x10000, CastingTimeIndex=7, DurationIndex=99)
    L.set(main, "Effect", 6, 0)
    L.set(main, "EffectAura", 4, 0)
    companion = _row(L, 9001)
    p = PortedSpell(436344, "Azerite Surge", rows=[main, companion], dropped=["effect 3"],
                    effects={0: ("slot", 0, 0), 1: ("value", 0)})
    plan = racials.RacialPlan(2895, "Racial - Earthen", [436344], ported={436344: p})
    notes = identity.apply_overrides(plan, L, _index_tables(), None, {436344: identity.OVERRIDES[436344]})
    assert len(p.rows) == 1 and p.dropped == [] and p.effects == {0: ("slot", 0, 0), 1: ("slot", 0, 1)}
    row = p.rows[0]
    assert [L.get(row, "Effect", k) for k in range(3)] == [2, 10, 0]
    assert [L.get(row, "ImplicitTargetB", k) for k in range(2)] == [15, 30]
    assert L.get(row, "EffectRadiusIndex", 0) == 14 and L.get(row, "EffectRadiusIndex", 1) == 14
    assert L.get(row, "EffectBasePoints", 0) == 9 and L.get(row, "EffectRealPointsPerLevel", 0) == _f(8.0)
    assert L.get(row, "Attributes") == 0 and L.get(row, "CastingTimeIndex") == 1 and L.get(row, "DurationIndex") == 0
    assert L.get(row, "RecoveryTime") == 120000 and L.get(row, "SchoolMask") == identity.FIRE
    assert p.ap_bonus == 0.3 and "Azerite Surge" in notes[0]


def test_quiet_contemplation_sits_like_food_and_runs_its_script():
    L = DbcLayout("Spell", DBD)
    food = _row(L, 433, Attributes=0x18000100, AuraInterruptFlags=0x40080, InterruptFlags=1)
    p = PortedSpell(461063, "Quiet Contemplation", rows=[_row(L, 461063, RecoveryTime=1000)])
    plan = racials.RacialPlan(2895, "Racial - Earthen", [461063], ported={461063: p})
    identity.apply_overrides(plan, L, _index_tables(), food, {461063: identity.OVERRIDES[461063]})
    row = p.rows[0]
    assert L.get(row, "AuraInterruptFlags") == 0x40080 and L.get(row, "Attributes") == 0x18000100
    assert L.get(row, "RecoveryTime") == 0 and L.get(row, "DurationIndex") == 18
    assert [L.get(row, "EffectAura", k) for k in range(2)] == [20, 21]
    assert L.get(row, "EffectAuraPeriod", 0) == 1000 and p.script == "spell_retroport_quiet_contemplation"


def test_extra_spells_come_from_their_template_and_well_fed_stays_on():
    L = DbcLayout("Spell", DBD)
    table = RawDBC(L.field_count if hasattr(L, "field_count") else 234, 4 * 234)
    table.add_row(_row(L, identity.FED_TEMPLATE, Attributes=0x8000000, SpellIconID=59, DurationIndex=42))
    table.add_row(_row(L, identity.GEM_TEMPLATE, Attributes=0x110, SpellIconID=2001, SpellVisualID=3220))
    extras = [x for x in identity.EXTRA_SPELLS if x.spell_id in (identity.INGEST_GEM, identity.FED["crit"])]
    rows = dict((x.spell_id, row) for x, row in identity.extra_rows(
        extras, table, L, _index_tables(), None, {777: 233003}, {identity.INGEST_MINERALS: 777}))
    fed, gem = rows[identity.FED["crit"]], rows[identity.INGEST_GEM]
    assert L.get(fed, "Attributes") == 0x8000000 | identity.ATTR0_CANT_CANCEL
    assert L.get(fed, "AttributesExC") & identity.ATTR3_DEATH_PERSISTENT
    assert L.get(fed, "DurationIndex") == 21 and L.get(fed, "SpellIconID") == 59
    assert L.get(fed, "EffectAura", 0) == 189 and L.get(fed, "EffectMiscValue", 0) == identity.CRIT_RATINGS
    assert L.get(gem, "Targets") == identity.TARGET_FLAG_ITEM and L.get(gem, "EquippedItemClass") == 3
    assert L.get(gem, "SpellIconID") == 233003 and L.get(gem, "SpellVisualID") == 0
    assert identity._add_extras(table, L, list(zip(extras, [rows[x.spell_id] for x in extras]))) == 2
    assert identity._drop_spells(table, {identity.INGEST_GEM, identity.FED["crit"]}) == 2
    assert {struct.unpack_from("<I", r)[0] for r in table.records} == {identity.FED_TEMPLATE, identity.GEM_TEMPLATE}


def test_identity_sql_teaches_the_line_to_whoever_its_rows_allow():
    racial = identity.sql.RacialSql(2895, "Racial - Earthen", [101, 125], ap_bonus={436344: 0.3},
                                    sp_bonus={436344: 0.4}, scripts={233901: "spell_retroport_ingest_gem"},
                                    old_spells=[20594])
    install, undo = identity._identity_sql("Earthen", identity.EARTHEN["races"], racial)
    assert "VALUES (0, 0, 2895, 0, 'Racial - Earthen');" in install
    assert "(436344, 0.4, 0, 0.3, 0, 'Racial - Earthen');" in install
    assert "(233901, 'spell_retroport_ingest_gem')" in install
    assert "DELETE FROM `playercreateinfo_skills` WHERE `skill` = 2895;" in undo
    assert "player_race_stats" not in install                  # the races' own rows are the registry's


def test_every_override_and_extra_is_one_the_module_knows():
    """The module (mod-retroport-racials) finds these by id: the ids here are its constants."""
    src = open(r"native\mod-retroport-racials\src\retroport_racials.cpp", encoding="utf-8").read()
    for sid in (identity.WIDE_EYED_WONDER, identity.INGEST_MINERALS, identity.INGEST_GEM, *identity.FED.values()):
        assert f"= {sid}," in src
    for x in identity.EXTRA_SPELLS + list(identity.OVERRIDES.values()):
        script = getattr(x, "override", x).script
        if script and script != identity.RATING_PCT:
            assert f"RegisterSpellScript({script})" in src
