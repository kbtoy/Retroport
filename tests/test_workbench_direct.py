"""Retail direct: retail's own items into the x64 client (retailpack's rules, direct's build, install, undo)."""

import json
import os
import struct
import types

import pytest

from retroport.dbc import DBCFile
from retroport.mpq import MPQ, write_archive
from retroport.workbench import direct as DR
from retroport.workbench import itemstats as IS
from retroport.workbench import jobs as J
from retroport.workbench import retailpack as RP
from retroport.workbench import server as SV


# -- the client's rules ---------------------------------------------------------------------------
def test_the_client_looks_for_a_models_texture_in_the_models_own_folder():
    head = "item\\objectcomponents\\head\\helm_cloth_raidwarlockulatek_d_01_be_m.m2"
    tex = "item\\objectcomponents\\collections\\cloth_raidwarlockulatek_d_01_shadowflamemythic.blp"
    assert RP.object_folder(head) == "head" and RP.object_folder(tex) == "collections"
    assert RP.texture_name(tex) == "cloth_raidwarlockulatek_d_01_shadowflamemythic"
    # the Damned Necrolyte skull: its texture lives in collections\, the client looks beside the helm
    assert RP.alias_for(head, tex) == "item\\objectcomponents\\head\\cloth_raidwarlockulatek_d_01_shadowflamemythic.blp"
    coll = "item\\objectcomponents\\collections\\cloth_x_hu_m.m2"
    assert RP.alias_for(coll, tex) == ""                                          # already where it looks
    assert RP.alias_for("creature\\foo\\foo.m2", tex) == ""                         # not an item component


def test_where_the_client_looks_for_a_displays_model():
    assert RP.model_look("item/objectcomponents/collections/cloth_x_hu_m.m2") == \
        "item\\objectcomponents\\collections\\cloth_x_hu_m.m2"
    assert RP.model_look("item\\objectcomponents\\collections\\sub\\cloth_x.m2") == \
        "item\\objectcomponents\\collections\\sub\\cloth_x.m2"                     # the name after collections\
    assert RP.model_look("item\\objectcomponents\\head\\sub\\helm_x.m2") == "item\\objectcomponents\\head\\helm_x.m2"
    assert RP.model_look("models\\unknown\\unk_1.m2") == ""


def test_a_file_without_a_listfile_name_or_out_of_reach_gets_a_path_the_client_finds():
    files = {10: "model", 11: "skin", 12: "texture", 13: "model"}
    names = {10: "item\\objectcomponents\\head\\helm_x.m2", 13: "models\\unknown\\unk_exp10_13.m2"}
    paths = RP.place(files, {11: 10, 12: None}, names, shown={10, 13})
    assert paths[10] == names[10]
    assert paths[11] == "item\\objectcomponents\\head\\wxl_11.skin"                # beside its model
    assert paths[12] == "item\\objectcomponents\\wxl\\wxl_12.blp"
    assert paths[13] == "item\\objectcomponents\\wxl\\unk_exp10_13_13.m2"          # a display model the client can reach
    assert RP.model_look(paths[13]) == paths[13]


def test_the_path_tables_round_trip_and_a_foreign_one_is_refused():
    rows = {7321845: "item\\objectcomponents\\head\\helm_x.m2", 5: "character\\human\\male\\humanmale.m2"}
    assert RP.read_paths(RP.write_paths(rows)) == rows
    assert RP.read_paths(b"") == {}
    bad = bytearray(RP.write_paths(rows))
    struct.pack_into("<I", bad, 8, 3)                                              # three fields
    with pytest.raises(ValueError):
        RP.read_paths(bytes(bad))


def _wdc5(layout: int) -> bytes:
    return b"WDC5" + bytes(152) + struct.pack("<I", layout) + bytes(16)


def test_a_tables_layout_is_read_from_its_header():
    assert RP.layout_of(_wdc5(0x9F3AB8A9)) == 0x9F3AB8A9
    assert RP.layout_of(b"WDC3" + bytes(20) + struct.pack("<I", 0x1234) + bytes(8)) == 0x1234
    assert RP.layout_of(b"WDBC" + bytes(40)) is None


