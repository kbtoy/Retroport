"""Run the retail backport kit - with a local retail install as its data source, where there is one.

The kit (wow-retail-backport's ``bp.py``) reads retail through one function, ``wago._get(url, dest)``:
a table as wago.tools' CSV, a file by FileDataID, at the project's pinned build, each kept on disk
once fetched. This launcher runs the kit as it is - its files are not touched or copied - with
that function answered from a local install when the request is for the install's own build:

* a table: our DB2 reader's rows written as wago's CSV (``ID`` + WoWDBDefs column names, arrays as
  ``Name_0``, ``Name_1``; a table keyed by its file - ModelFileData, TextureFileData - has no ``ID``
  column, as on wago; checked identical to wago's on ChrRaces, ParticleColor, ItemNameDescription,
  HelmetGeosetData and ModelFileData at 12.1.5.70391). wago's tables also carry the server's
  hotfixes, which an install's own tables do not: a table this install has no FileDataID for (an
  older listfile) comes from wago;
* a file: its bytes out of the install; one the install does not list does not exist at that
  build ("missing", no network); one it holds encrypted comes from wago (which serves zeros for
  content Blizzard has not released - the kit's own "encrypted" answer).

Anything else - another build, the community listfile, the build list - goes to the network as
before. A summary of what came from where is printed when the kit finishes. Without ``--retail``
the kit reads wago.tools as it always does.

Either way the kit is shown WarcraftXL's open-folder patches: a FOLDER named like an archive
(``Data\\patch-H.MPQ\\...``, as Equip Plus installs its pieces) is mounted by those clients where a
packed patch of that name would be. A kit whose client reader opens only MPQ files (its ``client``
module has no ``FolderArchive``) is handed our ``FolderArchive`` for those folders, in this process
only - its files are not touched.

And a model the client holds both as retail's (MD21) and, beneath it, as 3.3.5's (MD20) is read as
the 3.3.5 one. The x64 client (wowdecomp-dx11) mounts retail bodies over the 3.3.5 ones and draws
those, but it places a 3.3.5 helm by the 3.3.5 body it was made for (its helmet lift); the kit only
reads MD20 bodies, so on that client it found no Kul Tiran or Pandaren body at all.

The kit itself is changed in this process only - its files are never touched - where it trips over
what the workbench gives it:

* tables an older kitlocal cached with an ``ID`` column wago's don't have (ModelFileData,
  TextureFileData: the kit's ``newtech`` called it new retail technology) are put right, the
  file as it was kept beside it (``.retroport-backup``);
* a sequence a model calls external (flag 0x20 clear) but keys nothing for - nothing to stream - is
  made resident, and a model is given only the ``.anim`` files of sequences it does stream: the
  kit copied a source model's every ``.anim`` to each per-race helm, and the audit then wanted
  thousands of files no one had made ("C1/C2 closure ... .anim missing");
* the build plan forgets displays the selection no longer has (a piece taken out of the basket):
  the audit checked every display the plan ever held and wanted their files;
* its export of retail's 3D pieces for a client mod (``build --extension``) leaves out helms -
  their own model is the 3.3.5 row's - and with them the collection part some also wear (the Damned
  Necrolyte skull's hood: group 27 of the set's shared body model). That part is exported too, by
  the kit's own export run once more on just those parts (shown to it as slot ``head_collection``,
  filtered by the head's own geoset groups), and the workbench gives Equip Plus rows for the helm
  and its hood (``eprows``);
* its ``measure`` (helm placement and body geosets, minutes the first time) waits until the
  selection holds something worn on the body: weapons need neither - until then it passes with
  nothing measured, and the workbench runs it when a selection needs it (``Kit.needs_measure``);
* its ``tables`` step numbers items and displays around every id the workbench's projects ever
  gave (``--ids``, ``itemids``): a look that comes back gets its old ids again where they're free,
  and no new look gets another's - the kit only skips the ids its client tables still hold, so a
  look taken out (or installed by an older project) could have its numbers given to another;
* a helm that sits a little off a client body (the audit's "P1 placement": its centroid more than
  12 cm from retail's, say on a ported race whose body isn't retail's) is a warning - "P1
  placement (warning)" in the audit's notes - not a failure that stops the install. prove-gates
  runs its own audit in a process of its own, as the kit wrote it, so its planted misplaced helm
  is still caught.

And its ``prove-gates`` plants its defects where they can be seen. It picks models from the build's
manifest, which also lists files the build made but doesn't ship (a shoulder's untrimmed source
beside the trimmed variant the patch carries), and its "flying part" (M8) moves the first bone a
model keys - which, in a trimmed variant, may carry no vertex of the mesh it ships. Either way the
planted defect moves nothing the audit could see, and prove-gates calls the audit broken ("M8
motion MISSED"). Shown only the shipped models whose first keyed bone moves a shipped vertex, it
plants where the audit looks; the audit itself is not touched.

usage: python -m retroport.workbench.kitlocal --bp <bp.py> [--retail <install> --dbd <WoWDBDefs\\definitions>
           --listfile <listfile.csv> --product wow --cache <dir>] -- <bp.py arguments>
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import runpy
import struct
import sys
import threading
from collections import Counter

DB2_URL = re.compile(r"^https://wago\.tools/db2/([^/?]+)/csv\?build=(.+)$")
FILE_URL = re.compile(r"^https://wago\.tools/api/casc/(\d+)\?download&version=(.+)$")


def flatten(row: dict) -> dict:
    """A DB2 row as wago's CSV columns: an array field ``X`` becomes ``X_0``, ``X_1``, ..."""
    out = {}
    for k, v in row.items():
        if isinstance(v, (list, tuple)):
            for i, x in enumerate(v):
                out[f"{k}_{i}"] = x
        else:
            out[k] = v
    return out


