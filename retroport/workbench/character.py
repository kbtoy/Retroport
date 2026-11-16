"""The character the set view dresses: a BfA body for each race your 3.3.5 client plays.

The races are the client's own (CharBaseInfo: every race a class can be), by ChrRaces prefix: a
Kul Tiran (22, 23) and a Pandaren (24, 25) are one each. A race is found in BfA and in the item
source by that prefix (the lowest id: the neutral Pandaren, 24). The body is BfA's model of the
race and sex (``character/<race>/<sex>/<race><sex>.m2``: the HD bodies, bones in the model, Stand
in it) - what our race ports are made from - dressed with retail's or BfA's items alike.

Its skin is composited the way the client does it, from CharSections (BaseSection 0-4: skin,
face, facial hair, hair, underwear; the HD rows 5-9 where the race has them, on its hi-res
layout): the skin over the whole layout, then the face, facial hair and scalp in the face
sections, underwear in the upper leg and torso, then each item's section textures. The hair
texture and the default geosets (hair style, facial hair, ears, bare hands and feet, trousers)
go with it.
"""

from __future__ import annotations

import os
import threading

from ..dbc import DBCFile, RawDBC

SEXES = ("male", "female")
FACE_UPPER, FACE_LOWER = 9, 10
LEG_UPPER, TORSO_UPPER = 5, 3
# (CharSections BaseSection, MaterialResourcesID slot) -> where it goes on the layout
SLOTS = {(1, 0): FACE_LOWER, (1, 1): FACE_UPPER, (2, 0): FACE_LOWER, (2, 1): FACE_UPPER,
         (3, 1): FACE_LOWER, (3, 2): FACE_UPPER, (4, 0): LEG_UPPER, (4, 1): TORSO_UPPER}
HD = 5                            # BaseSection + 5: the HD rows
FACIAL_GROUPS = (1, 3, 2, 16, 17)  # CharacterFacialHairStyles.Geoset[i] -> geoset group
# a bare body: one geoset per group (group * 100 + value); hair and facial hair come from the race
DEFAULT_GEOSETS = {4: 1, 5: 1, 7: 2, 13: 1, 17: 2, 18: 1}      # 1702: the HD bodies' eyes


RACES_CFG = "wxl-races.cfg"
# The body a stock race wears when wxl-races.cfg says nothing of it: its own retail race
STOCK = {1, 2, 3, 4, 5, 6, 7, 8, 10, 11}


