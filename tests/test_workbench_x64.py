"""The x64 client as an install target, and a helm's collection part (a hood) through Equip Plus."""

import csv
import json
import os
import struct
import types

from retroport.mpq import write_archive
from retroport.workbench import eprows as EP
from retroport.workbench import kit as K
from retroport.workbench import kitlocal as L
from retroport.workbench import models as M


def _project(tmp_path, monkeypatch, exe="WowClient64.exe"):
    monkeypatch.setattr(K, "HELPER_SETTINGS", str(tmp_path / "helper.json"))
    monkeypatch.setattr(K, "wow_running", lambda: False)
    monkeypatch.setattr(K.deps, "have", lambda data_dir, name: True)
    work, client = tmp_path / "work", tmp_path / "client"
    data = client / "Data"
    (work / "reports").mkdir(parents=True)
    (work / "out").mkdir()
    data.mkdir(parents=True)
    (client / exe).write_bytes(b"MZ")
    (work / "bp.json").write_text(json.dumps({"build": "12.1.5.70391", "client_data": str(data)}))
    (work / "reports" / "steps.json").write_text(json.dumps({s: {"ok": True, "at": "x"} for s in K.ORDER}))
    (work / "out" / "patch-Y.MPQ").write_bytes(b"new patch")
    (tmp_path / "helper.json").write_text(json.dumps({"work": str(work), "client_data": str(data)}))
    kit = K.Kit({"bp": str(tmp_path / "bp.py"), "tools": str(tmp_path / "no-tools"), "equip_plus": "off"}, None, "", "",
                str(tmp_path / "wb"))
    kit.job = K.Job("test")
    return kit, work, data


def test_the_x64_client_draws_equip_plus_pieces_itself(tmp_path, monkeypatch):
    kit, work, data = _project(tmp_path, monkeypatch)
    ep = kit.equip_plus_client()
    assert ep["installed"] and ep["builtin"] and not ep["physics"] and ep["ini"] == ""
    assert kit.equip_plus_installed()
    kit.cfg.equip_plus = "auto"
    assert kit.equip_plus_wanted()
    assert not kit.set_equip_plus_options(True, True, True)          # no INI to write
    assert not os.path.exists(data.parent / "Extensions")
    assert K.is_x64_client(str(data.parent)) and not K.is_x64_client(str(tmp_path))


def test_a_stock_client_without_equip_plus_still_leaves_the_pieces_out(tmp_path, monkeypatch):
    kit, work, data = _project(tmp_path, monkeypatch, exe="Wow.exe")
    ep = kit.equip_plus_client()
    assert not ep["installed"] and not ep["builtin"]
    kit.cfg.equip_plus = "auto"
    assert not kit.equip_plus_wanted()


def test_either_client_running_counts(monkeypatch):
    def tasklist(out):
        return lambda *a, **k: types.SimpleNamespace(stdout=out)
    monkeypatch.setattr(K.os, "name", "nt")
    monkeypatch.setattr(K.subprocess, "run", tasklist('"explorer.exe","1"\n"WowClient64.exe","2"\n'))
    assert K.wow_running()
    monkeypatch.setattr(K.subprocess, "run", tasklist('"Wow.exe","3"\n'))
    assert K.wow_running()
    monkeypatch.setattr(K.subprocess, "run", tasklist('"WowError.exe","4"\n"notwow.exe","5"\n'))
    assert not K.wow_running()


