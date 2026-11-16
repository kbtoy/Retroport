"""Which client a folder holds (clients.py) and the server pack (serverpack.py)."""

import os
import re
import zipfile

import pytest

from retroport.workbench import clients as CL
from retroport.workbench import edition
from retroport.workbench import retailpack as RP
from retroport.workbench import serverpack as SP

from client_fakes import OLD, ULTRA, program

OTHER = "x86" if CL.WANT == "x64" else "x64"


def _folder(tmp_path, files: dict) -> str:
    root = tmp_path / "client"
    (root / "Data").mkdir(parents=True)
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return str(root)


# -- what the program is, not what it's called ------------------------------------------------
def test_no_program_is_no_client(tmp_path):
    cl = CL.look(_folder(tmp_path, {}))
    assert cl.kind == "none" and not cl.ok and edition.CLIENT_EXE in cl.problem
    assert CL.look("").kind == "none" and CL.look(str(tmp_path / "nowhere")).kind == "none"


def test_ultra_wow_is_the_one_install_goes_into(tmp_path):
    cl = CL.look(_folder(tmp_path, {edition.CLIENT_EXE: ULTRA}))
    assert (cl.kind, cl.arch, cl.exe) == ("ultra", CL.WANT, edition.CLIENT_EXE)
    assert cl.ok and cl.name == CL.ULTRA[CL.WANT] and not cl.note and not cl.folder_mpqs
    both = CL.look(_folder(tmp_path / "f", {edition.CLIENT_EXE: program(marks=(RP.MERGE_MARK, RP.FOLDER_MARK))}))
    assert both.ok and both.folder_mpqs


def test_a_plain_client_of_the_same_name_reads_only_335_data(tmp_path):
    cl = CL.look(_folder(tmp_path, {edition.CLIENT_EXE: program(marks=())}))    # a plain wowdecomp build
    assert cl.kind == "plain" and not cl.ok
    assert "reads only 3.3.5 data" in cl.problem and CL.ULTRA[CL.WANT] in cl.problem and "wowdecomp" in cl.name


def test_blizzards_wow_exe_with_or_without_warcraftxl(tmp_path):
    root = _folder(tmp_path, {"Wow.exe": program("x86", (), OLD)})
    cl = CL.look(root)
    assert cl.kind == "blizzard" and cl.name == "Blizzard's 3.3.5a Wow.exe" and "3.3.5 data" in cl.problem
    open(os.path.join(root, "WarcraftXL.dll"), "wb").close()
    cl = CL.look(root)
    assert cl.name.endswith("with WarcraftXL") and cl.injected == ["WarcraftXL.dll"] and not cl.ok
    assert "WarcraftXL reads some retail data" in cl.problem
    rebuilt = CL.look(_folder(tmp_path / "r", {"Wow.exe": program("x86", ())}))     # a rebuilt 32-bit Wow.exe
    assert rebuilt.kind == "plain"


def test_the_other_editions_ultra_wow_points_to_its_workbench(tmp_path):
    cl = CL.look(_folder(tmp_path, {"WowClient32.exe" if OTHER == "x86" else "WowClient64.exe": program(OTHER)}))
    assert cl.kind == "ultra" and cl.arch == OTHER and not cl.ok and CL.WORKBENCH[OTHER] in cl.problem


def test_ultra_wow_under_another_name_is_named(tmp_path):
    other = "Wow64.exe" if CL.WANT == "x64" else "Wow32.exe"
    cl = CL.look(_folder(tmp_path, {other: ULTRA}))
    assert cl.kind == "ultra" and not cl.ok and f"looks for {edition.CLIENT_EXE}" in cl.problem


def test_an_older_warcraftxl_client_still_installs_with_a_note(tmp_path):
    cl = CL.look(_folder(tmp_path, {edition.CLIENT_EXE: program(marks=(CL.WXL_MARK,))}))
    assert cl.kind == "wxl" and cl.ok and RP.LEGACY_PATCH in cl.note
    assert RP.patch_for(str(tmp_path / "client")) == RP.LEGACY_PATCH