def table_csv(rows: list[tuple[int, dict]]) -> str:
    """Rows as wago's CSV text: ID first (unless FileDataID is already the key column),
    then the columns in the order the rows have them."""
    flat = [flatten(r) for _i, r in rows]
    has_fdid_key = bool(flat and "ID" not in flat[0] and "FileDataID" in flat[0])
    columns = [] if has_fdid_key else ["ID"]
    seen = set(columns)
    for r in flat[:1] + flat[-1:]:
        for k in r:
            if k not in seen:
                seen.add(k)
                columns.append(k)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for (rid, _r), r in zip(rows, flat):
        w.writerow([rid if c == "ID" else _cell(r.get(c, "")) for c in columns])
    return buf.getvalue()


def _cell(v):
    """wago's float text: 11 decimals, trailing zeros dropped (-1.70000004768, 0.07699999958, 0)."""
    if isinstance(v, float):
        text = f"{v:.11f}".rstrip("0").rstrip(".")
        return "0" if text in ("", "-0") else text
    return v


class LocalRetail:
    """Answers the kit's requests from a local install (see the module doc)."""

    def __init__(self, source, extra_listfiles: list[str] = ()):
        self.src = source
        self.build = source.build
        self.stats: Counter = Counter()
        self.fallbacks: list[str] = []
        self._lock = threading.Lock()
        self._extra = [p for p in extra_listfiles if p and os.path.isfile(p)]

    def _db2_id(self, name: str) -> int | None:
        self.src.open()
        fdid = self.src._db2.get(name.lower())
        if fdid is None and self._extra:
            from .catalog import db2_ids
            for lf in self._extra:                           # a newer listfile (the kit's own) names more
                self.src._db2.update({k: v for k, v in db2_ids(lf).items() if k not in self.src._db2})
            self._extra = []
            fdid = self.src._db2.get(name.lower())
        return fdid

    def table(self, name: str, dest: str) -> str | None:
        """Write the table's CSV to ``dest``: "ok", or None when this install cannot answer."""
        if self._db2_id(name) is None:
            return None
        try:
            text = table_csv(self.src.table(name))
        except Exception as e:                               # unreadable here: let wago answer
            self._note(f"table {name}: {type(e).__name__}: {e}")
            return None
        _write(dest, text.encode("utf-8"))
        with self._lock:
            self.stats["tables"] += 1
        return "ok"

    def file(self, fdid: int, dest: str) -> str | None:
        """Write the file's bytes to ``dest``: "ok", "missing" (not in this build), or None."""
        casc = self.src.open()
        if fdid not in casc:
            with self._lock:
                self.stats["missing"] += 1
            return "missing"
        try:
            data = self.src.read(fdid)
        except Exception as e:                               # encrypted here, or not stored and no CDN
            self._note(f"file {fdid}: {type(e).__name__}")
            return None
        _write(dest, data)
        with self._lock:
            self.stats["files"] += 1
        return "ok"

    def _note(self, msg: str) -> None:
        with self._lock:
            self.fallbacks.append(msg)

    def wrap(self, original):
        """The kit's ``_get`` answered locally where it can, else ``original``."""
        def _get(url, dest, *args, **kwargs):
            m = DB2_URL.match(url)
            if m and m.group(2) == self.build:
                st = self.table(m.group(1), dest)
                if st:
                    return st
            m = FILE_URL.match(url)
            if m and m.group(2) == self.build:
                st = self.file(int(m.group(1)), dest)
                if st:
                    return st
            with self._lock:
                self.stats["network"] += 1
            return original(url, dest, *args, **kwargs)
        return _get

    def summary(self) -> str:
        s = self.stats
        line = (f"local retail {self.build}: {s['tables']} table(s) and {s['files']} file(s) from "
                f"{self.src.spec.path}; {s['missing']} not in this build; {s['network']} request(s) to the network")
        if self.fallbacks:
            line += "\n  from the network instead: " + "; ".join(self.fallbacks[:12]) + \
                    (f" (+{len(self.fallbacks) - 12} more)" if len(self.fallbacks) > 12 else "")
        return line


