"""3D previews: item displays and character bodies as meshes the page's viewer draws and animates.

An ItemDisplayInfo names up to two model resources and their material resources. Each model is
attached at a body point (a helm on the head, shoulders, a belt buckle) or is a *collection* - a
piece skinned to the body itself, its parts numbered by the body's geoset groups (401 hands, 501
feet, 1801 belt, 2201 torso...), each drawn only where the body shows that same geoset. Which, the
x64 client decides as RetailItemIndex.cpp's Attach does (``placement``): by the file's folder
(objectcomponents\\collection(s)\\), the slot and ``ModelType`` - a belt's race-and-sex collection is
skinned whatever its ModelType says. A model resource is one or more ModelFileData files - several when the
model differs by race and sex (helms) or side (shoulders, ComponentModelFileData.PositionIndex);
a material resource is TextureFileData files, by race and sex where they differ
(ComponentTextureFileData), with ChrRaces' model and texture fallbacks (a Nightborne wears the
Night Elf's). Armour drawn on the body is ItemDisplayInfoMaterialRes: a texture per body section.

The resolution tables are read once per build and kept on disk (``displays-<source>-<build>``).
A mesh is the model in its bind pose - positions, normals, UVs, triangles, per batch its geoset,
textures, blend mode and material flags - with its bones, vertex weights, attachment points and the
Stand animation's keyframes (from the model, its ``.skel`` or an ``.anim``), its particle emitters and
ribbons, and its physics (``physics``: what the client swings, the viewer hangs at rest), for the viewer
to play.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import struct
import threading
from collections import defaultdict

INDEX_VERSION = 6
TABLES = ("ItemDisplayInfo", "ModelFileData", "ComponentModelFileData", "TextureFileData",
          "ComponentTextureFileData", "ItemDisplayInfoMaterialRes", "ItemDisplayInfoModelMatRes",
          "HelmetGeosetData", "ChrRaces", "ParticleColor")
SECTIONS = {0: "Upper arm", 1: "Lower arm", 2: "Hand", 3: "Upper torso", 4: "Lower torso", 5: "Upper leg",
            6: "Lower leg", 7: "Foot", 8: "Accessory", 9: "Scalp upper", 10: "Scalp lower", 11: "Cloak", 12: "Cloak back",
            13: "Unknown 13", 14: "Unknown 14"}
VERTEX = 48                       # M2 vertex: position 12, bone weights 4, bone indices 4, normal 12, uv 8, uv2 8
ITEM_TEXTURE, ITEM_TEXTURE_2 = 2, 3   # M2 texture types: the display's own textures ("object skin" 1 and 2)
ATTACHED, COLLECTION = 0, 1       # ItemDisplayInfo.ModelType
# where the x64 client hangs a display's model that isn't a collection, by inventory type: (its first
# model, its second) - RetailItemIndex.cpp's Attach; a helm's second model on the head's top (55)
ITEM_POINTS = {1: (11, 55), 3: (6, 5), 4: (34, 34), 5: (34, 34), 19: (34, 34), 20: (34, 34), 6: (53, 53),
               7: (9, 10), 8: (47, 48), 9: (3, 4), 10: (1, 2), 16: (12, 12)}
COLLECTION_FOLDERS = ("item\\objectcomponents\\collection\\", "item\\objectcomponents\\collections\\")
SEQ_ALIAS = 0x40
QUAT16 = 32767.0


class ModelError(RuntimeError):
    pass


class DisplayIndex:
    """Where an item display's models and textures are (see the module doc)."""

    def __init__(self, d: dict):
        # id -> [mr0, mr1, mm0, mm1, type0, type1, GeosetGroup x6, AttachmentGeosetGroup x6, HelmetGeosetVis x2,
        #        GeosetGroupOverride]
        self.displays = {int(k): v for k, v in d["displays"].items()}
        self.model_files = {int(k): v for k, v in d["model_files"].items()}     # model resource -> [fdid]
        self.comp_models = {int(k): v for k, v in d["comp_models"].items()}     # fdid -> [race, gender, class, position]
        self.tex_files = {int(k): v for k, v in d["tex_files"].items()}         # material resource -> [[fdid, usage]]
        self.comp_tex = {int(k): v for k, v in d["comp_tex"].items()}           # fdid -> [race, gender, class]
        self.sections = {int(k): v for k, v in d["sections"].items()}           # display -> [[section, material res]]
        self.model_mat = {int(k): v for k, v in d["model_mat"].items()}         # display -> [[model, type, material res]]
        self.helmet_hides = {int(k): {int(r): g for r, g in v.items()} for k, v in d.get("helmet_hides", {}).items()}
        # race -> [male model race, sex, female model race, sex, male texture race, sex, female texture race, sex]
        self.fallbacks = {int(k): v for k, v in d.get("fallbacks", {}).items()}
        self.prefixes = dict(d.get("prefixes", {}))                             # ChrRaces prefix -> lowest race id
        # display -> its ParticleColor row's nine colours (start, middle, end of colour slots 11-13, ARGB)
        self.particle = {int(k): v for k, v in d.get("particle", {}).items()}
        self.visual = {int(k): v for k, v in d.get("visual", {}).items()}       # display -> its ItemVisual (a glow)
        # the model files the listfile puts in a collection folder; None without a listfile (then
        # ModelType 1 alone says collection)
        cf = d.get("collection_files")
        self.collection_files = set(cf) if cf is not None else None

    @classmethod
    def build(cls, src, log=lambda m: None) -> "DisplayIndex":
        t = {}
        for name in TABLES:
            log(f"{src.spec.label}: reading {name}")
            try:
                t[name] = src.table(name)
            except Exception as e:                        # an older build without the table
                log(f"{src.spec.label}: {name}: {e}")
                t[name] = []
        d = {"displays": {}, "model_files": defaultdict(list), "comp_models": {}, "tex_files": defaultdict(list),
             "comp_tex": {}, "sections": defaultdict(list), "model_mat": defaultdict(list),
             "helmet_hides": defaultdict(lambda: defaultdict(list)), "fallbacks": {}, "particle": {}, "visual": {}}
        from .mounts import particle_colors_of
        colors = {i: particle_colors_of(r) for i, r in t["ParticleColor"]}
        for i, r in t["ItemDisplayInfo"]:
            if colors.get(r.get("ParticleColorID") or 0):
                d["particle"][i] = colors[r["ParticleColorID"]]
            if r.get("ItemVisual"):
                d["visual"][i] = r["ItemVisual"]
            mr, mm = r["ModelResourcesID"], r["ModelMaterialResourcesID"]
            mt = list(r.get("ModelType") or [-1 if not mr[0] else ATTACHED, -1 if not mr[1] else ATTACHED])
            d["displays"][i] = [mr[0], mr[1], mm[0], mm[1], mt[0], mt[1], *list(r["GeosetGroup"])[:6],
                                *(list(r.get("AttachmentGeosetGroup") or [0] * 6)[:6]), *list(r["HelmetGeosetVis"])[:2],
                                r.get("GeosetGroupOverride") or 0]
        for _i, r in t["ModelFileData"]:
            d["model_files"][r["ModelResourcesID"]].append(r["FileDataID"])
        for i, r in t["ComponentModelFileData"]:
            d["comp_models"][i] = [r["RaceID"], r["GenderIndex"], r["ClassID"], r["PositionIndex"]]
        for _i, r in t["TextureFileData"]:
            d["tex_files"][r["MaterialResourcesID"]].append([r["FileDataID"], r["UsageType"]])
        for i, r in t["ComponentTextureFileData"]:
            d["comp_tex"][i] = [r["RaceID"], r["GenderIndex"], r["ClassID"]]
        for _i, r in t["ItemDisplayInfoMaterialRes"]:
            d["sections"][r["ItemDisplayInfoID"]].append([r["ComponentSection"], r["MaterialResourcesID"]])
        for _i, r in t["ItemDisplayInfoModelMatRes"]:
            d["model_mat"][r["ItemDisplayInfoID"]].append([r["ModelIndex"], r["TextureType"], r["MaterialResourcesID"]])
        for _i, r in t["HelmetGeosetData"]:
            d["helmet_hides"][r["HelmetGeosetVisDataID"]][r["RaceID"]].append(r["HideGeosetGroup"])
        for i, r in sorted(t["ChrRaces"], key=lambda x: x[0]):
            p = str(r.get("ClientPrefix") or "").lower()
            if p:
                d.setdefault("prefixes", {}).setdefault(p, i)
            d["fallbacks"][i] = [r.get(k, 0) or 0 for k in (
                "MaleModelFallbackRaceID", "MaleModelFallbackSex", "FemaleModelFallbackRaceID", "FemaleModelFallbackSex",
                "MaleTextureFallbackRaceID", "MaleTextureFallbackSex", "FemaleTextureFallbackRaceID",
                "FemaleTextureFallbackSex")]
        listfile = getattr(src, "listfile", "") or ""
        if os.path.isfile(listfile):
            from .retailpack import listfile_names
            log(f"{src.spec.label}: reading the listfile for the item models' folders")
            names = listfile_names(listfile, {f for files in d["model_files"].values() for f in files})
            d["collection_files"] = sorted(f for f, n in names.items() if any(m in n for m in COLLECTION_FOLDERS))
        return cls(d)

    def to_json(self) -> dict:
        return {"displays": self.displays, "model_files": self.model_files, "comp_models": self.comp_models,
                "tex_files": self.tex_files, "comp_tex": self.comp_tex, "sections": self.sections,
                "model_mat": self.model_mat, "helmet_hides": self.helmet_hides, "fallbacks": self.fallbacks,
                "prefixes": self.prefixes, "particle": self.particle, "visual": self.visual,
                "collection_files": sorted(self.collection_files) if self.collection_files is not None else None}

    # -- resolution ---------------------------------------------------------------
    def _fallback(self, race: int, sex: int, textures: bool) -> tuple[int, int] | None:
        fb = self.fallbacks.get(race)
        if not fb:
            return None
        k = (4 if textures else 0) + (2 if sex else 0)
        f_race, f_sex = fb[k], fb[k + 1]
        if not f_race:
            return None
        return f_race, (sex if f_sex < 0 else f_sex)

    def _fit(self, comp: list | None, race: int, sex: int) -> int:
        """How well a component row fits the race and sex: higher is better, -1 not at all."""
        if comp is None:
            return 1
        c_race, c_gender = comp[0], comp[1]
        if c_race not in (0, race) or c_gender not in (sex, 2, 3):
            return -1
        return (2 if c_race == race else 0) + (1 if c_gender == sex else 0)

    def texture(self, material: int, race: int, sex: int, _depth: int = 0) -> int:
        rows = self.tex_files.get(material) or []
        best, score = 0, -2
        for fdid, usage in rows:
            fit = self._fit(self.comp_tex.get(fdid), race, sex)
            if fit < 0:
                continue
            s = fit * 2 - (1 if usage else 0)
            if s > score:
                best, score = fdid, s
        if not best and rows and _depth < 3:
            fb = self._fallback(race, sex, textures=True)
            if fb:
                return self.texture(material, fb[0], fb[1], _depth + 1)
        return best

    def row(self, display: int) -> dict | None:
        r = self.displays.get(display)
        if not r:
            return None
        return {"model_resources": r[0:2], "materials": r[2:4], "model_types": r[4:6], "geoset_groups": r[6:12],
                "attachment_geosets": r[12:18], "helmet_vis": r[18:20], "geoset_override": r[20] if len(r) > 20 else 0}

    def placement(self, fdid: int, inv: int, column: int, model_type: int, position: int = -1) -> tuple[bool, int]:
        """Where the x64 client puts a display's model (RetailItemIndex.cpp's Attach): (skinned to the
        body - a collection, the attachment point it's hung on otherwise - -1 when ``inv`` doesn't say:
        a held item's). ``inv``: the item's inventory type (0 unknown: a collection by its folder alone);
        ``column``: the display's model 0 or 1. A collection is a file in objectcomponents\\collection(s)\\
        - a helm's only when its ModelType says 1 too, a belt's when ModelType 1 or made by race and sex
        (one made for the waist point is hung there), a cloak's by ModelType alone; shoulders are hung."""
        comp = self.comp_models.get(fdid)
        folder = (model_type == COLLECTION) if self.collection_files is None else fdid in self.collection_files
        by_race = comp is not None and (comp[0] != 0 or comp[1] in (0, 1))
        if inv == 3:
            skinned = False
        elif inv == 1:
            skinned = folder and model_type == COLLECTION
        elif inv == 6:
            skinned = folder and (model_type == COLLECTION or by_race)
        elif inv == 16:
            skinned = model_type == COLLECTION
        else:
            skinned = folder
        if skinned:
            return True, -1
        if inv == 3 and position in (0, 1):
            return False, ITEM_POINTS[3][position]         # a shoulder by its side: 0 left, 1 right
        return False, ITEM_POINTS.get(inv, (-1, -1))[1 if column else 0]

    def models(self, display: int, race: int, sex: int, inv: int = 0, _depth: int = 0) -> list[dict]:
        """The display's models for that race and sex: [{fdid, slot (0/1), position, type, attach, textures
        {type: fdid}}] - ``type`` COLLECTION (skinned to the body) or ATTACHED at ``attach`` (-1: a point
        ``inv``, the item's inventory type, doesn't say: a held item's), as ``placement`` puts them."""
        row = self.displays.get(display)
        if not row:
            return []
        out, wanted = [], 0
        for k in (0, 1):
            mr, mm, mtype = row[k], row[2 + k], row[4 + k]
            files = self.model_files.get(mr) or []
            if not mr or not files:
                continue
            wanted += 1
            textures = {ITEM_TEXTURE: self.texture(mm, race, sex)} if mm else {}
            for idx, ttype, mat in self.model_mat.get(display, []):
                if idx == k:
                    textures[ttype] = self.texture(mat, race, sex) or textures.get(ttype, 0)
            if ITEM_TEXTURE_2 not in textures and textures.get(ITEM_TEXTURE):
                textures[ITEM_TEXTURE_2] = textures[ITEM_TEXTURE]      # a second skin the display leaves to the first
            positions = sorted({(self.comp_models.get(f) or [0, 0, 0, -1])[3] for f in files})
            if len(positions) > 1 and row[1 - k] and k in positions:
                positions = [k]                            # a shoulder pair: resource 0 is the left one, 1 the right
            for pos in positions:                          # one resource for both sides: both models
                cands = [f for f in files if (self.comp_models.get(f) or [0, 0, 0, -1])[3] == pos]
                scored = sorted(((self._fit(self.comp_models.get(f), race, sex), f) for f in cands), reverse=True)
                if scored and scored[0][0] >= 0:
                    fdid = scored[0][1]
                    skinned, point = self.placement(fdid, inv, k, mtype, pos)
                    out.append({"fdid": fdid, "slot": k, "position": pos, "type": COLLECTION if skinned else ATTACHED,
                                "attach": point, "textures": textures})
        if wanted and not out and _depth < 3:          # nothing for this race: its fallback race's (Nightborne: Night Elf)
            fb = self._fallback(race, sex, textures=False)
            if fb:
                return self.models(display, fb[0], fb[1], inv, _depth + 1)
        return out

    def model_races(self, display: int) -> list[int]:
        """The races the display's models are made for, when they're made for some only (heritage armour:
        a Kul Tiran's bicorne); [] when one fits everyone."""
        row = self.displays.get(display)
        races: set[int] = set()
        for k in (0, 1):
            for f in (self.model_files.get(row[k]) or []) if row and row[k] else []:
                comp = self.comp_models.get(f)
                if comp is None or comp[0] == 0:
                    return []
                races.add(comp[0])
        return sorted(races)

    def body_textures(self, display: int, race: int, sex: int) -> list[dict]:
        out = []
        for section, mat in self.sections.get(display, []):
            fdid = self.texture(mat, race, sex)
            if fdid:
                out.append({"section": section, "name": SECTIONS.get(section, f"Section {section}"), "fdid": fdid})
        return out

    def helmet_hidden(self, display: int, race: int, sex: int) -> list[int]:
        """The body geoset groups a helm hides on that race (hair, ears, facial hair...)."""
        row = self.displays.get(display)
        if not row:
            return []
        vis = row[18 + (1 if sex else 0)]
        return sorted(set(self.helmet_hides.get(vis, {}).get(race, [])))


