"""The basket's mounts made for the client: their files, the client's tables and the server's SQL.

``build`` takes retail's own files, which the client reads as they are - a model finds its skins,
animations and skeleton by name beside it and its textures by FileDataID, so ``paths`` holds the
path-table rows; ``direct`` adds them all to its patch (``retailpack.patch_for``).

Every model and skin goes under ``creature\\retroport\\`` (``mounts.relocate``): a retail model
that kept an old model's path (the riding horse) never replaces the stock one NPCs use. Sounds keep
retail's paths - .ogg files, which 3.3.5 never had (``_sounds``). The tables are the client's own as
Install's patch finds them (``ClientData`` with the patch and everything above it set aside), so a
patch above it that holds one of them would hide the mounts' rows: the build stops and says which.
An older tool's item patch may hold the item display table above it: ``place_item_rows`` puts the
items' rows (their bag icons) in it at install.
"""

from __future__ import annotations

import ntpath
import os
import shutil
import time
from dataclasses import dataclass, field

from . import itemids
from . import mounts as MT
from . import retailpack as RP

DIRECT_SQL = "retail-direct-mounts.sql"


@dataclass
class Built:
    rides: list[MT.Ride]
    tables: dict[str, bytes]                                    # "Spell" -> the client's table with the mounts' rows
    files: dict[str, object]                                    # client path -> bytes, or a retail FileDataID to copy
    paths: dict[int, tuple[str, str]] = field(default_factory=dict)   # fdid -> ("model"/"texture"/"sound", path)
    sql: str = ""
    owned: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    item_ids: set[int] = field(default_factory=set)             # every ItemDisplayInfo id the registry gave
    item_table_above: str = ""                                  # the archive above the patch holding that table


SOUND_FOLDER = "sound\\retroport"            # a sound kit whose files lie in several folders: its own here


def _sounds(catalog: MT.MountCatalog, rides: list[MT.Ride], displays: dict[int, int], base: dict, ids: dict,
            owned: dict, names: dict[int, str], source, max_terrain: int) -> tuple[MT.Sounds, dict[str, int], list[str]]:
    """Each ride's retail sounds (``displays``: ride id -> its CreatureSoundData row) as 3.3.5 rows:
    ``rides`` get their columns and footsteps; the SoundEntries rows (each kit's files that read as
    Ogg), the FootstepTerrainLookup rows of the footsteps 3.3.5 lacks, the files ({path: FileDataID})
    and what was left out."""
    from ..dbc import DBCFile
    from ..race.sounds import MAX_FILES, Kit
    snd = catalog.sounds or {}
    kit_rows = snd.get("kits") or {}
    se = DBCFile.from_bytes(base["SoundEntries"])
    ftl = DBCFile.from_bytes(base["FootstepTerrainLookup"])
    se_taken = {r[0] for r in se.records if r[0] not in owned["SoundEntries"]}
    ftl_rows = [r for r in ftl.records if r[0] not in owned["FootstepTerrainLookup"]]
    have_steps, ftl_taken = {r[1] for r in ftl_rows}, {r[0] for r in ftl_rows}
    out, files, notes, made, dead, long = MT.Sounds(), {}, [], {}, set(), []
    readable: dict[int, bool] = {}

    def kit(retail_id: int) -> int:
        """Our SoundEntries id for a retail kit (0: it has no file 3.3.5 can play)."""
        if retail_id in made or retail_id in dead:
            return made.get(retail_id, 0)
        k = kit_rows.get(str(retail_id))
        if not k:
            dead.add(retail_id)
            return 0
        entries = k[6][:MAX_FILES]
        if len(k[6]) > MAX_FILES:
            long.append(retail_id)
        paths = [(f, names.get(f) or f"{SOUND_FOLDER}\\{f}.ogg", w) for f, w in entries]
        if len({ntpath.dirname(p) for _f, p, _w in paths}) > 1:          # one row, one folder
            paths = [(f, ntpath.join(SOUND_FOLDER, str(retail_id), ntpath.basename(p)), w) for f, p, w in paths]
        keep = []
        for f, p, w in paths:
            if f not in readable:
                data, _why = source.try_read(f)
                readable[f] = bool(data) and data[:4] == b"OggS"
            if readable[f]:
                keep.append((f, p, w))
        if not keep:
            dead.add(retail_id)
            return 0
        n = MT.sound_id(ids, retail_id, se_taken)
        out.kits[n] = Kit(n, f"RetroportMount{retail_id}", keep, k[0], k[1], k[2], k[3], k[4], k[5])
        for f, p, _w in keep:
            files[p] = f
        made[retail_id] = n
        return n

    added_steps: dict[int, bool] = {}
    for r in rides:
        row = (snd.get("rows") or {}).get(str(displays.get(r.id) or 0))
        if not row:
            continue
        r.sound_kits = {int(col): v for col, k in row["kits"].items() if (v := kit(k))}
        step = int(row.get("footstep") or 0)
        if step and step not in have_steps and step not in added_steps:
            got = False
            for terrain, sound, splash in (snd.get("footsteps") or {}).get(str(step), []):
                if not 0 <= terrain <= max_terrain:       # 3.3.5 knows fewer terrains: the client's array ends there
                    continue
                a, b = kit(sound) if sound else 0, kit(splash) if splash else 0
                if a or b:
                    out.footsteps.append([MT.footstep_id(ids, step, terrain, ftl_taken), step, terrain, a, b])
                    got = True
            added_steps[step] = got
        if step and (step in have_steps or added_steps.get(step)):
            r.footstep = step
    if long:
        notes.append(f"{len(long)} sound kit(s) have more than {MAX_FILES} files (footsteps, mostly) - 3.3.5 plays "
                     f"the first {MAX_FILES} of each")
    lost = sorted(k for k in dead if k)
    if lost:
        notes.append(f"{len(lost)} sound kit(s) have no file your retail install plays as Ogg - left out")
    return out, files, notes


