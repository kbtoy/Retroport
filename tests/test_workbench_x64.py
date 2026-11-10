"""The x64 client as the place Install goes into, and the preview's display rows."""

import types

from retroport.workbench import edition
from retroport.workbench import jobs as J
from retroport.workbench import models as M


def test_the_client_is_the_folder_with_the_x64_clients_program(tmp_path):
    client = tmp_path / "client"
    (client / "Data").mkdir(parents=True)
    assert not J.is_client(str(client))
    (client / "Wow.exe").write_bytes(b"MZ")
    assert not J.is_client(str(client))                                     # a 32-bit client isn't it
    (client / edition.CLIENT_EXE).write_bytes(b"MZ")
    assert J.is_client(str(client)) and edition.CLIENT_EXE == "WowClient64.exe"
    assert not J.is_client("")


def test_either_client_running_counts(monkeypatch):
    def tasklist(out):
        return lambda *a, **k: types.SimpleNamespace(stdout=out)
    monkeypatch.setattr(J.os, "name", "nt")
    monkeypatch.setattr(J.subprocess, "run", tasklist(f'"explorer.exe","1"\n"{edition.CLIENT_EXE}","2"\n'))
    assert J.wow_running()
    monkeypatch.setattr(J.subprocess, "run", tasklist('"Wow.exe","3"\n'))
    assert J.wow_running()
    monkeypatch.setattr(J.subprocess, "run", tasklist('"WowError.exe","4"\n"notwow.exe","5"\n'))
    assert not J.wow_running()


# -- the preview's helms and shoulders ----------------------------------------------------
def test_a_display_row_carries_its_geoset_group_override():
    row = [0, 0, 0, 0, 0, -1, *(0,) * 6, *(0,) * 6, 644, 645]
    idx = M.DisplayIndex({"displays": {"1": [*row, 1], "2": row}, "model_files": {}, "comp_models": {}, "tex_files": {},
                          "comp_tex": {}, "sections": {}, "model_mat": {}})
    assert idx.row(1)["geoset_override"] == 1 and idx.row(1)["helmet_vis"] == [644, 645]
    assert idx.row(2)["geoset_override"] == 0                              # an index from before it was kept
