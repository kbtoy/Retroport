"""The workbench on anyone's machine: game data from wago.tools, the kit and Equip Plus fetched from
their GitHub, the kit shown open-folder patches, settings with their defaults."""

import io
import json
import os
import threading
import types
import zipfile

import pytest

from retroport.workbench import catalog as C
from retroport.workbench import deps as D
from retroport.workbench import kit as K
from retroport.workbench import kitlocal as L
from retroport.workbench import server as SV
from retroport.workbench import wago as W


# -- wago.tools -----------------------------------------------------------------------------
def test_wagos_csv_reads_as_the_local_readers_rows():
    text = ('ID,Name_lang,Flags,Scale,ModelResourcesID_0,ModelResourcesID_1,Offset_0,Offset_1,Field_9_1_0_38312_030\n'
            '7,"Season 2",3,0.5,100,0,0,1.25,4\n'
            '9,1234,0,2,0,0,0,0,0\n')
    rows = W.rows_from_csv(text)
    assert [i for i, _r in rows] == [7, 9]
    r = rows[0][1]
    assert r == {"ID": 7, "Name_lang": "Season 2", "Flags": 3, "Scale": 0.5, "ModelResourcesID": [100, 0],
                 "Offset": [0.0, 1.25], "Field_9_1_0_38312_030": 4}
    assert rows[1][1]["Name_lang"] == "1234" and isinstance(rows[1][1]["Offset"][0], float)   # text stays text
    # a table keyed by its file (ModelFileData): no ID column, the FileDataID is the row's id
    assert W.rows_from_csv("FileDataID,ModelResourcesID\n116902,18251\n") == [(116902, {"FileDataID": 116902,
                                                                                          "ModelResourcesID": 18251})]


def test_a_wago_source_keeps_what_it_fetched_and_knows_missing_and_encrypted_files(tmp_path):
    asked = []
    answers = {"db2/ItemSet": b"ID,Name_lang\n1,\"The Gladiator\"\n", "casc/5?": b"BLP2", "casc/6?": b"\0" * 64}

    def fetch(url, dest):
        asked.append(url)
        for k, v in answers.items():
            if k in url:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                open(dest, "wb").write(v)
                return
        raise W.WagoMissing("no such file")
    spec = C.SourceSpec("retail", "Retail", kind="wago", build="12.1.5.70391")
    src = W.WagoSource(spec, str(tmp_path), fetch)
    assert src.table("ItemSet") == [(1, {"ID": 1, "Name_lang": "The Gladiator"})]
    assert src.read(5) == b"BLP2" and src.read(5) == b"BLP2"
    with pytest.raises(W.WagoError, match="encrypted"):
        src.read(6)
    for _ in range(2):
        with pytest.raises(LookupError):
            src.read(7)                                                  # not in this build
    assert sum("casc/7?" in u for u in asked) == 1                       # ...asked once, remembered
    assert sum("db2/ItemSet" in u for u in asked) == 1
    src.table("ItemSet")
    assert sum("db2/ItemSet" in u for u in asked) == 1                   # kept on disk


def test_the_newest_build_is_asked_for_now_and_then_and_remembered_while_wago_is_down(tmp_path):
    def fetch(url, dest):
        open(dest, "w").write(json.dumps({"wow": [{"version": "12.1.5.70391"}], "wowt": [{"version": "12.1.7.1"}]}))
    assert W.latest_build(str(tmp_path), "wow", fetch) == "12.1.5.70391"

    def down(url, dest):
        raise W.WagoError("down")
    assert W.latest_build(str(tmp_path), "wow", down, max_age=0) == "12.1.5.70391"


# -- the kit and Equip Plus from GitHub ------------------------------------------------------
def _archive(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_a_github_archive_unpacks_without_its_top_folder_and_never_outside(tmp_path):
    D.unpack(_archive({"repo-abc/": b"", "repo-abc/tools/a.py": b"print(1)", "repo-abc/README.md": b"hi"}), str(tmp_path / "x"))
    assert (tmp_path / "x" / "tools" / "a.py").read_bytes() == b"print(1)"
    with pytest.raises(RuntimeError, match="outside"):
        D.unpack(_archive({"repo-abc/../../evil.py": b"x"}), str(tmp_path / "y"))
    assert not (tmp_path / "evil.py").exists()


def test_the_kit_is_fetched_once_at_its_pinned_commit(tmp_path):
    got = []

    def get(url, dest):
        got.append(url)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "wb").write(_archive({"r-1/wow-retail-backport/scripts/bp.py": b"# kit"}))
    path = D.fetch(str(tmp_path), "kit", say=lambda m: None, get=get)
    assert open(path).read() == "# kit" and D.have(str(tmp_path), "kit")
    D.fetch(str(tmp_path), "kit", say=lambda m: None, get=get)
    assert got == [f"https://codeload.github.com/Kirazul/wow-retail-backport/zip/{D.PINNED['kit']['ref']}"]


