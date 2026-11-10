"""Retail's own items for the x64 client: what its item graph reads, and where it looks for the files.

The x64 client (wowdecomp-dx11, WXL/modules/db2/items and modules/equipment) draws an item whose
display id its ItemDisplayInfo.dbc doesn't hold from retail's own tables (``TABLES``, read as they
are), each FileDataID turned into a path by DBFilesClient\\ModelFilePath.db2 / TextureFilePath.db2
(WXL/modules/db2/FdidCompat.cpp). It finds:

* a display's models at ``Item\\ObjectComponents\\<folder>\\<name>``: the folder right after
  objectcomponents, the name after collections\\ for a collection, else the file's own name - so the
  files go at their retail paths;
* a model's own texture (ModelMaterialResourcesID) by its name *in the model's folder*: a helm kept
  in head\\ whose texture retail keeps in collections\\ (the Damned Necrolyte skull) needs a copy of
  it beside the helm, or the helm isn't drawn (``alias_for``);
* the other textures - ItemDisplayInfoMaterialRes body layers, ItemDisplayInfoModelMatRes - at
  their full paths.

This module is the pure part: the client's rules, the walk from displays to files, the path tables
(WDC1, the layout retroport-native's x64_retail_pack.py writes for patch-R), the item entries, the
item SQL and a patch writer. ``direct`` runs it.
"""

from __future__ import annotations

import os
import struct
from collections import defaultdict
from dataclasses import dataclass, field

# the retail tables the x64 client's item graph reads (WXL/modules/db2/items/RetailSchemas.hpp):
# file name -> the layout hash it was written for; another layout and the client refuses the table
TABLES = {
    "item": 0x996192AA, "itemappearance": 0x481C4281, "itemmodifiedappearance": 0x03A6C979,
    "itemdisplayinfo": 0x9F3AB8A9, "itemdisplayinfomaterialres": 0xAA462C0E,
    "itemdisplayinfomodelmatres": 0x52510D63, "modelfiledata": 0x2AE4E788, "texturefiledata": 0xBD7C74C2,
    "componentmodelfiledata": 0xAD90D87A, "componenttexturefiledata": 0xB32B030A,
    "helmetgeosetdata": 0x103B3B37, "helmetanimscaling": 0xFF7E3A8A,
}
# The patch retail direct installs (``patch_for``): patch-Q for a client that reads every archive's
# path tables (FdidCompat.cpp, 2026-11-03) - over patch-H's spell tables, under patch-R and the undead
# pack's patch-T, a letter no other tool takes; patch-T, as before, for an older client, which reads
# only the top copy of the path tables and so needs this patch above patch-R. In the Retail and Next
# folders patch-T became the undead pack's, and retail direct refused to install there.
PATCH = "patch-Q.MPQ"
LEGACY_PATCH = "patch-T.MPQ"
OWN_PATCHES = (PATCH, LEGACY_PATCH)        # where an install of this route may stand (its manifest says so)
MANIFEST = "retroport\\direct.json"         # in the patch: what made it (an install only replaces its own)
# FdidCompat.cpp's log line, in a client that reads the path tables under the top copy
MERGE_MARK = b"more copies under them"
MODEL_PATHS = "DBFilesClient\\ModelFilePath.db2"
TEXTURE_PATHS = "DBFilesClient\\TextureFilePath.db2"
EXTENSION = {"model": ".m2", "skin": ".skin", "anim": ".anim", "bone": ".bone", "skel": ".skel",
             "phys": ".phys", "texture": ".blp"}
OBJECT = "item\\objectcomponents\\"
COLLECTIONS = (OBJECT + "collection\\", OBJECT + "collections\\")
VARIANT = 1_000_000                         # an item's other looks: (modifier + 1) * VARIANT + item
SPARE = 16_000_000                          # past those: numbered from here (item_template's entry is 24-bit)
ENTRY_MAX = 16_777_215
MPQ_LIMIT = 3_900_000_000                   # MPQ v1's offsets are 32-bit


_MERGES: dict[tuple, bool] = {}


def merges_path_tables(client_dir: str) -> bool | None:
    """Whether the client's program (``edition.CLIENT_EXE``) reads every archive's path tables (``MERGE_MARK`` in it);
    None without an exe to read. Kept per exe (path, size, time)."""
    from . import edition
    exe = os.path.join(client_dir or "", edition.CLIENT_EXE)
    try:
        st = os.stat(exe)
    except OSError:
        return None
    key = (os.path.normcase(exe), st.st_size, st.st_mtime_ns)
    if key not in _MERGES:
        try:
            with open(exe, "rb") as fh:
                _MERGES[key] = MERGE_MARK in fh.read()
        except OSError:
            return None
    return _MERGES[key]


