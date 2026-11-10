"""Mounts: retail's mounts as rides in the x64 client - the catalog, the client's tables, the server's
SQL, retail's own files."""

import json
import os
import struct
import types

import pytest

from retroport.dbc import DBCFile
from retroport.mpq import MPQ, write_archive
from retroport.workbench import catalog as C
from retroport.workbench import direct as DR
from retroport.workbench import itemids
from retroport.workbench import jobs as J
from retroport.workbench import mountpack as MP
from retroport.workbench import mounts as MT
from retroport.workbench import retailpack as RP


# -- the 3.3.5 rules ------------------------------------------------------------------------------
def test_geoset_data_packs_a_nibble_per_group_and_says_what_it_cannot():
    packed, lost = MT.geoset_data([[0, 1], [2, 3], [9, 1], [1, 20]])
    assert packed == 0x301 and lost == [[9, 1], [1, 20]]
    assert MT.geosets_shown(packed) == {1: 101, 3: 303}
    assert MT.geoset_data([]) == (0, [])


def test_every_mount_file_goes_in_a_folder_of_its_own():
    assert MT.relocate("creature/ridinghorse/ridinghorse.m2") == "creature\\retroport\\ridinghorse\\ridinghorse.m2"
    assert MT.relocate("item\\objectcomponents\\x.blp") == "creature\\retroport\\item\\objectcomponents\\x.blp"
    assert MT.relocate("creature\\retroport\\a\\a.m2") == "creature\\retroport\\a\\a.m2"


def test_a_displays_skins_are_named_in_the_models_folder():
    names, files = MT.texture_names("creature\\retroport\\drake\\drake.mdx",
                                    {0: "creature\\drake\\skin.blp", 1: "creature\\other\\skin.blp", 2: "x\\Glow.BLP"})
    assert names == ["skin", "skin_1", "glow", ""]
    assert files == {"creature\\retroport\\drake\\skin.blp": 0, "creature\\retroport\\drake\\skin_1.blp": 1,
                     "creature\\retroport\\drake\\glow.blp": 2}


def test_a_displays_fourth_skin_is_named_for_the_x64_clients_table():
    names, files = MT.texture_names("creature\\retroport\\cormaera\\cormaera.mdx",
                                    {0: "creature\\cormaera\\body.blp", 3: "creature\\cormaera\\Body_Glow.blp"})
    assert names == ["body", "", "", "body_glow"]
    assert files == {"creature\\retroport\\cormaera\\body.blp": 0, "creature\\retroport\\cormaera\\body_glow.blp": 3}
    r = MT.Ride(1, "Cormaera", "flying", 7, 250123, 990001, "creature\\retroport\\cormaera\\cormaera.mdx", names)
    assert MT.skin_table([r]).decode().splitlines()[1:] == ["250123\t5\tbody_glow"]   # type 5, after a comment line
    assert MT.skin_table([MT.Ride(1, "Horse", "ground", 7, 250124, 990002, "x.mdx", ["skin", "", "", ""])]) is None


def test_a_state_kits_models_are_taken_with_their_placement_and_the_rest_left_out():
    t = {"SpellVisualKitEffect": [(1, {"EffectType": 2, "Effect": 10, "ParentSpellVisualKitID": 500}),
                                  (2, {"EffectType": 2, "Effect": 11, "ParentSpellVisualKitID": 500}),
                                  (3, {"EffectType": 2, "Effect": 12, "ParentSpellVisualKitID": 500}),
                                  (4, {"EffectType": 16, "Effect": 77, "ParentSpellVisualKitID": 500})],
         "SpellVisualKitModelAttach": [
             (10, {"SpellVisualEffectNameID": 20, "AttachmentID": 0xFFFFFFFF, "Scale": 0.5, "Offset": [0.1, 0, 0.2],
                   "Yaw": 1.5, "Pitch": 0, "Roll": 0, "AnimID": 0xFFFF, "StartAnimID": 158, "EndAnimID": 0xFFFF}),
             (11, {"SpellVisualEffectNameID": 21, "AttachmentID": 16, "Scale": 0, "PositionerID": 9}),
             (12, {"SpellVisualEffectNameID": 20, "AttachmentID": 17, "Scale": 1, "ScaleVariation": 0.2})],
         "SpellVisualEffectName": [(20, {"ModelFileDataID": 9001, "Scale": 2.0, "Alpha": 0.75}),
                                   (21, {"ModelFileDataID": 9002, "Scale": 1.0})]}
    got = MT.state_attachments(t)
    # one model: the positioned one and the randomly scaled one are left out, the gradient isn't a model
    assert got == {500: [{"model": 9001, "attachment": 255, "scale": 1.0, "alpha": 0.75, "offset": [0.1, 0.0, 0.2],
                          "rotation": [1.5, 0.0, 0.0], "anim": 0, "start": 158, "end": -1}]}
    r = MT.Ride(1, "Ghost", "flying", 7, 250125, 990003, "x.mdx", ["", "", "", ""],
                state=[dict(got[500][0], path="creature\\retroport\\spells\\ghost_state.m2")])
    assert MT.state_table([r]).decode().splitlines()[1:] == [
        "250125\tattach\t255\tcreature\\retroport\\spells\\ghost_state.m2\t1\t0.75\t0.1,0,0.2\t1.5,0,0\t0\t158\t-1"]
    assert MT.state_table([MT.Ride(1, "Horse", "ground", 7, 250124, 990002, "x.mdx", ["", "", "", ""])]) is None


