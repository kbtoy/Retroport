"""Retail's item glows (ItemDisplayInfo.ItemVisual): the walk to their models, what the client draws, and
retail direct shipping them."""

import os

from retroport.mpq import MPQ, write_archive
from retroport.workbench import glows as GL
from retroport.workbench import retailpack as RP

from test_workbench_direct import BASKET, LISTFILE, PLAN, _direct, _md20_model, _wdc5

STAFF = 10


def _attach(effect_name: int, point: int, **over) -> dict:
    row = {"Offset": [0.0, 0.0, 0.0], "OffsetVariation": [0.0, 0.0, 0.0], "SpellVisualEffectNameID": effect_name,
           "AttachmentID": point, "PositionerID": 0, "Yaw": 0.0, "Pitch": 0.0, "Roll": 0.0, "YawVariation": 0.0,
           "PitchVariation": 0.0, "RollVariation": 0.0, "Scale": 1.0, "ScaleVariation": 0.0, "StartAnimID": -1,
           "AnimID": -1, "EndAnimID": -1, "AnimKitID": 0, "Flags": 0, "StartDelay": 0.0}
    return row | over


def _name(model: int, **over) -> dict:
    row = {"ModelFileDataID": model, "Scale": 1.0, "Alpha": 1.0, "Flags": 0, "TextureFileDataID": 0,
           "DissolveEffectID": 0, "ModelPosition": 0}
    return row | over


# visual 456: a model at points 0 and 1, a kit with a still model and one at retail's ModelPosition -1,
# an effect row for any item, one for staves (with a kit of its own) and one for swords
ROWS = {
    "ItemVisuals": [(456, {"SpellVisualKitId1": 900, "SpellVisualKitId2": 0, "ModelFileID": [240835, 240836, 0, 0, 0]}),
                    (457, {"SpellVisualKitId1": 0, "SpellVisualKitId2": 0, "ModelFileID": [0, 0, 0, 0, 0]})],
    "ItemVisualsXEffect": [
        (1, {"ItemVisualsID": 456, "AttachmentID": 7, "DisplayWeaponSubclassID": -1, "SpellVisualKitID": 0,
             "AttachmentModelFileID": 2086123, "Scale": 1.0}),
        (2, {"ItemVisualsID": 456, "AttachmentID": 1, "DisplayWeaponSubclassID": STAFF, "SpellVisualKitID": 901,
             "AttachmentModelFileID": 2086124, "Scale": 1.5}),
        (3, {"ItemVisualsID": 456, "AttachmentID": 1, "DisplayWeaponSubclassID": 7, "SpellVisualKitID": 0,
             "AttachmentModelFileID": 2086125, "Scale": 1.0})],
    "SpellVisualKitModelAttach": [(50, _attach(60, 1, ParentSpellVisualKitID=900)),
                                  (51, _attach(61, 2, ParentSpellVisualKitID=0)),
                                  (52, _attach(62, 3, ParentSpellVisualKitID=901, AnimKitID=12))],
    "SpellVisualKitEffect": [(70, {"ParentSpellVisualKitID": 900, "EffectType": 2, "Effect": 51}),
                             (71, {"ParentSpellVisualKitID": 900, "EffectType": 1, "Effect": 5})],
    "SpellVisualEffectName": [(60, _name(3000001)), (61, _name(3000002, ModelPosition=-1)), (62, _name(3000003))],
}


def test_a_visuals_models_by_way_of_its_points_effects_and_kits():
    idx = GL.index(ROWS)
    assert 457 not in idx                                                    # no model: no glow
    assert sorted(map(tuple, idx[456])) == sorted([
        (240835, "point", 0, None, ""), (240836, "point", 1, None, ""),
        (3000001, "kit", 1, None, ""),                                      # the kit's own attach row
        (3000002, "kit", 2, None, GL.MODEL_POSITION),                       # a type-2 kit effect's
        (2086123, "effect", 7, GL.ANY, ""), (2086124, "effect", 1, STAFF, ""),
        (3000003, "kit", 3, STAFF, "an anim kit"), (2086125, "effect", 1, 7, "")])


def test_a_look_takes_its_items_glows_only():
    idx = GL.index(ROWS)
    staff = {g.fdid: g for g in GL.for_look(idx[456], {"ClassID": GL.WEAPON, "SubclassID": STAFF})}
    assert set(staff) == {240835, 240836, 3000001, 3000002, 2086123, 2086124, 3000003}   # not the sword's
    assert staff[2086123].skip == GL.ANY_ITEM and staff[2086124].skip == "" and staff[3000003].skip == "an anim kit"
    robe = {g.fdid for g in GL.for_look(idx[456], {"ClassID": 4, "SubclassID": 1})}
    assert robe == {240835, 240836, 3000001, 3000002, 2086123}
    assert GL.for_look(None, None) == []