def chosen_display(entry: dict, row: list) -> int:
    """The display a basket entry rides: the one picked on the Mounts page, else the mount's first."""
    shown = row[MT.F["displays"]]
    want = int(entry.get("display") or 0)
    return want if want in shown else shown[0]


def _rank(label: str):
    """A Data\\patch-<x> archive's (or folder's) rank, from its ClientData label (None: another archive)."""
    from ..mpq import _patch_rank
    name = label.split(" (folder)")[0]
    name = name[5:] if name.lower().startswith("data\\") else name
    low = name.lower()
    return _patch_rank(low[6:-4]) if "\\" not in low and low.startswith("patch-") and low.endswith(".mpq") else None


def _has(s, name: str) -> bool:
    """Whether a ClientData source (an MPQ, or a folder patch's path) holds ``name``."""
    if isinstance(s, str):
        return os.path.isfile(os.path.join(s, *name.split("\\")))
    return s.has(name)


def _read(s, name: str) -> bytes | None:
    if isinstance(s, str):
        p = os.path.join(s, *name.split("\\"))
        if not os.path.isfile(p):
            return None
        with open(p, "rb") as fh:
            return fh.read()
    return s.read(name)


def _client(client_dir: str, patch: str):
    """The client as ``patch`` finds it - the patch itself and everything above it set aside (in
    ``above``) - and the archives above it that hold one of the mounts' tables."""
    from ..mpq import ClientData
    cd = ClientData(client_dir)
    mine = _rank(patch)
    up = [(label, s) for label, s in cd.sources if label.lower() != patch.lower()
          and (_rank(label) or 0) > mine]
    cd.sources = [(label, s) for label, s in cd.sources if label.lower() != patch.lower() and (label, s) not in up]
    cd.above = up                                          # closed with the rest
    return cd, [label for label, s in up if any(_has(s, f"DBFilesClient\\{t}.dbc") for t in MT.TABLES)]