def test_a_state_kits_gradient_is_listed_for_the_x64_client():
    t = {"SpellVisualKitEffect": [(1, {"EffectType": 16, "Effect": 7, "ParentSpellVisualKitID": 600})],
         "GradientEffect": [(7, {"Colors0_r": 0.0, "Colors0_g": 0.086, "Colors0_b": 0.22, "Colors1_r": 0.071,
                                 "Colors1_g": 0.655, "Colors1_b": 0.769, "Colors2_r": 1, "Colors2_g": 1, "Colors2_b": 1,
                                 "Alpha1": 0.5, "Alpha2": 0.9, "EdgeColor_r": 1, "EdgeColor_g": 1, "EdgeColor_b": 1,
                                 "Field_8_1_0_28440_015": 2})]}
    g = MT.state_gradients(t)[600]
    assert g == {"low": [0.0, 0.086, 0.22], "middle": [0.071, 0.655, 0.769], "high": [1.0, 1.0, 1.0], "split": 0.5,
                 "rim": 0.9, "edge": [1.0, 1.0, 1.0], "flags": 2}
    r = MT.Ride(1, "Spectral", "flying", 7, 250126, 990004, "x.mdx", ["", "", "", ""], gradient=g)
    assert MT.state_table([r]).decode().splitlines()[1:] == [
        "250126\tgradient\t0,0.086,0.22\t0.071,0.655,0.769\t1,1,1\t0.5\t0.9\t1,1,1\t2"]


def test_a_state_kits_dissolve_is_listed_with_its_layers_for_the_x64_client():
    t = {"SpellVisualKitEffect": [(1, {"EffectType": 11, "Effect": 2462, "ParentSpellVisualKitID": 700}),
                                  (2, {"EffectType": 11, "Effect": 9999, "ParentSpellVisualKitID": 701})],
         "DissolveEffect": [(2462, {"Ramp": 0.1, "StartValue": 0.0, "EndValue": 1.0, "FadeInTime": 0.05, "ProjectionType": 4,
                                    "TextureBlendSetID": 1760, "Scale": 1.0, "Flags": 8207, "FresnelIntensity": 0.4,
                                    "Field_9_1_5_40496_014": 0.0431, "Field_9_1_5_40496_015": 0.0471,
                                    "Field_9_1_5_40496_016": 0.2353, "Field_9_1_5_40496_017": 1.0,
                                    "Field_9_1_5_40496_018": 1.1})],
         "TextureBlendSet": [(1760, {"TextureFileDataID": [3025380, 6692906, 0], "TextureScaleU": [1.0, 1.0, 2.0],
                                     "TextureScaleV": [0.25, 0.25, 0.5], "TextureScrollRateU": [0.1, -0.04, 0.08],
                                     "TextureScrollRateV": [-0.1, -0.05, 0.08], "ModX": [0.72, 0.65, 1.1, 1.0]})]}
    got = MT.state_dissolves(t)
    # the kit whose dissolve row is missing has none
    assert list(got) == [700]
    d = got[700]
    assert (d["projection"], d["ramp"], d["start"], d["end"], d["fade"], d["flags"], d["fresnel"]) == (4, 0.1, 0.0, 1.0, 0.05, 8207, 0.4)
    assert d["tint"] == [0.0431, 0.0471, 0.2353, 1.0] and d["intensity"] == 1.1 and d["modx"] == [0.72, 0.65, 1.1, 1.0]
    assert [layer["texture"] for layer in d["layers"]] == [3025380, 6692906, 0]
    assert d["layers"][2] == {"texture": 0, "scale": [2.0, 0.5], "scroll": [0.08, 0.08]}
    d["layers"][0]["path"] = "creature\\retroport\\fx\\a.blp"
    d["layers"][1]["path"] = "creature\\retroport\\fx\\b.blp"
    r = MT.Ride(1, "Void-Scarred Gryphon", "flying", 7, 250129, 990007, "x.mdx", ["", "", "", ""], dissolve=d)
    assert MT.state_table([r]).decode().splitlines()[1:] == [
        "250129\tdissolve\t4\t0.1\t0,1,0.05\t8207\t0.4\t0.0431,0.0471,0.2353,1\t1.1\t0.72,0.65,1.1,1\t1"
        "\tcreature\\retroport\\fx\\a.blp\t1,0.25,0.1,-0.1\tcreature\\retroport\\fx\\b.blp\t1,0.25,-0.04,-0.05\t-\t2,0.5,0.08,0.08"]
    # a dissolve none of whose layers was placed is left out
    for layer in d["layers"]:
        layer["path"] = ""
    assert MT.state_table([r]) is None


def test_a_mount_flies_when_one_of_its_capabilities_does():
    assert MT.mount_kind([{"Flags": 29}, {"Flags": 7}]) == "flying"
    assert MT.mount_kind([{"Flags": 29}, None]) == "ground"


def test_ids_skip_the_clients_and_stay_with_their_mount(tmp_path):
    ids = MT.load_ids(str(tmp_path))
    got = MT.allocate(ids, 268, {"Spell": {MT.ID_BASE, MT.ID_BASE + 1}, "CreatureDisplayInfo": {MT.ID_BASE + 2}},
                      {MT.ITEM_BASE})
    assert got == {"id": MT.ID_BASE + 3, "item": MT.ITEM_BASE + 1}
    assert MT.allocate(ids, 268, {}, set()) is got                     # the same mount: the same ids
    assert MT.allocate(ids, 6, {}, set())["id"] == MT.ID_BASE           # the next one: the first free
    assert MT.icon_id(ids, 5260432, {MT.ID_BASE}) == MT.ID_BASE + 1
    MT.save_ids(str(tmp_path), ids)
    assert MT.load_ids(str(tmp_path))["mounts"]["268"] == got


# -- the client's tables and the server's SQL -----------------------------------------------------
def _spell(rows):
    d = DBCFile(MT.SPELL_FIELDS)
    for sid, aura2 in rows:
        r = [0] * MT.SPELL_FIELDS
        r[0], r[95], r[96] = sid, 78, aura2
        r[MT.SPELL_ICON] = 1176
        r[MT.SPELL_NAME] = d.add_string("Stock")
        r[MT.SPELL_AURA_TEXT] = d.add_string("Increases speed by $s2%.")
        r[216] = MT.f2u(1.0)                                   # a float field
        d.add_record(r)
    return d