def test_the_project_follows_the_client_in_settings(tmp_path, monkeypatch):
    kit, work, data = _project(tmp_path, monkeypatch)
    old = str(tmp_path / "old client" / "Data")
    (work / "bp.json").write_text(json.dumps({"build": "12.1.5.70391", "client_data": old, "namespace": "Backport"}))
    (work / "client").mkdir()
    for n in ("helm_shift.json", "geoset_map.json", "scan.json"):
        (work / "client" / n).write_text(n)
    assert kit.client_changed()
    basket = [{"kind": "set", "source": "retail", "id": 5, "name": "A"}]
    assert not kit.status(basket)["built"]
    ran = []

    def kit_step(args, step="", local=None, cwd=None):
        ran.append(args[0])
        if args[0] == "select":
            (work / "selection.json").write_text(json.dumps({"displays": {}}))
        return 0
    monkeypatch.setattr(kit, "_run", kit_step)
    assert kit.go(basket)
    prj = json.loads((work / "bp.json").read_text())
    assert prj["client_data"] == str(data) and prj["namespace"] == "Backport"
    assert ran[:2] == ["scan", "select"]                      # read again, then the selection for this client
    aside = [d for d in os.listdir(work / "backups") if d.startswith("client-")]
    assert len(aside) == 1
    kept = work / "backups" / aside[0]
    assert sorted(os.listdir(kept)) == ["bp.json", "geoset_map.json", "helm_shift.json", "scan.json"]
    assert json.loads((kept / "bp.json").read_text())["client_data"] == old
    assert not L.measured(str(work)) and (work / "client" / "scan.json").exists()
    assert not kit.client_changed() and not kit.follow_client()


def test_undo_puts_back_into_the_client_the_install_went_into(tmp_path, monkeypatch):
    kit, work, data = _project(tmp_path, monkeypatch)
    (data / "patch-Y.MPQ").write_bytes(b"old patch")
    assert kit.install()
    assert kit.last_install()["data"] == str(data)
    other = tmp_path / "other" / "Data"
    other.mkdir(parents=True)
    kit.cfg.client_data = str(other)
    assert kit.undo()
    assert (data / "patch-Y.MPQ").read_bytes() == b"old patch" and not os.listdir(other)


def test_the_kit_reads_the_335_body_beneath_a_retail_one():
    class Archive:
        def __init__(self, files):
            self.files = files

        def locate(self, name):
            return 0 if name in self.files else None

        def read(self, name):
            return self.files[name]

    class Client:                                    # the kit's reader, as far as it matters here
        def __init__(self, archives):
            self.archives = archives

        def who(self, path, data=False):
            for p, a in self.archives:
                if a.locate(path) is not None:
                    return p, (a.read(path) if data else None)
            return None

    mod = types.SimpleNamespace(Client=Client)
    assert L.classic_models_first(mod) and not L.classic_models_first(mod)
    body, table = "Character\\KulTiran\\Male\\KulTiranMale.m2", "DBFilesClient\\Item.dbc"
    c = Client([("patch-R.MPQ", Archive({body: b"MD21 retail", table: b"x64's"})),
                ("patch-H.MPQ", Archive({body: b"MD20 classic", table: b"ours"}))])
    assert c.who(body, data=True) == ("patch-H.MPQ", b"MD20 classic") and c.who(body) == ("patch-H.MPQ", None)
    assert c.who(table, data=True) == ("patch-R.MPQ", b"x64's")              # anything else: the winning copy
    only = Client([("patch-R.MPQ", Archive({body: b"MD21 retail"}))])
    assert only.who(body, data=True) == ("patch-R.MPQ", b"MD21 retail") and only.who("none.m2") is None