_lock = threading.Lock()


def load_index(src, cache_dir: str, log=lambda m: None) -> DisplayIndex:
    path = os.path.join(cache_dir, f"displays-{src.key}-{src.build}-v{INDEX_VERSION}.json.gz")
    with _lock:
        if os.path.isfile(path):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    return DisplayIndex(json.load(fh))
            except (OSError, ValueError, KeyError):
                pass
        idx = DisplayIndex.build(src, log)
        os.makedirs(cache_dir, exist_ok=True)
        tmp = path + ".part"
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(idx.to_json(), fh, separators=(",", ":"))
        os.replace(tmp, path)
        return idx


# -- meshes ------------------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def stand_index(sequences: list[dict], anim: int = 0) -> int | None:
    """The sequence an animation (0: Stand; its first variation) plays, through any alias - Stand's when
    the model hasn't that one."""
    if anim and not any(s.get("id") == anim for s in sequences):
        anim = 0
    for k, s in enumerate(sequences):
        if s.get("id") == anim and s.get("variation_index", 0) == 0:
            seen = set()
            while s.get("flags", 0) & SEQ_ALIAS and s.get("alias_next", k) < len(sequences) and k not in seen:
                seen.add(k)
                k = s["alias_next"]
                s = sequences[k]
            return k
    return None