def _tables():
    sla = DBCFile(14)
    sla.add_record([18779, MT.MOUNT_SKILL, 23229, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0])
    icon = DBCFile(2)
    icon.add_record([1176, icon.add_string("Interface\\Icons\\Ability_Mount_RidingHorse")])
    cdi, cmd = DBCFile(MT.CDI_FIELDS), DBCFile(MT.CMD_FIELDS)
    cdi.add_record([2404, 216] + [0] * 14)
    row = [216, 0, cmd.add_string("Creature\\RidingHorse\\RidingHorse.mdx"), 1, MT.f2u(1.0), 1] + [0] * 22
    row[13] = 65                                              # its sounds
    cmd.add_record(row)
    se, csd, ftl = DBCFile(30), DBCFile(MT.CSD_FIELDS), DBCFile(MT.FTL_FIELDS)
    se.add_record([500, 1, se.add_string("HorseStep")] + [0] * 27)
    sounds = [65] + [500] * 8 + [10] + [0] * 28
    sounds[25], sounds[31] = 2, MT.f2u(5.0)                   # impact type, fidget delay
    csd.add_record(sounds)
    ftl.add_record([1, 10, 1, 500, 0])                        # the horse's feet on dirt
    return {"Spell": _spell([(23229, 32), (32242, 207)]).to_bytes(), "SkillLineAbility": sla.to_bytes(),
            "SpellIcon": icon.to_bytes(), "CreatureDisplayInfo": cdi.to_bytes(), "CreatureModelData": cmd.to_bytes(),
            "SoundEntries": se.to_bytes(), "CreatureSoundData": csd.to_bytes(), "FootstepTerrainLookup": ftl.to_bytes()}


def _ride(**kw):
    base = dict(mount=268, name="Albino Drake", kind="flying", display=25836, id=MT.ID_BASE, item=MT.ITEM_BASE,
                model_path="creature\\retroport\\drakemount\\drakemount.mdx", textures=["drakeskinwhite1", "", ""],
                scale=1.1, geosets=0x31, model_data={"ModelScale": 2.0, "MountHeight": 2.5, "GeoBox": [1, 2, 3, 4, 5, 6]},
                icon=MT.ID_BASE + 7, item_name="Reins of the Albino Drake", quality=4, item_display=56308)
    base.update(kw)
    return MT.Ride(**base)


def test_the_client_tables_get_the_mounts_rows_once():
    base = _tables()
    cmd_rows = DBCFile.from_bytes(base["CreatureModelData"])
    tpl = MT.model_template(cmd_rows.records, cmd_rows.get_string, "creature/ridinghorse/ridinghorse.m2", "ground")
    rides = [_ride(), _ride(mount=6, name="Brown Horse", kind="ground", id=MT.ID_BASE + 1, item=MT.ITEM_BASE + 1,
                        icon=0, template_model=tpl)]
    out = MT.client_tables(base, rides, {MT.ID_BASE + 7: "Interface\\Icons\\INV_Drake"})
    again = MT.client_tables(out, rides, {MT.ID_BASE + 7: "Interface\\Icons\\INV_Drake"})    # an install over it
    for name in MT.TABLES:
        assert DBCFile.from_bytes(again[name]).records == DBCFile.from_bytes(out[name]).records
    spell = DBCFile.from_bytes(out["Spell"])
    drake = spell.find_by_id(MT.ID_BASE)
    assert drake[96] == 207 and drake[MT.SPELL_MISC_1] == MT.ID_BASE and drake[MT.SPELL_ICON] == MT.ID_BASE + 7
    assert spell.get_string(drake[MT.SPELL_NAME]) == "Albino Drake" and "flies" in spell.get_string(drake[MT.SPELL_DESCRIPTION])
    assert spell.find_by_id(MT.ID_BASE + 1)[MT.SPELL_ICON] == 1176                   # the template's icon kept
    sla = DBCFile.from_bytes(out["SkillLineAbility"]).find_by_id(MT.ID_BASE)
    assert sla[1] == MT.MOUNT_SKILL and sla[2] == MT.ID_BASE and sla[7] == 1
    cdi = DBCFile.from_bytes(out["CreatureDisplayInfo"])
    row = cdi.find_by_id(MT.ID_BASE)
    assert row[1] == MT.ID_BASE and abs(MT.u2f(row[4]) - 1.1) < 1e-6 and row[14] == 0x31
    assert [cdi.get_string(x) for x in row[6:9]] == ["drakeskinwhite1", "", ""]
    cmd = DBCFile.from_bytes(out["CreatureModelData"])
    horse = cmd.find_by_id(MT.ID_BASE + 1)
    assert cmd.get_string(horse[2]).endswith("drakemount.mdx") and horse[13] == 65   # the stock row's sounds
    assert abs(MT.u2f(cmd.find_by_id(MT.ID_BASE)[MT.CMD_MOUNT_HEIGHT]) - 2.5) < 1e-6
    icon = DBCFile.from_bytes(out["SpellIcon"])
    assert icon.get_string(icon.find_by_id(MT.ID_BASE + 7)[1]) == "Interface\\Icons\\INV_Drake"


def test_a_client_without_the_stock_mount_spells_says_so():
    base = _tables()
    base["Spell"] = _spell([(23229, 32)]).to_bytes()
    with pytest.raises(ValueError, match="32242"):
        MT.client_tables(base, [_ride()], {})


def test_the_sql_reads_back_the_client_rows_and_deletes_only_its_own():
    rides = [_ride()]
    tables = MT.client_tables(_tables(), rides, {})
    owned = {"item_template": [[MT.ITEM_BASE + 5, "Old mount"]]}
    sql = MT.mount_sql(tables, rides, owned, "12.1.5", "now", "retail direct")
    assert f"DELETE FROM `spell_dbc` WHERE (`ID`, `Name_Lang_enUS`) IN (({MT.ID_BASE},'Albino Drake'));" in sql
    assert f"({MT.ITEM_BASE},'Reins of the Albino Drake'),({MT.ITEM_BASE + 5},'Old mount')" in sql
    spell_values = sql.split("INSERT INTO `spell_dbc` VALUES\n(", 1)[1].split(");", 1)[0]
    values = [v.strip() for v in spell_values.split(",")]
    assert len(values) == MT.SPELL_FIELDS and values[216] == "1.0" and values[MT.SPELL_NAME] == "'Albino Drake'"
    assert values[MT.SPELL_MISC_1] == str(MT.ID_BASE)
    item = sql.split("INSERT INTO `item_template`", 1)[1]
    assert f",{MT.LEARNING},0,-1,-1,-1,{MT.ID_BASE},6," in item and ",762,300," in item        # Learning, then the mount
    assert "`creature_template_model`" in sql and f".learn {MT.ID_BASE}" in sql
    out = MT.owned_now(rides, owned)
    assert [MT.ITEM_BASE, "Reins of the Albino Drake"] in out["item_template"] and len(out["item_template"]) == 2