# -- a helm's collection part ---------------------------------------------------------------
def test_a_helms_collection_part_goes_through_the_kits_own_export(tmp_path):
    """The kit's export skips helms; kitlocal runs it once more on just their collection parts."""
    seen = []
    groups = {"head": ((27, 0), (21, 1)), "chest": ((13, 2),)}

    def export_extension(prj, log, sel, plan):
        out = {}
        for d, e in sel["displays"].items():
            if e["slot"] not in fake.PIECE_SLOTS or e["slot"] in ("head", "shoulder"):
                continue
            seen.append((d, e["slot"], fake.SLOT_GROUPS[e["slot"]], [m["k"] for m in e["models"]]))
            out[d] = {"slot": e["slot"], "new_display": 7, "pieces": [{"model": f"m{d}", "k": e["models"][0]["k"]}]}
        (tmp_path / "out" / "extension").mkdir(parents=True, exist_ok=True)
        (tmp_path / "out" / "extension" / "extension.json").write_text(json.dumps(out))

    class Retail:
        def __init__(self, prj):
            pass

        def multi_slot(self, res):
            return res == "83019"                          # the set's shared body model

    fake = types.SimpleNamespace(export_extension=export_extension, SLOT_GROUPS=groups, Retail=Retail,
                                 PIECE_SLOTS=("chest", "head", "shoulder"))
    bpcore = types.SimpleNamespace(load_json=lambda p, d=None: json.load(open(p)) if os.path.exists(p) else d,
                                   save_json=lambda p, o: json.dump(o, open(p, "w")))
    L.attached_collections(fake, bpcore)
    prj = types.SimpleNamespace(path=lambda *parts: os.path.join(str(tmp_path), *parts))
    row = lambda r0, r1: {"ModelResourcesID_0": r0, "ModelResourcesID_1": r1}
    sel = {"displays": {
        "1": {"slot": "chest", "row": row("83019", "0"), "models": [{"k": 0}]},
        "2": {"slot": "head", "row": row("83020", "83019"), "models": [{"k": 0}, {"k": 1}]},   # the skull and its hood
        "3": {"slot": "head", "row": row("83030", "0"), "models": [{"k": 0}]}}}                 # a helm on its own
    fake.export_extension(prj, print, sel, {})
    man = json.loads((tmp_path / "out" / "extension" / "extension.json").read_text())
    assert sorted(man) == ["1", "2"] and man["2"]["slot"] == "head" and man["1"]["slot"] == "chest"
    assert seen == [("1", "chest", ((13, 2),), [0]), ("2", "head_collection", ((27, 0), (21, 1)), [1])]
    assert fake.PIECE_SLOTS == ("chest", "head", "shoulder") and "head_collection" not in groups


def _model(*texs):
    """An MD20 model holding only its texture table: (type, file name) each."""
    names = b"".join(n.encode() + b"\0" for _t, n in texs if n)
    body = bytearray(0x100 + 16 * len(texs))
    body[:4] = b"MD20"
    struct.pack_into("<II", body, 0x50, len(texs), 0x100)
    at = len(body)
    for i, (t, n) in enumerate(texs):
        struct.pack_into("<IIII", body, 0x100 + i * 16, t, 0, len(n) + 1 if n else 0, at if n else 0)
        at += len(n) + 1 if n else 0
    return bytes(body) + names