def _anim_file(read, refs, anim_id: int, sub: int, chunk: str) -> bytes | None:
    """An ``.anim``'s keyframe block: the named chunk of a chunked file (AFM2 model tracks, AFSB
    skeleton bones), else the whole file."""
    ref = next((r for r in refs if r.anim_id == anim_id and r.sub_anim_id == sub), None)
    if ref is None or not ref.file_id:
        return None
    try:
        data = read(ref.file_id)
    except Exception:
        return None
    pos, found = 0, {}
    while pos + 8 <= len(data):
        name = data[pos:pos + 4][::-1].decode("latin-1", "replace")
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if not name.isalnum() or pos + 8 + size > len(data):
            break
        found[name] = data[pos + 8:pos + 8 + size]
        pos += 8 + size
    if not found:
        return data
    return found.get(chunk) or found.get("AFM2") or next(iter(found.values()))


def _keys(track, seq: int, ext: bytes | None) -> tuple[list[int], list]:
    """One sequence's keyframes of a track: in the model, or in the ``.anim`` at the spans the
    model names."""
    from wotlkconv.m2.types import _fmt, value_size
    i = 0 if track.global_sequence >= 0 else seq
    if i >= len(track.timestamps):
        return [], []
    if i in track.external:
        if ext is None or i >= len(track.timestamp_spans) or i >= len(track.value_spans):
            return [], []
        (tc, to), (vc, vo) = track.timestamp_spans[i], track.value_spans[i]
        size, fmt = value_size(track.kind), _fmt(track.kind)
        if to + tc * 4 > len(ext) or vo + vc * size > len(ext):
            return [], []
        times = list(struct.unpack_from(f"<{tc}I", ext, to)) if tc else []
        return times, [fmt.unpack_from(ext, vo + k * size) for k in range(vc)]
    return list(track.timestamps[i]), list(track.values[i])