def build(entries: list[dict], catalog: MT.MountCatalog, source, client_dir: str, patch: str,
          data_dir: str, listfile: str, say=print, step=lambda s: None) -> Built:
    """The mounts of ``entries`` (basket entries of kind "mount"), their tables as ``patch`` will hold
    them."""
    from ..dbc import DBCFile
    if not entries:
        raise ValueError("no mounts to build")
    rows = []
    for e in entries:
        row = catalog.by_id.get(int(e.get("id") or 0))
        if row is None:
            say(f"!  {e.get('name') or e.get('id')}: not a mount of retail {catalog.build} - left out")
            continue
        display = chosen_display(e, row)
        rows.append((row, display, catalog.displays.get(display) or {}))
    snd = catalog.sounds or {}
    want = set()
    for _row, _d, dd in rows:
        want |= {dd.get("model") or 0, *(dd.get("textures") or [])}
        want |= {st.get("model") or 0 for st in dd.get("state") or []}
        want |= {layer.get("texture") or 0 for layer in (dd.get("dissolve") or {}).get("layers") or []}
        csd = (snd.get("rows") or {}).get(str(dd.get("sound") or 0)) or {}
        kits = set(csd.get("kits", {}).values())
        for _t, a, b in (snd.get("footsteps") or {}).get(str(csd.get("footstep") or 0), []):
            kits |= {a, b}
        for k in kits:
            want |= {f for f, _w in ((snd.get("kits") or {}).get(str(k)) or [[]] * 7)[6]}
    want |= {row[MT.F["icon"]] for row, _d, _dd in rows}
    names = RP.listfile_names(listfile, {f for f in want if f})
    icons = {f: MT.icon_name(names[f]) for f in {row[MT.F["icon"]] for row, _d, _dd in rows} if f in names}

    cd, above = _client(client_dir, patch)
    try:
        if above:
            raise ValueError(f"{', '.join(above)} hold{'s' if len(above) == 1 else ''} the client's spell, creature "
                             f"or sound tables above {patch} - the mounts' rows would be hidden. Rename or remove "
                             f"{'it' if len(above) == 1 else 'them'}, or move them below {patch}")
        base = {t: cd.read(f"DBFilesClient\\{t}.dbc") for t in (*MT.TABLES, MT.ITEM_TABLE)}
        item_dbc = DBCFile.from_bytes(cd.read("DBFilesClient\\Item.dbc"))
        terrains = DBCFile.from_bytes(cd.read("DBFilesClient\\TerrainTypeSounds.dbc"))
        top = next(((label, s) for label, s in cd.above if _has(s, f"DBFilesClient\\{MT.ITEM_TABLE}.dbc")), None)
        top_idi = DBCFile.from_bytes(_read(top[1], f"DBFilesClient\\{MT.ITEM_TABLE}.dbc")) if top else None
        icon_there = {n: cd.exists(f"Interface\\Icons\\{n}.blp") for n in icons.values()}
    finally:
        cd.close()
    tables = {t: DBCFile.from_bytes(base[t]) for t in ("Spell", "SpellIcon", "SkillLineAbility", "CreatureDisplayInfo",
                                                       "CreatureModelData", "CreatureSoundData", MT.ITEM_TABLE)}

    ids = MT.load_ids(data_dir)
    owned = MT.owned_ids(ids)
    taken = {t: {r[0] for r in tables[t].records} for t in ("Spell", "SkillLineAbility", "CreatureDisplayInfo",
                                                            "CreatureModelData", "CreatureSoundData")}
    reg = itemids.load(itemids.path(data_dir))
    items_taken = {r[0] for r in item_dbc.records} | set(reg["reserved"]["item"])
    icons_by_name = {tables["SpellIcon"].get_string(r[1]).replace("/", "\\").lower(): r[0]
                     for r in tables["SpellIcon"].records}
    idi = tables[MT.ITEM_TABLE]
    stock_items = {}                                     # icon -> a stock item display showing it (values)
    for r in idi.records:
        stock_items.setdefault(idi.get_string(r[MT.IDI_ICON]).lower(),
                               [idi.get_string(v) if i in MT.IDI_STRINGS else v for i, v in enumerate(r)])
    display_taken = ({r[0] for r in idi.records} | {r[0] for r in (top_idi.records if top_idi else [])}) - owned[MT.ITEM_TABLE]
    item_rows_ok = top is None or (_rank(top[0]) is not None and not isinstance(top[1], str))
    notes = []
    if not item_rows_ok:
        notes.append(f"{top[0]} holds the client's item display table above {patch} and can't take rows - the "
                     "mount items show a stock icon in the bags")
    cmd = tables["CreatureModelData"]

    rides, new_icons, ship_icons, sound_of = [], {}, {}, {}
    for row, display, dd in rows:
        name, kind = row[MT.F["name"]], row[MT.F["kind"]]
        model = dd.get("model") or 0
        if not model or model not in names:
            say(f"!  {name}: its model (FileDataID {model}) isn't in the listfile - left out")
            continue
        got = MT.allocate(ids, row[0], taken, items_taken)
        client_model = os.path.splitext(MT.relocate(names[model]))[0] + ".m2"
        tex_ids = {i: f for i, f in enumerate((dd.get("textures") or [])[:len(MT.SKIN_TYPES)]) if f}
        tex = {i: names.get(f, f"{os.path.dirname(names[model])}\\wxl_{f}.blp") for i, f in tex_ids.items()}
        tnames, _files = MT.texture_names(client_model, tex)
        packed, lost = MT.geoset_data(dd.get("geosets"))
        if lost:
            notes.append(f"{name}: parts 3.3.5 can't choose ({lost}) - they all show")
        icon_fdid, spell_icon, item_icon = row[MT.F["icon"]], 0, ""
        if icon_fdid in icons:
            iname = icons[icon_fdid]
            spell_icon = icons_by_name.get(f"interface\\icons\\{iname}".lower())
            if not spell_icon:
                spell_icon = MT.icon_id(ids, icon_fdid, {r[0] for r in tables["SpellIcon"].records})
                new_icons[spell_icon] = f"Interface\\Icons\\{iname}"
            if not icon_there.get(iname):
                ship_icons[f"interface\\icons\\{iname}.blp".lower()] = icon_fdid
            item_icon = iname if item_rows_ok else ""
        stock_item = next((stock_items[n] for n in MT.ITEM_ICONS[kind] if n in stock_items), None)
        item_display = MT.display_id(ids, row[0], display_taken) if item_icon else (stock_item or [0])[0]
        template = MT.model_template(cmd.records, cmd.get_string, names[model], kind)
        rides.append(MT.Ride(row[0], name, kind, display, got["id"], got["item"],
                             os.path.splitext(client_model)[0] + ".mdx", tnames, float(dd.get("scale") or 1.0),
                             int(dd.get("alpha") if dd.get("alpha") is not None else 255), packed,
                             dd.get("model_data") or {}, spell_icon or 0, row[MT.F["item_name"]],
                             int(row[MT.F["quality"]] if row[MT.F["quality"]] is not None else 4), item_display,
                             template, {"model": model, "textures": tex, "texture_ids": tex_ids,
                                        "icon": icon_fdid, "names": names},
                             item_icon=item_icon, item_template=stock_item,
                             state=[dict(s) for s in dd.get("state") or [] if s.get("model") in names],
                             gradient=dd.get("gradient"),
                             dissolve=(dict(dd["dissolve"], layers=[dict(layer) for layer in dd["dissolve"]["layers"]])
                                       if dd.get("dissolve") else None),
                             bank=dd.get("bank")))
        if dd.get("dissolve"):
            notes.append(f"{name}: retail lays a dissolve over it")
        if dd.get("gradient"):
            notes.append(f"{name}: retail shades it with a gradient")
        if dd.get("state"):
            notes.append(f"{name}: retail attaches {len(dd['state'])} model(s) to it")
        sound_of[got["id"]] = dd.get("sound") or 0
    if not rides:
        raise ValueError("none of the mounts could be made")

    max_terrain = max((r[0] for r in terrains.records), default=-1)
    sounds, sound_files, sound_notes = _sounds(catalog, rides, sound_of, base, ids, owned, names, source, max_terrain)
    notes += sound_notes
    out = Built(rides, MT.client_tables(base, rides, new_icons, sounds, owned), {}, notes=notes,
                item_ids=owned[MT.ITEM_TABLE] | {r.item_display for r in rides if r.item_icon},
                item_table_above=top[0] if top else "")
    for r in rides:
        step("mounts")
        _direct_files(out, r, source, listfile)
    for path, fdid in sorted(ship_icons.items()):
        out.files[path] = fdid
        out.paths[fdid] = ("texture", path)
    for path, fdid in sorted(sound_files.items()):
        out.files[path] = fdid
        out.paths.setdefault(fdid, ("sound", path))
    skins = MT.skin_table(rides)
    if skins:
        out.files[MT.SKIN_TABLE] = skins
    states = MT.state_table(rides)
    if states:
        out.files[MT.STATE_TABLE] = states
    heard = sum(1 for r in rides if r.sound_kits)
    say(f"   sounds: {heard} of {len(rides)} mount(s) with retail's ({len(sounds.kits)} sound kits, "
        f"{len(sound_files)} files, footsteps for {len({row[1] for row in sounds.footsteps})} new kind(s) of feet)")
    made = time.strftime("%Y-%m-%d %H:%M")
    out.sql = MT.mount_sql(out.tables, rides, ids["owned"], catalog.build, made, "retail direct")
    out.owned = ids["owned"] = MT.owned_now(rides, ids["owned"])
    MT.save_ids(data_dir, ids)
    itemids.remember(itemids.path(data_dir), {"item": {f"mount:{r.mount}": r.item for r in rides}}, "mounts")
    for n in notes:
        say(f"   {n}")
    return out