def test_a_helm_and_its_hood_become_equip_plus_rows(tmp_path):
    work, patch = tmp_path / "work", tmp_path / "patch-U.MPQ"
    (work / "out" / "extension").mkdir(parents=True)
    (work / "build").mkdir()
    hood = "Item\\ObjectComponents\\Collections\\Backport\\cloth_x_{r}_{s}__c77_{P}{S}__src__sa54.m2"
    pieces, files = [], {}
    for prefix, sex, tag in (("Hu", "M", "hu_m"), ("Or", "F", "or_f")):
        rel = hood.format(r=tag[:2], s=tag[-1], P=prefix, S=sex)
        pieces.append({"race": 1, "prefix": prefix, "sex": sex, "k": 1, "model": rel, "retail_race": 1})
        files[rel] = _model((2, ""), (0, "Item\\ObjectComponents\\Backport\\1360817.blp"))
        files[rel[:-3] + "00.skin"] = b"SKIN"
    pieces.append({"race": 9, "sex": "M", "error": "no cut"})
    files["Item\\ObjectComponents\\Backport\\1360817.blp"] = b"BLP2 hard-coded"
    write_archive(str(work / "out" / "extension" / "patch-Y-ext.MPQ"), files)
    (work / "out" / "extension" / "extension.json").write_text(json.dumps(
        {"732008": {"slot": "head", "new_display": None, "pieces": pieces},
         "731968": {"slot": "chest", "pieces": []}}))
    (work / "ids.json").write_text(json.dumps({"display": {"732008": 227038}}))
    (work / "selection.json").write_text(json.dumps({"displays": {"732008": {"model_tex": [
        {"k": 0, "race": 0, "fdid": 7520491}, {"k": 1, "race": 0, "fdid": 7520429}]}}}))
    (work / "build" / "plan.json").write_text(json.dumps({"732008": {"row": {
        "model": ["Backport\\helm_skull__s7b.mdx", ""], "tex": ["Backport\\7520491", ""]}}}))
    (work / "bp.json").write_text(json.dumps({"namespace": "Backport", "build": "12.1.5.70391"}))
    # Equip Plus's converter made the patch: the set's chest row, and the colourway it shares
    (patch / "DBFilesClient").mkdir(parents=True)
    (patch / "DBFilesClient" / "WXLItemDisplayModels.csv").write_text(
        ",".join(EP.COLUMNS) + "\n227036,,Chest,Base,C,Collections\\Backport,cloth_x__c77__src__s321.mdx,"
        "backport_7520429,,19,Legacy,Exact,\n")
    (patch / "Item" / "ObjectComponents" / "Collections" / "Backport").mkdir(parents=True)
    (patch / "Item" / "ObjectComponents" / "Collections" / "Backport" / "backport_7520429.blp").write_bytes(b"BLP2 colour")
    said = []
    assert EP.add(str(work), str(patch), said.append) == 1
    rows = list(csv.DictReader(open(patch / "DBFilesClient" / "WXLItemDisplayModels.csv", encoding="utf-8")))
    assert [(r["DisplayID"], r["Slot"], r["Folder"], r["Model"], r["Texture"], r["Attach"]) for r in rows] == [
        ("227036", "Chest", "Collections\\Backport", "cloth_x__c77__src__s321.mdx", "backport_7520429", "19"),
        ("227038", "Head", "Collections\\Backport", "cloth_x__c77__src__sa54.mdx", "backport_7520429", "19"),
        ("227038", "Head", "Head\\Backport", "helm_skull__s7b.mdx", "7520491", "11")]
    folder = patch / "Item" / "ObjectComponents" / "Collections" / "Backport"
    assert sorted(os.listdir(folder)) == ["backport_7520429.blp", "cloth_x__c77__src__sa54_HuM.m2", "cloth_x__c77__src__sa54_HuM00.skin",
                                          "cloth_x__c77__src__sa54_OrF.m2", "cloth_x__c77__src__sa54_OrF00.skin"]
    assert (patch / "Item" / "ObjectComponents" / "Backport" / "1360817.blp").read_bytes() == b"BLP2 hard-coded"
    assert EP.add(str(work), str(patch), said.append) == 1                 # again: the same rows, once
    assert len(list(csv.DictReader(open(patch / "DBFilesClient" / "WXLItemDisplayModels.csv", encoding="utf-8")))) == 3


def test_a_helm_row_needs_its_texture_beside_its_model():
    row = {"model": ["Backport\\helm_a.mdx", ""], "tex": ["Backport\\5", ""]}
    assert EP.helm_row(9, row)["Folder"] == "Head\\Backport" and EP.helm_row(9, row)["Texture"] == "5"
    assert EP.helm_row(9, dict(row, tex=["Other\\5", ""])) is None
    assert EP.helm_row(9, {"model": ["", ""]}) is None
    assert EP.stem_of("Item\\ObjectComponents\\Collections\\Backport\\c_d_01_hu_m__504_HuM__src__s63.m2", "Hu", "M") == \
        ("Collections\\Backport", "c_d_01__504__src__s63")


# -- the preview's helms and shoulders ----------------------------------------------------
def test_a_display_row_carries_its_geoset_group_override():
    row = [0, 0, 0, 0, 0, -1, *(0,) * 6, *(0,) * 6, 644, 645]
    idx = M.DisplayIndex({"displays": {"1": [*row, 1], "2": row}, "model_files": {}, "comp_models": {}, "tex_files": {},
                          "comp_tex": {}, "sections": {}, "model_mat": {}})
    assert idx.row(1)["geoset_override"] == 1 and idx.row(1)["helmet_vis"] == [644, 645]
    assert idx.row(2)["geoset_override"] == 0                              # an index from before it was kept