def race_cfg(client_dir: str) -> dict[int, int]:
    """The x64 client's race rows (``wxl-races.cfg`` in its folder: ``WXL_M2_RACE_<client id>=<retail race>,
    <team>[,flags]``): client race id -> the retail race whose body it wears; 0 for ``=none`` (a built-in row
    taken out) and for a row the client won't let anyone create (``nocreate``)."""
    out: dict[int, int] = {}
    try:
        lines = open(os.path.join(client_dir, RACES_CFG), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line.startswith("WXL_M2_RACE_") or "=" not in line:
            continue
        key, value = line[len("WXL_M2_RACE_"):].split("=", 1)
        if not key.strip().isdigit():
            continue
        fields = [f.strip() for f in value.split(",")]
        retail = int(fields[0]) if fields[0].isdigit() else 0
        out[int(key)] = 0 if "nocreate" in fields[2:] else retail
    return out


def server_races(client_dir: str, chr_races: dict[int, dict]) -> list[dict]:
    """The races the client plays, by the body each wears: [{key, prefix, name, client: [ids], retail}] - the
    client's own (CharBaseInfo) and those wxl-races.cfg adds past 32, each by its row there (else a stock
    race's own, else the retail race of its ChrRaces prefix). ``chr_races``: a source's ChrRaces (retail's,
    which has every body race; names and prefixes from there). Two client races of one body are one race
    (Kul Tiran 22 and 23, Pandaren 24 and 25, Earthen 33 and 34); one ChrRaces prefix of two bodies is two
    (Orc 2 and Mag'har 26)."""
    cfg = race_cfg(client_dir)
    client = client_races(client_dir)
    by_prefix = {}
    for i, r in sorted(chr_races.items()):
        by_prefix.setdefault(str(r.get("ClientPrefix") or "").lower(), i)
    ids: dict[int, str] = {}                                    # client id -> its ChrRaces prefix
    for r in client:
        for i in r["ids"]:
            ids[i] = r["prefix"]
    for i, retail in cfg.items():
        if i > 32 and retail:
            ids.setdefault(i, "")
    out: dict[str, dict] = {}
    for i in sorted(ids):
        retail = cfg.get(i) if i in cfg else (i if i in STOCK else by_prefix.get(ids[i].lower(), 0))
        row = chr_races.get(retail or 0)
        if not row:
            continue
        prefix = str(row.get("ClientPrefix") or ids[i])
        e = out.setdefault(prefix.lower(), {"key": prefix.lower(), "prefix": prefix,
                                            "name": row.get("Name_lang") or row.get("ClientFileString") or prefix,
                                            "client": [], "retail": retail})
        e["client"].append(i)
    return list(out.values())


def stock_races(chr_races: dict[int, dict]) -> list[dict]:
    """The ten races every 3.3.5 client plays, from a source's ChrRaces: the race list before a client folder is
    chosen (or when its tables can't be read), in ``server_races``' form."""
    out = []
    for i in sorted(STOCK):
        row = chr_races.get(i)
        if not row:
            continue
        prefix = str(row.get("ClientPrefix") or "")
        if prefix:
            out.append({"key": prefix.lower(), "prefix": prefix, "client": [i], "retail": i,
                        "name": row.get("Name_lang") or row.get("ClientFileString") or prefix})
    return out


# A body's other posture: (race key, sex) -> its choices, the first the client's own. A model: where the
# body is - ("bfa", FileDataID), or ("client", its path in the client: our own upright undead, patch-T).
POSTURES = {
    ("or", 0): [("hunched", "Hunched", None), ("upright", "Upright", ("bfa", 1968587))],
    # the x64 client's Mag'har man stands upright (retail's "Upright" choice: orcmaleupright)
    ("mo", 0): [("upright", "Upright", ("bfa", 1968587)), ("hunched", "Hunched", None)],
    ("sc", 0): [("normal", "Normal", None), ("upright", "Upright", ("client", "character\\scourge\\male\\scourgemaleupright.m2"))],
    ("sc", 1): [("normal", "Normal", None), ("upright", "Upright", ("client", "character\\scourge\\female\\scourgefemaleupright.m2"))],
}


class ClientFiles:
    """The 3.3.5 client's files by FileDataID, as the x64 client finds them: through every archive's file id
    tables (the top archive's row first), and a model's companions it names after the model when no table
    does (``<model>.skel``, ``<model>NN.skin``, ``<model>AAAA-SS.anim``) - our own upright undead's."""

    def __init__(self, client_dir: str):
        self.client_dir = client_dir
        self._cd = None
        self._paths: dict[int, str] | None = None
        self._extra: dict[int, str] = {}
        self._named: set[str] = set()                # models whose companions are named (read once)
        self._lock = threading.RLock()

    def _open(self):
        if self._cd is None:
            from ..mpq import ClientData
            from . import retailpack as RP
            self._cd = ClientData(self.client_dir)
            paths: dict[int, str] = {}
            for _label, archive in self._cd.sources:
                for name in (RP.MODEL_PATHS, RP.TEXTURE_PATHS):
                    try:
                        data = archive.read(name)
                    except Exception:
                        data = None
                    if data:
                        try:
                            for f, p in RP.read_paths(data).items():
                                paths.setdefault(f, p)
                        except ValueError:
                            continue
            self._paths = paths
        return self._cd

    def exists(self, path: str) -> bool:
        with self._lock:
            return self._open().exists(path)

    def fdid_of(self, path: str, companions: bool = True) -> int:
        """A path's FileDataID in the client's tables (0: none), its model's companions named (``companions``:
        reading its skeleton, seconds for a body - not wanted just to know it's there)."""
        with self._lock:
            self._open()
            want = path.replace("/", "\\").lower()
            fdid = next((f for f, p in self._paths.items() if p.lower() == want), 0)
            if fdid and companions:
                self._name_companions(fdid, want)
            return fdid

    def _name_companions(self, fdid: int, path: str) -> None:
        if not path.endswith(".m2") or path in self._named:
            return
        from wotlkconv.m2.model import parse_m2
        from wotlkconv.m2.skel import parse_skel
        stem = path[:-3]
        m = parse_m2(self._cd.read(path), path)
        for i, s in enumerate(m.skin_file_ids or []):
            self._extra.setdefault(s, f"{stem}{i:02d}.skin")
        refs = list(m.anim_file_ids or [])
        if m.skeleton_file_id and self._cd.exists(stem + ".skel"):
            self._extra.setdefault(m.skeleton_file_id, stem + ".skel")
            refs += parse_skel(self._cd.read(stem + ".skel"), stem + ".skel").anim_file_ids or []
        for a in refs:
            self._extra.setdefault(a.file_id, f"{stem}{a.anim_id:04d}-{a.sub_anim_id:02d}.anim")
        self._named.add(path)

    def read(self, fdid: int) -> bytes:
        with self._lock:
            self._open()
            path = self._paths.get(fdid) or self._extra.get(fdid)
            if not path:
                raise LookupError(f"file {fdid} isn't in the client's tables")
            return self._cd.read(path)

    def close(self) -> None:
        with self._lock:
            if self._cd is not None:
                self._cd.close()
                self._cd = None


def client_races(client_dir: str) -> list[dict]:
    """The races the 3.3.5 client plays, one per ChrRaces prefix: [{prefix, ids, name}]."""
    from ..mpq import ClientData
    cd = ClientData(client_dir)
    try:
        races = DBCFile.from_bytes(cd.read("DBFilesClient\\ChrRaces.dbc"))
        playable = {r[0] for r in RawDBC.from_bytes(cd.read("DBFilesClient\\CharBaseInfo.dbc")).records}
    finally:
        cd.close()
    out: dict[str, dict] = {}
    for r in races.records:
        if r[0] not in playable:
            continue
        prefix = races.get_string(r[6])
        e = out.setdefault(prefix.lower(), {"prefix": prefix, "ids": [], "name": ""})
        e["ids"].append(r[0])
    return list(out.values())


def hd_skin(rows: list[dict]) -> bool:
    """Whether a race's CharSections rows have the HD skins (BaseSection 5-9); 10 and up are other
    kinds, which Pandaren has without HD skins."""
    return any(HD <= r["BaseSection"] < HD + 5 for r in rows)


def by_prefix(rows: list[tuple[int, dict]]) -> dict[str, tuple[int, dict]]:
    """A source's ChrRaces by prefix: the lowest id of each (Pandaren 24, not 25 or 26)."""
    out: dict[str, tuple[int, dict]] = {}
    for i, r in sorted(rows, key=lambda t: t[0]):
        p = str(r.get("ClientPrefix") or "").lower()
        if p and p not in out:
            out[p] = (i, r)
    return out


class Bodies:
    """BfA bodies, their skins and default geosets, by BfA race id and sex (cached)."""

    def __init__(self, bfa):
        self.src = bfa
        self._tables: dict[str, list] = {}
        self._cache: dict[tuple[int, int], dict] = {}
        self._lock = threading.Lock()

    def table(self, name: str) -> list:
        if name not in self._tables:
            self._tables[name] = self.src.table(name)
        return self._tables[name]

    def races(self) -> dict[str, tuple[int, dict]]:
        return by_prefix(self.table("ChrRaces"))

    def _model_fdid(self, rrow: dict, sex: int) -> int:
        """The race's HD body, as ChrRaces names it: its HighRes display for the classic races
        (``<race><sex>_hd.m2``; their plain display is the pre-WoD model, on the 512x512 layout),
        else its display (races BfA made HD: Kul Tiran, Pandaren...) - display -> model -> file."""
        displays = dict(self.table("CreatureDisplayInfo"))
        models = dict(self.table("CreatureModelData"))
        sexed = ("Female" if sex else "Male")
        for col in (f"HighRes{sexed}DisplayID", f"{sexed}DisplayID"):
            model = displays.get(rrow.get(col) or 0, {}).get("ModelID")
            fdid = models.get(model or 0, {}).get("FileDataID")
            if fdid:
                return fdid
        raise LookupError(f"{rrow.get('ClientFileString')}: ChrRaces names no body model for sex {sex}")

    def body(self, race: int, sex: int, model: tuple | None = None) -> dict:
        """The body of a BfA race id and sex: its mesh (with bones and Stand), layout, skin
        textures by layout section, hair texture and default geosets. ``model``: another posture's
        mesh in its place - (its name, read(fdid), its FileDataID) - on the same skin."""
        ck = (race, sex, model[0] if model else "")
        with self._lock:
            if ck in self._cache:
                return self._cache[ck]
        from . import models as M
        from ..character.layouts import layout_from_tables
        rrow = dict(self.table("ChrRaces"))[race]
        mesh = M.mesh(model[1], model[2], {}) if model else M.mesh(self.src.read, self._model_fdid(rrow, sex), {})
        rows = [r for _i, r in self.table("CharSections") if r["RaceID"] == race and r["SexID"] == sex]
        hd = hd_skin(rows)
        layout_id = (rrow.get("CharComponentTexLayoutHiResID") if hd else 0) or rrow["CharComponentTextureLayoutID"]
        layouts = dict(self.table("CharComponentTextureLayouts"))
        lay = layout_from_tables(layouts, [r for _i, r in self.table("CharComponentTextureSections")], layout_id)
        tfd: dict[int, list] = {}
        for _i, t in self.table("TextureFileData"):
            tfd.setdefault(t["MaterialResourcesID"], []).append((t.get("UsageType", 0), t["FileDataID"]))

        def fdid(mat: int) -> int:
            files = sorted(tfd.get(mat, [])) if mat else []
            return files[0][1] if files else 0

        def row(section: int, variation: int = 0, color: int = 0):
            base = section + (HD if hd else 0)
            return next((r for r in rows if r["BaseSection"] == base and r["VariationIndex"] == variation
                         and r["ColorIndex"] == color), None)

        # a hair style that has both a mesh and a texture
        hairs = sorted((r["VariationID"], r["GeosetID"]) for _i, r in self.table("CharHairGeosets")
                       if r["RaceID"] == race and r["SexID"] == sex and r.get("GeosetType", 0) == 0)
        style, hair_geoset = 0, 0
        for var, geo in hairs:
            hr = row(3, var)
            if geo > 0 and hr and fdid(list(hr["MaterialResourcesID"])[0]):
                style, hair_geoset = var, geo
                break
        geosets = {0: hair_geoset} | dict(DEFAULT_GEOSETS)
        facial = next((r for _i, r in self.table("CharacterFacialHairStyles")
                       if r["RaceID"] == race and r["SexID"] == sex and r["VariationID"] == 0), None)
        if facial:
            for g, v in zip(FACIAL_GROUPS, facial["Geoset"]):
                if v >= 0:
                    geosets[g] = v
        skin = row(0)
        layers = []                                         # [section or -1 (the whole layout), fdid]
        if skin:
            mats = list(skin["MaterialResourcesID"])
            layers.append([-1, fdid(mats[0])])
        for section, variation in ((1, 0), (2, 0), (3, style), (4, 0)):
            r = row(section, variation)
            if not r:
                continue
            for slot, mat in enumerate(list(r["MaterialResourcesID"])):
                target = SLOTS.get((section, slot))
                if target is not None and fdid(mat):
                    layers.append([target, fdid(mat)])
        hair = row(3, style)
        out = {"race": race, "sex": sex, "name": rrow.get("Name_lang", rrow["ClientFileString"]), "mesh": mesh,
               "source": "bfa",
               "layout": {"width": lay.width, "height": lay.height,
                          "sections": {s: [r.x, r.y, r.w, r.h] for s, r in lay.sections.items()}},
               "skin": [l for l in layers if l[1]], "hair": fdid(list(hair["MaterialResourcesID"])[0]) if hair else 0,
               "skin_extra": fdid(list(skin["MaterialResourcesID"])[1]) if skin else 0, "geosets": geosets, "types": {}}
        with self._lock:
            self._cache[ck] = out
        return out


ALL_SECTIONS = 0xFFFFFFFF


class RetailBodies:
    """Bodies of the races only retail has (Earthen): retail keeps no CharSections, so the body is its
    ChrModel's model dressed in the first choice of each of its customization options - each choice's
    materials painted into the layout where ChrModelTextureLayer puts its target (section bits; all of them:
    the whole layout), the other texture types as they are, its geosets shown - as the x64 client composes a
    retail race (AppearanceCompat) with nothing chosen."""

    TABLES = ("ChrRaceXChrModel", "ChrModel", "ChrModelTextureLayer", "ChrCustomizationOption", "ChrCustomizationChoice",
              "ChrCustomizationElement", "ChrCustomizationMaterial", "ChrCustomizationGeoset", "CharComponentTextureLayouts",
              "CharComponentTextureSections", "CreatureDisplayInfo", "CreatureModelData", "TextureFileData", "ChrRaces")

    def __init__(self, retail):
        self.src = retail
        self._t: dict[str, list] = {}
        self._cache: dict[tuple[int, int], dict] = {}
        self._lock = threading.Lock()

    def table(self, name: str) -> list:
        if name not in self._t:
            self._t[name] = self.src.table(name)
        return self._t[name]

    def body(self, race: int, sex: int) -> dict:
        with self._lock:
            if (race, sex) in self._cache:
                return self._cache[(race, sex)]
        from . import models as M
        link = next((r for _i, r in self.table("ChrRaceXChrModel") if r["ChrRacesID"] == race and r["Sex"] == sex), None)
        if link is None:
            raise LookupError(f"retail has no body for race {race}, sex {sex}")
        model_id = link["ChrModelID"]
        cm = dict(self.table("ChrModel"))[model_id]
        cdi = dict(self.table("CreatureDisplayInfo")).get(cm["DisplayID"], {})
        fdid = dict(self.table("CreatureModelData")).get(cdi.get("ModelID") or 0, {}).get("FileDataID")
        if not fdid:
            raise LookupError(f"ChrModel {model_id}: no model file")
        mesh = M.mesh(self.src.read, fdid, {})
        layout_id = cm["CharComponentTextureLayoutID"]
        lay = dict(self.table("CharComponentTextureLayouts"))[layout_id]
        sections = {r["SectionType"]: [r["X"], r["Y"], r["Width"], r["Height"]]
                    for _i, r in self.table("CharComponentTextureSections") if r["CharComponentTextureLayoutID"] == layout_id}
        tfd: dict[int, list] = {}
        for _i, t in self.table("TextureFileData"):
            tfd.setdefault(t["MaterialResourcesID"], []).append((t.get("UsageType", 0), t["FileDataID"]))
        targets: dict[int, list[dict]] = {}
        for _i, r in self.table("ChrModelTextureLayer"):
            if r["CharComponentTextureLayoutsID"] != layout_id:
                continue
            for target in (r["ChrModelTextureTargetID"] if isinstance(r["ChrModelTextureTargetID"], list)
                           else [r["ChrModelTextureTargetID"]]):
                if target:
                    targets.setdefault(target, []).append(r)
        choices: dict[int, list] = {}
        for i, c in self.table("ChrCustomizationChoice"):
            choices.setdefault(c["ChrCustomizationOptionID"], []).append((c["OrderIndex"], i, c))
        elements: dict[int, list] = {}
        for _i, e in self.table("ChrCustomizationElement"):
            elements.setdefault(e["ChrCustomizationChoiceID"], []).append(e)
        materials = dict(self.table("ChrCustomizationMaterial"))
        geosets_t = dict(self.table("ChrCustomizationGeoset"))
        layers, types, geosets = [], {}, {}
        options = sorted((o["OrderIndex"], i) for i, o in self.table("ChrCustomizationOption") if o["ChrModelID"] == model_id)
        # each option's first choice (every one names a requirement - 141, any player - so none is skipped for that)
        picks = [p for p in (next((i for _o, i, _c in sorted(choices.get(option, []), key=lambda t: (t[0], t[1]))), None)
                             for _order, option in options) if p is not None]
        picked = set(picks)
        for pick in picks:
            for e in elements.get(pick, []):
                # an element for another choice too (a face's texture for each skin colour) is that choice's
                related = e.get("RelatedChrCustomizationChoiceID") or 0
                if related and related not in picked:
                    continue
                g = geosets_t.get(e.get("ChrCustomizationGeosetID") or 0)
                if g:
                    geosets[g["GeosetType"]] = g["GeosetID"]
                mat = materials.get(e.get("ChrCustomizationMaterialID") or 0)
                if not mat:
                    continue
                files = sorted(tfd.get(mat["MaterialResourcesID"], []))
                if not files:
                    continue
                for layer in targets.get(mat["ChrModelTextureTargetID"], []):
                    if layer["TextureType"] != 1:
                        types[layer["TextureType"]] = files[0][1]
                        continue
                    bits, blend = layer["TextureSectionTypeBitMask"] & ALL_SECTIONS, layer.get("BlendMode", 9)
                    if bits == ALL_SECTIONS:
                        layers.append((layer["Layer"], -1, files[0][1], blend))
                    else:
                        layers += [(layer["Layer"], s, files[0][1], blend) for s in range(32) if bits >> s & 1 and s in sections]
        layers.sort(key=lambda t: t[0])
        # hair is a geoset choice's value; DEFAULT_GEOSETS fill what no choice names
        hair = geosets.pop(0, 0)
        out = {"race": race, "sex": sex, "name": dict(self.table("ChrRaces")).get(race, {}).get("Name_lang", f"race {race}"),
               "mesh": mesh, "source": "retail",
               "layout": {"width": lay["Width"], "height": lay["Height"], "sections": sections},
               # [section (-1: all), fdid, blend]: the client's blends - 1 pastes, 4 multiplies, 6 overlays,
               # 7 screens, 9 and 15 blend by alpha (CharacterAtlas Paint)
               "skin": [[s, f, b] for _l, s, f, b in layers], "hair": types.pop(6, 0), "skin_extra": types.pop(8, 0),
               "geosets": {0: hair} | dict(DEFAULT_GEOSETS) | geosets, "types": {str(t): f for t, f in types.items()}}
        with self._lock:
            self._cache[(race, sex)] = out
        return out


# Which body geoset group each of an item's GeosetGroup values switches, by inventory type
# (the value v shows geoset group * 100 + 1 + v): 3.3.5's own rules, and BfA's later groups.
ITEM_GEOSETS = {
    1: (27, 21), 3: (26,), 4: (8, 10), 5: (8, 10, 13, 22, 28), 20: (8, 10, 13, 22, 28),
    6: (18,), 7: (9, 13, 11), 8: (5, 20), 10: (4, 23), 16: (15,), 19: (12,),
}
# the order the client dresses a body in: later slots win a geoset group and draw over earlier textures
DRESS_ORDER = (4, 7, 8, 9, 5, 20, 6, 10, 19, 16, 1, 3)
# where a held item hangs on the body: inventory type -> M2 attachment id (worn pieces: models.ITEM_POINTS)
ATTACH_POINTS = {13: 1, 21: 1, 17: 1, 22: 2, 23: 2, 14: 0, 15: 2, 26: 1, 25: 1}
