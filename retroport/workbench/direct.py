"""The workbench's second way in: retail's own items, straight into the x64 client and the server.

The backport kit (``kit``) turns each look into 3.3.5 files any 3.3.5a client draws. The x64 client
(``WowClient64.exe``) draws retail's items itself, from retail's own tables and files, so this route
hands it those as they are:

* ``Data\\patch-Q.MPQ`` (``retailpack.patch_for``; patch-T in a client older than 2026-11-03, which
  reads only the top copy of the path tables) - retail's item tables (``retailpack.TABLES``, whole: the client reads any
  display from them), every file the looks name at retail's paths (models for every race and sex,
  their skins and textures, body layers, icons), a copy of a model's texture where the client looks
  for it (``retailpack.alias_for``), and the FileDataID path tables: the client's own (patch-R's)
  with the new files added - so Install again after patch-R is made again;
* the item SQL (``<data>\\direct\\out\\sql\\retail-direct-items.sql``, yours to apply): an
  item_template row per look, its displayid retail's own ItemDisplayInfo id, its entry the retail
  item's id (``retailpack.entry_for``); the Stats step's numbers after it;
* the basket's mounts (``mountpack``, route "direct"): retail's own models in their own folder and
  their sounds, the client's spell, creature and sound tables with their rows (in the same patch),
  their items' bag icons (rows in the item display table on top - the item kit's patch, backed up:
  ``mountpack.place_item_rows``), and their SQL (``retail-direct-mounts.sql``).

Nothing is converted, so there are no measurements, audit or Equip Plus pieces; a 32-bit 3.3.5
client shows these items without a model. The server's dbc folder is left alone: AzerothCore keeps
an item its Item.dbc doesn't have, and the x64 client takes the item's display from the server.
Install backs up the patch it replaces (``<data>\\direct\\backups\\<time>\\install.json``, the kit's
record format) and clears the client's Cache; Undo puts it back. It never runs SQL.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field

from . import catalog as C
from . import itemstats as IS
from . import kit as K
from . import mountpack as MP
from . import mounts as MT
from . import retailpack as RP

ORDER = ["read", "collect", "mounts", "pack", "sql"]
STEP_WORDS = {
    "read": "Read retail's item tables",
    "collect": "Work out every file the looks need",
    "mounts": "Make the mounts (retail's own models, the client's spell and creature tables)",
    "pack": "Pack the patch",
    "sql": "Write the server's item SQL",
}
SQL_NAME = "retail-direct-items.sql"
DB2_NAMES = {"ItemDisplayInfo": "itemdisplayinfo", "ModelFileData": "modelfiledata", "TextureFileData": "texturefiledata",
             "ItemDisplayInfoMaterialRes": "itemdisplayinfomaterialres",
             "ItemDisplayInfoModelMatRes": "itemdisplayinfomodelmatres", "Item": "item",
             "ItemModifiedAppearance": "itemmodifiedappearance", "ItemAppearance": "itemappearance"}


def _made_here(path: str) -> bool:
    """Whether the archive at ``path`` is one retail direct made (its manifest)."""
    from ..mpq import MPQ
    if not path or not os.path.isfile(path):
        return False
    try:
        m = MPQ(path)
        try:
            return m.has(RP.MANIFEST)
        finally:
            m.close()
    except Exception:
        return False


@dataclass
class DirectSettings:
    """What the page reads of a route's settings."""
    work: str
    client_data: str = ""
    server_dbc: str = ""                    # this route leaves the server's dbc folder alone


class Stopped(Exception):
    pass


@dataclass
class Files:
    """What goes in the patch besides the tables."""
    ship: dict[int, str]                     # FileDataID -> path, to put in the patch
    kinds: dict[int, str]                    # every file the looks name -> its kind ("model", "texture" ...)
    paths: dict[int, str]                    # every file the looks name -> its path (the client's own, if it had one)
    aliases: list[tuple[str, int]]           # (another path, texture FileDataID): a model's texture beside it
    base: dict[str, dict[int, str]]          # the client's path tables: {"model"/"texture": {fdid: path}}
    graph: RP.Graph | None = None
    displays: list[int] | None = None
    dbc: dict[str, bytes] = field(default_factory=dict)       # client tables (the mounts'), "Spell" -> bytes
    rides: list = field(default_factory=list)                  # the mounts (mounts.Ride)