def _track(track, seq: int, ext: bytes | None, kind: str) -> dict | None:
    times, values = _keys(track, seq, ext)
    n = min(len(times), len(values))
    if not n:
        return None
    flat = []
    for v in values[:n]:
        if kind == "quat16":
            v = [(c + 32768 if c < 0 else c - 32767) / QUAT16 for c in v]
        elif kind == "fixed16":
            v = v / QUAT16
        elif kind == "gravity_packed":
            v = _gravity(v)
        flat.extend(round(float(c), 5) for c in (v if isinstance(v, (tuple, list)) else (v,)))
    return {"i": track.interpolation, "g": track.global_sequence, "t": times[:n], "v": flat}


def _gravity(v) -> list[float]:
    """A packed particle gravity (flag 0x800000): a direction's x and y in 1/128ths and a magnitude,
    as the acceleration it gives (the plain kind pulls down by its value)."""
    x, y, z = v[0] / 128.0, v[1] / 128.0, 0.0
    z = max(0.0, 1.0 - x * x - y * y) ** 0.5
    mag = v[2] * 0.04238648
    return [-x * mag, -y * mag, -z * mag]


def _part(pt, scale: float = 1.0) -> dict | None:
    """A particle's over-its-life track (times 0..32767 -> 0..1)."""
    if pt is None or not getattr(pt, "times", None):
        return None
    flat = []
    for v in pt.values:
        flat.extend(round(float(c) * scale, 5) for c in (v if isinstance(v, (tuple, list)) else (v,)))
    return {"t": [round(t / QUAT16, 5) for t in pt.times], "v": flat}


