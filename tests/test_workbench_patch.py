"""The patch Install writes: compressed files, MPQ v2 past 4 GB, the room it asks for first and the
backups it keeps."""

import json
import os
import struct

from retroport.mpq import MPQ
from retroport.workbench import direct as DR
from retroport.workbench import retailpack as RP

from test_workbench_direct import BASKET, PLAN, _direct

WORDS = b"the quick brown fox jumps over the lazy dog " * 400          # compresses well: about 17 KB
NOISE = os.urandom(3 * RP.SECTOR + 123)                               # doesn't compress


def _header(path):
    with open(path, "rb") as fh:
        head = fh.read(44)
    magic, size, _archive, fmt, shift, ht, bt, ht_n, bt_n = struct.unpack_from("<4sIIHHIIII", head)
    hi = struct.unpack_from("<QHH", head, 32) if fmt else None
    return {"magic": magic, "header": size, "format": fmt, "sector": 512 << shift, "hash": ht, "block": bt,
            "slots": ht_n, "blocks": bt_n, "hi": hi}


def _blocks(path):
    """Each file's (offset, stored size, size, flags), read as Storm does: the block table decrypted."""
    m = MPQ(path)
    try:
        return list(m._blocks)
    finally:
        m.close()


def test_a_file_is_kept_compressed_when_that_makes_it_smaller():
    stored, flags = RP.squeeze(WORDS)
    assert flags == 0x80000200 and len(stored) < len(WORDS) // 4
    count = (len(WORDS) + RP.SECTOR - 1) // RP.SECTOR
    offsets = struct.unpack_from(f"<{count + 1}I", stored)
    assert offsets[0] == 4 * (count + 1) and offsets[-1] == len(stored)     # Storm's sector table
    assert all(stored[at] == 0x02 for at in offsets[:-1])                   # each sector: zlib's mask byte first
    assert RP.squeeze(NOISE) == (NOISE, 0x80000000)                        # nothing saved: as it is
    assert RP.squeeze(b"") == (b"", 0x80000000)


def test_the_patch_reads_back_file_for_file_compressed(tmp_path):
    files = {"a\\words.txt": WORDS, "b\\noise.blp": NOISE, "c\\tiny.txt": b"x", "d\\empty.txt": b"",
             "e\\mixed.m2": WORDS[:5000] + NOISE + WORDS, "f\\one-sector.skin": WORDS[:RP.SECTOR]}
    path = str(tmp_path / "patch-Q.MPQ")
    w = RP.PatchWriter(path, workers=3)
    for name, data in files.items():
        w.add(name, data)
    assert w.alias("g\\words-too.txt", "a\\words.txt")
    w.close()
    h = _header(path)
    assert h["magic"] == b"MPQ\x1a" and h["format"] == 0 and h["header"] == 32 and h["sector"] == 4096
    assert not w.v2 and w.raw == sum(len(v) for v in files.values()) + len(b"\r\n".join(
        n.encode() for n in [*files, "g\\words-too.txt"]))
    assert os.path.getsize(path) < w.raw
    m = MPQ(path)
    try:
        for name, data in files.items():
            assert m.read(name) == data, name
        assert m.read("g\\words-too.txt") == WORDS
    finally:
        m.close()
    flags = {b[3] for b in _blocks(path)}
    assert flags == {0x80000000, 0x80000200}                     # some compressed, some as they are


def test_a_folder_mpqs_build_keeps_its_files_as_they_are(tmp_path):
    path = str(tmp_path / "patch-Q.MPQ")
    w = RP.PatchWriter(path, compress=False)
    w.add("a\\words.txt", WORDS)
    w.close()
    assert {b[3] for b in _blocks(path)} == {0x80000000}
    m = MPQ(path)
    try:
        assert m.read("a\\words.txt") == WORDS
    finally:
        m.close()


def test_past_4_gb_the_patch_is_mpq_v2_as_the_client_reads_it(tmp_path, monkeypatch):
    monkeypatch.setattr(RP, "V1_END", 1000)                      # "4 GB" made small: the v2 header and its table
    path = str(tmp_path / "patch-Q.MPQ")
    w = RP.PatchWriter(path)
    w.add("a\\words.txt", WORDS)
    w.add("b\\noise.blp", NOISE)
    w.close()
    assert w.v2
    h, end = _header(path), os.path.getsize(path)
    assert h["format"] == 1 and h["header"] == 44
    hi_at, ht_hi, bt_hi = h["hi"]
    # the client's checks (SFileArchives.cpp, s_OpenArchive): both tables start inside the archive, the
    # extended block table (2 bytes a block) is its last part
    assert h["hash"] < end and h["block"] < end and (ht_hi, bt_hi) == (0, 0)
    assert hi_at == h["block"] + 16 * h["blocks"] and hi_at + 2 * h["blocks"] == end
    with open(path, "rb") as fh:
        fh.seek(hi_at)
        assert struct.unpack(f"<{h['blocks']}H", fh.read(2 * h["blocks"])) == (0,) * h["blocks"]
    m = MPQ(path)
    try:
        assert m.read("a\\words.txt") == WORDS and m.read("b\\noise.blp") == NOISE
    finally:
        m.close()


