"""The workbench on anyone's machine: game data from wago.tools, settings with their defaults, which
copy of the app is running, and what an install keeps track of."""

import json
import os
import threading
import types

import pytest

from retroport.workbench import catalog as C
from retroport.workbench import jobs as J
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


# -- settings --------------------------------------------------------------------------------
def test_fresh_settings_read_retail_and_bfas_bodies_from_wago():
    st = SV.Settings()
    specs = {s.key: s for s in st.effective_sources()}
    assert specs["retail"].kind == "wago" and specs["retail"].browse
    assert specs["bfa"].kind == "wago" and specs["bfa"].build == "8.3.7.35435" and not specs["bfa"].browse
    assert st.problems() == ["choose the 32-bit client's folder in Settings"]     # wago needs no DBDefs or listfile
    st.set_source("retail", "Retail", "X:\\nowhere", product="wow")
    assert any("not a game install" in p for p in st.problems())


def test_settings_keep_what_an_older_workbench_saved_in_the_same_file(tmp_path):
    path = tmp_path / "workbench.json"
    path.write_text(json.dumps({"client": "C:\\x64", "kit": {"work": "W:\\project"}, "route": "direct"}))
    st = SV.Settings.load(str(path))
    assert st.client == "C:\\x64" and not hasattr(st, "kit")
    st.client = "C:\\other"
    st.save(str(path))
    saved = json.loads(path.read_text())
    assert saved["client"] == "C:\\other" and saved["kit"] == {"work": "W:\\project"} and saved["route"] == "direct"


def test_a_workbench_knows_which_copy_it_is(tmp_path, monkeypatch):
    from retroport.workbench import app as A
    info = SV.app_info()
    assert info["version"].endswith("(source)") and os.path.isfile(os.path.join(info["from"], "pyproject.toml"))
    mine = {"from": "D:\\Retroport Workbench", "code": 100.0, "version": "0.3.0"}
    assert A.same_copy({"from": "d:\\retroport workbench", "code": 100.0}, mine)
    assert not A.same_copy({"from": "I:\\repo", "code": 100.0}, mine)            # another copy
    assert not A.same_copy({"from": mine["from"], "code": 50.0}, mine)           # this one, older code
    assert not A.same_copy({}, mine)                                             # too old to say


def test_a_running_workbench_stops_for_another_copy_but_never_in_an_install_job():
    import types
    from retroport.workbench import app as A
    wb = types.SimpleNamespace(quitting=False, last_hello=1.0, last_bye=0.0, direct=types.SimpleNamespace(busy=lambda: False))
    wb.busy = types.MethodType(SV.Workbench.busy, wb)
    assert not A.should_end(wb, 0.0, 2.0, True)
    wb.quitting = True
    assert A.should_end(wb, 0.0, 2.0, True)
    wb.direct.busy = lambda: True
    assert not A.should_end(wb, 0.0, 2.0, True)
    w = types.SimpleNamespace(direct=types.SimpleNamespace(busy=lambda: True), quitting=False)
    w.busy = types.MethodType(SV.Workbench.busy, w)
    with pytest.raises(RuntimeError, match="busy"):
        SV.Workbench.quit(w)


def test_a_piece_left_out_is_not_among_its_entrys_looks():
    looks = [{"display": 1, "name": "Helm"}, {"display": 2, "name": "Chest"}]
    cat = types.SimpleNamespace(looks_for=lambda e: (looks, [10, 11]))
    basket = [{"kind": "set", "source": "retail", "id": 5, "name": "A", "leave_out": ["1"]}]
    plan = C.plan_basket({"retail": cat}, basket)
    e = plan["entries"][0]
    assert [l["display"] for l in e["looks"]] == [2] and [l["display"] for l in e["left_out"]] == [1]
    assert plan["looks"] == 1


def _workbench(tmp_path, last=None):
    """The part of a Workbench that keeps the basket, what's in the game and the history."""
    work, data = tmp_path / "work", tmp_path / "data"
    work.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    wb = types.SimpleNamespace(basket_path=str(data / "basket.json"), _basket_lock=threading.Lock(),
                               settings=types.SimpleNamespace(data_dir=str(data)),
                               direct=types.SimpleNamespace(work=str(work), job=J.Job("go"), last_install=lambda: last))
    for name in ("basket", "save_basket", "in_game", "_take_out_path", "take_out", "set_take_out", "install_list",
                 "history", "after_install", "_history_path"):
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
    wb.direct.last_install = lambda: {"time": "29991231-000000", "basket": [a, c]}     # the install it just made
    wb.after_install(True, [c], [b])
    assert [e["id"] for e in wb.basket()] == [9]                          # what was installed left the basket
    assert wb.take_out() == [] and [h["result"] for h in wb.history()] == ["installed", "failed"]
    for k in range(6):
        wb.direct.last_install = lambda k=k: {"time": f"2999123{k}-000000", "basket": [a, c]}
        wb.after_install(True, [], [])
    assert len(wb.history()) == 5                                         # the last five


def test_a_basket_entry_stands_for_the_games_entry_of_the_same_key(tmp_path):
    a = {"kind": "set", "source": "retail", "id": 1, "name": "Set"}
    wb = _workbench(tmp_path, last={"time": "x", "basket": [a]})
    left = dict(a, leave_out=["7"])
    wb.save_basket([left])
    assert wb.install_list() == [left]


def test_the_history_reads_the_installs_it_has_no_record_of(tmp_path):
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