def patch_for(client_dir: str) -> str:
    """The patch retail direct installs in this client (see ``PATCH``)."""
    return LEGACY_PATCH if merges_path_tables(client_dir) is False else PATCH


# -- the client's rules (RetailItemIndex.cpp) ---------------------------------------------------
def norm(path: str) -> str:
    return path.replace("/", "\\").lower()


def object_folder(path: str) -> str:
    """The folder a model or texture is looked for in: the one right after objectcomponents ("" when
    the path isn't under it)."""
    low = norm(path)
    at = low.find(OBJECT)
    if at < 0:
        return ""
    rest = low[at + len(OBJECT):]
    return rest.split("\\", 1)[0] if "\\" in rest else ""


def texture_name(path: str) -> str:
    """The name the client looks a model's texture up by: after collections\\ for a collection, else
    the file's own name; without its extension."""
    low = norm(path)
    marker = next((m for m in COLLECTIONS if m in low), None)
    name = low[low.find(marker) + len(marker):] if marker else low.rsplit("\\", 1)[-1]
    return os.path.splitext(name)[0]


def object_path(folder: str, name: str) -> str:
    return f"{OBJECT}{folder}\\{name}.blp"


def alias_for(model_path: str, texture_path: str) -> str:
    """Where the client looks for ``texture_path`` as ``model_path``'s own texture, when that isn't
    where the texture is ("" when it is, or the model isn't an item component)."""
    folder = object_folder(model_path)
    if not folder:
        return ""
    want = object_path(folder, texture_name(texture_path))
    return "" if want == norm(texture_path) else want


def model_look(path: str) -> str:
    """Where the client looks for a display's model: ``Item\\ObjectComponents\\<folder>\\<name>.m2``
    (the name after collections\\ for a collection) - "" when it can't (not an item component)."""
    folder = object_folder(path)
    if not folder:
        return ""
    low = norm(path)
    marker = next((m for m in COLLECTIONS if m in low), None)
    name = low[low.find(marker) + len(marker):] if marker else low.rsplit("\\", 1)[-1]
    return f"{OBJECT}{folder}\\{os.path.splitext(name)[0]}.m2"


def lookups(graph: "Graph", display: int, paths: dict[int, str]) -> list[tuple[str, str]]:
    """(what, path) for every file the client opens by name for ``display`` - its models where it
    looks for them, each model's own texture beside it, the material textures at their paths - ""
    as the path when it can't find one at all (a file without a path, a model outside
    objectcomponents). Files a model names by id (skins, its textures) are found through the path
    tables."""
    row = graph.displays.get(display)
    if row is None:
        return [("display", "")]
    out = []
    mres = list(row.get("ModelResourcesID") or [])
    tres = list(row.get("ModelMaterialResourcesID") or [])
    for col in range(2):
        m = mres[col] if col < len(mres) else 0
        t = tres[col] if col < len(tres) else 0
        own = (graph.texture_files.get(t) or [0])[0] if t else 0     # the client takes the first row
        for f in graph.model_files.get(m, []) if m else []:
            p = paths.get(f, "")
            if p and not p.endswith(".m2"):
                continue
            look = model_look(p) if p else ""
            out.append((f"model {f}", look))
            if look:
                out.append((f"skin 0 of model {f}", skin_name(look, 0)))
            if look and own:
                tp = paths.get(own, "")
                out.append((f"texture {own} of model {f}",
                            object_path(object_folder(p), texture_name(tp)) if tp else ""))
    for res in graph.layers.get(display, []) + graph.model_materials.get(display, []):
        for f in graph.texture_files.get(res, []):
            out.append((f"texture {f}", paths.get(f, "")))
    return list(dict.fromkeys(out))


def layout_of(data: bytes) -> int | None:
    """A DB2's layout hash (WDC3/4: after five counts; WDC5: after its version and schema too)."""
    if data[:4] == b"WDC5" and len(data) >= 160:
        return struct.unpack_from("<I", data, 156)[0]
    if data[:4] in (b"WDC3", b"WDC4") and len(data) >= 28:
        return struct.unpack_from("<I", data, 24)[0]
    return None