def _texture_fdid(m, textures: dict[int, int], ti: int) -> int:
    """The FileDataID of the model's texture ``ti``: its own, or the replaceable one of its type."""
    tex = m.textures[ti] if 0 <= ti < len(m.textures) else None
    if tex is None:
        return 0
    return (m.texture_file_ids[ti] if ti < len(m.texture_file_ids) else 0) if tex["type"] == 0 else textures.get(tex["type"], 0)


MULTI_TEXTURE = 0x10000000          # a particle emitter of three textures (packed 5 bits each in its texture)


def model_anims(m, seq, ext, textures: dict[int, int]) -> dict:
    """What a model animates besides its bones: texture transforms (scrolling, turning UVs), colours,
    transparency, its particle emitters (with each one's texture - three for a multi-texture one) and its
    ribbons."""
    def tr(track):
        return _track(track, seq, ext, track.kind) if seq is not None and track is not None else None
    uv = [{"t": tr(t.get("translation")), "r": tr(t.get("rotation")), "s": tr(t.get("scaling"))}
          for t in m.texture_transforms]
    colors = [{"c": tr(c.get("color")), "a": tr(c.get("alpha"))} for c in m.colors]
    weights = [tr(w.get("weight")) for w in m.texture_weights]
    particles = []
    for pe in m.particles:
        packed, flags = pe.get("texture", 0), pe["flags"]
        if flags & MULTI_TEXTURE:
            fdids = [_texture_fdid(m, textures, (packed >> (5 * k)) & 0x1F) for k in range(3)]
        else:
            fdids = [_texture_fdid(m, textures, packed if packed < len(m.textures) else packed & 0x1F)]
        if not fdids[0]:
            continue
        particles.append({
            "bone": pe["bone"], "pos": [round(c, 5) for c in pe["position"]], "flags": flags,
            "type": pe["emitter_type"], "blend": pe["blending_type"], "texture": fdids[0],
            # a multi-texture emitter's other two, and how their coordinates run (WebWowViewerCpp's
            # BuildQuadT3: the cell's size in each, then a start and a scroll each particle takes)
            "textures": fdids[1:] if flags & MULTI_TEXTURE else [],
            "multi": [list(pe.get("multi_texture_param_x") or (32, 32)), list(pe.get("multi_texture_param0") or (0,) * 4),
                      list(pe.get("multi_texture_param1") or (0,) * 4)] if flags & MULTI_TEXTURE else None,
            # 11-13: its colours come from the display's ParticleColor row, as the client gives them
            "color_index": pe.get("particle_color_index", 0),
            "rows": max(1, pe.get("texture_dimensions_rows") or 1), "cols": max(1, pe.get("texture_dimensions_columns") or 1),
            "speed": tr(pe.get("emission_speed")), "speed_var": tr(pe.get("speed_variation")),
            "vrange": tr(pe.get("vertical_range")), "hrange": tr(pe.get("horizontal_range")),
            "gravity": tr(pe.get("gravity")), "life": tr(pe.get("lifespan")), "life_var": pe.get("lifespan_vary", 0),
            "rate": tr(pe.get("emission_rate")), "rate_var": pe.get("emission_rate_vary", 0),
            "length": tr(pe.get("emission_area_length")), "width": tr(pe.get("emission_area_width")),
            "z_source": tr(pe.get("z_source")), "enabled": tr(pe.get("enabled_in")),
            "color": _part(pe.get("color_track"), 1 / 255.0), "alpha": _part(pe.get("alpha_track"), 1 / QUAT16),
            "scale": _part(pe.get("scale_track")), "scale_var": list(pe.get("scale_vary") or (0, 0)),
            "cells": _part(pe.get("head_cell_track")), "tail_cells": _part(pe.get("tail_cell_track")),
            "tail_length": pe.get("tail_length", 0), "drag": pe.get("drag", 0),
            "spin": pe.get("spin", 0), "spin_var": pe.get("spin_vary", 0),
            "base_spin": pe.get("base_spin", 0), "base_spin_var": pe.get("base_spin_vary", 0),
            "twinkle": [pe.get("twinkle_speed", 0), pe.get("twinkle_percent", 1), *list(pe.get("twinkle_scale") or (1, 1))],
            "wind": [round(c, 5) for c in pe.get("wind_vector") or (0, 0, 0)],
            "spline": [[round(c, 5) for c in p] for p in pe.get("spline_points") or []],
        })
    ribbons = []
    for r in m.ribbons:
        mats = [m.materials[i] if i < len(m.materials) else {"flags": 0, "blending_mode": 2} for i in r.get("material_indices") or []]
        fdids = [_texture_fdid(m, textures, i) for i in r.get("texture_indices") or []]
        layers = [{"texture": f, "blend": mt["blending_mode"], "mflags": mt["flags"]} for f, mt in zip(fdids, mats) if f]
        if not layers:
            continue
        # its texture animation: an index into the model's lookup where the model's flag 0x20000 says so
        # (WebWowViewerCpp's m2Object), else none
        lookup = r.get("texture_transform_lookup_index", 0) if m.global_flags & 0x20000 else -1
        ribbons.append({
            "bone": r["bone_index"], "pos": [round(c, 5) for c in r["position"]], "layers": layers,
            "color": tr(r.get("color_track")), "alpha": tr(r.get("alpha_track")),
            "above": tr(r.get("height_above_track")), "below": tr(r.get("height_below_track")),
            "edges": r.get("edges_per_second", 0), "life": r.get("edge_lifetime", 0), "gravity": r.get("gravity", 0),
            "rows": max(1, r.get("texture_rows") or 1), "cols": max(1, r.get("texture_cols") or 1),
            "slot": tr(r.get("tex_slot_track")), "visible": tr(r.get("visibility_track")),
            "priority": r.get("priority_plane", 0),
            "uvanim": _lookup(m.texture_transform_combos, lookup) if lookup >= 0 else -1,
        })
    return {"uvanims": uv, "colors": colors, "weights": weights, "particles": particles, "ribbons": ribbons}