def test_an_items_entry_is_its_retail_id_for_its_default_look():
    spare: dict = {}
    assert RP.entry_for(271546, 0, True, set(), spare) == 271546
    assert RP.entry_for(19019, 0, True, {19019}, spare) == 1_019_019              # 3.3.5 has that id: its own
    assert RP.entry_for(271546, 3, False, set(), spare) == 4_271_546              # Mythic
    assert RP.entry_for(271546, 153, False, set(), spare) == 16_000_000           # past the numbered modifiers
    assert RP.entry_for(271547, 153, False, set(), spare) == 16_000_001
    assert RP.entry_for(271546, 153, False, set(), spare) == 16_000_000           # kept
    assert RP.default_display([(3, 0, 732008, 2), (0, 5, 700000, 1), (1, 0, 710000, 3)]) == 700000
    assert RP.default_display([(3, 2, 732008, 2), (4, 1, 731000, 1)]) == 731000
    assert RP.default_display([]) == 0


def test_the_item_sql_deletes_only_rows_this_route_made_and_reads_back_like_the_kits():
    p = RP.Piece(4271546, 271546, 732008, 3, "Skull of the Damned Necrolyte", 4,
                 **RP.item_fields({"ClassID": 4, "SubclassID": 5, "Material": 7, "InventoryType": 1,
                                   "SheatheType": 0, "Sound_override_subclassID": 255}), label="Mythic")
    assert (p.sub, p.sound) == (0, -1)                                             # cosmetic armour: Miscellaneous
    text = RP.item_sql([p], [(271546, 700000)], "12.1.5.70391", "now")
    assert "WHERE (`entry`, `displayid`) IN ((271546,700000),(4271546,732008));" in text
    rows = IS.kit_items(text)
    assert rows[4271546]["displayid"] == 732008 and rows[4271546]["description"] == "Mythic"
    assert rows[4271546]["name"] == "Skull of the Damned Necrolyte" and rows[4271546]["InventoryType"] == 1


def test_the_patch_writer_gives_a_file_a_second_name(tmp_path):
    path = str(tmp_path / "patch-T.MPQ")
    w = RP.PatchWriter(path)
    w.add("a\\one.blp", b"texture")
    w.add("A\\ONE.blp", b"again")                                                   # a name it has: kept as it was
    assert w.alias("b\\two.blp", "a\\one.blp") and not w.alias("c\\x.blp", "missing.blp")
    w.close()
    m = MPQ(path)
    try:
        assert m.read("a\\one.blp") == b"texture" == m.read("b\\two.blp")
        assert "b\\two.blp" in m.read("(listfile)").decode()
    finally:
        m.close()


# -- the walk, build, install and undo --------------------------------------------------------------
HEAD = 7321845
LISTFILE = {HEAD: "item/objectcomponents/head/helm_cloth_x_be_m.m2",
            7321900: "item/objectcomponents/head/helm_cloth_x_be_m00.skin",
            7520491: "item/objectcomponents/collections/cloth_x_shadowflamemythic.blp",
            948080: "item/objectcomponents/head/armorreflect4.blp",
            7520805: "item/texturecomponents/torsouppertexture/cloth_x_tu_u_7520805.blp",
            5000: "interface/icons/inv_helm_x.blp"}


def _model(skin: int, texture: int) -> bytes:
    def chunk(magic, payload):
        return magic + struct.pack("<I", len(payload)) + payload
    return chunk(b"MD21", b"\0" * 16) + chunk(b"SFID", struct.pack("<I", skin)) + chunk(b"TXID", struct.pack("<I", texture))