class FolderArchive:
    """An open-folder patch read like an MPQ (``locate`` / ``read``, names without case, its
    ``(listfile)`` made from what's in it)."""

    def __init__(self, path: str):
        self.path = path
        self.index = {}
        for d, _dirs, names in os.walk(path):
            for n in names:
                full = os.path.join(d, n)
                rel = os.path.relpath(full, path).replace(os.sep, "\\")
                self.index[rel.lower()] = (rel, full)

    def locate(self, name: str):
        hit = self.index.get(name.replace("/", "\\").lower())
        return hit[1] if hit else None

    def read(self, name: str) -> bytes:
        if name == "(listfile)":
            return "\r\n".join(rel for rel, _full in self.index.values()).encode("latin-1", "replace")
        full = self.locate(name)
        if full is None:
            raise KeyError(name)
        with open(full, "rb") as f:
            return f.read()


def show_folder_patches(client) -> bool:
    """Teach the kit's ``client`` module open-folder patches (see the module doc); False when it
    knows them already."""
    if hasattr(client, "FolderArchive"):
        return False
    real_os, real_reader = client.os, client.MpqReader

    class _Path:
        def __getattr__(self, name):
            return getattr(real_os.path, name)

        @staticmethod
        def isfile(p):
            return real_os.path.isfile(p) or (real_os.path.isdir(p) and str(p).lower().endswith(".mpq"))

    class _Os:
        path = _Path()

        def __getattr__(self, name):
            return getattr(real_os, name)

    client.os = _Os()
    client.MpqReader = lambda p, *a, **k: FolderArchive(p) if real_os.path.isdir(p) else real_reader(p, *a, **k)
    return True


def classic_models_first(client) -> bool:
    """Teach the kit's ``client`` module to read, for a model, the 3.3.5 (MD20) copy beneath a retail
    (MD21) one (see the module doc); False when it does already."""
    cls = getattr(client, "Client", None)
    if cls is None or getattr(cls.who, "classic_first", False):
        return False
    who = cls.who

    def _who(self, path, data=False):
        if not str(path).lower().endswith(".m2"):
            return who(self, path, data)
        name, retail = str(path).replace("/", "\\"), None
        for p, a in self.archives:
            try:
                if a.locate(name) is None:
                    continue
                body = a.read(name)
            except Exception:
                continue
            if body[:4] != b"MD21":
                return p, (body if data else None)
            retail = retail or (p, body if data else None)
        return retail
    _who.classic_first = True
    cls.who = _who
    return True