# -- retail's own files ---------------------------------------------------------------------------
def _direct_files(out: Built, r: MT.Ride, source, listfile: str) -> None:
    """The model and every file it names (recursively), at their relocated paths, as path-table rows;
    the display's skins in the model's folder under the names CreatureDisplayInfo gives them."""
    model = r.retail["model"]
    files, owner = {}, {}
    queue = [(model, "model", None)] + [(s["model"], "model", None) for s in r.state]
    while queue:
        fdid, kind, by = queue.pop()
        if fdid in files:
            continue
        files[fdid], owner[fdid] = kind, by
        if kind in ("model", "skel"):
            data, why = source.try_read(fdid)
            if not data:
                if fdid == model:
                    raise ValueError(f"{r.name}: its model isn't readable from your retail install ({why})")
                out.notes.append(f"{r.name}: FileDataID {fdid} isn't readable ({why})")
                files[fdid] = None
                continue
            for f, k in RP.companions(data):
                queue.append((f, k, fdid if kind == "model" else by))
    files = {f: k for f, k in files.items() if k}
    names = RP.listfile_names(listfile, files)
    placed = RP.place(files, owner, names)
    for f, path in placed.items():
        there = MT.relocate(path)
        kind = "texture" if files[f] == "texture" else "model"
        if kind == "texture" and f in out.paths:
            continue
        out.paths[f] = (kind, there)
        out.files[there] = f
    for path, slot in MT.texture_names(r.model_path, r.retail["textures"])[1].items():
        fdid = r.retail["texture_ids"][slot]
        out.files[path] = fdid
        out.paths.setdefault(fdid, ("texture", path))
    # the state kit's models where they went (their files are among the model's)
    for s in r.state:
        got = out.paths.get(s["model"])
        s["path"] = os.path.splitext(got[1])[0] + ".m2" if got and files.get(s["model"]) else ""
        if not s["path"]:
            out.notes.append(f"{r.name}: a model its state kit attaches (FileDataID {s['model']}) isn't readable - left out")
    # the dissolve's layer textures: where the model's files put them, else in their own retail folders
    layers = (r.dissolve or {}).get("layers") or []
    named = RP.listfile_names(listfile, {layer["texture"] for layer in layers if layer.get("texture")})
    for layer in layers:
        fdid = layer.get("texture") or 0
        got = out.paths.get(fdid)
        if got:
            layer["path"] = got[1]
        elif fdid in named:
            layer["path"] = MT.relocate(named[fdid])
            out.paths[fdid] = ("texture", layer["path"])
            out.files[layer["path"]] = fdid
        else:
            layer["path"] = ""
            if fdid:
                out.notes.append(f"{r.name}: a texture its dissolve lays over it (FileDataID {fdid}) has no name - left out")