class FakeRetail:
    """A local install's tables and files, enough for one helm and one robe."""
    spec = types.SimpleNamespace(kind="local")
    build = "12.1.5.70391"

    def __init__(self):
        self.files = {HEAD: _model(7321900, 948080), 7321900: b"SKIN", 7520491: b"BLP2mythic", 948080: b"BLP2reflect",
                      7520805: b"BLP2torso", 5000: b"BLP2icon"}
        self.rows = {
            "ItemDisplayInfo": [(732008, {"ModelResourcesID": [83020, 0], "ModelMaterialResourcesID": [1087579, 0]}),
                                (731968, {"ModelResourcesID": [0, 0], "ModelMaterialResourcesID": [0, 0]})],
            "ModelFileData": [(HEAD, {"FileDataID": HEAD, "ModelResourcesID": 83020})],
            "TextureFileData": [(1, {"FileDataID": 7520491, "MaterialResourcesID": 1087579}),
                                (2, {"FileDataID": 7520805, "MaterialResourcesID": 900}),
                                (3, {"FileDataID": 948080, "MaterialResourcesID": 901})],
            "ItemDisplayInfoMaterialRes": [(5, {"ItemDisplayInfoID": 731968, "MaterialResourcesID": 900, "ComponentSection": 6})],
            "ItemDisplayInfoModelMatRes": [(6, {"ItemDisplayInfoID": 732008, "MaterialResourcesID": 901, "TextureType": 24,
                                                "ModelIndex": 0})],
            "Item": [(271546, {"ClassID": 4, "SubclassID": 1, "Material": 7, "InventoryType": 1, "SheatheType": 0,
                               "Sound_override_subclassID": 255}),
                     (271549, {"ClassID": 4, "SubclassID": 1, "Material": 7, "InventoryType": 20, "SheatheType": 0,
                               "Sound_override_subclassID": 255})],
            "ItemAppearance": [(1, {"ItemDisplayInfoID": 700000}), (2, {"ItemDisplayInfoID": 732008}),
                               (3, {"ItemDisplayInfoID": 731968})],
            "ItemModifiedAppearance": [(10, {"ItemID": 271546, "ItemAppearanceModifierID": 0, "ItemAppearanceID": 1, "OrderIndex": 0}),
                                       (11, {"ItemID": 271546, "ItemAppearanceModifierID": 3, "ItemAppearanceID": 2, "OrderIndex": 0}),
                                       (12, {"ItemID": 271549, "ItemAppearanceModifierID": 0, "ItemAppearanceID": 3, "OrderIndex": 0})]}

    def raw_table(self, name):
        return _wdc5(RP.TABLES[name])

    def parse(self, name, data):
        return self.rows.get(name, [])

    def try_read(self, fdid):
        return (self.files[fdid], "") if fdid in self.files else (None, "not in this install")

    def size_of(self, fdid):
        return len(self.files.get(fdid, b""))


def _client(tmp_path):
    root = tmp_path / "WotLK x64"
    (root / "Data" / "enUS").mkdir(parents=True)
    (root / "WowClient64.exe").write_bytes(b"MZ" + RP.MERGE_MARK)   # a client that reads every path table
    (root / "Cache" / "WDB").mkdir(parents=True)
    write_archive(str(root / "Data" / "enUS" / "locale-enUS.MPQ"), {})
    items, displays = DBCFile(8), DBCFile(25)
    items.add_record([19019, 2, 7, -1 & 0xFFFFFFFF, 1, 1, 13, 3])
    displays.add_record([5] + [0] * 24)
    write_archive(str(root / "Data" / "patch.MPQ"), {"DBFilesClient\\Item.dbc": items.to_bytes(),
                                                     "DBFilesClient\\ItemDisplayInfo.dbc": displays.to_bytes()})
    write_archive(str(root / "Data" / "patch-R.MPQ"),
                  {RP.MODEL_PATHS: RP.write_paths({1: "character\\human\\male\\humanmale_hd.m2"}),
                   RP.TEXTURE_PATHS: RP.write_paths({2: "character\\human\\male\\humanmaleskin00_00.blp"})})
    return root


def _direct(tmp_path, monkeypatch):
    listfile = tmp_path / "listfile.csv"
    listfile.write_text("".join(f"{k};{v}\n" for k, v in LISTFILE.items()))
    d = DR.Direct(str(tmp_path / "data"), str(listfile))
    d.client, d.source = str(_client(tmp_path)), FakeRetail()
    monkeypatch.setattr(J, "wow_running", lambda: False)
    return d