def test_the_kit_and_equip_plus_tools_are_always_the_workbenchs_own_copies(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "HELPER_SETTINGS", str(tmp_path / "none.json"))
    data = str(tmp_path / "wb")
    kit = K.Kit({}, None, "", "", data)
    assert kit.cfg.bp == D.entry(data, "kit") and kit.cfg.work == os.path.join(data, "backport-project")
    assert kit.cfg.tools == os.path.dirname(D.entry(data, "equip-plus"))
    assert not any("bp.py" in p for p in kit.problems())                 # Install fetches it first
    # neither the helper's kit nor an older setting points it at another copy
    (tmp_path / "helper.json").write_text(json.dumps({"kit": str(tmp_path / "my-clone"), "work": str(tmp_path / "w")}))
    monkeypatch.setattr(K, "HELPER_SETTINGS", str(tmp_path / "helper.json"))
    kit = K.Kit({"bp": str(tmp_path / "my-clone" / "bp.py"), "tools": str(tmp_path / "old-tools")}, None, "", "", data)
    assert kit.cfg.bp == D.entry(data, "kit") and kit.cfg.tools == os.path.dirname(D.entry(data, "equip-plus"))
    kit.set_settings({"bp": "x", "tools": "y", "work": str(tmp_path / "w2")})
    assert kit.cfg.bp == D.entry(data, "kit") and kit.cfg.work == str(tmp_path / "w2")
    assert set(kit.own_copies()) == {"kit", "equip-plus"} and not kit.own_copies()["kit"]["have"]


# -- open-folder patches ---------------------------------------------------------------------
def test_the_kit_is_shown_open_folder_patches(tmp_path):
    folder = tmp_path / "Data" / "patch-Z.MPQ" / "Item" / "Objects"
    folder.mkdir(parents=True)
    (folder / "a.m2").write_bytes(b"MD20")
    opened = []
    client = types.SimpleNamespace(os=os, MpqReader=lambda p: opened.append(p) or "mpq")
    assert L.show_folder_patches(client)
    patch = str(tmp_path / "Data" / "patch-Z.MPQ")
    assert client.os.path.isfile(patch) and not client.os.path.isfile(str(tmp_path / "Data"))
    arc = client.MpqReader(patch)
    assert arc.read("item\\objects\\A.M2") == b"MD20" and arc.read("(listfile)") == b"Item\\Objects\\a.m2"
    assert client.MpqReader(str(tmp_path / "x.MPQ")) == "mpq" and opened == [str(tmp_path / "x.MPQ")]
    assert not L.show_folder_patches(types.SimpleNamespace(FolderArchive=object))   # a kit that knows them


# -- settings --------------------------------------------------------------------------------
def test_fresh_settings_read_retail_and_bfas_bodies_from_wago():
    st = SV.Settings()
    specs = {s.key: s for s in st.effective_sources()}
    assert specs["retail"].kind == "wago" and specs["retail"].browse
    assert specs["bfa"].kind == "wago" and specs["bfa"].build == "8.3.7.35435" and not specs["bfa"].browse
    assert st.problems() == ["choose your 3.3.5 client folder in Settings"]     # wago needs no DBDefs or listfile
    st.set_source("retail", "Retail", "X:\\nowhere", product="wow")
    assert any("not a game install" in p for p in st.problems())