_HOLDS: dict[tuple, set] = {}


def _held(full: str) -> set[str]:
    """Which of the mounts' tables (and the item display table) a packed archive holds (cached by
    its path and time)."""
    from ..mpq import MPQ
    key = (full, os.path.getmtime(full))
    if key not in _HOLDS:
        try:
            m = MPQ(full)
            try:
                _HOLDS[key] = {t for t in (*MT.TABLES, MT.ITEM_TABLE) if m.has(f"DBFilesClient\\{t}.dbc")}
            finally:
                m.close()
        except Exception:
            _HOLDS[key] = set()
    return _HOLDS[key]


def stale(client_data: str, patch: str) -> list[str]:
    """The archives under ``patch`` (in ``client_data``) that hold one of the mounts' tables and
    changed after it was made - a race package installed again into patch-H, say. Their new rows
    are hidden behind the patch's copies until the mounts are installed again. (The patch's item
    display table counts only while no archive above it holds one.)"""
    from ..mpq import _patch_rank
    path = os.path.join(client_data, patch)
    if not os.path.isfile(path):
        return []
    made, mine = os.path.getmtime(path), _patch_rank(patch[6:-4])
    lower, item_above = [], False
    for name in sorted(os.listdir(client_data)):
        low = name.lower()
        if not (low.startswith("patch-") and low.endswith(".mpq")) or low == patch.lower():
            continue
        rank = _patch_rank(low[6:-4])
        full = os.path.join(client_data, name)
        if rank is None or not os.path.isfile(full):
            continue
        if rank > mine:
            item_above = item_above or MT.ITEM_TABLE in _held(full)
        elif os.path.getmtime(full) > made:
            lower.append((name, _held(full)))
    return [name for name, held in lower if held & set(MT.TABLES) or (MT.ITEM_TABLE in held and not item_above)]