FILE_KEYED = ("ModelFileData", "TextureFileData")         # wago's CSV of these has no ID column


def repair_cached_tables(work: str) -> list[str]:
    """The project's cached tables an older kitlocal wrote with an ``ID`` column wago's don't have,
    without it (each one kept as it was beside it, ``.retroport-backup``). The ones put right."""
    fixed = []
    root = os.path.join(work, "db2")
    if not os.path.isdir(root):
        return fixed
    for build in os.listdir(root):
        for name in FILE_KEYED:
            path = os.path.join(root, build, name + ".csv")
            try:
                with open(path, encoding="utf-8", newline="") as fh:
                    rows = list(csv.reader(fh))
            except OSError:
                continue
            if not rows or rows[0][:1] != ["ID"] or "FileDataID" not in rows[0]:
                continue
            backup = path + ".retroport-backup"
            if not os.path.exists(backup):
                os.replace(path, backup)
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(r[1:] for r in rows)
            _write(path, buf.getvalue().encode("utf-8"))
            fixed.append(f"{build}/{name}")
    return fixed


def resident_when_unkeyed(body: bytes, needed: set, sequences_at: int) -> bytes:
    """``body`` with every external sequence (flag 0x20 clear, not an alias) that isn't in
    ``needed`` - it keys nothing, there's nothing to stream - made resident (0x20 set)."""
    n, o = struct.unpack_from("<II", body, sequences_at)
    out = None
    for s in range(n):
        at = o + s * 64 + 0x0C
        fl = struct.unpack_from("<I", body, at)[0]
        if not fl & 0x60 and s not in needed:
            out = out or bytearray(body)
            struct.pack_into("<I", out, at, fl | 0x20)
    return bytes(out) if out is not None else body


def keep_needed_anims(convert, m2edit, m2model) -> bool:
    """Sequences that key nothing made resident wherever the kit packs a model, and each model
    given only the ``.anim`` files of sequences it streams (see the module doc). False when the
    kit does this itself."""
    if hasattr(convert, "mark_unused_anims_resident"):
        return False

    def resident(model):
        model = bytes(model)
        needed = {s for s, _a, _v in convert.required_external_animations(model)} |                  {s for s, a, _v in m2model.external_set(model) if a > convert.MAX_ANIM_ID}   # as the kit leaves them
        return resident_when_unkeyed(model, needed, 0x1C)

    for name in ("union_bounds", "repack"):
        original = getattr(m2edit, name)
        setattr(m2edit, name, lambda model, *a, _original=original, **k: _original(resident(model), *a, **k))

    copy_anims = convert.Builder.copy_anims

    def only_streamed(self, src_rel: str, rel: str) -> None:
        want = {m2model.anim_name(rel, a, v).lower() for _s, a, v in m2model.external_set(self.read_built(rel))
                if a <= convert.MAX_ANIM_ID}
        write = self.write

        def write_wanted(dst, data, kind, *a, **k):
            if kind == "anim" and dst.lower() not in want:
                return None
            return write(dst, data, kind, *a, **k)
        self.write = write_wanted
        try:
            copy_anims(self, src_rel, rel)
        finally:
            del self.write                                   # the class's own again
    convert.Builder.copy_anims = only_streamed
    return True


def plan_follows_selection(build_mod, bpcore) -> None:
    """The kit's build first drops plan entries for displays the selection no longer has."""
    run = build_mod.run

    def _run(prj, log, only, *a, **k):
        if not only:
            displays = (bpcore.load_json(prj.path("selection.json"), {}) or {}).get("displays") or {}
            path = prj.path("build", "plan.json")
            plan = bpcore.load_json(path, {}) or {}
            kept = {d: p for d, p in plan.items() if d in displays}
            if len(kept) < len(plan):
                bpcore.save_json(path, kept)
                log(f"kitlocal: {len(plan) - len(kept)} display(s) no longer selected left out of the build plan")
        return run(prj, log, only, *a, **k)
    build_mod.run = _run