# -- the catalog ----------------------------------------------------------------------------------
KIT = {"SoundType": 2, "VolumeFloat": 0.5, "Flags": 0, "MinDistance": 8.0, "DistanceCutoff": 45.0, "EAXDef": 1}
SOUNDS = {        # the drake: wing flaps, a jump in two folders, a fidget whose file isn't Ogg, new feet; the horse: old feet
    "CreatureSoundData": [(2684, {"SoundFootstepID": 587, "SoundWingFlapID": 230502, "SoundJumpStartID": 10905,
                                  "SoundFidget": [230501, 0, 0, 0, 0], "CustomAttack": [0, 0, 0, 0]}),
                          (5914, {"SoundFootstepID": 10, "SoundAggroID": 95692, "SoundFidget": [0] * 5,
                                  "CustomAttack": [0] * 4})],
    "FootstepTerrainLookup": [(1, {"CreatureFootstepID": 587, "TerrainSoundID": 1, "SoundID": 7001, "SoundIDSplash": 0}),
                              (2, {"CreatureFootstepID": 587, "TerrainSoundID": 15, "SoundID": 7002, "SoundIDSplash": 0}),
                              (3, {"CreatureFootstepID": 10, "TerrainSoundID": 1, "SoundID": 7003, "SoundIDSplash": 0})],
    "SoundKit": [(k, dict(KIT)) for k in (230502, 10905, 230501, 7001, 7002, 7003, 95692, 999)],
    "SoundKitEntry": [(1, {"SoundKitID": 230502, "FileDataID": 5001, "Frequency": 1}),
                      (2, {"SoundKitID": 10905, "FileDataID": 5002, "Frequency": 3}),
                      (3, {"SoundKitID": 10905, "FileDataID": 5003, "Frequency": 1}),
                      (4, {"SoundKitID": 230501, "FileDataID": 5004, "Frequency": 1}),
                      (5, {"SoundKitID": 7001, "FileDataID": 5005, "Frequency": 1}),
                      (6, {"SoundKitID": 7002, "FileDataID": 5006, "Frequency": 1}),
                      (7, {"SoundKitID": 7003, "FileDataID": 5007, "Frequency": 1}),
                      (8, {"SoundKitID": 95692, "FileDataID": 5008, "Frequency": 1})],
}
SOUND_FILES = {5001: "sound/creature/drake/wingflap.ogg", 5002: "sound/creature/drake/jump_01.ogg",
               5003: "sound/creature/other/jump_02.ogg", 5004: "sound/creature/drake/fidget.ogg",
               5005: "sound/footsteps/drake_dirt.ogg", 5006: "sound/footsteps/drake_snow.ogg",
               5008: "sound/creature/horse/aggro.ogg"}


class FakeSource:
    spec = types.SimpleNamespace(kind="local", label="Retail")
    key, build = "retail", "12.1.5.70391"

    def __init__(self, tmp_path, files=None):
        self.cache_dir = str(tmp_path / "cache")
        self.files = files or {}
        self.rows = {
            "Mount": [(268, {"Name_lang": "Albino Drake", "MountTypeID": 424, "SourceSpellID": 60025, "SourceTypeEnum": 5,
                             "Description_lang": "Pale.", "SourceText_lang": "Achievement"}),
                      (6, {"Name_lang": "Brown Horse", "MountTypeID": 230, "SourceSpellID": 458, "SourceTypeEnum": 2}),
                      (9, {"Name_lang": "[PH] Nothing", "MountTypeID": 230, "SourceSpellID": 9}),
                      (10, {"Name_lang": "No display", "MountTypeID": 230, "SourceSpellID": 10})],
            "MountXDisplay": [(1, {"MountID": 268, "CreatureDisplayInfoID": 25836}),
                              (2, {"MountID": 6, "CreatureDisplayInfoID": 2404}),
                              (3, {"MountID": 9, "CreatureDisplayInfoID": 2404})],
            "MountTypeXCapability": [(1, {"MountTypeID": 424, "MountCapabilityID": 455}),
                                     (2, {"MountTypeID": 230, "MountCapabilityID": 227})],
            "MountCapability": [(455, {"Flags": 7}), (227, {"Flags": 29})],
            "CreatureDisplayInfo": [(25836, {"ModelID": 2858, "CreatureModelScale": 1.0, "CreatureModelAlpha": 255,
                                             "TextureVariationFileDataID": [234596, 0, 0, 0]}),
                                    (2404, {"ModelID": 216, "CreatureModelScale": 1.0,
                                            "TextureVariationFileDataID": [125622, 0, 0, 0]})],
            "CreatureModelData": [(2858, {"FileDataID": 234564, "ModelScale": 1.0, "MountHeight": 2.9,
                                          "GeoBox": [0, 0, 0, 1, 1, 1], "SoundID": 2684}),
                                  (216, {"FileDataID": 125614, "MountHeight": 1.9, "SoundID": 5914})],
            "CreatureDisplayInfoGeosetData": [(1, {"CreatureDisplayInfoID": 25836, "GeosetIndex": 0, "GeosetValue": 2})],
            "SpellMisc": [(1, {"SpellID": 60025, "SpellIconFileDataID": 236231, "DifficultyID": 0})],
            "ItemEffect": [(5, {"TriggerType": 6, "SpellID": 60025})],
            "ItemXItemEffect": [(1, {"ItemEffectID": 5, "ItemID": 44178})],
            "ItemSearchName": [(44178, {"Display_lang": "Reins of the Albino Drake", "OverallQualityID": 4})],
            **SOUNDS,
        }

    def table(self, name):
        return self.rows.get(name, [])

    def try_read(self, fdid):
        return (self.files[fdid], "") if fdid in self.files else (None, "not stored")

    def open(self):
        return None