class Direct:
    """Retail direct: one job at a time, its output in ``lines`` (as ``kit.Kit``)."""

    def __init__(self, data_dir: str, listfile: str = ""):
        self.data_dir, self.listfile = data_dir, listfile
        self.work = os.path.join(data_dir, "direct")
        self.client = ""                     # the client folder (Settings)
        self.source = None                   # retail, a local install (catalog.Source)
        self.lines: list[str] = []
        self.first = 0
        self.job: K.Job | None = None
        self.mount_catalog = lambda: None    # retail's mounts (the workbench sets it)
        self.mount_built = None              # the last build's mounts (mountpack.Built: the items' rows)
        self._lock = threading.Lock()

    # -- state ------------------------------------------------------------------
    @property
    def patch_name(self) -> str:
        """The patch this route installs in the client (``retailpack.patch_for``)."""
        return RP.patch_for(self.client)

    def own_patches(self) -> set[str]:
        """The client's archives this route made (lower case): its patch, and an earlier install's at
        the other letter (its manifest says whose) - the client as a build finds it leaves them out."""
        out = {self.patch_name.lower()}
        data = self.cfg.client_data
        for name in RP.OWN_PATCHES:
            path = os.path.join(data, name) if data else ""
            if name.lower() not in out and path and _made_here(path):
                out.add(name.lower())
        return out

    @property
    def cfg(self) -> DirectSettings:
        return DirectSettings(self.work, os.path.join(self.client, "Data") if self.client else "")

    def problems(self) -> list[str]:
        out = []
        if not self.client or not K.is_x64_client(self.client):
            out.append("Retail direct installs into the x64 client: choose its folder (with WowClient64.exe) in Settings")
        if self.source is None or getattr(getattr(self.source, "spec", None), "kind", "") != "local":
            out.append("Retail direct reads retail from your own install: set Retail items to \"My own install\" in Settings")
        if not self.listfile or not os.path.isfile(self.listfile):
            out.append("Retail direct needs the community listfile (Settings)")
        return out

    def retail_build(self) -> str:
        try:
            return self.source.build if self.source is not None else ""
        except Exception:
            return ""

    def last_install(self) -> dict | None:
        root = os.path.join(self.work, "backups")
        if not os.path.isdir(root):
            return None
        for stamp in sorted(os.listdir(root), reverse=True):
            rec = K._load_json(os.path.join(root, stamp, "install.json"))
            if rec:
                return rec | {"backup": os.path.join(root, stamp)}
        return None

    def sql_files(self) -> list[str]:
        out = [p for p in (os.path.join(self.work, "out", "sql", SQL_NAME),) if os.path.isfile(p)]
        mounts = (self.built_record().get("summary") or {}).get("mounts_sql")
        if mounts and os.path.isfile(mounts):
            out.append(mounts)
        return out

    def built_record(self) -> dict:
        return K._load_json(os.path.join(self.work, "out", "build.json"), {}) or {}

    def status(self, looks: set[str] | None = None, mounts: set[str] | None = None) -> dict:
        b, last = self.built_record(), self.last_install()
        steps = [{"step": s, "words": STEP_WORDS[s], "ok": (b.get("steps") or {}).get(s, {}).get("ok"),
                  "at": (b.get("steps") or {}).get(s, {}).get("at", "")} for s in ORDER]
        mounts = set(mounts or [])
        built = looks is not None and bool(looks or mounts) and set(b.get("looks") or []) == set(looks) and \
            set(b.get("mounts") or []) == mounts and \
            b.get("build") == self.retail_build() and b.get("client") == self.cfg.client_data and \
            all(x["ok"] for x in steps)
        return {"route": "direct", "settings": asdict(self.cfg), "problems": self.problems(),
                "project": {"build": self.retail_build()}, "retail_build": self.retail_build(), "local": True,
                "patch_name": self.patch_name, "steps": steps, "job": asdict(self.job) if self.job else None, "sheets": "",
                "sql": self.sql_files(), "last_install": last, "next_line": self.first + len(self.lines),
                "selected": None, "equip_plus": {"installed": True, "wanted": True}, "built": built,
                "installed": bool(built and last and last.get("time", "") >= b.get("time", "") and
                                  last.get("data") == self.cfg.client_data),
                "measure": {"needed": False, "done": True}, "summary": b.get("summary") or {}}

    # -- output -----------------------------------------------------------------
    def say(self, text: str) -> None:
        with self._lock:
            for line in str(text).splitlines() or [""]:
                self.lines.append(line)
            if len(self.lines) > 6000:
                drop = len(self.lines) - 5000
                del self.lines[:drop]
                self.first += drop

    def log_since(self, since: int) -> dict:
        with self._lock:
            start = max(since - self.first, 0)
            return {"lines": self.lines[start:], "next": self.first + len(self.lines),
                    "job": asdict(self.job) if self.job else None}

    def busy(self) -> bool:
        return bool(self.job and self.job.state == "running")

    def start(self, name: str, fn, *args) -> None:
        if self.busy():
            raise RuntimeError(f"retail direct is busy ({self.job.name})")
        if self.problems():
            raise RuntimeError("; ".join(self.problems()))
        self.job = K.Job(name)
        self.say("")
        self.say(f"=== {name} - retail direct ({time.strftime('%H:%M:%S')}) ===")

        def body():
            try:
                ok = fn(*args)
                if self.job.state == "running":
                    self.job.state = "ok" if ok else "failed"
            except Stopped:
                self.job.state = "stopped"
            except Exception as e:                   # the page shows it; the server stays up
                self.say(f"!! {type(e).__name__}: {e}")
                self.job.state = "failed"
            finally:
                self.job.ended = time.time()
                self.say(f"=== {name}: {self.job.state} ===")
        threading.Thread(target=body, name=f"direct-{name}", daemon=True).start()

    def stop(self) -> None:
        if self.job and self.job.state == "running":
            self.job.state = "stopped"
            self.say("!! stopping")

    def _step(self, step: str) -> None:
        if self.job:
            if self.job.state == "stopped":
                raise Stopped()
            self.job.step = step

    def _passed(self, step: str) -> None:
        if self.job and step not in self.job.done:
            self.job.done.append(step)

    # -- the job ----------------------------------------------------------------
    def go(self, items: list[dict], plan: dict, install: bool = True) -> bool:
        """Build the patch and the SQL for what Install builds (``plan``: catalog.plan_basket of
        ``items``), then - ``install`` - put the patch in the client."""
        if install and K.wow_running():
            self.say("!! close World of Warcraft first")
            return False
        looks = self.looks_of(plan)
        rides = MT.basket_mounts(items)
        if not looks and not rides:
            self.say("!! nothing to build: the looks have no retail item")
            return False
        os.makedirs(os.path.join(self.work, "out", "sql"), exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        record = {"time": stamp, "looks": sorted(str(d) for _i, d, _l in looks), "build": self.retail_build(),
                  "client": self.cfg.client_data, "steps": {},
                  "mounts": sorted(C.entry_key(e) for e in rides)}

        def passed(step):
            record["steps"][step] = {"ok": True, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            self._passed(step)

        self._step("read")
        tables, rows = self.read_tables()
        passed("read")
        self._step("collect")
        pieces, files, summary = self.collect(looks, rows)
        passed("collect")
        self._step("mounts")
        self.mount_built = None
        mounts_sql = self.mounts(rides, files) if rides else ""
        passed("mounts")
        self._step("pack")
        patch = os.path.join(self.work, "out", self.patch_name)
        self.pack(patch, tables, files, pieces, record)
        passed("pack")
        self._step("sql")
        sql = self.write_sql(pieces)
        passed("sql")
        record["summary"] = summary | {"items": len(pieces), "sql": sql, "mounts": len(files.rides),
                                       "mounts_sql": mounts_sql}
        record["entries"] = {str(p.display): p.entry for p in pieces}
        K._save_json(os.path.join(self.work, "out", "build.json"), record)
        if not install:
            self.say("Built. Install puts the patch in your client.")
            return True
        return self.install(patch, items, sql, record["mounts"])

    def mounts(self, rides: list[dict], files: Files) -> str:
        """The basket's mounts into ``files`` (retail's own files, the client's tables) and their SQL."""
        cat = self.mount_catalog()
        if cat is None:
            raise ValueError("retail's mounts are still loading - try again in a minute")
        self.say(f"Making {len(rides)} mount(s) from retail's own files")
        built = MP.build(rides, cat, self.source, self.client, "direct", self.patch_name, self.data_dir, self.listfile,
                         self.say, self._step)
        for fdid, (kind, path) in built.paths.items():
            files.kinds.setdefault(fdid, kind)
            files.paths.setdefault(fdid, path)
        for path, v in sorted(built.files.items()):
            if not isinstance(v, int):
                continue
            if v not in files.ship:
                files.ship[v] = path
                files.paths.setdefault(v, path)
            elif files.ship[v].lower() != path.lower():
                files.aliases.append((path, v))
        files.dbc.update(built.tables)
        files.rides = built.rides
        self.mount_built = built
        path = os.path.join(self.work, "out", "sql", MP.DIRECT_SQL)
        with open(path + ".part", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(built.sql)
        os.replace(path + ".part", path)
        self.say(f"   {len(built.rides)} mount(s), {len(built.files)} files; their SQL: {path}")
        return path

    def looks_of(self, plan: dict) -> list[tuple[int, int, dict]]:
        """(retail item, display, look) for each look the plan builds, once each."""
        out, seen = [], set()
        for e in plan.get("entries") or []:
            for l in e.get("looks") or []:
                item, display = int(l.get("item") or 0), int(l.get("display") or 0)
                if not display:
                    continue
                if not item:
                    self.say(f"   {l.get('name') or display}: no retail item shows this look - left out")
                    continue
                if (item, display) not in seen:
                    seen.add((item, display))
                    out.append((item, display, l))
        return out

    def read_tables(self) -> tuple[dict[str, bytes], dict[str, list]]:
        """retail's item tables as they are ({file name: bytes}, each checked against the layout the
        client reads) and the ones the walk needs read into rows."""
        src = self.source
        self.say(f"Reading retail {self.retail_build()}'s item tables")
        tables = {}
        for name, want in RP.TABLES.items():
            self._step("read")
            data = src.raw_table(name)
            got = RP.layout_of(data)
            if got != want:
                raise ValueError(f"{name}.db2 of retail {self.retail_build()} has layout {got or 0:08X}; the x64 client "
                                 f"reads {want:08X} - this client and retail build don't go together")
            tables[name] = data
        self.say(f"   {len(tables)} tables, {sum(map(len, tables.values())) / 1048576:.1f} MB, each the layout the client reads")
        rows = {table: src.parse(table, tables[file]) for table, file in DB2_NAMES.items()}
        return tables, rows

    def collect(self, looks, rows) -> tuple[list[RP.Piece], Files, dict]:
        """The pieces (the server's items), the files the patch holds, and a summary for the page."""
        from ..dbc import DBCFile
        from ..mpq import ClientData, MPQError
        g = RP.Graph.from_rows(rows["ItemDisplayInfo"], rows["ModelFileData"], rows["TextureFileData"],
                               rows["ItemDisplayInfoMaterialRes"], rows["ItemDisplayInfoModelMatRes"])
        item_rows = {i: r for i, r in rows["Item"]}
        apps = {i: r for i, r in rows["ItemAppearance"]}
        by_item: dict[int, list[tuple]] = {}
        for i, r in rows["ItemModifiedAppearance"]:
            a = apps.get(r["ItemAppearanceID"])
            by_item.setdefault(r["ItemID"], []).append((r["ItemAppearanceModifierID"], r.get("OrderIndex", 0),
                                                        a["ItemDisplayInfoID"] if a else 0, r["ItemAppearanceID"]))

        cd = ClientData(self.client)
        try:
            # the client as this patch finds it: everything but the patch itself
            cd.sources = [(label, s) for label, s in cd.sources if label.lower() not in self.own_patches()]
            taken = {r[0] for r in DBCFile.from_bytes(cd.read("DBFilesClient\\Item.dbc")).records}
            dbc_displays = {r[0] for r in DBCFile.from_bytes(cd.read("DBFilesClient\\ItemDisplayInfo.dbc")).records}
            base = {}
            for kind, name in (("model", RP.MODEL_PATHS), ("texture", RP.TEXTURE_PATHS)):
                hit = cd.find(name)
                try:
                    base[kind] = RP.read_paths(hit[1]) if hit else {}
                except ValueError as e:
                    raise MPQError(f"{name} in {hit[0]}: {e}") from None
                self.say(f"   the client's {name.split(chr(92))[-1]}: {len(base[kind]):,} rows" +
                         (f" ({hit[0]})" if hit else " (none yet)"))

            # the pieces
            ids = self._ids()
            pieces = []
            for item, display, look in looks:
                versions = by_item.get(item, [])
                default = RP.default_display(versions)
                mods = sorted(m for m, _o, d, _a in versions if d == display)
                modifier = mods[0] if mods else 0
                r = item_rows.get(item)
                if r is None:
                    self.say(f"   {look.get('name') or item}: retail has no Item row for {item} - left out")
                    continue
                entry = RP.entry_for(item, modifier, display == default or not versions, taken, ids["spare"])
                label = "" if display == default else C.MODIFIERS.get(modifier, "")
                pieces.append(RP.Piece(entry, item, display, modifier, look.get("name") or f"Item {item}",
                                       int(look.get("quality") if look.get("quality") is not None else 1),
                                       **RP.item_fields(r), label=label))
                if display in dbc_displays:
                    self.say(f"!  {look.get('name')}: display {display} is a row of your client's ItemDisplayInfo.dbc "
                             "(3.3.5's own or the kit's) - the x64 client draws that row, not retail's")
            self._save_ids(ids)

            # the files: each display's models (every race and sex) and textures, each model's own
            # files, the icons
            files, owner, pairs, icons, shown = {}, {}, set(), set(), set()
            profiles: dict[int, list[int]] = {}          # a model's skin profiles, by FileDataID
            queue = []
            visuals = 0
            for _item, display, look in looks:
                models, textures, own = g.files(display)
                queue += [(f, "model", None) for f in models] + [(t, "texture", None) for t in textures]
                shown.update(models)
                pairs.update(own)
                visuals += bool((g.displays.get(display) or {}).get("ItemVisual"))
                if look.get("icon"):
                    icons.add(int(look["icon"]))
            queue += [(t, "texture", None) for t in sorted(icons)]
            unreadable = []
            while queue:
                fdid, kind, by = queue.pop()
                if fdid in files:
                    continue
                files[fdid], owner[fdid] = kind, by
                if kind in ("model", "skel"):
                    self._step("collect")
                    data, why = self.source.try_read(fdid)
                    if not data:
                        unreadable.append((fdid, why))
                        files[fdid] = None
                        continue
                    for f, k in RP.companions(data):
                        queue.append((f, k, fdid if kind == "model" else by))
                    if kind == "model":
                        profiles[fdid] = RP.skin_profiles(data)
            files = {f: k for f, k in files.items() if k}
            names = RP.listfile_names(self.listfile, files)
            paths = RP.place(files, owner, names, shown)
            for f in paths:                              # a file the client's tables already name stays there
                known = base["texture" if files[f] == "texture" else "model"].get(f)
                if known:
                    paths[f] = RP.norm(known)
            aliases = []                                 # where the client looks, when that isn't where it is
            for f, p in paths.items():
                look = RP.model_look(p) if files[f] == "model" and p.endswith(".m2") else ""
                if look and look != p:
                    aliases.append((look, f))
                # its skin profiles under its own name, where retail keeps them in another model's
                # (the client opens <model>NN.skin; a converter run does too)
                for at in dict.fromkeys(x for x in (p, look) if x and x.endswith(".m2")):
                    for i, skin in enumerate(profiles.get(f, [])):
                        own = RP.skin_name(at, i)
                        if skin in paths and paths[skin] != own:
                            aliases.append((own, skin))
            for model, texture in sorted(pairs):
                if model in paths and texture in paths:
                    alias = RP.alias_for(paths[model], paths[texture])
                    if alias:
                        aliases.append((alias, texture))
            aliases = list(dict.fromkeys(aliases))
            have = {f for f, p in paths.items() if cd.exists(p) and f in base["texture" if files[f] == "texture" else "model"]}
        finally:
            cd.close()

        kinds: dict[str, list] = {}
        for f, k in files.items():
            if f not in have:
                kinds.setdefault(k, []).append(f)
        size = {k: sum(self.source.size_of(f) or 0 for f in v) for k, v in kinds.items()}
        self.say(f"   {len(pieces)} items, {len({d for _i, d, _l in looks})} looks")
        for k, v in sorted(kinds.items()):
            self.say(f"   {k:8} {len(v):5} files {size[k] / 1048576:7.1f} MB")
        if have:
            self.say(f"   {len(have)} file(s) your client already has where its path tables say")
        if aliases:
            self.say(f"   {len(aliases)} file(s) also where the client looks for them (a texture beside the model that "
                     "wears it, a model in a sub-folder)")
        if unreadable:
            self.say(f"!  {len(unreadable)} model(s) aren't readable from your retail install - their looks miss a part:")
            for fdid, why in unreadable[:8]:
                self.say(f"     FileDataID {fdid}: {why}")
        if visuals:
            self.say(f"   {visuals} look(s) have a retail item glow (ItemVisual) - the x64 client doesn't draw those from retail yet")
        unnamed = [f for f in files if f not in names and f not in have]
        if unnamed:
            self.say(f"   {len(unnamed)} file(s) the listfile doesn't name: put beside their model as wxl_<id>")
        ship = {f: paths[f] for f in files if f not in have}
        summary = {"files": len(ship), "mb": round(sum(size.values()) / 1048576, 1), "aliases": len(aliases),
                   "unreadable": len(unreadable)}
        return pieces, Files(ship, files, paths, aliases, base, g, [d for _i, d, _l in looks]), summary

    def pack(self, patch: str, tables: dict, files: Files, pieces: list, record: dict) -> None:
        """The patch: what made it, the tables, the path tables (the client's with the new files'
        rows), the files, then each texture's other path."""
        model_rows = dict(files.base.get("model") or {})
        texture_rows = dict(files.base.get("texture") or {})
        for f, p in files.paths.items():
            if files.kinds[f] != "sound":            # the client opens sounds by name (SoundEntries)
                (texture_rows if files.kinds[f] == "texture" else model_rows).setdefault(f, p)
        w = RP.PatchWriter(patch)
        try:
            w.add(RP.MANIFEST, json.dumps({"by": "Retroport Workbench (retail direct)", "time": record["time"],
                                           "build": record["build"], "looks": record["looks"],
                                           "entries": sorted(p.entry for p in pieces),
                                           "mounts": [r.mount for r in files.rides]}, indent=1).encode())
            for name, data in tables.items():
                w.add(f"DBFilesClient\\{name}.db2", data)
            for name, data in files.dbc.items():
                w.add(f"DBFilesClient\\{name}.dbc", data)
            w.add(RP.MODEL_PATHS, RP.write_paths(model_rows))
            w.add(RP.TEXTURE_PATHS, RP.write_paths(texture_rows))
            missing = 0
            for n, (fdid, path) in enumerate(sorted(files.ship.items(), key=lambda t: t[1])):
                if n % 200 == 0:
                    self._step("pack")
                data, _why = self.source.try_read(fdid)
                if not data:
                    missing += 1
                    continue
                w.add(path, data)
            for alias, f in files.aliases:
                if not w.alias(alias, files.paths[f]):
                    data, _why = self.source.try_read(f)
                    if data:
                        w.add(alias, data)
            held = {n.lower() for n in w.names}
            w.close()
        except BaseException:
            w.abandon()
            raise
        self.say(f"   wrote {patch} ({os.path.getsize(patch) / 1048576:.1f} MB): {len(tables)} tables, the path "
                 f"tables ({len(model_rows):,} models, {len(texture_rows):,} textures), {len(files.ship) - missing} files")
        if missing:
            self.say(f"!  {missing} file(s) couldn't be read from your retail install")
        self.check(files, held)

    def check(self, files: Files, held: set[str]) -> int:
        """Each file the client will open by name for each look, looked for in the patch and the
        client as the patch finds it; how many aren't anywhere (each said)."""
        from ..mpq import ClientData
        cd = ClientData(self.client)
        bad = []
        try:
            cd.sources = [(label, s) for label, s in cd.sources if label.lower() not in self.own_patches()]
            for d in files.displays or []:
                for what, path in RP.lookups(files.graph, d, files.paths):
                    if not path or (path.lower() not in held and not cd.exists(path)):
                        bad.append((d, what, path))
            for r in files.rides:                    # a mount: its model, its skins beside it, its icon
                model = r.model_path[:-4] + ".m2"
                wanted = [("model", model), ("skin", model[:-3] + "00.skin")]
                wanted += [("skin texture", p) for p in MT.texture_names(r.model_path, r.retail["textures"])[1]]
                for what, path in wanted:
                    if path.lower() not in held and not cd.exists(path):
                        bad.append((f"mount {r.name}", what, path))
        finally:
            cd.close()
        if bad:
            self.say(f"!  {len(bad)} file(s) the client will look for aren't in the patch or your client - those parts won't show:")
            for d, what, path in bad[:12]:
                self.say(f"     {d if isinstance(d, str) else f'display {d}'}: {what}: " +
                         (path or "has no path the client can find"))
        else:
            self.say("   checked: every file the client opens for these looks is where it will look")
        return len(bad)

    def write_sql(self, pieces: list[RP.Piece]) -> str:
        ids = self._ids()
        owned = [tuple(p) for p in ids.get("owned") or []]
        path = os.path.join(self.work, "out", "sql", SQL_NAME)
        if not pieces and not owned:                 # mounts only: no item SQL to apply
            if os.path.isfile(path):
                os.remove(path)
            return ""
        text = RP.item_sql(pieces, owned, self.retail_build(), time.strftime("%Y-%m-%d %H:%M"))
        edits = IS.load(self.data_dir)
        stats = []
        for p in pieces:
            row = dict(zip(RP.COLUMNS, p.values()))
            stats += IS.updates(edits, {"item": {str(p.display): p.entry}}, {p.entry: row}, {})
        if stats:
            text += f"\n-- Retroport Workbench, the Stats step: levels, stats, armor, damage, sockets ({len(stats)} items)\n" + \
                    "\n".join(stats) + "\n"
        if edits.get("sets"):
            self.say("   (item sets from the Stats step need ItemSet.dbc rows - the kit's route only)")
        with open(path + ".part", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(path + ".part", path)
        ids["owned"] = sorted(set(owned) | {(p.entry, p.display) for p in pieces})
        self._save_ids(ids)
        self.say(f"   wrote {path} ({len(pieces)} items" + (f", {len(stats)} with stats" if stats else "") + ")")
        return path

    def install(self, patch: str, items: list[dict], sql: str, mounts: list | None = None) -> bool:
        if self.job:
            self.job.step = "install"
        if K.wow_running():
            self.say("!! close World of Warcraft first")
            return False
        data = self.cfg.client_data
        name = self.patch_name
        dest = os.path.join(data, name)
        if os.path.isfile(dest) and not _made_here(dest):
            self.say(f"!! {dest} is another tool's patch - retail direct won't replace it")
            return False
        # an earlier install of this route at the other letter (patch-T, before the client read every
        # archive's path tables): taken out, kept in the backup (Undo puts it back)
        earlier = [n for n in RP.OWN_PATCHES if n.lower() != name.lower() and _made_here(os.path.join(data, n))]
        stamp = base = time.strftime("%Y%m%d-%H%M%S")
        n = 2
        while os.path.exists(os.path.join(self.work, "backups", stamp)):     # two installs in one second
            stamp, n = f"{base}-{n}", n + 1
        backup = os.path.join(self.work, "backups", stamp)
        os.makedirs(os.path.join(backup, "client"), exist_ok=True)
        record = {"time": stamp, "client": [], "server": [], "added": [], "by": "retroport workbench (retail direct)",
                  "basket": items, "data": data, "sql": sql, "mounts": mounts or []}
        self.say(f"Backing up and installing (backup: {backup})")
        for n in earlier:
            shutil.copy2(os.path.join(data, n), os.path.join(backup, "client", n))
            record["client"].append(n)
            os.remove(os.path.join(data, n))
            self.say(f"   took out {n} (this route's, from before) - its items are in {name} now")
        if os.path.exists(dest):
            shutil.copy2(dest, os.path.join(backup, "client", name))
            record["client"].append(name)
            os.remove(dest)                          # never write through a hard link into another client
        else:
            record["added"].append(dest)
        shutil.copy2(patch, dest)
        self.say(f"   installed {name}")
        self.check_shadowed(name)
        built = self.mount_built
        if built is not None and mounts:
            try:                                     # the mount items' bag icons: in the item kit's patch, say
                MP.place_item_rows(self.client, name, built.rides, built.item_ids, backup, record, self.say)
            except Exception as e:                   # the record is still saved: Undo works
                self.say(f"!! the mount items' icons: {type(e).__name__}: {e}")
        cache = os.path.join(os.path.dirname(data.rstrip("\\/")), "Cache")
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
            self.say("   cleared the client's Cache folder")
        K._save_json(os.path.join(backup, "install.json"), record)
        self.say("Installed. Apply the SQL to your world database, restart the worldserver, then log in "
                 "with the x64 client:")
        for p in self.sql_files():
            self.say(f"   {p}")
        return True

    def client_check(self) -> bool:
        """The installed patch's models as the x64 client reads them in play, natively: the client run
        in its model check mode (WXL_RETAIL_MODEL_CHECK, retroport-native's x64_native_model_check.py) on
        the patch's .m2 files - a window opens and closes by itself, about a second a model. Each model
        is read by the native loader and by the converter and the two compared: "same" or "DIFFERS"
        (it draws, but not as retail has it) or not read at all (the client refuses it: play converts
        it on the spot - a freeze of a few hundred ms - or leaves it out). The client's logs are put
        back as they were; the result goes in the build record and the log."""
        rec = self.last_install()
        if not rec:
            self.say("!! Install first: the check reads the models your client has")
            return False
        if K.wow_running():
            self.say("!! close World of Warcraft first")
            return False
        from ..mpq import MPQ
        data = rec.get("data") or self.cfg.client_data
        name = self.patch_name
        patch = os.path.join(data, name)
        if not os.path.isfile(patch):
            self.say(f"!! {patch} isn't there - Install first")
            return False
        m = MPQ(patch)
        try:
            listed = (m.read("(listfile)") or b"").decode("latin-1").splitlines()
        finally:
            m.close()
        models = sorted({f.strip() for f in listed if f.strip().lower().endswith(".m2")}, key=str.lower)
        if not models:
            self.say(f"   {name} holds no models to check")
            return True
        client = os.path.dirname(data.rstrip("\\/"))
        work = os.path.join(self.work, "client-check")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        with open(os.path.join(work, "models.txt"), "w", encoding="latin-1", newline="\r\n") as fh:
            fh.write("\n".join(models) + "\n")
        logs = os.path.join(client, "Logs")
        kept = os.path.join(work, "logs-before")
        os.makedirs(kept)
        for n in os.listdir(logs) if os.path.isdir(logs) else []:
            if n.lower().endswith(".log"):
                shutil.copy2(os.path.join(logs, n), kept)
        errors = os.path.join(client, "Errors")
        crashes = len([n for n in os.listdir(errors) if n.endswith("Crash.txt")]) if os.path.isdir(errors) else 0
        env = {k: v for k, v in os.environ.items() if k not in ("WXL_PRECONVERT", "WXL_PRECONVERT_CHECK")}
        env.update({"WXL_RETAIL_MODEL_CHECK": work, "WXL_LOG_FLUSH": "1", "WXL_NATIVE_RETAIL_MODELS": "1"})
        timeout = 60 + 3 * len(models)
        self.say(f"Checking {len(models)} model(s) of {name} in the client (a window opens and closes by itself; "
                 f"up to {timeout // 60 + 1} min)")
        started = time.time()
        import subprocess
        proc = subprocess.Popen([os.path.join(client, "WowClient64.exe"), "-windowed"], cwd=client, env=env)
        try:
            while proc.poll() is None:
                if self.job and self.job.state == "stopped":
                    proc.kill()
                    raise Stopped()
                if time.time() - started > timeout:
                    proc.kill()
                    break
                time.sleep(0.5)
            proc.wait()
        finally:
            for n in os.listdir(kept):
                shutil.copy2(os.path.join(kept, n), logs)
            shutil.rmtree(kept, ignore_errors=True)
        after = len([n for n in os.listdir(errors) if n.endswith("Crash.txt")]) if os.path.isdir(errors) else 0
        report = os.path.join(work, "check.txt")
        if not os.path.isfile(report):
            self.say(f"!! the client wrote no check ({time.time() - started:.0f} s" +
                     (f", {after - crashes} new crash report(s) in {errors}" if after > crashes else "") +
                     ") - an older client has no check mode")
            return False
        results = []
        with open(report, encoding="latin-1") as fh:
            for line in fh:
                key, _tab, result = line.rstrip("\r\n").partition("\t")
                if key:
                    results.append((key, result))
        same = [k for k, r in results if r.startswith("same")]
        differs = [(k, r) for k, r in results if r.startswith("DIFFERS")]
        failed = [(k, r) for k, r in results if not r.startswith(("same", "DIFFERS"))]
        self.say(f"   {len(same)} of {len(results)} read natively as retail has them, {len(differs)} differ, "
                 f"{len(failed)} not read ({time.time() - started:.0f} s)" +
                 (f"; {after - crashes} new crash report(s) in {errors}" if after > crashes else ""))
        for k, r in failed[:12]:
            self.say(f"!    {k}: {r}")
        for k, r in differs[:6]:
            self.say(f"     {k}: {r}")
        b = self.built_record()
        if b:
            b.setdefault("summary", {})["client_check"] = {
                "time": time.strftime("%Y%m%d-%H%M%S"), "models": len(results), "same": len(same),
                "differs": [k for k, _ in differs], "failed": [k for k, _ in failed]}
            K._save_json(os.path.join(self.work, "out", "build.json"), b)
        return after == crashes                      # what it found is in the notes; a crash fails the job

    def check_shadowed(self, name: str) -> list[tuple[str, str]]:
        """The files of the installed patch the client takes from an archive above it instead (each
        such archive named once, with a few of its files) - a whole table another tool put higher
        up hides this patch's rows. The path tables count only for a client that reads the top copy
        alone; one that reads them all (``retailpack.merges_path_tables``) finds this patch's too."""
        from ..mpq import ClientData, MPQ
        data = self.cfg.client_data
        merges = RP.merges_path_tables(self.client) is not False
        skip = {RP.MODEL_PATHS.lower(), RP.TEXTURE_PATHS.lower(), RP.MANIFEST.lower()} if merges else {RP.MANIFEST.lower()}
        try:
            m = MPQ(os.path.join(data, name))
            try:
                listed = (m.read("(listfile)") or b"").decode("latin-1").splitlines()
            finally:
                m.close()
            cd = ClientData(self.client, top=name)
        except Exception as e:
            self.say(f"!  couldn't check what stands above {name}: {type(e).__name__}: {e}")
            return []
        hidden = []
        try:
            for f in listed:
                f = f.strip()
                if not f or f.lower() in skip or f.startswith("("):
                    continue
                by = cd.shadowed_by(f)
                if by:
                    hidden.append((f, by))
        finally:
            cd.close()
        if hidden:
            by_archive: dict[str, list[str]] = {}
            for f, by in hidden:
                by_archive.setdefault(by, []).append(f)
            self.say(f"!  {len(hidden)} file(s) of {name} are hidden by an archive above it - the client reads theirs:")
            for by, fs in by_archive.items():
                self.say(f"     {by}: " + ", ".join(fs[:4]) + (f" and {len(fs) - 4} more" if len(fs) > 4 else ""))
        else:
            self.say(f"   checked: nothing above {name} hides its files")
        return hidden

    def undo(self) -> bool:
        rec = self.last_install()
        if not rec:
            self.say("there is no install to undo")
            return False
        if K.wow_running():
            self.say("!! close World of Warcraft first")
            return False
        backup, data = rec["backup"], rec.get("data") or self.cfg.client_data
        for n in rec.get("client", []):
            fp = (rec.get("item_rows") or {}).get(n)
            if fp and os.path.isfile(os.path.join(data, n)) and MP._fingerprint(os.path.join(data, n)) != fp:
                self.say(f"   client: {n} changed after this install (another one replaced it) - left as it is")
                continue
            K._remove_any(os.path.join(data, n))
            shutil.copy2(os.path.join(backup, "client", n), os.path.join(data, n))
            self.say(f"   client: put back {n}")
        for p in rec.get("added", []):
            K._remove_any(p)
            self.say(f"   client: removed {p}")
        os.replace(os.path.join(backup, "install.json"), os.path.join(backup, "install.json.undone"))
        self.say("Undone. Clear the client's Cache folder; the SQL rows stay (without the patch the x64 client "
                 "draws them without a model).")
        return True

    # -- the entries this route gave ----------------------------------------------
    def _ids(self) -> dict:
        got = K._load_json(os.path.join(self.work, "ids.json"), {}) or {}
        return {"spare": {str(k): int(v) for k, v in (got.get("spare") or {}).items()},
                "owned": [tuple(int(x) for x in p) for p in got.get("owned") or []]}

    def _save_ids(self, ids: dict) -> None:
        K._save_json(os.path.join(self.work, "ids.json"), {"spare": ids["spare"], "owned": [list(p) for p in ids["owned"]]})