def skeleton(read, m, anim: int = 0) -> dict:
    """The model's bones (its own, or its ``.skel``'s) with an animation's keyframes (Stand's, or ``anim``'s)."""
    bones, attachments, sequences, refs, loops, chunk = m.bones, m.attachments, m.sequences, m.anim_file_ids, \
        m.global_loops, "AFM2"
    skel_id = getattr(m, "skeleton_file_id", 0)
    if skel_id:
        from wotlkconv.m2.skel import load_skeleton_chain

        from ..convert import skeleton
        skeleton.install()              # the parent skeleton's sequences too (HandsClosed...)

        def loader(fdid):
            try:
                return read(fdid)
            except Exception:
                return None
        sk = load_skeleton_chain(loader, skel_id)
        if sk is not None and sk.bones:
            bones, sequences, refs, chunk = sk.bones, sk.sequences or sequences, sk.anim_file_ids or refs, "AFSB"
            attachments, loops = sk.attachments or attachments, sk.global_loops or loops
    seq = stand_index(sequences, anim)
    ext = ext_model = None
    if seq is not None:
        s = sequences[seq]
        if not s.get("flags", 0) & 0x20:                   # its keyframes live in an .anim
            ext = _anim_file(read, refs, s["id"], s.get("variation_index", 0), chunk)
            ext_model = ext if chunk == "AFM2" else _anim_file(read, refs, s["id"], s.get("variation_index", 0), "AFM2")
    m_seq = stand_index(m.sequences, anim) if m.sequences else seq
    out = []
    for b in bones:
        e = {"p": b["parent_bone"], "v": [round(c, 5) for c in b["pivot"]], "c": b.get("bone_name_crc", 0),
             "k": b.get("key_bone_id", -1), "f": b.get("flags", 0)}
        if seq is not None:
            for key, name, kind in (("t", "translation", "vec3"), ("r", "rotation", "quat16"), ("s", "scale", "vec3")):
                tr = _track(b[name], seq, ext, b[name].kind)
                if tr:
                    e[key] = tr
        out.append(e)
    # the sequence's bounds (its reach as far as it moves): a gradient's height runs up them, as the client's
    reach = None
    if seq is not None and "bounds_min" in sequences[seq]:
        lo, hi = sequences[seq]["bounds_min"], sequences[seq]["bounds_max"]
        if hi[2] > lo[2]:
            reach = [[round(c, 5) for c in lo], [round(c, 5) for c in hi]]
    return {"bones": out, "duration": sequences[seq]["duration"] if seq is not None else 0, "globals": list(loops),
            "attachments": [[a["id"], a["bone"], *[round(c, 5) for c in a["position"]]] for a in attachments],
            "reach": reach, "_model_seq": m_seq, "_model_ext": ext_model}