# -- the walk from displays to files -------------------------------------------------------------
@dataclass
class Graph:
    """The rows under ItemDisplayInfo that name files, indexed the way the client follows them."""
    displays: dict[int, dict]
    model_files: dict[int, list[int]] = field(default_factory=dict)      # ModelResourcesID -> FileDataIDs
    texture_files: dict[int, list[int]] = field(default_factory=dict)    # MaterialResourcesID -> FileDataIDs
    layers: dict[int, list[int]] = field(default_factory=dict)           # display -> MaterialResourcesIDs (body layers)
    model_materials: dict[int, list[int]] = field(default_factory=dict)  # display -> MaterialResourcesIDs (per model)
    # display -> (ModelIndex, TextureType, MaterialResourcesID) of each per-model material
    model_types: dict[int, list[tuple[int, int, int]]] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, displays, model_files, texture_files, material_res, model_mat_res) -> "Graph":
        """From parsed rows: (id, row) pairs of ItemDisplayInfo, ModelFileData, TextureFileData,
        ItemDisplayInfoMaterialRes and ItemDisplayInfoModelMatRes."""
        g = cls({i: r for i, r in displays})
        models, textures = defaultdict(list), defaultdict(list)
        for _i, r in model_files:
            if r.get("ModelResourcesID") and r.get("FileDataID"):
                models[r["ModelResourcesID"]].append(r["FileDataID"])
        for i, r in texture_files:
            if r.get("MaterialResourcesID"):
                textures[r["MaterialResourcesID"]].append(r.get("FileDataID") or i)
        layers, per_model, typed = defaultdict(list), defaultdict(list), defaultdict(list)
        for _i, r in material_res:
            if r.get("MaterialResourcesID"):
                layers[r["ItemDisplayInfoID"]].append(r["MaterialResourcesID"])
        for _i, r in model_mat_res:
            if r.get("MaterialResourcesID"):
                per_model[r["ItemDisplayInfoID"]].append(r["MaterialResourcesID"])
                typed[r["ItemDisplayInfoID"]].append((r.get("ModelIndex", -1), r.get("TextureType", 0),
                                                      r["MaterialResourcesID"]))
        g.model_files, g.texture_files = dict(models), dict(textures)
        g.layers, g.model_materials, g.model_types = dict(layers), dict(per_model), dict(typed)
        return g

    def worn(self, display: int) -> list[tuple[int, dict[int, int]]]:
        """Each model of a display (every race and sex) with the textures it wears by type, as the
        client's equipment code gives them: 2 its column's ModelMaterialResourcesID, and the
        TextureType of each ItemDisplayInfoModelMatRes row for its column (a row naming neither
        column, for both) - retail's armour and weapons fill types 3, 4 and 24 this way, which a model
        drawn without them shows white. The first file of each material."""
        row = self.displays.get(display)
        if row is None:
            return []
        mres = list(row.get("ModelResourcesID") or [])
        tres = list(row.get("ModelMaterialResourcesID") or [])
        out = []
        for col in range(2):
            m = mres[col] if col < len(mres) else 0
            t = tres[col] if col < len(tres) else 0
            wears: dict[int, int] = {}
            own = self.texture_files.get(t, []) if t else []
            if own:
                wears[2] = own[0]
            for index, ttype, res in self.model_types.get(display, []):
                files = self.texture_files.get(res, [])
                if files and 0 < ttype < 32 and (index == col or index not in (0, 1)):
                    wears.setdefault(ttype, files[0])
            out += [(f, wears) for f in (self.model_files.get(m, []) if m else [])]
        return out

    def files(self, display: int) -> tuple[list[int], list[int], list[tuple[int, int]]]:
        """A display's (models, textures, own-texture pairs): each model of its two columns (every
        race and sex), each texture any of its materials names, and (model, texture) for each model
        with the texture its column's ModelMaterialResourcesID gives it."""
        row = self.displays.get(display)
        if row is None:
            return [], [], []
        models, textures, pairs = [], [], []
        mres = list(row.get("ModelResourcesID") or [])
        tres = list(row.get("ModelMaterialResourcesID") or [])
        for col in range(2):
            m = mres[col] if col < len(mres) else 0
            t = tres[col] if col < len(tres) else 0
            own = self.texture_files.get(t, []) if t else []
            textures += own
            for f in self.model_files.get(m, []) if m else []:
                models.append(f)
                pairs += [(f, x) for x in own]
        for res in self.layers.get(display, []) + self.model_materials.get(display, []):
            textures += self.texture_files.get(res, [])
        return list(dict.fromkeys(models)), list(dict.fromkeys(textures)), list(dict.fromkeys(pairs))