def test_prove_gates_is_shown_only_the_files_the_patch_ships(tmp_path, monkeypatch):
    import sys
    work = tmp_path / "work"
    (work / "build").mkdir(parents=True)
    (work / "build" / "plan.json").write_text("{}")
    shipped = r"item\objectcomponents\shoulder\backport\x__s1.m2"
    unshipped = r"item\objectcomponents\shoulder\backport\x.m2"           # the untrimmed source beside it
    manifest = {shipped: {"kind": "shoulder"}, unshipped: {"kind": "shoulder"}}
    (work / "build" / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setitem(sys.modules, "bpcore", types.SimpleNamespace(Project=lambda w: w))
    monkeypatch.setitem(sys.modules, "scan", types.SimpleNamespace(load=lambda prj: {}))
    monkeypatch.setitem(sys.modules, "gates", types.SimpleNamespace(closure=lambda prj, plan, sc: ({shipped.upper(): 1}, {})))
    provegates = types.SimpleNamespace(json=json)
    L.shipped_manifest(provegates, str(work))
    with open(work / "build" / "manifest.json", encoding="utf-8") as fh:
        assert list(provegates.json.load(fh)) == [shipped]
    with open(work / "build" / "plan.json", encoding="utf-8") as fh:
        assert provegates.json.load(fh) == {}                                 # every other file as it is
    assert provegates.json.dumps({"a": 1}) == '{"a": 1}'


def _model_with_two_bones():
    """A minimal M2: sequence 0 in the model, bone 0 keyed (moves), bone 1 not; vertex 0 rides bone 0,
    vertex 1 bone 1."""
    import struct
    b = bytearray(0x700)
    struct.pack_into("<II", b, 0x1C, 1, 0x200)                     # sequences
    struct.pack_into("<I", b, 0x200 + 0x0C, 0x20)                  # sequence 0 lives in the model
    struct.pack_into("<II", b, 0x2C, 2, 0x300)                     # bones
    for i in range(2):
        at = 0x300 + i * 88
        struct.pack_into("<h", b, at + 8, -1)                      # no parent
        struct.pack_into("<hh", b, at + 0x10, 1, -1)               # translation: linear, no global loop
        struct.pack_into("<II", b, at + 0x10 + 12, 1 if i == 0 else 0, 0x480)
    struct.pack_into("<II", b, 0x480, 1, 0x500)                    # bone 0's one key...
    struct.pack_into("<3f", b, 0x500, 0.0, 0.0, 0.0)
    struct.pack_into("<II", b, 0x3C, 2, 0x600)                     # vertices
    for v, bone in ((0, 0), (1, 1)):
        at = 0x600 + v * 48
        b[at + 12:at + 16] = bytes([255, 0, 0, 0])
        b[at + 16:at + 20] = bytes([bone, 0, 0, 0])
    return bytes(b)


def test_prove_gates_skips_a_model_whose_moved_bone_draws_nothing():
    import struct
    body = _model_with_two_bones()
    skin = lambda verts: b"SKIN" + struct.pack("<II", len(verts), 12) + b"".join(struct.pack("<H", v) for v in verts)
    assert L.first_keyed_bone(body) == 0
    assert L.moves_what_it_ships(body, skin([0, 1]))                # the moved bone carries a drawn vertex
    assert not L.moves_what_it_ships(body, skin([1]))               # a trimmed skin: nothing it draws moves


def test_a_workbench_knows_which_copy_it_is(tmp_path, monkeypatch):
    from retroport.workbench import app as A
    info = SV.app_info()
    assert info["version"].endswith("(source)") and os.path.isfile(os.path.join(info["from"], "pyproject.toml"))
    mine = {"from": "D:\\Retroport Workbench", "code": 100.0, "version": "0.3.0"}
    assert A.same_copy({"from": "d:\\retroport workbench", "code": 100.0}, mine)
    assert not A.same_copy({"from": "I:\\repo", "code": 100.0}, mine)            # another copy
    assert not A.same_copy({"from": mine["from"], "code": 50.0}, mine)           # this one, older code
    assert not A.same_copy({}, mine)                                             # too old to say


def test_a_running_workbench_stops_for_another_copy_but_never_in_a_kit_job():
    import types
    from retroport.workbench import app as A
    wb = types.SimpleNamespace(quitting=False, last_hello=1.0, last_bye=0.0, kit=types.SimpleNamespace(busy=lambda: False),
                               direct=types.SimpleNamespace(busy=lambda: False))
    wb.busy = types.MethodType(SV.Workbench.busy, wb)
    assert not A.should_end(wb, 0.0, 2.0, True)
    wb.quitting = True
    assert A.should_end(wb, 0.0, 2.0, True)
    wb.kit.busy = lambda: True
    assert not A.should_end(wb, 0.0, 2.0, True)
    wb.kit.busy, wb.direct.busy = (lambda: False), (lambda: True)          # retail direct's job counts too
    assert not A.should_end(wb, 0.0, 2.0, True)
    w = types.SimpleNamespace(kit=types.SimpleNamespace(busy=lambda: True), direct=types.SimpleNamespace(busy=lambda: False),
                              quitting=False)
    w.busy = types.MethodType(SV.Workbench.busy, w)
    with pytest.raises(RuntimeError, match="busy"):
        SV.Workbench.quit(w)


def test_a_piece_left_out_is_its_entrys_other_looks_for_the_kit():
    looks = [{"display": 1, "name": "Helm"}, {"display": 2, "name": "Chest"}]
    cat = types.SimpleNamespace(looks_for=lambda e: (looks, [10, 11]))
    basket = [{"kind": "set", "source": "retail", "id": 5, "name": "A", "leave_out": ["1"]}]
    plan = C.plan_basket({"retail": cat}, basket)
    e = plan["entries"][0]
    assert [l["display"] for l in e["looks"]] == [2] and [l["display"] for l in e["left_out"]] == [1]
    assert plan["looks"] == 1
    wb = types.SimpleNamespace(basket=lambda: basket, install_list=lambda: basket)
    assert SV.Workbench.kit_basket(wb, plan) == [{"kind": "look", "source": "retail", "id": 2, "name": "Chest"}]
    wb.kit_basket = lambda plan: SV.Workbench.kit_basket(wb, plan)
    assert SV.Workbench.kit_args(wb, plan) == ["--display", "2"]
    plan["entries"][0]["state"] = "loading"
    with pytest.raises(RuntimeError, match="loading"):
        SV.Workbench.kit_basket(wb, plan)


def _workbench(tmp_path, last=None):
    """The part of a Workbench that keeps the basket, what's in the game and the history."""
    work, data = tmp_path / "work", tmp_path / "data"
    work.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    wb = types.SimpleNamespace(basket_path=str(data / "basket.json"), _basket_lock=threading.Lock(),
                               settings=types.SimpleNamespace(data_dir=str(data), route=""),
                               kit=types.SimpleNamespace(cfg=types.SimpleNamespace(work=str(work)), job=K.Job("go"),
                                                         last_install=lambda: last), direct=None)
    for name in ("basket", "save_basket", "in_game", "_take_out_path", "take_out", "set_take_out", "install_list",
                 "history", "after_install", "runner", "_history_path"):
        setattr(wb, name, types.MethodType(getattr(SV.Workbench, name), wb))
    return wb


def test_an_install_adds_the_basket_to_whats_in_the_game_and_empties_it(tmp_path):
    a = {"kind": "set", "source": "retail", "id": 1, "name": "Old set"}
    b = {"kind": "item", "source": "retail", "id": 2, "name": "Old sword"}
    c = {"kind": "set", "source": "retail", "id": 3, "name": "New set"}
    wb = _workbench(tmp_path, last={"time": "20261019-111826", "basket": [a, b]})
    wb.save_basket([c])
    assert wb.install_list() == [a, b, c]                                 # the game's, then the basket
    wb.set_take_out(C.entry_key(b), True)
    assert wb.install_list() == [a, c]
    with pytest.raises(LookupError):
        wb.set_take_out(C.entry_key(c), True)                             # not in the game
    wb.after_install(False, [c], [b])                                     # a failed install: kept, remembered
    assert wb.basket() == [c] and wb.take_out() == [C.entry_key(b)]
    assert wb.history()[0]["result"] == "failed" and wb.history()[0]["basket"] == [c]
    wb.save_basket([c, {"kind": "item", "source": "retail", "id": 9, "name": "Added meanwhile"}])
    wb.kit.last_install = lambda: {"time": "29991231-000000", "basket": [a, c]}     # the install it just made
    wb.after_install(True, [c], [b])
    assert [e["id"] for e in wb.basket()] == [9]                          # what was installed left the basket
    assert wb.take_out() == [] and [h["result"] for h in wb.history()] == ["installed", "failed"]
    for k in range(6):
        wb.kit.last_install = lambda k=k: {"time": f"2999123{k}-000000", "basket": [a, c]}
        wb.after_install(True, [], [])
    assert len(wb.history()) == 5                                         # the last five


def test_a_basket_entry_stands_for_the_games_entry_of_the_same_key(tmp_path):
    a = {"kind": "set", "source": "retail", "id": 1, "name": "Set"}
    wb = _workbench(tmp_path, last={"time": "x", "basket": [a]})
    left = dict(a, leave_out=["7"])
    wb.save_basket([left])
    assert wb.install_list() == [left]


def test_the_history_reads_the_projects_installs_it_has_no_record_of(tmp_path):
    a = {"kind": "set", "source": "retail", "id": 1, "name": "First"}
    b = {"kind": "set", "source": "retail", "id": 2, "name": "Second"}
    wb = _workbench(tmp_path)
    root = tmp_path / "work" / "backups"
    for stamp, name, basket in (("20261018-100000", "install.json", [a]), ("20261018-120000", "install.json", [a, b]),
                                ("20261018-130000", "install.json.undone", [b])):
        (root / stamp).mkdir(parents=True)
        (root / stamp / name).write_text(json.dumps({"time": stamp, "basket": basket}))
    h = wb.history()
    assert [(x["time"], x["result"]) for x in h] == [("20261018-130000", "undone"), ("20261018-120000", "installed"),
                                                     ("20261018-100000", "installed")]
    assert h[1]["basket"] == [b] and h[2]["basket"] == [a]                     # what each added
    assert h[0]["taken_out"] == [a]                                             # the undone one took the first out