def test_the_client_draws_a_still_kit_model_only():
    assert GL.kit_skip(_attach(1, 0), _name(5)) == ""
    assert GL.kit_skip(_attach(1, 0), None) == "no SpellVisualEffectName row"
    assert GL.kit_skip(_attach(1, 0, Flags=4), _name(5)) == "flags"
    assert GL.kit_skip(_attach(1, 0, YawVariation=0.5), _name(5)) == "random variation"
    assert GL.kit_skip(_attach(1, 0, OffsetVariation=[0.0, 0.1, 0.0]), _name(5)) == "random variation"
    assert GL.kit_skip(_attach(1, 0), _name(5, TextureFileDataID=9)) == "a texture swap"
    assert GL.kit_skip(_attach(1, 0), _name(5, DissolveEffectID=9)) == "a dissolve"
    assert GL.kit_skip(_attach(1, 0), _name(5, ModelPosition=-1)) == GL.MODEL_POSITION
    assert GL.kit_skip(_attach(1, 300), _name(5)) == "an attachment point it doesn't know"
    assert GL.kit_skip(_attach(1, 0), _name(5, Alpha=2.0)) == "an alpha"


def test_a_glow_file_moves_aside_from_a_file_of_the_clients_own():
    assert GL.relocate("spells/Enchantments/Sparkle_A.m2") == "spells\\retroport\\enchantments\\sparkle_a.m2"
    assert GL.relocate("spells\\retroport\\x.m2") == "spells\\retroport\\x.m2"
    assert GL.relocate("x.m2") == "retroport\\x.m2"


# -- retail direct ----------------------------------------------------------------------------------
SPARKLE = "spells/enchantments/sparkle_a.m2"


def _glowing(tmp_path, monkeypatch):
    monkeypatch.setitem(LISTFILE, 240835, SPARKLE)
    monkeypatch.setitem(LISTFILE, 240900, "spells/enchantments/sparkle_a00.skin")
    monkeypatch.setitem(LISTFILE, 240901, "spells/sparkle.blp")
    monkeypatch.setitem(LISTFILE, 2086123, "spells/cfx_glow.m2")
    d = _direct(tmp_path, monkeypatch)
    src = d.source
    src.rows = dict(src.rows)
    src.rows["ItemDisplayInfo"] = [(i, r | {"ItemVisual": 456} if i == 732008 else r) for i, r in src.rows["ItemDisplayInfo"]]
    src.rows.update(ROWS)
    src.files.update({240835: _md20_model([240900], 240901, 1), 240900: b"SKINsparkle", 240901: b"BLP2sparkle"})
    for model in (240836, 2086123, 3000001, 3000002):                         # each with a skin of its own
        src.files.update({model: _md20_model([model + 50_000_000], 240901, 1), model + 50_000_000: b"SKIN"})
    # 3.3.5's own sparkle model at the retail path: its enchants keep it
    write_archive(os.path.join(d.client, "Data", "patch-2.MPQ"), {SPARKLE.replace("/", "\\"): b"MD20old"})
    return d


def test_retail_direct_ships_a_looks_glow_models_and_its_tables(tmp_path, monkeypatch):
    d = _glowing(tmp_path, monkeypatch)
    assert d.go(BASKET, PLAN, install=False)
    m = MPQ(os.path.join(d.work, "out", RP.PATCH))
    try:
        assert all(m.has(f"DBFilesClient\\{t}.db2") for t in GL.TABLES)
        models = RP.read_paths(m.read(RP.MODEL_PATHS))
        moved = "spells\\retroport\\enchantments\\sparkle_a.m2"
        assert models[240835] == moved and m.has(moved)                        # beside 3.3.5's, not over it
        assert m.has("spells\\retroport\\enchantments\\sparkle_a00.skin")      # its skin where the client opens it
        assert m.has("spells\\cfx_glow.m2") and models[2086123] == "spells\\cfx_glow.m2"
        assert {240836, 3000001, 3000002} <= set(models)                          # unnamed: found by id all the same
        assert not m.has(SPARKLE.replace("/", "\\"))
    finally:
        m.close()
    said = "\n".join(d.lines)
    assert "1 look(s) have a retail item glow: 5 glow model(s)" in said and "3 of them drawn" in said
    assert GL.ANY_ITEM in said and GL.MODEL_POSITION in said
    assert "under a retroport\\ folder" in said
    assert "checked: every file the client opens" in said
    rec = d.built_record()["summary"]
    assert (rec["glows"], rec["glow_models"], rec["glows_drawn"]) == (1, 5, 3)
    assert os.path.isfile(os.path.join(d.work, f"glows-{d.retail_build()}.json"))


def test_the_glow_walk_is_kept_for_the_retail_build(tmp_path, monkeypatch):
    d = _glowing(tmp_path, monkeypatch)
    assert d.go(BASKET, PLAN, install=False)
    parsed = []
    real = d.source.parse
    d.source.parse = lambda name, data: parsed.append(name) or real(name, data)
    assert d.go(BASKET, PLAN, install=False)
    assert not set(parsed) & set(GL.ROWS)                                    # the kit tables not read again


def test_glow_tables_of_another_layout_leave_the_glows_out_not_the_items(tmp_path, monkeypatch):
    d = _glowing(tmp_path, monkeypatch)
    real = d.source.raw_table
    d.source.raw_table = lambda name: _wdc5(0x12345678) if name == "spellvisualkiteffect" else real(name)
    assert d.go(BASKET, PLAN, install=False)
    m = MPQ(os.path.join(d.work, "out", RP.PATCH))
    try:
        assert not any(m.has(f"DBFilesClient\\{t}.db2") for t in GL.TABLES)
        assert not m.has("spells\\cfx_glow.m2") and m.has("item\\objectcomponents\\head\\helm_cloth_x_be_m.m2")
    finally:
        m.close()
    said = "\n".join(d.lines)
    assert "item glows left out" in said and "1 look(s) have a retail item glow, left out" in said