def chunks(data: bytes):
    at = 0
    while at + 8 <= len(data):
        magic, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        yield magic, data[at + 8:at + 8 + size]
        at += 8 + size


def _u32s(payload: bytes) -> list[int]:
    return list(struct.unpack_from(f"<{len(payload) // 4}I", payload)) if len(payload) >= 4 else []


def companions(data: bytes) -> list[tuple[int, str]]:
    """(FileDataID, kind) a retail model (MD21) or skeleton names: skins, animations, bones, its
    skeleton, physics, particle models and textures."""
    if data[:4] not in (b"MD21", b"SKL1"):
        return []
    out = []
    for magic, payload in chunks(data):
        if magic == b"SFID":
            out += [(f, "skin") for f in _u32s(payload)]
        elif magic == b"AFID":
            out += [(struct.unpack_from("<I", payload, i + 4)[0], "anim") for i in range(0, len(payload) - 7, 8)]
        elif magic == b"BFID":
            out += [(f, "bone") for f in _u32s(payload)]
        elif magic == b"SKID":
            out += [(f, "skel") for f in _u32s(payload)[:1]]
        elif magic == b"SKPD" and len(payload) >= 12:
            out.append((struct.unpack_from("<I", payload, 8)[0], "skel"))
        elif magic == b"TXID":
            out += [(f, "texture") for f in _u32s(payload)]
        elif magic == b"PFID":
            out += [(f, "phys") for f in _u32s(payload)[:1]]
        elif magic in (b"RPID", b"GPID"):
            out += [(f, "model") for f in _u32s(payload)]
    return [(f, k) for f, k in out if f]


def skin_profiles(data: bytes) -> list[int]:
    """The skin profiles a retail model (MD21) is drawn with, by FileDataID: its SFID list's first
    numSkinProfiles ids (the LOD skins it lists after them aren't profiles)."""
    if data[:4] != b"MD21":
        return []
    count, sfid = 0, []
    for magic, payload in chunks(data):
        if magic == b"MD21" and len(payload) >= 72 and payload[:4] == b"MD20":
            count = struct.unpack_from("<I", payload, 68)[0]            # the body's numSkinProfiles
        elif magic == b"SFID":
            sfid = _u32s(payload)
    return [f for f in sfid[:count] if f]


def skin_name(model_path: str, profile: int) -> str:
    """The name the client opens a model's skin profile by: its path less the extension, then NN.skin
    (CM2Shared::LoadSkinProfile). Retail shares one skin between models of one mesh, under the other
    model's name - the cloth of the Ethereal warlock set is drawn with its belt's - so a model whose
    profile lives elsewhere needs a copy here as well."""
    stem, dot = model_path, model_path.rfind(".")
    if dot > max(model_path.rfind("\\"), model_path.rfind("/")):
        stem = model_path[:dot]
    return f"{stem}{profile:02d}.skin"


