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

    def body(self, race: int, sex: int) -> dict:
        """The body of a BfA race id and sex: its mesh (with bones and Stand), layout, skin
        textures by layout section, hair texture and default geosets."""
        with self._lock:
            if (race, sex) in self._cache:
                return self._cache[(race, sex)]
        from . import models as M
        from ..character.layouts import layout_from_tables
        rrow = dict(self.table("ChrRaces"))[race]
        mesh = M.mesh(self.src.read, self._model_fdid(rrow, sex), {})
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
               "layout": {"width": lay.width, "height": lay.height,
                          "sections": {s: [r.x, r.y, r.w, r.h] for s, r in lay.sections.items()}},
               "skin": [l for l in layers if l[1]], "hair": fdid(list(hair["MaterialResourcesID"])[0]) if hair else 0,
               "skin_extra": fdid(list(skin["MaterialResourcesID"])[1]) if skin else 0, "geosets": geosets}
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
