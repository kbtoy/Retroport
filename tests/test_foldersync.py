"""folder-sync: a folder MPQ kept in step with a package's files (retroport/foldersync.py)."""

import json
import os

from retroport import foldersync
from retroport.mpq import write_archive


def _write(base, rel, data):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _read(base, rel):
    with open(os.path.join(base, rel), "rb") as fh:
        return fh.read()


def test_game_key():
    assert foldersync.game_key("Creature/Goblin/GoblinMale.M2") == "creature\\goblin\\goblinmale.m2"
    assert foldersync.game_key("\\.\\DBFilesClient\\Spell.dbc") == "dbfilesclient\\spell.dbc"


def test_sync_copies_only_what_changed(tmp_path):
    src, dst = str(tmp_path / "src"), str(tmp_path / "patch-Z.MPQ")
    _write(src, "Creature\\A\\a.m2", b"one")
    _write(src, "Textures\\b.blp", b"two")
    r = foldersync.sync(src, dst, "pkg")
    assert sorted(r.added) == ["Creature\\A\\a.m2", "Textures\\b.blp"] and not r.changed
    assert _read(dst, "Creature\\A\\a.m2") == b"one"
    r = foldersync.sync(src, dst, "pkg")
    assert r.unchanged == 2 and not r.added and not r.changed and r.bytes_copied == 0
    _write(src, "Textures\\b.blp", b"two, again")
    r = foldersync.sync(src, dst, "pkg")
    assert r.changed == ["Textures\\b.blp"] and r.unchanged == 1
    assert _read(dst, "Textures\\b.blp") == b"two, again"
    # the manifest lies under a folder the client skips (it starts with ".")
    manifest = json.loads(_read(dst, ".retroport-sync\\pkg.json"))
    assert set(manifest["files"]) == {"creature\\a\\a.m2", "textures\\b.blp"}


def test_dry_run_changes_nothing(tmp_path):
    src, dst = str(tmp_path / "src"), str(tmp_path / "patch-Z.MPQ")
    _write(src, "a.txt", b"x")
    r = foldersync.sync(src, dst, "pkg", dry_run=True)
    assert r.added == ["a.txt"] and not os.path.exists(dst)


def test_dropped_files_are_removed_but_not_when_changed_by_hand(tmp_path):
    src, dst = str(tmp_path / "src"), str(tmp_path / "patch-Z.MPQ")
    _write(src, "Sub\\gone.blp", b"g")
    _write(src, "kept.blp", b"k")
    _write(src, "edited.blp", b"e")
    foldersync.sync(src, dst, "pkg")
    os.remove(os.path.join(src, "Sub\\gone.blp"))
    os.remove(os.path.join(src, "edited.blp"))
    _write(dst, "edited.blp", b"changed by hand")
    r = foldersync.sync(src, dst, "pkg")
    assert r.removed == ["Sub\\gone.blp"] and r.left == ["edited.blp"]
    assert not os.path.exists(os.path.join(dst, "Sub"))            # its emptied folder goes too
    assert _read(dst, "edited.blp") == b"changed by hand"


def test_another_packages_files_are_left_alone(tmp_path):
    a, b, dst = str(tmp_path / "a"), str(tmp_path / "b"), str(tmp_path / "patch-Z.MPQ")
    _write(a, "mine.blp", b"a")
    _write(a, "both.blp", b"a")
    _write(b, "both.blp", b"b")
    foldersync.sync(a, dst, "A")
    r = foldersync.sync(b, dst, "B")
    assert r.shared == ["both.blp (also A)"] and _read(dst, "both.blp") == b"b"
    r = foldersync.remove(dst, "B")
    assert r.removed == [] and os.path.exists(os.path.join(dst, "both.blp"))   # A still lists it
    r = foldersync.remove(dst, "A")
    assert sorted(r.removed) == ["mine.blp"] and r.left == ["both.blp"]       # B's bytes there now
    assert set(foldersync.manifests(dst)) == set()


def test_backup_and_restore_undo_a_sync(tmp_path):
    src, dst, kept = str(tmp_path / "src"), str(tmp_path / "patch-Q.MPQ"), str(tmp_path / "backup")
    _write(src, "a.blp", b"a1")
    _write(src, "b.blp", b"b1")
    first = foldersync.sync(src, dst, "wb", backup=str(tmp_path / "first"))
    assert first.manifest_added == ".retroport-sync\\wb.json"
    _write(src, "a.blp", b"a2")
    os.remove(os.path.join(src, "b.blp"))
    _write(src, "c.blp", b"c1")
    r = foldersync.sync(src, dst, "wb", backup=kept)
    assert r.changed == ["a.blp"] and r.removed == ["b.blp"] and r.added == ["c.blp"] and not r.manifest_added
    foldersync.restore(dst, kept, r.added)
    assert _read(dst, "a.blp") == b"a1" and _read(dst, "b.blp") == b"b1" and not os.path.exists(os.path.join(dst, "c.blp"))
    assert set(foldersync.manifests(dst)["wb"]["files"]) == {"a.blp", "b.blp"}       # the manifest as it was
    foldersync.restore(dst, str(tmp_path / "first"), first.added + [first.manifest_added])
    assert not any(os.path.isfile(os.path.join(root, n)) for root, _d, ns in os.walk(dst) for n in ns)


def test_packed_mpq_source(tmp_path):
    mpq, dst = str(tmp_path / "patch-Q.MPQ"), str(tmp_path / "patch-Z.MPQ")
    write_archive(mpq, {"Interface\\x.blp": b"blp", "(listfile)": b"Interface\\x.blp\r\n"})
    r = foldersync.sync(mpq, dst, "Q")
    assert r.added == ["Interface\\x.blp"] and _read(dst, "Interface\\x.blp") == b"blp"