def test_warcraftxls_dlls_beside_ultra_wow_are_not_needed(tmp_path):
    cl = CL.look(_folder(tmp_path, {edition.CLIENT_EXE: ULTRA, "Extensions/wxl-equip-plus/wxl-equip-plus.dll": b"MZ"}))
    assert cl.ok and "wxl-equip-plus.dll" in cl.note


def test_what_isnt_a_windows_program(tmp_path):
    cl = CL.look(_folder(tmp_path, {edition.CLIENT_EXE: b"MZ" + RP.MERGE_MARK}))  # no PE header
    assert cl.kind == "unknown" and not cl.ok


def test_install_refuses_a_client_that_cant_show_retail(tmp_path, monkeypatch):
    from test_workbench_direct import _direct
    d = _direct(tmp_path, monkeypatch)
    with open(os.path.join(d.client, edition.CLIENT_EXE), "wb") as fh:
        fh.write(program(marks=()))
    why = d.problems()
    assert any("reads only 3.3.5 data" in w for w in why)
    with pytest.raises(RuntimeError):
        d.start("go", d.go, {}, {})


# -- the server pack --------------------------------------------------------------------------
def test_the_shipped_patch_covers_every_ultra_wow_opcode():
    text = open(os.path.join(SP.FILES, SP.PATCH), encoding="ascii").read()
    head, diff = text.split("diff --git", 1)
    assert "GNU General Public License" in head and "git apply" in head
    files = re.findall(r"^diff --git a/(\S+)", "diff --git" + diff, re.M)
    assert files == ["src/server/game/Server/Protocol/Opcodes.cpp", "src/server/game/Server/Protocol/Opcodes.h"]
    entries = {int(x, 16) for x in re.findall(r"^\+\s*/\*(0x5[0-9a-fA-F]{2})\*/", diff, re.M)}
    assert set(range(0x521, 0x557)) <= entries
    assert re.search(r"^\+\s*NUM_MSG_TYPES\s*=\s*0x557", diff, re.M)


def test_the_server_pack_holds_the_sql_the_patch_and_the_notes(tmp_path):
    work = tmp_path / "direct"
    (work / "out" / "sql").mkdir(parents=True)
    items, mounts = work / "out" / "sql" / "retail-direct-items.sql", work / "mounts.sql"
    items.write_text("DELETE ...;", encoding="utf-8")
    mounts.write_text("INSERT ...;", encoding="utf-8")
    out = SP.build(str(work), [str(items), str(mounts)], r"F:\Game", "patch-Q.MPQ", False, "0.7.1")
    folder = out["folder"]
    assert sorted(os.listdir(os.path.join(folder, "sql"))) == ["1-retail-direct-items.sql", "2-mounts.sql"]
    with open(os.path.join(folder, "azerothcore", SP.PATCH), "rb") as a, open(os.path.join(SP.FILES, SP.PATCH), "rb") as b:
        assert a.read() == b.read()
    readme = open(os.path.join(folder, "README.txt"), encoding="utf-8", newline="").read()
    assert "\r\n" in readme and edition.NAME in readme and "0.7.1" in readme
    assert readme.index("1-retail-direct-items.sql") < readme.index("2-mounts.sql")
    assert "SOURCE " + os.path.join(folder, "sql", "1-retail-direct-items.sql").replace("\\", "/") + ";" in readme
    assert "USE acore_world;" in readme and "git apply --check" in readme and "Warden.Enabled = 0" in readme and 'SET wxlCustomOpcodes "0"' in readme
    assert os.path.join(r"F:\Game", "Data", "patch-Q.MPQ") in readme and CL.WORKBENCH[OTHER] in readme
    with zipfile.ZipFile(out["zip"]) as z:
        names = set(z.namelist())
    assert {"Retroport server pack/README.txt", f"Retroport server pack/azerothcore/{SP.PATCH}",
            "Retroport server pack/sql/2-mounts.sql"} <= {n.replace("\\", "/") for n in names}
    # made again: the last one replaced, nothing left from it
    again = SP.build(str(work), [], "", "patch-Q.MPQ", True, "0.7.1")
    assert os.listdir(os.path.join(again["folder"], "sql")) == []
    assert "None yet" in open(os.path.join(again["folder"], "README.txt"), encoding="utf-8").read()
    assert not os.path.exists(again["folder"] + ".new")