def test_the_reader_takes_an_offset_past_4_gb_from_the_extended_table(tmp_path, monkeypatch):
    """A v2 archive whose extended table says a block is 4 GB further on: the reader goes there (a file
    really past 4 GB is 4 GB to write - this checks the arithmetic against a fake seek)."""
    monkeypatch.setattr(RP, "V1_END", 100)
    path = str(tmp_path / "patch-Q.MPQ")
    w = RP.PatchWriter(path, compress=False)
    w.add("a\\far.txt", b"far away")
    w.close()
    h = _header(path)
    with open(path, "r+b") as fh:                                # block 0's top bits: 1
        fh.seek(h["hi"][0])
        fh.write(struct.pack("<H", 1))
    m = MPQ(path)
    try:
        assert m._blocks[0][0] >> 32 == 1
        seen = []
        real = m._fh

        class Far:
            def seek(self, at):
                seen.append(at)
                real.seek(at - (1 << 32) if at >= 1 << 32 else at)

            def read(self, n):
                return real.read(n)

        m._fh = Far()
        assert m.read("a\\far.txt") == b"far away" and seen[-1] >= 1 << 32
        m._fh = real
    finally:
        m.close()


def test_a_stopped_pack_leaves_nothing_behind(tmp_path):
    path = str(tmp_path / "patch-Q.MPQ")
    w = RP.PatchWriter(path, workers=2)
    for i in range(20):
        w.add(f"f\\{i}.txt", WORDS)
    w.abandon()
    assert not os.listdir(tmp_path)


def test_install_says_the_patchs_size_and_writes_it_compressed(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    assert d.go(BASKET, PLAN, install=False)
    assert any(line.startswith("   the patch: about ") for line in d.lines)
    assert any("wrote " in line and "MB" in line for line in d.lines)


def test_not_enough_room_stops_install_before_it_writes(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    monkeypatch.setattr(DR, "_free", lambda path: 1000)
    assert not d.go(BASKET, PLAN)
    said = [line for line in d.lines if line.startswith("!! not enough disk space")]
    assert said and "free" in said[0]
    assert not os.path.exists(os.path.join(d.work, "out", RP.PATCH))
    assert not os.path.exists(os.path.join(d.work, "out", RP.PATCH + ".part"))
    assert not os.path.exists(os.path.join(d.client, "Data", RP.PATCH))


def test_the_room_asked_for_adds_up_per_disk(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    asked = {}
    monkeypatch.setattr(DR, "_free", lambda path: asked.setdefault(DR._drive(path), 0) or 0)
    why = d.room(100 << 20, install=True)
    assert why.startswith("not enough disk space")
    assert "the build" in why and "the client's copy" in why              # one disk here: both on it
    monkeypatch.setattr(DR, "_free", lambda path: 1 << 40)
    assert d.room(100 << 20, install=True) == ""


def _backup(root, stamp, record="install.json"):
    folder = os.path.join(root, stamp)
    os.makedirs(os.path.join(folder, "client"))
    if record:
        with open(os.path.join(folder, record), "w") as fh:
            json.dump({"time": stamp, "client": [], "added": [], "basket": []}, fh)
    return folder


def test_only_the_last_three_backups_stay(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    root = os.path.join(d.work, "backups")
    for s in ("20261101-100000", "20261102-100000", "20261103-100000", "20261104-100000"):
        _backup(root, s)
    _backup(root, "20261102-120000", "install.json.undone")
    _backup(root, "20261101-090000", None)                      # an install that stopped part-way: kept
    os.makedirs(os.path.join(root, "notes"))                    # not a backup of ours: kept
    gone = d.prune_backups()
    assert gone == ["20261101-100000", "20261102-100000"]
    assert sorted(os.listdir(root)) == ["20261101-090000", "20261102-120000", "20261103-100000", "20261104-100000",
                                        "notes"]
    assert d.last_install()["time"] == "20261104-100000"


def test_each_install_keeps_three_backups_and_undo_goes_back_through_them(tmp_path, monkeypatch):
    d = _direct(tmp_path, monkeypatch)
    root = os.path.join(d.work, "backups")
    stamps = iter(f"20261115-1000{i:02d}" for i in range(10))
    monkeypatch.setattr(DR.time, "strftime", lambda fmt, *a: next(stamps) if fmt == "%Y%m%d-%H%M%S" else "x")
    for _ in range(5):
        assert d.go(BASKET, PLAN)
    kept = sorted(n for n in os.listdir(root) if DR.STAMP.match(n))
    assert len(kept) == 3
    assert any("took out 1 older backup(s)" in line for line in d.lines)
    assert d.undo() and d.undo() and d.undo()                   # back through the three
    assert not d.undo()