def _fingerprint(path: str) -> list[int]:
    st = os.stat(path)
    return [st.st_size, st.st_mtime_ns]


def place_item_rows(client_dir: str, patch: str, rides: list[MT.Ride], ours: set[int], backup: str, record: dict,
                    say=print) -> str:
    """The mount items' ItemDisplayInfo rows (their bag icons) into the archive the client reads that
    table from, when it outranks ``patch`` (which carries them itself): an older tool's item patch, say.
    The archive is backed up into ``backup`` and noted in ``record`` unless this install put it
    there (``record``'s client/added: its Undo takes it out anyway), then replaced by a copy with the
    rows - never written through a hard link. Which archive took them ("" none)."""
    from ..mpq import ClientData, add_files
    name = f"DBFilesClient\\{MT.ITEM_TABLE}.dbc"
    cd = ClientData(client_dir)
    try:
        top = next(((label, s) for label, s in cd.sources if _has(s, name)), None)
        data = _read(top[1], name) if top else None
    finally:
        cd.close()
    if top is None or top[0].lower() == patch.lower() or (_rank(top[0]) or 0) <= (_rank(patch) or 0):
        return ""                                       # the patch's own copy is the one the client reads
    label = top[0]
    if _rank(label) is None or label.endswith("(folder)"):
        say(f"!  {label} holds the client's item display table and can't take rows - the mount items show "
            "without their icons")
        return ""
    if not any(r.item_icon for r in rides) and not ours:
        return ""
    data_dir = os.path.join(client_dir, "Data")
    path = os.path.join(data_dir, label)
    merged = MT.with_item_displays(data, rides, ours)
    placed = {os.path.normcase(n) for n in record.get("client") or []} | \
        {os.path.normcase(os.path.basename(p)) for p in record.get("added") or []}
    if os.path.normcase(label) not in placed:
        os.makedirs(os.path.join(backup, "client"), exist_ok=True)
        shutil.copy2(path, os.path.join(backup, "client", label))
        record.setdefault("client", []).append(label)
    part = path + ".part"
    shutil.copy2(path, part)
    try:
        add_files(part, {name: merged})
    except BaseException:
        os.remove(part)
        raise
    os.remove(path)                                     # a hard link's other client keeps its own
    os.replace(part, path)
    record.setdefault("item_rows", {})[label] = _fingerprint(path)
    record["item_ids"] = sorted({r.item_display for r in rides if r.item_icon})
    say(f"   the mount items' bag icons: {len(record['item_ids'])} row(s) in {label}'s item display table")
    return label


_ROWS_IN: dict[tuple, bool] = {}


def item_rows_gone(client_data: str, record: dict | None) -> list[str]:
    """The archives an install put the mount items' rows in that hold them no longer (another
    install replaced the archive since): the items show red question marks until Install again."""
    from ..dbc import DBCFile
    from ..mpq import MPQ
    out = []
    want = set((record or {}).get("item_ids") or [])
    for label, fp in ((record or {}).get("item_rows") or {}).items():
        path = os.path.join(client_data, label)
        if not os.path.isfile(path):
            out.append(label)
            continue
        now = _fingerprint(path)
        if now == fp or not want:
            continue
        key = (path, *now)
        if key not in _ROWS_IN:
            try:
                m = MPQ(path)
                try:
                    data = m.read(f"DBFilesClient\\{MT.ITEM_TABLE}.dbc")
                finally:
                    m.close()
                _ROWS_IN[key] = bool(data) and want <= {r[0] for r in DBCFile.from_bytes(data).records}
            except Exception:
                _ROWS_IN[key] = False
        if not _ROWS_IN[key]:
            out.append(label)
    return out