def ids_across_projects(tables, bpcore, registry: str) -> None:
    """The kit's tables step with every project's ids (see the module doc)."""
    from . import itemids
    run, dbc = tables.run, tables._dbc

    def _run(prj, log, *a, **k):
        reg = itemids.load(registry)
        path = prj.path("ids.json")
        ids = bpcore.load_json(path, None) or {"display": {}, "item": {}, "helmvis": {}}
        plan = bpcore.load_json(prj.path("build", "plan.json"), {}) or {}
        looks = [d for d, p in plan.items() if (p or {}).get("ok")]
        got = itemids.give_back(reg, ids, looks, dbc(prj, "Item").ids(), dbc(prj, "ItemDisplayInfo").ids())
        if got:
            bpcore.save_json(path, ids)
            log(f"kitlocal: {got} id(s) given back to looks that had them before")
        reserved = itemids.reserved_for(reg, ids)

        class _Reserved:
            def __init__(self, table, extra):
                self._t, self._extra = table, extra

            def __getattr__(self, name):
                return getattr(self._t, name)

            def ids(self):
                return self._t.ids() | self._extra

        def _dbc(prj_, name):
            t = dbc(prj_, name)
            extra = reserved["item"] if name == "Item" else reserved["display"] if name == "ItemDisplayInfo" else None
            return _Reserved(t, extra) if extra else t
        tables._dbc = _dbc
        try:
            return run(prj, log, *a, **k)
        finally:
            tables._dbc = dbc
    tables.run = _run


WEAPON_SLOTS = {"mainhand", "offhand", "ranged", "held"}        # the kit's: nothing worn on the body


def wears_on_body(selection: dict) -> bool:
    """Whether a selection holds a piece worn on the body (a helm, armour, a cloak, shoulders) - what
    the kit's measurements are for; weapons, shields and off-hands need neither."""
    return any((d or {}).get("slot") not in WEAPON_SLOTS for d in ((selection or {}).get("displays") or {}).values())


MEASUREMENTS = ("helm_shift.json", "geoset_map.json")          # what the kit's measure writes in client\


def measured(work: str) -> bool:
    """Whether the kit measured this project's client (helm placement and body geosets)."""
    return all(os.path.isfile(os.path.join(work, "client", n)) for n in MEASUREMENTS)


def measure_when_worn(measure, bpcore) -> None:
    """The kit's measure only for a selection with something worn on the body (see the module doc)."""
    run = measure.run

    def _run(prj, log, only=None, *a, **k):
        if not only and not wears_on_body(bpcore.load_json(prj.path("selection.json"), {}) or {}):
            log("kitlocal: nothing selected is worn on the body (weapons only) - measuring waits until something is")
            return 0
        return run(prj, log, only, *a, **k)
    measure.run = _run


ATTACHED_SLOTS = ("head",)      # a slot whose own model is the 3.3.5 row's (the kit's export skips it; shoulders
                                # too, but no retail shoulder is known to wear a collection part)
ALIAS = "_collection"           # such a slot's collection part, shown to the export under <slot>_collection


def attached_collections(build_mod, bpcore) -> None:
    """The kit's export of retail's 3D pieces (``build --extension``) also gives a helm's collection
    part (see the module doc)."""
    export = build_mod.export_extension

    def _export(prj, log, sel, plan, *a, **k):
        export(prj, log, sel, plan, *a, **k)
        retail = build_mod.Retail(prj)
        parts = {}
        for d, e in (sel.get("displays") or {}).items():
            if e.get("slot") not in ATTACHED_SLOTS or not e.get("row"):
                continue
            ks = {kk for kk in (0, 1) if retail.multi_slot(e["row"].get(f"ModelResourcesID_{kk}", "0"))}
            models = [m for m in e.get("models", []) if m["k"] in ks]
            if models:
                parts[d] = dict(e, slot=e["slot"] + ALIAS, models=models)
        if not parts:
            return
        path = prj.path("out", "extension", "extension.json")
        man = bpcore.load_json(path, {}) or {}
        groups = build_mod.SLOT_GROUPS
        for slot in ATTACHED_SLOTS:
            groups[slot + ALIAS] = groups[slot]
        slots = build_mod.PIECE_SLOTS
        build_mod.PIECE_SLOTS = (*slots, *(s + ALIAS for s in ATTACHED_SLOTS))
        try:
            export(prj, log, {**sel, "displays": parts}, plan, *a, **k)
        finally:
            build_mod.PIECE_SLOTS = slots
            for slot in ATTACHED_SLOTS:
                groups.pop(slot + ALIAS, None)
        got = bpcore.load_json(path, {}) or {}
        for d, entry in got.items():
            man[d] = dict(entry, slot=entry["slot"][:-len(ALIAS)] if entry["slot"].endswith(ALIAS) else entry["slot"])
        bpcore.save_json(path, man)
        log(f"kitlocal: {len(got)} helm(s) with a collection part (a hood) -> extension.json")
    build_mod.export_extension = _export