def test_the_catalog_lists_mounts_with_their_looks_kind_icon_and_item(tmp_path):
    src = FakeSource(tmp_path)
    cat = MT.load_catalog(src)
    assert MT.load_catalog(src).to_json() == cat.to_json()             # the second time from the cache
    assert [m[1] for m in cat.mounts] == ["Albino Drake", "Brown Horse", "[PH] Nothing"]   # no display: left out
    drake = cat.detail(268)
    assert drake["kind"] == "flying" and drake["icon"] == 236231 and drake["item"] == 44178
    assert drake["item_name"] == "Reins of the Albino Drake" and drake["source_label"] == "Achievement"
    assert drake["display_rows"][0]["geosets"] == [[0, 2]] and drake["display_rows"][0]["model"] == 234564
    assert cat.search("", "ground")[0] == 1 and cat.search("", "", junk=True, families=False)[0] == 3
    assert cat.search("60025")[1][0]["id"] == 268 and cat.search("reins")[1][0]["id"] == 268
    # its sounds: the display's row (its model's), the kits it names, its footsteps by terrain
    assert cat.displays[25836]["sound"] == 2684 and cat.displays[2404]["sound"] == 5914
    row = cat.sounds["rows"]["2684"]
    assert row == {"kits": {"11": 230502, "26": 10905, "14": 230501}, "footstep": 587}
    assert cat.sounds["footsteps"]["587"] == [[1, 7001, 0], [15, 7002, 0]]
    assert cat.sounds["kits"]["10905"] == [2, 0.5, 0, 8.0, 45.0, 1, [[5002, 3], [5003, 1]]]
    assert "999" not in cat.sounds["kits"]                              # no files


def test_mounts_of_one_model_are_versions_of_one_family():
    def mount(i, name, display, kind="flying"):
        return [i, name, kind, 1, 9000 + i, 5, 0, "", 4, [display], "", ""]
    displays = {1: {"model": 234564}, 2: {"model": 234564}, 3: {"model": 234564}, 4: {"model": 124052}, 5: {"model": 0},
                6: {"model": 0}, 7: {"model": 123418}, 8: {"model": 123418}}
    cat = MT.MountCatalog("retail", "1", [
        mount(268, "Albino Drake", 1), mount(246, "Azure Drake", 2), mount(250, "Twilight Drake", 3),
        mount(300, "[PH] Drake", 1), mount(80, "Striped Frostsaber", 4, "ground"), mount(5, "Nothing A", 5),
        mount(6, "Nothing B", 6), mount(310, "Black Wolf", 7, "ground"), mount(320, "Black Wolf", 8, "ground")], displays)
    assert cat.families[246] == [246, 250, 268, 300] and cat.root_of[268] == 246
    assert cat.root_of[5] == 5 and cat.root_of[6] == 6                 # no model: each alone
    # one card per family - its oldest mount that matches - with how many versions it has
    total, rows = cat.search()
    assert total == 5 and [(r["id"], r["versions"]) for r in rows] == [(310, 2), (246, 3), (80, 1), (6, 1), (5, 1)]
    assert [r["id"] for r in cat.search("albino")[1]] == [268] and cat.search("albino")[1][0]["versions"] == 3
    assert cat.search("", junk=True)[1][1]["versions"] == 4            # the placeholder too
    assert cat.search("", families=False)[0] == 8
    # the drawer: each version with its label - the words they don't all share
    fam = cat.detail(268)["family"]
    assert [(f["id"], f["label"]) for f in fam] == [(246, "Azure"), (250, "Twilight"), (268, "Albino")]
    assert fam[0]["kind"] == "flying" and fam[0]["displays"] == [2] and cat.detail(268)["root"] == 246
    assert [f["label"] for f in cat.detail(300)["family"]] == ["Azure", "Twilight", "Albino", "[PH]"]
    assert [f["label"] for f in cat.detail(310)["family"]] == ["Black Wolf", "Black Wolf 2"]
    assert [f["id"] for f in cat.detail(80)["family"]] == [80]
    assert MT.version_labels(["Azure Riding Crane", "Golden Riding Crane"]) == ["Azure", "Golden"]
    assert MT.version_labels(["Azure Drake", "Experiment 12-B"]) == ["Azure Drake", "Experiment 12-B"]


def test_mounts_in_the_basket_are_entries_of_their_own():
    basket = [{"kind": "mount", "source": "retail", "id": 268, "name": "Albino Drake", "display": 25836,
               "mount_kind": "flying"}, {"kind": "mount", "source": "retail", "id": 268, "name": "again"}]
    plan = C.plan_basket({}, basket)
    assert plan["mounts"] == 1 and plan["looks"] == 0
    assert plan["entries"][0]["state"] == "ready" and plan["entries"][0]["mount"]["display"] == 25836
    assert [e["id"] for e in MT.basket_mounts(basket)] == [268]


# -- the build -----------------------------------------------------------------------------------
def _model(*chunks):
    out = b""
    for magic, ids in chunks:
        payload = struct.pack(f"<{len(ids)}I", *ids)
        out += magic + struct.pack("<I", len(payload)) + payload
    return b"MD21" + struct.pack("<I", 16) + b"\0" * 16 + out


LISTFILE = {234564: "creature/drakemount/drakemount.m2", 234570: "creature/drakemount/drakemount00.skin",
            234596: "creature/drakemount/drakeskinwhite1.blp", 234565: "creature/drakemount/drakemount_saddle.blp",
            236231: "interface/icons/ability_mount_drake_proto.blp", 125614: "creature/ridinghorse/ridinghorse.m2",
            125622: "creature/ridinghorse/ridinghorseskinbrown.blp", **SOUND_FILES}