PLAN = {"entries": [{"looks": [{"item": 271546, "display": 732008, "name": "Skull of the Damned Necrolyte", "quality": 4,
                                "icon": 5000},
                               {"item": 271549, "display": 731968, "name": "Damned Necrolyte's Rattling Robes", "quality": 4},
                               {"item": 0, "display": 123, "name": "A look no item has"}]}]}
BASKET = [{"kind": "set", "source": "retail", "id": 5884, "name": "Damned Necrolyte's Shattered Restraints"}]


def test_retail_direct_builds_a_patch_the_x64_client_finds_everything_in(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    assert d.problems() == []
    assert d.go(BASKET, PLAN, install=False)
    out = os.path.join(d.work, "out")
    m = MPQ(os.path.join(out, RP.PATCH))
    try:
        assert json.loads(m.read(RP.MANIFEST))["looks"] == ["731968", "732008"]
        assert all(m.has(f"DBFilesClient\\{t}.db2") for t in RP.TABLES)
        assert m.read(LISTFILE[HEAD].replace("/", "\\")) == FakeRetail().files[HEAD]
        assert m.has("item\\objectcomponents\\head\\helm_cloth_x_be_m00.skin")          # the model's own files
        assert m.has("item\\objectcomponents\\head\\armorreflect4.blp")
        assert m.read("item\\objectcomponents\\head\\cloth_x_shadowflamemythic.blp") == b"BLP2mythic"   # beside the helm
        assert m.read("interface\\icons\\inv_helm_x.blp") == b"BLP2icon"
        models, textures = RP.read_paths(m.read(RP.MODEL_PATHS)), RP.read_paths(m.read(RP.TEXTURE_PATHS))
        assert models[1] == "character\\human\\male\\humanmale_hd.m2"                     # patch-R's rows kept
        assert models[HEAD] == "item\\objectcomponents\\head\\helm_cloth_x_be_m.m2" and 7321900 in models
        assert textures[2] and textures[7520805].endswith("cloth_x_tu_u_7520805.blp")
    finally:
        m.close()
    sql = open(d.sql_files()[0], encoding="utf-8").read()
    rows = IS.kit_items(sql)
    assert sorted(rows) == [271549, 4271546]                     # the robe's default look; the skull's Mythic one
    assert rows[4271546]["description"] == "Mythic" and rows[271549]["description"] == ""
    assert any("checked: every file the client opens" in line for line in d.lines)
    view = open(os.path.join(out, "view-models.txt"), encoding="utf-8").read().splitlines()
    assert view == ["item\\objectcomponents\\head\\helm_cloth_x_be_m.m2\t-35\t-1\t"     # its own texture, and type 24's
                    "2=item\\objectcomponents\\collections\\cloth_x_shadowflamemythic.blp;"
                    "24=item\\objectcomponents\\head\\armorreflect4.blp"]
    assert any("A look no item has" in line for line in d.lines)
    st = d.status({"731968", "732008"})
    assert st["built"] and not st["installed"] and st["route"] == "direct"
    assert d.built_record()["entries"] == {"732008": 4271546, "731968": 271549}


def test_a_file_made_here_goes_in_the_patch_as_it_is(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    patch = str(tmp_path / "made.MPQ")
    files = DR.Files({}, {}, {}, [], {}, made={"DBFilesClient\\WxlCreatureDisplaySkins.txt": b"250001\t5\tglow\r\n"})
    d.pack(patch, {}, files, [], {"time": "", "build": "", "looks": []})
    m = MPQ(patch)
    try:
        assert m.read("DBFilesClient\\WxlCreatureDisplaySkins.txt") == b"250001\t5\tglow\r\n"
    finally:
        m.close()


def test_retail_direct_installs_backs_up_and_undoes(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    dest = os.path.join(d.client, "Data", RP.PATCH)
    assert d.go(BASKET, PLAN)
    assert os.path.isfile(dest) and not os.path.isdir(os.path.join(d.client, "Cache"))
    first = d.last_install()
    assert first["added"] == [dest] and first["basket"] == BASKET and first["data"] == d.cfg.client_data
    assert d.status({"731968", "732008"})["installed"]
    assert d.go(BASKET, PLAN)                                     # again: the first one backed up
    second = d.last_install()
    assert second["client"] == [RP.PATCH]
    assert os.path.isfile(os.path.join(second["backup"], "client", RP.PATCH))
    assert d.undo() and os.path.isfile(dest)                      # the first install's patch is back
    assert d.undo() and not os.path.exists(dest)                  # and then nothing
    assert not d.undo()
    sql = open(d.sql_files()[0], encoding="utf-8").read()
    assert "(4271546,732008)" in sql.split("INSERT")[0]           # rows it made are its to replace


def test_retail_direct_never_replaces_another_tools_patch(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    write_archive(os.path.join(d.client, "Data", RP.PATCH), {"something": b"else"})
    assert not d.go(BASKET, PLAN)
    assert any("another tool's patch" in line for line in d.lines)
    assert d.last_install() is None


def test_retail_direct_needs_the_x64_client_and_a_local_retail(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    os.remove(os.path.join(d.client, "WowClient64.exe"))
    d.source = types.SimpleNamespace(spec=types.SimpleNamespace(kind="wago"))
    why = d.problems()
    assert any("x64 client" in w for w in why) and any("own install" in w for w in why)
    with pytest.raises(RuntimeError):
        d.start("go", d.go, BASKET, PLAN)


def test_a_table_of_another_layout_stops_the_build(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    d.source.raw_table = lambda name: _wdc5(0x12345678)
    with pytest.raises(ValueError, match="layout"):
        d.go(BASKET, PLAN, install=False)


# -- the workbench ----------------------------------------------------------------------------------
def test_install_builds_everything_in_one_go():
    wb = types.SimpleNamespace(direct=types.SimpleNamespace(busy=lambda: False))
    with pytest.raises(ValueError, match="one go"):
        SV.Workbench.run(wb, "rerun")


# -- which patch, and what stands with it (0.5.0) -------------------------------------------------
def test_the_patch_follows_what_the_client_reads(tmp_path):
    root = tmp_path / "client"
    root.mkdir()
    assert RP.patch_for(str(root)) == RP.PATCH                           # no exe to read: the current one
    (root / "WowClient64.exe").write_bytes(b"MZ older")
    assert RP.merges_path_tables(str(root)) is False and RP.patch_for(str(root)) == RP.LEGACY_PATCH
    (root / "WowClient64.exe").write_bytes(b"MZ newer " + RP.MERGE_MARK + b" (rows)")
    assert RP.merges_path_tables(str(root)) is True and RP.patch_for(str(root)) == "patch-Q.MPQ"


def test_an_earlier_install_at_patch_t_moves_to_patch_q(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    data = os.path.join(d.client, "Data")
    old = os.path.join(data, RP.LEGACY_PATCH)
    write_archive(old, {RP.MANIFEST: b"{}", "item\\old.blp": b"BLP2"})
    assert d.go(BASKET, PLAN)
    rec = d.last_install()
    assert not os.path.exists(old) and os.path.isfile(os.path.join(data, RP.PATCH))
    assert rec["client"] == [RP.LEGACY_PATCH] and rec["added"] == [os.path.join(data, RP.PATCH)]
    assert any("took out patch-T.MPQ" in line for line in d.lines)
    assert d.undo() and os.path.isfile(old) and not os.path.exists(os.path.join(data, RP.PATCH))


def test_another_tools_patch_t_stays_where_it_is(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    data = os.path.join(d.client, "Data")
    undead = os.path.join(data, RP.LEGACY_PATCH)                          # the undead pack's
    write_archive(undead, {"DBFilesClient\\chrcustomizationchoice.db2": b"WDC5theirs"})
    before = open(undead, "rb").read()
    assert d.go(BASKET, PLAN)
    assert open(undead, "rb").read() == before and os.path.isfile(os.path.join(data, RP.PATCH))
    assert d.last_install()["client"] == []
    assert any("nothing above patch-Q.MPQ hides its files" in line for line in d.lines)


def test_install_names_what_an_archive_above_hides(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    data = os.path.join(d.client, "Data")
    write_archive(os.path.join(data, "patch-Z.MPQ"), {"DBFilesClient\\item.db2": b"WDC5older",
                                                     RP.MODEL_PATHS: RP.write_paths({9: "x.m2"})})
    assert d.go(BASKET, PLAN)
    hidden = d.check_shadowed(RP.PATCH)
    assert ("DBFilesClient\\item.db2", "patch-Z.MPQ") in hidden
    assert all(f != RP.MODEL_PATHS for f, _ in hidden)                    # the client reads every path table
    assert any("hidden by an archive above it" in line for line in d.lines)


def test_check_in_the_client_reads_the_installed_models(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    assert not d.client_check()                                           # nothing installed yet
    assert d.go(BASKET, PLAN)
    logs = os.path.join(d.client, "Logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, "WXL-native.log"), "w") as fh:
        fh.write("the user's own log")
    seen = {}

    class FakeClient:                                   # the client in its check mode
        def __init__(self, args, cwd, env):
            seen["env"], seen["cwd"] = env, cwd
            work = env["WXL_RETAIL_MODEL_CHECK"]
            models = open(os.path.join(work, "models.txt"), encoding="latin-1").read().split()
            with open(os.path.join(work, "check.txt"), "w", encoding="latin-1") as out:
                for i, m in enumerate(models):
                    out.write(f"{m}\t" + ("same (NATIVE) loaded in 1.0 ms" if i else "LOAD FAILED: a section past 256 bones") + "\n")
            with open(os.path.join(logs, "WXL-native.log"), "w") as fh:
                fh.write("the check's log")

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", FakeClient)
    assert d.client_check()
    assert seen["env"]["WXL_NATIVE_RETAIL_MODELS"] == "1" and seen["cwd"] == d.client
    assert open(os.path.join(logs, "WXL-native.log")).read() == "the user's own log"   # put back
    cc = d.built_record()["summary"]["client_check"]
    assert cc["failed"] and cc["same"] == cc["models"] - 1
    assert any("not read" in line for line in d.lines) and any("LOAD FAILED" in line for line in d.lines)


def _md20_model(skins: list[int], texture: int, profiles: int) -> bytes:
    def chunk(magic, payload):
        return magic + struct.pack("<I", len(payload)) + payload
    body = b"MD20" + b"\0" * 64 + struct.pack("<I", profiles) + b"\0" * 8      # numSkinProfiles at 68
    return chunk(b"MD21", body) + chunk(b"SFID", struct.pack(f"<{len(skins)}I", *skins)) + \
        chunk(b"TXID", struct.pack("<I", texture))


def test_a_models_skin_profiles_and_the_name_the_client_opens():
    data = _md20_model([11, 12, 13, 14, 15], 948080, 2)                     # two profiles, then LOD skins
    assert RP.skin_profiles(data) == [11, 12]
    assert RP.skin_name("item\\objectcomponents\\head\\helm_x.m2", 1) == "item\\objectcomponents\\head\\helm_x01.skin"
    assert RP.skin_profiles(b"MD20....") == []


def test_a_skin_another_model_shares_goes_in_under_this_ones_name_too(tmp_path, monkeypatch):
    # retail draws the Ethereal warlock cloth with its belt's skin (one mesh, the belt's name)
    monkeypatch.setitem(LISTFILE, 7321901, "item/objectcomponents/head/helm_cloth_y_be_m00.skin")
    d = _direct(tmp_path, monkeypatch)
    d.source.files[HEAD] = _md20_model([7321901], 948080, 1)
    d.source.files[7321901] = b"SKINshared"
    assert d.go(BASKET, PLAN, False)
    m = MPQ(os.path.join(d.work, "out", RP.PATCH))
    try:
        assert m.read("item\\objectcomponents\\head\\helm_cloth_y_be_m00.skin") == b"SKINshared"
        assert m.read("item\\objectcomponents\\head\\helm_cloth_x_be_m00.skin") == b"SKINshared"    # the client's name
    finally:
        m.close()
    assert any("checked: every file the client opens" in line for line in d.lines)