PLACEMENT, PLACEMENT_WARNING = "P1 placement", "P1 placement (warning)"


def placement_warns(gates) -> None:
    """The audit's helm-placement misses become notes ``P1 placement (warning)`` (see the module doc)."""
    placement = gates.placement

    def _placement(prj, rep, *a, **k):
        fail = rep.fail
        rep.fail = lambda gate, what: (rep.note(PLACEMENT_WARNING, what) if gate == PLACEMENT else fail(gate, what))
        try:
            return placement(prj, rep, *a, **k)
        finally:
            del rep.fail
    gates.placement = _placement


MODEL_KINDS = ("helm", "shoulder", "weapon", "shield")


def first_keyed_bone(body: bytes) -> int | None:
    """The bone prove-gates' M8 moves: the first whose translation is keyed in sequence 0 (when that
    sequence lives in the model) or in a global loop."""
    nb, ob = struct.unpack_from("<II", body, 0x2C)
    ns, so = struct.unpack_from("<II", body, 0x1C)
    resident0 = ns and struct.unpack_from("<I", body, so + 0x0C)[0] & 0x20
    for i in range(nb):
        tr = ob + i * 88 + 0x10
        gseq = struct.unpack_from("<h", body, tr + 2)[0]
        nv, ov = struct.unpack_from("<II", body, tr + 12)
        for s in (range(nv) if gseq >= 0 else ([0] if resident0 else [])):
            if s < nv:
                count, at = struct.unpack_from("<II", body, ov + s * 8)
                if count and at + 12 <= len(body):
                    return i
    return None


def moves_what_it_ships(body: bytes, skin: bytes) -> bool:
    """Whether moving the model's first keyed bone moves a vertex its skin draws (a bone under it
    moves with it)."""
    bone = first_keyed_bone(body)
    if bone is None:
        return True                                       # nothing for M8 to move here: no harm
    nb, ob = struct.unpack_from("<II", body, 0x2C)
    parent = [struct.unpack_from("<h", body, ob + i * 88 + 8)[0] for i in range(nb)]

    def under(b: int) -> bool:
        for _ in range(nb):
            if b == bone:
                return True
            if b < 0 or b >= nb:
                return False
            b = parent[b]
        return False
    nverts, ov = struct.unpack_from("<II", body, 0x3C)
    n, o = struct.unpack_from("<II", skin, 0x04)          # the vertices this skin draws
    for k in range(n):
        v = struct.unpack_from("<H", skin, o + k * 2)[0]
        if v >= nverts:
            continue
        at = ov + v * 48
        weights, bones = body[at + 12:at + 16], body[at + 16:at + 20]
        if any(weights[j] and under(bones[j]) for j in range(4)):
            return True
    return False