def _client(tmp_path, above: dict | None = None):
    root = tmp_path / "client"
    (root / "Data" / "enUS").mkdir(parents=True)
    (root / "WowClient64.exe").write_bytes(b"MZ" + RP.MERGE_MARK)   # a client that reads every path table
    write_archive(str(root / "Data" / "enUS" / "locale-enUS.MPQ"), {})
    items, terrains = DBCFile(8), DBCFile(1)
    items.add_record([MT.ITEM_BASE] + [0] * 7)
    for t in range(11):                                       # 3.3.5's terrain sounds: 0-10
        terrains.add_record([t])
    files = {f"DBFilesClient\\{n}.dbc": d for n, d in _tables().items()}
    files |= {"DBFilesClient\\Item.dbc": items.to_bytes(), "DBFilesClient\\ItemDisplayInfo.dbc": _item_displays(),
              "DBFilesClient\\TerrainTypeSounds.dbc": terrains.to_bytes()}
    write_archive(str(root / "Data" / "patch-H.MPQ"), files)
    write_archive(str(root / "Data" / "patch-R.MPQ"),
                  {RP.MODEL_PATHS: RP.write_paths({1: "character\\human\\male\\humanmale_hd.m2"}),
                   RP.TEXTURE_PATHS: RP.write_paths({2: "character\\human\\male\\humanmaleskin00_00.blp"})})
    for name, held in (above or {}).items():
        write_archive(str(root / "Data" / name), held)
    return root


def _item_displays(*more) -> bytes:
    """A client's ItemDisplayInfo: the stock drake reins' row (its pick-up sound 16), and ``more``."""
    idi = DBCFile(25)
    for display, icon in ((56308, "Ability_Mount_Drake_Proto"), *more):
        row = [display] + [0] * 24
        row[MT.IDI_ICON], row[12] = idi.add_string(icon), 16
        idi.add_record(row)
    return idi.to_bytes()


def _setup(tmp_path):
    files = {234564: _model((b"SFID", [234570]), (b"TXID", [234565])), 234570: b"SKIN", 234565: b"BLP2saddle",
             234596: b"BLP2white", 236231: b"BLP2icon", 125614: _model(), 125622: b"BLP2brown",
             **{f: b"OggS" + bytes([f % 256]) for f in (5001, 5002, 5003, 5005, 5006, 5007, 5008)},
             5004: b"\0\0\0\0encrypted"}
    src = FakeSource(tmp_path, files)
    lf = tmp_path / "listfile.csv"
    lf.write_text("".join(f"{k};{v}\n" for k, v in LISTFILE.items()))
    entries = [{"kind": "mount", "source": "retail", "id": 268, "name": "Albino Drake"}]
    return src, str(lf), MT.load_catalog(src), entries


def test_direct_ships_retail_files_in_their_own_folder_with_path_rows(tmp_path):
    src, lf, cat, entries = _setup(tmp_path)
    client = _client(tmp_path)
    built = MP.build(entries, cat, src, str(client), RP.PATCH, str(tmp_path / "data"), lf, lambda m: None)
    folder = "creature\\retroport\\drakemount\\"
    assert built.files[folder + "drakemount.m2"] == 234564 and built.files[folder + "drakemount00.skin"] == 234570
    assert built.files[folder + "drakeskinwhite1.blp"] == 234596                # the display's skin, by its name
    assert built.paths[234564] == ("model", folder + "drakemount.m2") and built.paths[234565][0] == "texture"
    r = built.rides[0]
    assert r.model_path == folder + "drakemount.mdx" and r.textures == ["drakeskinwhite1", "", "", ""]
    assert MT.SKIN_TABLE not in built.files                                   # no fourth skin: no table
    assert r.geosets == 0x2 and r.item_name == "Reins of the Albino Drake"
    assert r.item_display == MT.ID_BASE and r.item_icon == "ability_mount_drake_proto"   # a row of its own
    idi = DBCFile.from_bytes(built.tables[MT.ITEM_TABLE])
    own = idi.find_by_id(MT.ID_BASE)
    assert idi.get_string(own[MT.IDI_ICON]) == "ability_mount_drake_proto" and own[12] == 16   # the stock reins' sounds
    assert idi.find_by_id(56308) is not None
    assert r.icon == MT.ID_BASE and built.files["interface\\icons\\ability_mount_drake_proto.blp"] == 236231
    reg = itemids.load(itemids.path(str(tmp_path / "data")))
    assert r.item in reg["reserved"]["item"] and r.item != MT.ITEM_BASE        # the client's Item.dbc has 990000
    assert "INSERT INTO `spell_dbc`" in built.sql
    again = MP.build(entries, cat, src, str(client), RP.PATCH, str(tmp_path / "data"), lf, lambda m: None)
    assert again.rides[0].id == r.id and "DELETE FROM `creature_template`" in again.sql


def test_a_fourth_skin_ships_with_the_x64_clients_table(tmp_path):
    src, lf, cat, entries = _setup(tmp_path)
    cat.displays[25836]["textures"] = [234596, 0, 0, 234565]       # retail's fourth: the model's type 5
    built = MP.build(entries, cat, src, str(_client(tmp_path)), RP.PATCH, str(tmp_path / "data"), lf,
                     lambda m: None)
    r = built.rides[0]
    folder = "creature\\retroport\\drakemount\\"
    assert r.textures == ["drakeskinwhite1", "", "", "drakemount_saddle"]
    assert built.files[folder + "drakemount_saddle.blp"] == 234565
    assert built.files[MT.SKIN_TABLE].decode().splitlines()[1:] == [f"{r.id}\t5\tdrakemount_saddle"]
    cdi = DBCFile.from_bytes(built.tables["CreatureDisplayInfo"])
    row = cdi.find_by_id(r.id)
    assert [cdi.get_string(row[6 + i]) for i in range(3)] == ["drakeskinwhite1", "", ""]   # the DBC keeps three


def test_a_patch_above_holding_the_tables_stops_the_build(tmp_path):
    src, lf, cat, entries = _setup(tmp_path)
    client = _client(tmp_path, {"patch-Z.MPQ": {"DBFilesClient\\Spell.dbc": b"theirs"}})
    with pytest.raises(ValueError, match="patch-Z.MPQ"):
        MP.build(entries, cat, src, str(client), RP.PATCH, str(tmp_path / "data"), lf, lambda m: None)