def mesh(read, fdid: int, textures: dict[int, int], animate: bool = True, anim: int = 0) -> dict:
    """A model (FileDataID) as the viewer's mesh, with its skeleton, its Stand animation (or ``anim``'s)
    and its physics (``physics.read``: the viewer hangs what the client swings).
    ``read(fdid) -> bytes``; ``textures``: M2 texture type -> FileDataID for the replaceable ones."""
    from wotlkconv.m2.model import parse_m2
    from wotlkconv.m2.skin import parse_skin

    from . import physics
    raw = read(fdid)
    m = parse_m2(raw, f"model {fdid}")
    if not m.skin_file_ids:
        raise ModelError(f"model {fdid} names no skin file")
    skin = parse_skin(read(m.skin_file_ids[0]), f"skin {m.skin_file_ids[0]}")
    n = len(skin.vertices)
    pos, nrm, uv, uv2, wts = bytearray(n * 12), bytearray(n * 12), bytearray(n * 8), bytearray(n * 8), bytearray(n * 8)
    lo, hi = [1e9] * 3, [-1e9] * 3
    for k, v in enumerate(skin.vertices):
        o = v * VERTEX
        x, y, z = struct.unpack_from("<3f", m.vertices, o)
        pos[k * 12:k * 12 + 12] = m.vertices[o:o + 12]
        wts[k * 8:k * 8 + 8] = m.vertices[o + 12:o + 20]          # 4 weights, then 4 bone indices
        nrm[k * 12:k * 12 + 12] = m.vertices[o + 20:o + 32]
        uv[k * 8:k * 8 + 8] = m.vertices[o + 32:o + 40]
        uv2[k * 8:k * 8 + 8] = m.vertices[o + 40:o + 48]          # a glow layer's own coordinates
        for a, c in enumerate((x, y, z)):
            lo[a], hi[a] = min(lo[a], c), max(hi[a], c)
    tri = struct.pack(f"<{len(skin.indices)}I", *skin.indices)
    sections = [struct.unpack_from("<HHHHHH", s) for s in skin.submeshes]
    batches = []
    for b in skin.batches:
        flags, priority, shader, sec, _geo, color, mat, _layer, count, combo, _coord, wcombo, tcombo = \
            struct.unpack_from("<BbHHHhHHHHHHH", b)
        if sec >= len(sections):
            continue
        sid, level, _vstart, _vcount, istart, icount = sections[sec]
        ti = m.texture_combos[combo] if combo < len(m.texture_combos) else 0
        tex = m.textures[ti] if ti < len(m.textures) else {"type": 0, "flags": 0}
        if tex["type"] == 0:
            tfd = m.texture_file_ids[ti] if ti < len(m.texture_file_ids) else 0
        else:
            tfd = textures.get(tex["type"], 0)
        material = m.materials[mat] if mat < len(m.materials) else {"flags": 0, "blending_mode": 0}
        batches.append({"start": istart + (level << 16), "count": icount, "texture": tfd, "texture_type": tex["type"],
                        "wrap": [bool(tex["flags"] & 1), bool(tex["flags"] & 2)], "blend": material["blending_mode"],
                        "two_sided": bool(material["flags"] & 4), "unlit": bool(material["flags"] & 1),
                        # the material's flags as the client draws by them (CM2SceneRender::SetupMaterial):
                        # 0x4 both sides (else the back is culled), 0x8 no depth test, 0x10 no depth write
                        "mflags": material["flags"],
                        "priority": priority, "geoset": sid, "color": color, "shader": shader,
                        "weight": _lookup(m.texture_weight_combos, wcombo), "uvanim": _lookup(m.texture_transform_combos, tcombo),
                        "layers": _layers(m, textures, combo, tcombo, wcombo, count)})
    out = {"fdid": fdid, "vertices": n, "triangles": len(skin.indices) // 3, "positions": _b64(bytes(pos)),
           "normals": _b64(bytes(nrm)), "uvs": _b64(bytes(uv)), "uvs2": _b64(bytes(uv2)), "skin": _b64(bytes(wts)),
           "indices": _b64(tri),
           "batches": batches, "bounds": [lo, hi]}
    if animate:
        try:
            sk = skeleton(read, m, anim)
            seq, ext = sk.pop("_model_seq"), sk.pop("_model_ext")
            out.update(sk)
            out.update(model_anims(m, seq, ext, textures))
        except Exception as e:                             # a model we can't animate still shows in its bind pose
            out.update({"bones": [], "duration": 0, "globals": [], "attachments": [], "uvanims": [], "colors": [],
                        "weights": [], "particles": [], "ribbons": [], "anim_problem": f"{type(e).__name__}: {e}"})
        try:
            data = physics.chunk(raw, "PFDC")
            if data is None and getattr(m, "phys_file_id", 0):
                data = read(m.phys_file_id)
            phys = physics.read(data) if data else None
            if phys and out["bones"]:
                out["phys"] = phys
        except Exception:                                  # physics that won't read: the model as modelled
            pass
    return out


def _layers(m, textures: dict[int, int], combo: int, tcombo: int, wcombo: int, count: int) -> list[dict]:
    """A batch's texture layers after the first (a scrolling glow, an environment map): each one's
    texture, texture animation and weight, in their slots (a layer we can't resolve has texture 0)."""
    out = []
    for k in range(1, min(count, 4)):
        if combo + k >= len(m.texture_combos):
            break
        ti = m.texture_combos[combo + k]
        tex = m.textures[ti] if ti < len(m.textures) else {"type": 0, "flags": 0}
        fd = (m.texture_file_ids[ti] if ti < len(m.texture_file_ids) else 0) if tex["type"] == 0 else textures.get(tex["type"], 0)
        out.append({"texture": fd, "type": tex["type"], "uvanim": _lookup(m.texture_transform_combos, tcombo + k),
                    "weight": _lookup(m.texture_weight_combos, wcombo + k),
                    "wrap": [bool(tex["flags"] & 1), bool(tex["flags"] & 2)]})
    return out


def _lookup(table: list[int], index: int) -> int:
    """An M2 lookup table entry, -1 for none (an index past it, or 0xFFFF)."""
    if index >= len(table):
        return -1
    v = table[index]
    return -1 if v in (0xFFFF, -1) else v