def shipped_manifest(provegates, work: str) -> None:
    """prove-gates shown only the shipped models a planted defect shows in (see the module doc)."""
    import json as _json
    import bpcore
    import gates
    import scan

    shipped: dict = {}

    def closure() -> set:
        if "keys" not in shipped:
            prj = bpcore.Project(work)
            plan = _json.load(open(os.path.join(work, "build", "plan.json"), encoding="utf-8"))
            want, _m = gates.closure(prj, plan, scan.load(prj))
            shipped["keys"] = {k.lower() for k in want}
        return shipped["keys"]

    def visible(build: str, key: str, entry: dict) -> bool:
        if entry.get("kind") not in MODEL_KINDS or not key.lower().endswith(".m2"):
            return True
        path = os.path.join(build, entry.get("path") or key)
        try:
            with open(path, "rb") as fh:
                body = fh.read()
            with open(path[:-3] + "00.skin", "rb") as fh:
                skin = fh.read()
            return moves_what_it_ships(body, skin)
        except (OSError, struct.error):
            return True

    class _Json:
        def __getattr__(self, name):
            return getattr(_json, name)

        @staticmethod
        def load(fh, *a, **k):
            data = _json.load(fh, *a, **k)
            name = str(getattr(fh, "name", ""))
            if name.lower().endswith("manifest.json") and isinstance(data, dict):
                keep = closure()
                build = os.path.dirname(name)
                ok = {key: v for key, v in data.items() if (not keep or key.lower() in keep) and visible(build, key, v)}
                if len(ok) < len(data):
                    print(f"kitlocal: prove-gates plants where the audit can see it ({len(data) - len(ok)} manifest "
                          "entries left out: built but not shipped, or a first keyed bone that moves no shipped vertex)",
                          flush=True)
                    data = ok
            return data
    provegates.json = _Json()


def _write(dest: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part = f"{dest}.{threading.get_ident()}.local"
    with open(part, "wb") as fh:
        fh.write(data)
    os.replace(part, dest)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        print("usage: python -m retroport.workbench.kitlocal --bp <bp.py> --retail <install> ... -- <bp.py args>")
        return 2
    cut = argv.index("--")
    ap = argparse.ArgumentParser(prog="kitlocal")
    ap.add_argument("--bp", required=True)
    ap.add_argument("--retail", default="")
    ap.add_argument("--product", default="wow")
    ap.add_argument("--dbd", default="")
    ap.add_argument("--listfile", default="")
    ap.add_argument("--cache", default=os.path.join(os.path.expanduser("~"), ".retroport", "workbench", "cache"))
    ap.add_argument("--ids", default="", help="the workbench's ids of every project (itemids)")
    a = ap.parse_args(argv[:cut])
    kit_args = argv[cut + 1:]

    scripts = os.path.dirname(os.path.abspath(a.bp))
    for d in (os.path.join(scripts, "lib"), scripts):
        if d not in sys.path:
            sys.path.insert(0, d)
    try:
        import client as kit_client                       # the kit's own modules, as they are
        if show_folder_patches(kit_client):
            print("kitlocal: the kit is shown the client's open-folder patches", flush=True)
        classic_models_first(kit_client)
    except ImportError:
        pass
    work = kit_args[kit_args.index("--work") + 1] if "--work" in kit_args[:-1] else ""
    if work:
        fixed = repair_cached_tables(work)
        if fixed:
            print(f"kitlocal: put right {', '.join(fixed)} (cached with an ID column wago's tables don't have)", flush=True)
    try:
        import convert
        import m2edit
        import m2model
        keep_needed_anims(convert, m2edit, m2model)
        import bpcore
        import build as kit_build
        plan_follows_selection(kit_build, bpcore)
        attached_collections(kit_build, bpcore)
        import gates
        placement_warns(gates)
        import measure
        measure_when_worn(measure, bpcore)
        if a.ids:
            import tables as kit_tables
            ids_across_projects(kit_tables, bpcore, a.ids)
    except ImportError:
        pass
    if kit_args[:1] == ["prove-gates"] and "--work" in kit_args:
        try:
            import provegates
            shipped_manifest(provegates, kit_args[kit_args.index("--work") + 1])
        except ImportError:
            pass
    local = None
    if a.retail:
        from .catalog import Source, SourceSpec
        src = Source(SourceSpec("retail", "Retail", a.retail, a.product, True), a.dbd, a.listfile, a.cache)
        local = LocalRetail(src, [os.path.join(work, "listfile.csv")] if work else [])
        import wago
        wago._get = local.wrap(wago._get)
        print(f"kitlocal: retail data from {a.retail} (build {local.build}); the kit's other requests go to the network",
              flush=True)
    sys.argv = [a.bp, *kit_args]
    code = 0
    try:
        runpy.run_path(a.bp, run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        if local:
            print(local.summary(), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