def test_retail_direct_builds_mounts_alone_into_its_patch(tmp_path, monkeypatch):
    src, lf, cat, entries = _setup(tmp_path)
    client = _client(tmp_path)
    src.raw_table = lambda name: b"WDC5" + bytes(152) + struct.pack("<I", RP.TABLES[name]) + bytes(16)
    src.parse = lambda name, data: []
    d = DR.Direct(str(tmp_path / "data"), lf)
    d.client, d.source, d.mount_catalog = str(client), src, (lambda: cat)
    monkeypatch.setattr(J, "wow_running", lambda: False)
    assert d.go(entries, C.plan_basket({}, entries), install=False)
    m = MPQ(os.path.join(d.work, "out", RP.PATCH))
    try:
        assert m.has("DBFilesClient\\Spell.dbc") and m.has("creature\\retroport\\drakemount\\drakemount.m2")
        assert json.loads(m.read(RP.MANIFEST))["mounts"] == [268]
        assert RP.read_paths(m.read(RP.MODEL_PATHS))[234564] == "creature\\retroport\\drakemount\\drakemount.m2"
    finally:
        m.close()
    assert [os.path.basename(p) for p in d.sql_files()] == [MP.DIRECT_SQL]           # no empty item SQL
    st = d.status(set(), {"mount:retail:268"})
    assert st["built"] and not d.status(set(), set())["built"]


def test_a_lower_patch_changed_after_the_mounts_is_said(tmp_path):
    data = tmp_path / "Data"
    data.mkdir()
    write_archive(str(data / RP.PATCH), {RP.MANIFEST: b"{}"})
    write_archive(str(data / "patch-H.MPQ"), {"DBFilesClient/Spell.dbc".replace("/", chr(92)): b"race rows"})
    write_archive(str(data / "patch-D.MPQ"), {"other": b"x"})
    write_archive(str(data / "patch-Y.MPQ"), {"DBFilesClient/Spell.dbc".replace("/", chr(92)): b"above"})
    made = os.path.getmtime(data / RP.PATCH)
    for name in ("patch-H.MPQ", "patch-D.MPQ", "patch-Y.MPQ"):
        os.utime(data / name, (made + 60, made + 60))
    assert MP.stale(str(data), RP.PATCH) == ["patch-H.MPQ"]        # below it, holds a table, newer
    os.utime(data / "patch-H.MPQ", (made - 60, made - 60))
    assert MP.stale(str(data), RP.PATCH) == []
    assert MP.stale(str(data), "patch-T.MPQ") == []                    # no such patch


def test_the_item_table_is_stale_only_while_nothing_above_holds_it(tmp_path):
    data = tmp_path / "Data"
    data.mkdir()
    write_archive(str(data / RP.PATCH), {RP.MANIFEST: b"{}"})
    write_archive(str(data / "patch-I.MPQ"), {f"DBFilesClient\\{MT.ITEM_TABLE}.dbc": b"old rows"})
    made = os.path.getmtime(data / RP.PATCH)
    os.utime(data / "patch-I.MPQ", (made + 60, made + 60))
    assert MP.stale(str(data), RP.PATCH) == ["patch-I.MPQ"]
    write_archive(str(data / "patch-Y.MPQ"), {f"DBFilesClient\\{MT.ITEM_TABLE}.dbc": b"theirs, above"})
    assert MP.stale(str(data), RP.PATCH) == []                     # the client reads patch-Y's anyway


# -- sounds and icons -----------------------------------------------------------------------------
def _both(tmp_path):
    src, lf, cat, _entries = _setup(tmp_path)
    entries = [{"kind": "mount", "source": "retail", "id": 268, "name": "Albino Drake"},
               {"kind": "mount", "source": "retail", "id": 6, "name": "Brown Horse"}]
    return src, lf, cat, entries


def test_a_mount_brings_retails_sounds_and_the_feet_3_3_5_lacks(tmp_path):
    src, lf, cat, entries = _both(tmp_path)
    client = _client(tmp_path)
    data = str(tmp_path / "data")
    built = MP.build(entries, cat, src, str(client), RP.PATCH, data, lf, lambda m: None)
    drake, horse = built.rides
    ids = MT.load_ids(data)["sounds"]
    flap, jump, dirt, aggro = (ids[str(k)] for k in (230502, 10905, 7001, 95692))
    assert drake.sound_kits == {11: flap, 26: jump}                    # the fidget's file isn't Ogg: left out
    assert "230501" not in ids and "7002" not in ids                   # nor a terrain 3.3.5 hasn't got (15)
    assert drake.footstep == 587 and horse.footstep == 10 and horse.sound_kits == {10: aggro}
    se = DBCFile.from_bytes(built.tables["SoundEntries"])
    row = se.find_by_id(jump)
    assert [se.get_string(x) for x in row[3:5]] == ["jump_01.ogg", "jump_02.ogg"] and row[13:15] == [3, 1]
    assert se.get_string(row[23]) == "sound\\retroport\\10905"           # two folders: a folder of its own
    assert se.get_string(se.find_by_id(flap)[23]) == "sound\\creature\\drake" and se.find_by_id(500)
    assert built.files["sound\\retroport\\10905\\jump_02.ogg"] == 5003 and built.paths[5001][0] == "sound"
    assert "sound\\creature\\drake\\fidget.ogg" not in built.files
    csd = DBCFile.from_bytes(built.tables["CreatureSoundData"])
    d, h = csd.find_by_id(drake.id), csd.find_by_id(horse.id)
    assert d[11] == flap and d[26] == jump and d[9] == 587 and d[14] == 0
    assert h[10] == aggro and h[1] == 0 and h[9] == 10                   # the stock horse's sounds all replaced
    assert h[25] == 2 and h[31] == MT.f2u(5.0)                           # its impact type and fidget delay kept
    assert DBCFile.from_bytes(built.tables["CreatureDisplayInfo"]).find_by_id(drake.id)[MT.CDI_SOUND] == drake.id
    assert DBCFile.from_bytes(built.tables["CreatureModelData"]).find_by_id(horse.id)[MT.CMD_SOUND] == horse.id
    ftl = DBCFile.from_bytes(built.tables["FootstepTerrainLookup"])
    assert sorted(r[1:] for r in ftl.records) == [[10, 1, 500, 0], [587, 1, dirt, 0]]
    again = MP.build(entries, cat, src, str(client), RP.PATCH, data, lf, lambda m: None)
    for name in ("SoundEntries", "CreatureSoundData", "FootstepTerrainLookup", MT.ITEM_TABLE):
        assert DBCFile.from_bytes(again.tables[name]).records == DBCFile.from_bytes(built.tables[name]).records