def listfile_names(path: str, ids) -> dict[int, str]:
    """{FileDataID: path with backslashes, lower case} for ``ids``, from the community listfile."""
    want, found = set(ids), {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            at = line.find(";")
            if at <= 0:
                continue
            head = line[:at]
            if head.isdigit() and int(head) in want:
                found[int(head)] = norm(line[at + 1:].strip())
    return found


def place(files: dict[int, str], owner: dict[int, int], names: dict[int, str], shown=()) -> dict[int, str]:
    """Each file's path: the listfile's; one it doesn't name goes beside the model it came with as
    ``wxl_<fdid>`` (the client finds it by id, through the path table, wherever it is). A display's
    own model (``shown``) the client finds only under objectcomponents: one kept elsewhere
    (creature\\, the listfile's models\\unknown\\) goes to objectcomponents\\wxl\\."""
    out = {}
    for fdid, kind in files.items():
        name = names.get(fdid, "")
        if fdid in shown and kind == "model" and not object_folder(name):
            stem = os.path.splitext(name.rsplit("\\", 1)[-1])[0] if name else "wxl"
            out[fdid] = f"{OBJECT}wxl\\{stem}_{fdid}.m2"
            continue
        if name:
            out[fdid] = name
            continue
        base = os.path.dirname(names[owner[fdid]]) if owner.get(fdid) in names else OBJECT + "wxl"
        out[fdid] = f"{base}\\wxl_{fdid}{EXTENSION.get(kind, '')}"
    return out


# -- the path tables (WDC1 as x64_retail_pack.py writes them) -------------------------------------
_WDC1 = struct.Struct("<4s10I2H9I")


def write_paths(rows: dict[int, str]) -> bytes:
    """A WDC1 table of (id, path): inline id in field 0, the path's string offset in field 1 - the
    layout FdidCompat.cpp's PathTable reads."""
    rows = sorted(rows.items())
    strings, offsets = bytearray(b"\0"), {}
    for _fdid, path in rows:
        if path not in offsets:
            offsets[path] = len(strings)
            strings += path.encode("latin-1", "replace") + b"\0"
    records = b"".join(struct.pack("<II", fdid, offsets[path]) for fdid, path in rows)
    ids = [fdid for fdid, _ in rows] or [0]
    storage = struct.pack("<HHIIIII", 0, 32, 0, 0, 0, 0, 0) + struct.pack("<HHIIIII", 32, 32, 0, 0, 0, 0, 0)
    header = _WDC1.pack(b"WDC1", len(rows), 2, 8, len(strings), 0, 0, min(ids), max(ids), 0, 0, 0, 0, 2, 0, 0, 0,
                        0, len(storage), 0, 0, 0)
    return header + struct.pack("<hHhH", 0, 0, 0, 4) + records + bytes(strings) + storage


def read_paths(data: bytes) -> dict[int, str]:
    """The rows of a path table ``write_paths`` (or x64_retail_pack.py) wrote."""
    if not data:
        return {}
    (magic, count, fields, size, strings, _th, _lh, _min, _max, _loc, _copy, flags, id_index, total, _bp, _lc,
     _om, idlist, _storage, _cd, _pd, _rd) = _WDC1.unpack_from(data, 0)
    if magic != b"WDC1" or fields != 2 or size != 8 or flags != 0 or id_index != 0 or idlist != 0:
        raise ValueError("not a FileDataID path table of the layout x64_retail_pack.py writes")
    at = _WDC1.size + total * 4
    blob = data[at + count * size:at + count * size + strings]
    out = {}
    for i in range(count):
        fdid, offset = struct.unpack_from("<II", data, at + i * size)
        end = blob.find(b"\0", offset)
        out[fdid] = blob[offset:end if end >= 0 else len(blob)].decode("latin-1")
    return out


# -- items ----------------------------------------------------------------------------------------
def default_display(rows: list[tuple[int, int, int, int]]) -> int:
    """The display an item shows by default, as the client picks it: of its (modifier, order,
    display, appearance) rows, normal (modifier 0) first, then by order."""
    rows = [r for r in rows if r[2]]
    if not rows:
        return 0
    return min(rows, key=lambda r: (r[0] != 0, r[1], r[2], r[3]))[2]


def entry_for(item: int, modifier: int, default: bool, taken: set[int], spare: dict[str, int]) -> int:
    """The item_template entry of ``item``'s look with ``modifier``: the item's own id for its
    default look (the client then has retail's Item row for it too), unless the client's Item.dbc
    already has that id; its other looks (modifier + 1) * 1,000,000 + item; past those, numbered
    from 16,000,000 (``spare``: the numbers given so far, kept between installs)."""
    if default and item not in taken:
        return item
    if 0 <= modifier <= 14 and 0 < item < VARIANT:
        return (modifier + 1) * VARIANT + item
    key = f"{item}:{modifier}"
    if key not in spare:
        used = set(spare.values())
        n = SPARE
        while n in used:
            n += 1
        if n > ENTRY_MAX:
            raise ValueError("no item_template entries left for retail looks")
        spare[key] = n
    return spare[key]


@dataclass
class Piece:
    """One item the server gets: a retail item's look (display) under its entry."""
    entry: int
    item: int
    display: int
    modifier: int
    name: str
    quality: int
    cls: int
    sub: int
    inventory: int
    material: int
    sheath: int
    sound: int
    label: str = ""                         # the look's name when it isn't the item's default ("Mythic")

    def values(self) -> list:
        return [self.entry, self.cls, self.sub, self.sound, self.name, self.display, min(max(self.quality, 0), 7),
                self.inventory, -1, -1, 1, 0, self.material, self.sheath, 0, 1, 0, self.label]


COLUMNS = ("entry", "class", "subclass", "SoundOverrideSubclass", "name", "displayid", "Quality", "InventoryType",
           "AllowableClass", "AllowableRace", "ItemLevel", "RequiredLevel", "Material", "sheath", "bonding",
           "stackable", "MaxDurability", "description")


def item_fields(row: dict) -> dict:
    """An Item row's class, subclass, sound, material and sheath as 3.3.5 takes them: retail's
    cosmetic armour (subclass 5, 3.3.5's obsolete Buckler) as Miscellaneous, its "own subclass" sound
    sentinel 255 as -1 - as the x64 client does with retail's Item rows."""
    cls, sub = row.get("ClassID", 0), row.get("SubclassID", 0)
    sound = row.get("Sound_override_subclassID", -1)
    return {"cls": cls, "sub": 0 if cls == 4 and sub == 5 else sub, "sound": -1 if sound in (255, -1, None) else sound,
            "material": row.get("Material", 0), "sheath": row.get("SheatheType", 0),
            "inventory": row.get("InventoryType", 0)}


def _q(s) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"


def item_sql(pieces: list[Piece], owned: list[tuple[int, int]], build: str, made: str) -> str:
    """The item_template rows, in the format the Stats step reads back (``itemstats.kit_items``).
    Only rows Install made are deleted first (an entry with one of the displays it gave it): an
    entry someone else's row already has makes the INSERT stop with "Duplicate entry" - nothing of
    theirs is replaced."""
    from . import edition
    lines = [f"-- generated by {edition.NAME} (retail direct, for {edition.CLIENT_NAME}) {made}; retail {build}",
             "-- each item shows retail's own look: its displayid is retail's ItemDisplayInfo id, which the x64",
             "-- client draws from retail's tables (a stock 3.3.5 client shows these items without a model)",
             "-- entries: a retail item's own id for its default look; its other looks (modifier + 1) * 1,000,000 + id"]
    pairs = sorted(set(owned) | {(p.entry, p.display) for p in pieces})
    if pairs:
        lines.append("DELETE FROM `item_template` WHERE (`entry`, `displayid`) IN (" +
                     ",".join(f"({e},{d})" for e, d in pairs) + ");")
    if pieces:
        lines.append("INSERT INTO `item_template` (" + ",".join(f"`{c}`" for c in COLUMNS) + ") VALUES")
        rows = []
        for p in sorted(pieces, key=lambda p: p.entry):
            rows.append("(" + ",".join(_q(v) if isinstance(v, str) else str(int(v)) for v in p.values()) + ")")
        lines.append(",\n".join(rows) + ";")
    return "\n".join(lines) + "\n"


# -- the patch ------------------------------------------------------------------------------------
class PatchWriter:
    """An MPQ v1 patch (files stored), written as it goes so a big one never sits in memory; a name
    can share another's data (``alias``)."""

    def __init__(self, path: str):
        self.path, self.blocks, self.names, self._seen = path, [], {}, {}
        self.size = 32
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.file = open(path + ".part", "wb")
        self.file.write(bytes(32))

    def add(self, name: str, data: bytes) -> None:
        if self.size + len(data) > MPQ_LIMIT:
            raise ValueError(f"{os.path.basename(self.path)} would pass 3.9 GB - take some looks out of the basket")
        if name.lower() in self._seen:
            return
        self.names[name] = self._seen[name.lower()] = len(self.blocks)
        self.blocks.append((self.file.tell(), len(data), len(data), 0x80000000))
        self.file.write(data)
        self.size += len(data)

    def alias(self, name: str, of: str) -> bool:
        """``name`` as another name of ``of`` (added before); False when ``of`` isn't in the patch."""
        block = self._seen.get(of.lower())
        if block is None or name.lower() in self._seen:
            return False
        self.names[name] = self._seen[name.lower()] = block
        return True

    def close(self) -> None:
        from .. import mpq
        self.add("(listfile)", "\r\n".join(self.names).encode("latin-1", "replace"))
        slots = 16
        while slots < 2 * len(self.names):
            slots *= 2
        hashes = [(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFF, 0xFFFFFFFF)] * slots
        for name, block in self.names.items():
            i = mpq._slot(hashes, name)
            hashes[i] = (mpq.hash_string(name, 1), mpq.hash_string(name, 2), 0, 0, block)
        ht, bt = mpq._tables(hashes, self.blocks)
        at = self.file.tell()
        self.file.write(ht + bt)
        end = self.file.tell()
        self.file.seek(0)
        self.file.write(struct.pack("<4sIIHHIIII", b"MPQ\x1a", 32, end, 0, 3, at, at + len(ht), slots, len(self.blocks)))
        self.file.close()
        os.replace(self.path + ".part", self.path)

    def abandon(self) -> None:
        self.file.close()
        try:
            os.remove(self.path + ".part")
        except OSError:
            pass