def test_retail_direct_ships_the_sounds_outside_the_path_tables(tmp_path, monkeypatch):
    src, lf, cat, entries = _both(tmp_path)
    client = _client(tmp_path)
    src.raw_table = lambda name: b"WDC5" + bytes(152) + struct.pack("<I", RP.TABLES[name]) + bytes(16)
    src.parse = lambda name, data: []
    d = DR.Direct(str(tmp_path / "data"), lf)
    d.client, d.source, d.mount_catalog = str(client), src, (lambda: cat)
    monkeypatch.setattr(J, "wow_running", lambda: False)
    assert d.go(entries, C.plan_basket({}, entries), install=False)
    m = MPQ(os.path.join(d.work, "out", RP.PATCH))
    try:
        assert m.read("sound\\creature\\drake\\wingflap.ogg")[:4] == b"OggS"
        assert m.has("DBFilesClient\\SoundEntries.dbc") and m.has(f"DBFilesClient\\{MT.ITEM_TABLE}.dbc")
        assert 5001 not in RP.read_paths(m.read(RP.MODEL_PATHS)) and 5001 not in RP.read_paths(m.read(RP.TEXTURE_PATHS))
    finally:
        m.close()


def _item_patch(data, held: bytes) -> str:
    """An older tool's item patch in ``data``, holding the client's item display table above the mounts'."""
    path = str(data / "patch-Y.MPQ")
    write_archive(path, {f"DBFilesClient\\{MT.ITEM_TABLE}.dbc": held, "Item\\x.blp": b"theirs"})
    return path


def test_the_items_icons_go_in_the_item_table_above_the_mounts_patch(tmp_path):
    client = _client(tmp_path)
    data = client / "Data"
    write_archive(str(data / RP.PATCH), {RP.MANIFEST: b"{}", f"DBFilesClient\\{MT.ITEM_TABLE}.dbc": _item_displays()})
    older = _item_patch(data, _item_displays((227000, "INV_Kit_Item"), (MT.ID_BASE + 9, "Old_Mount")))
    other = tmp_path / "other client"
    other.mkdir()
    os.link(older, other / "patch-Y.MPQ")                                     # the x64 clients' Data: hard links
    rides = [_ride(item_display=MT.ID_BASE + 3, item_icon="inv_mount_new", item_template=[0] * 12 + [16] + [0] * 12)]
    record, backup = {"client": [], "added": []}, tmp_path / "backup"
    assert MP.place_item_rows(str(client), RP.PATCH, rides, {MT.ID_BASE + 9}, str(backup), record,
                              lambda m: None) == "patch-Y.MPQ"
    m = MPQ(older)
    try:
        idi = DBCFile.from_bytes(m.read(f"DBFilesClient\\{MT.ITEM_TABLE}.dbc"))
        assert m.read("Item\\x.blp") == b"theirs"
    finally:
        m.close()
    row = idi.find_by_id(MT.ID_BASE + 3)
    assert idi.get_string(row[MT.IDI_ICON]) == "inv_mount_new" and row[12] == 16
    assert idi.find_by_id(227000) and not idi.find_by_id(MT.ID_BASE + 9)    # theirs kept, an old one of ours gone
    assert record["client"] == ["patch-Y.MPQ"] and (backup / "client" / "patch-Y.MPQ").is_file()
    assert record["item_ids"] == [MT.ID_BASE + 3] and MP.item_rows_gone(str(data), record) == []
    held = MPQ(str(other / "patch-Y.MPQ"))
    try:                                                                    # the other client's copy untouched
        assert not DBCFile.from_bytes(held.read(f"DBFilesClient\\{MT.ITEM_TABLE}.dbc")).find_by_id(MT.ID_BASE + 3)
    finally:
        held.close()
    # the same install put that patch in: its own record covers it, no second backup
    again = {"client": [], "added": [older]}
    MP.place_item_rows(str(client), RP.PATCH, rides, set(), str(tmp_path / "b2"), again, lambda m: None)
    assert again["client"] == [] and not (tmp_path / "b2" / "client" / "patch-Y.MPQ").exists()
    # another install replaces that patch: the page says the icons went with it
    _item_patch(data, _item_displays((227000, "INV_Kit_Item")))
    assert MP.item_rows_gone(str(data), again) == ["patch-Y.MPQ"]
    # nothing above the mounts' patch: it carries the rows itself
    os.remove(older)
    assert MP.place_item_rows(str(client), RP.PATCH, rides, set(), str(backup), {}, lambda m: None) == ""


def test_retail_direct_undo_leaves_an_archive_another_install_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "wow_running", lambda: False)
    client = _client(tmp_path)
    data = client / "Data"
    older = _item_patch(data, _item_displays())
    d = DR.Direct(str(tmp_path / "data"))
    d.client = str(client)
    for name, fp in (("1", MP._fingerprint(older)), ("2", [0, 0])):          # the archive as written; then not
        backup = os.path.join(d.work, "backups", f"2026102{name}-000000")
        os.makedirs(os.path.join(backup, "client"))
        write_archive(os.path.join(backup, "client", "patch-Y.MPQ"), {"before": name.encode()})
        J.save_json(os.path.join(backup, "install.json"), {"time": name, "client": ["patch-Y.MPQ"], "added": [],
                                                           "data": str(data), "item_rows": {"patch-Y.MPQ": fp}})
    assert d.undo()                                                         # the last one's archive changed since
    m = MPQ(older)
    try:
        assert m.read("before") is None
    finally:
        m.close()
    assert d.undo()                                                         # this one's is as it wrote it
    m = MPQ(older)
    try:
        assert m.read("before") == b"1"
    finally:
        m.close()

def test_a_mounts_banking_angle_is_listed_only_where_it_is_not_retails_usual():
    r20 = MT.Ride(1, "Blanchy", "ground", 7, 250127, 990005, "x.mdx", ["", "", "", ""], bank=20.0)
    r45 = MT.Ride(2, "Gryphon", "flying", 8, 250128, 990006, "y.mdx", ["", "", "", ""], bank=45.0)
    assert MT.state_table([r20, r45]).decode().splitlines()[1:] == ["250127\tbank\t20"]
