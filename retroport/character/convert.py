"""`retroport character`: port one BfA (8.x) playable race/sex to 3.3.5a.

Output (under ``out_dir``, laid out like the MPQ):

* ``Character\\<Race>\\<Sex>\\<Race><Sex>.m2`` + skins + anims - converted by wotlkconv
  straight from the install, fixed up, and UV-remapped to the 3.3.5 layout;
* every CharSections texture the race/sex uses, converted to the 3.3.5 layout and
  written palettized (facial hair and scalp overlays with 8-bit alpha, never DXT);
* ``DBFilesClient\\CharSections.dbc``, ``CharHairGeosets.dbc``,
  ``CharacterFacialHairStyles.dbc`` - the template DBCs with rows for ``race_id``
  appended (when a template folder is given).

BfA CharSections slots (per wowdev / the BfA tables) and what each becomes:
  0 skin:        [skin composite, extra composite, -]
  1 face:        [FaceLower, FaceUpper, -]               (layout 2: one texture, whole face)
  2 facial hair: [FacialLowerHair, FacialUpperHair, -]
  3 hair:        [hair texture, ScalpLowerHair, ScalpUpperHair]
  4 underwear:   [NakedPelvisSkin, NakedTorsoSkin, -]
"""

from __future__ import annotations

import os
import re
import shutil
import struct
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel

from ..check import analyze_skin, check_model
from ..convert import engine, fixup, skeleton
from ..convert.texbake import resolve_fdids
from ..dbc import DBCError, DBCFile, _refuse_overwrite
from ..formats import blp
from ..listfile import Listfile
from ..safeio import write_verified
from . import layouts as L
from . import retail as retail_tables
from .extras import ExtrasError, split_extra_region
from .model import remap_model_uvs
from .textures import convert_composite, convert_region, extra_texture, group_for

SEX_NAMES = {0: "Male", 1: "Female"}
FACE, LOWER, UPPER = (9, 10), 10, 9
# (BaseSection, slot) -> the layout section a region texture covers
REGION_SLOTS = {(1, 0): LOWER, (1, 1): UPPER, (2, 0): LOWER, (2, 1): UPPER,
                (3, 1): LOWER, (3, 2): UPPER, (4, 0): 5, (4, 1): 3}
# (BaseSection, destination section) -> 3.3.5 slot, and the file-name part
OUT_SLOTS = {(1, LOWER): (0, "FaceLower"), (1, UPPER): (1, "FaceUpper"),
             (2, LOWER): (0, "FacialLowerHair"), (2, UPPER): (1, "FacialUpperHair"),
             (3, LOWER): (1, "ScalpLowerHair"), (3, UPPER): (2, "ScalpUpperHair"),
             (4, 5): (0, "NakedPelvisSkin"), (4, 3): (1, "NakedTorsoSkin")}
DB2_TABLES = ("ChrRaces", "CharComponentTextureLayouts", "CharComponentTextureSections",
              "CharSections", "TextureFileData", "CharHairGeosets", "CharacterFacialHairStyles")
CHARSECTIONS_FIELDS, HAIR_FIELDS, FACIAL_FIELDS = 10, 6, 8
# CharacterFacialHairStyles.Geoset[i] drives geoset group FACIAL_SLOT_GROUPS[i] (from 3.3.5's own
# rows: Human female piercings are slot 1 -> 3xx, Blood Elf eyes are slot 4 -> 17xx).
FACIAL_SLOT_GROUPS = (1, 3, 2, 16, 17)
# 3.3.5 (CCharacterComponent::GeosRenderPrep, 0x4ED900) hides geosets 0-2000, then shows the one
# value it keeps per group 0-18 - the belt group like BfA: 1801 + the waist item's
# ItemDisplayInfo.GeosetGroup[0], so a Kul Tiran shows its band (1802) or sash (1803) only under
# belts that ask for one. Group 19 never shows; ids above 2000 (BfA's 20 feet, 22 torso) are never
# hidden, so every variant of those draws at once.
MANAGED_GEOSET_GROUPS = 19
# A piece fills a hole in the body when (nearly) all of its open edges meet open edges of the
# body. A belt band welded to the body along one side (Kul Tiran 1802) meets half of them.
HOLE_FILL_RATIO = 0.75


def unmanaged_geoset_remap(geosets: set[int], fills: dict[int, float] | None = None) -> dict[int, int | None]:
    """Groups 3.3.5 never switches (BfA's 20 feet, 22 torso, ...) would draw every variant at once
    (or, group 19, none). Keep one variant per group as always-on body (0): the one that fills a
    hole in the default body (``fills``, from hole_fill_ratios) - the default xx01 when several do
    (2001 feet over the 2002 alternative) - and hide the rest; a group none of whose pieces fills
    a hole is hidden whole. ``fills`` None means "unknown": then xx01 (or the lowest) is kept."""
    groups: dict[int, list[int]] = {}
    for g in geosets:
        if g // 100 >= MANAGED_GEOSET_GROUPS:
            groups.setdefault(g // 100, []).append(g)
    out: dict[int, int | None] = {}
    for grp, ids in groups.items():
        ids.sort()
        default = grp * 100 + 1
        if fills is None:
            keep = default if default in ids else ids[0]
        else:
            filling = [i for i in ids if fills.get(i, 0.0) >= HOLE_FILL_RATIO]
            keep = default if default in filling else max(filling, key=lambda i: (fills[i], -i), default=None)
        out.update({i: (0 if i == keep else None) for i in ids})
    return out


def hole_fill_ratios(m2_path: str, skin_path: str, candidates: set[int]) -> dict[int, float]:
    """For each candidate piece, the share of its open edges that close an open edge of the default
    body: geoset 0 plus each switched group's default piece (401 hands, 501 lower legs, 1301 legs,
    ...). 1.0 is a piece that fills a hole exactly (Kul Tiran 2001 feet, 2201 torso); a piece
    laid on the body meets few or none (a belt band, 0.5), and a closed one (a sash) has no open
    edges at all (0)."""
    with open(m2_path, "rb") as fh:
        m2 = fh.read()
    with open(skin_path, "rb") as fh:
        skin = fh.read()
    n_v, v_off = struct.unpack_from("<II", m2, 0x3C)
    n_l, l_off = struct.unpack_from("<II", skin, 0x04)
    n_t, t_off = struct.unpack_from("<II", skin, 0x0C)
    n_s, s_off = struct.unpack_from("<II", skin, 0x1C)
    lookup = struct.unpack_from(f"<{n_l}H", skin, l_off)
    tris = struct.unpack_from(f"<{n_t}H", skin, t_off)

    def point(k: int):
        v = lookup[tris[k]]
        x, y, z = struct.unpack_from("<3f", m2, v_off + v * 48) if v < n_v else (0.0, 0.0, 0.0)
        return round(x, 4), round(y, 4), round(z, 4)

    # edge (by position: pieces carry their own copies of shared vertices) -> triangles using it
    edges: dict[int, dict[frozenset, int]] = {}
    for i in range(n_s):
        sid, level, _vs, _vc, start, count = struct.unpack_from("<HHHHHH", skin, s_off + i * 48)
        base_piece = sid == 0 or (sid // 100 < MANAGED_GEOSET_GROUPS and sid % 100 == 1)
        if not base_piece and sid not in candidates:
            continue
        uses = edges.setdefault(0 if base_piece else sid, {})
        first = (level << 16) | start
        for k in range(first, min(first + count, n_t) - 2, 3):
            a, b, c = point(k), point(k + 1), point(k + 2)
            for e in ((a, b), (b, c), (c, a)):
                if e[0] != e[1]:
                    key = frozenset(e)
                    uses[key] = uses.get(key, 0) + 1

    def open_edges(piece: int) -> set[frozenset]:
        return {e for e, n in edges.get(piece, {}).items() if n == 1}

    body = open_edges(0)
    out = {}
    for g in candidates:
        own = open_edges(g)
        out[g] = len(own & body) / len(own) if own else 0.0
    return out


def facial_styles(facial: list[dict], extras: list[dict], eyes_geoset: int | None) -> list[dict]:
    """3.3.5 CharacterFacialHairStyles rows. BfA keeps female piercings/earrings as extra
    CharHairGeosets rows (GeosetType 1-3); 3.3.5 shows them through the facial-style slot, so they
    are folded in by VariationID. ``eyes_geoset`` (e.g. 2 for 1702) switches the eye mesh on in
    every style, the way 3.3.5 does for Blood Elves."""
    real = [r for r in facial if any(g > 0 for g in r["Geoset"])]
    by_var: dict[int, list[int]] = {}
    if real or not extras:
        for r in facial:
            by_var[r["VariationID"]] = [max(g, 0) for g in (list(r["Geoset"]) + [0] * 5)[:5]]
    for r in extras:
        if r["GeosetType"] in FACIAL_SLOT_GROUPS:
            slot = FACIAL_SLOT_GROUPS.index(r["GeosetType"])
            by_var.setdefault(r["VariationID"], [0] * 5)[slot] = max(r["GeosetID"], 0)
    if eyes_geoset is not None:
        by_var.setdefault(0, [0] * 5)
        for geo in by_var.values():
            if not geo[4]:
                geo[4] = eyes_geoset
    return [{"VariationID": v, "Geoset": geo} for v, geo in sorted(by_var.items())]


class CharacterResult(BaseModel):
    race: str
    sex: str
    race_id: int
    model: str = ""
    files: list[str] = []
    textures: int = 0
    rows: dict[str, int] = {}
    uv: dict = {}
    # the skin BfA paints outside its layout's sections (extras.py): the corner the skin rows'
    # extra textures are cut from ({x, y, w, h} in source-layout pixels), and what was split off
    extra: dict = {}
    warnings: list[str] = []
    check: list[str] = []
    # the race-independent customization data, for writing rows under any race id
    sections: list[dict] = []
    hair: list[dict] = []
    facial: list[dict] = []
    # a retail source's barber shop names: {"hair": {variation: name}, "facial": {variation: name}}
    # (BfA's come from its BarberShopStyle table)
    names: dict[str, dict[int, str]] = {}
    source: str = "bfa"                    # "bfa" or "retail"


@dataclass
class _Row:
    section: int
    variation: int
    color: int
    flags: int
    textures: list[str] = field(default_factory=lambda: ["", "", ""])


def _find_listfile_paths(listfile: str, paths: set[str]) -> dict[str, int]:
    """Stream the listfile once for exact (case-insensitive) paths -> FileDataID."""
    want = {p.lower().replace("\\", "/") for p in paths}
    found: dict[str, int] = {}
    with open(listfile, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parsed = Listfile._split(line)
            if parsed:
                key = parsed[1].lower().replace("\\", "/")
                if key in want:
                    found[key] = parsed[0]
    return found


def _listfile_names(listfile: str, fdids: set[int]) -> dict[int, str]:
    """Stream the listfile once for FileDataID -> path (backslashes)."""
    found: dict[int, str] = {}
    with open(listfile, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parsed = Listfile._split(line)
            if parsed and parsed[0] in fdids:
                found[parsed[0]] = parsed[1]
    return found


class BfaInstall:
    """Read access to a local install: files by FileDataID and DB2 tables by name. A BfA (8.x)
    install, or a retail one (9.0+, ``retail``: its customization is read through retail.py;
    ``product`` picks it in a .build.info that lists several, e.g. "wow")."""

    def __init__(self, install_dir: str, dbd_dir: str, listfile: str, product: str | None = None):
        from wotlkconv.casc import CascStorage
        from wotlkconv.db.dbd import DbdIndex
        from wotlkconv.errors import ConverterError
        try:
            self.casc = CascStorage.open(install_dir, product=product)
        except ConverterError as e:
            raise ValueError(f"{install_dir}: {e}") from e
        self.defs = DbdIndex(dbd_dir)
        if not self.defs:
            raise ValueError(f"no .dbd definitions in {dbd_dir} (point at WoWDBDefs\\definitions)")
        self.listfile = listfile
        self.retail = install_major(self.casc.build.version) >= 9
        self._tables: dict[str, list[tuple[int, dict]]] = {}
        names = DB2_TABLES + (retail_tables.DB2_TABLES if self.retail else ())
        self.fdids = _find_listfile_paths(listfile, {f"dbfilesclient/{t.lower()}.db2" for t in names})

    def read(self, fdid: int) -> bytes:
        return self.casc.read_file_id(fdid)

    def table(self, name: str) -> list[tuple[int, dict]]:
        from wotlkconv.db.db2 import parse_db2
        from wotlkconv.errors import ConverterError
        if name not in self._tables:
            fdid = self.fdids.get(f"dbfilesclient/{name.lower()}.db2")
            if fdid is None:
                raise ValueError(f"{name}.db2 is not in the listfile")
            try:
                data = self.casc.read_file_id(fdid, zero_encrypted=True)
                self._tables[name] = list(parse_db2(data, name, definitions=self.defs, table_name=name))
            except ConverterError as e:             # a table this build no longer has (retail's CharSections)
                raise ValueError(f"{name}.db2: {e}") from e
        return self._tables[name]


def install_major(version: str) -> int:
    """The expansion number of a .build.info version ("8.3.7.35662" -> 8); 0 when unknown."""
    head = str(version or "").split(".")[0]
    return int(head) if head.isdigit() else 0


def _find_race(install: BfaInstall, race: str) -> tuple[int, dict]:
    want = race.lower().replace(" ", "").replace("'", "")
    for rid, row in install.table("ChrRaces"):
        names = {str(row.get("ClientFileString", "")).lower(), str(row.get("Name_lang", "")).lower().replace(" ", "").replace("'", "")}
        if want in names:
            return rid, row
    raise ValueError(f"race '{race}' not found in ChrRaces (use the ClientFileString, e.g. KulTiran)")


def convert_character(install_dir: str, race: str, sex: str, out_dir: str, *, race_id: int = 33,
                      listfile: str, dbd_dir: str, dbc_dir: str | None = None, target: str = "hd",
                      product: str | None = None,
                      on_log: Callable[[str], None] | None = None) -> CharacterResult:
    """``install_dir`` is a BfA install, or a retail one (``product`` "wow"): its ChrModel and
    customization are projected onto CharSections & co. by retail.py, and its type-19 eye texture
    is baked into the eyeballs."""
    log = on_log or (lambda m: None)
    sex_id = {"male": 0, "female": 1}.get(sex.lower())
    if sex_id is None:
        raise ValueError("sex must be male or female")
    if target not in L.TARGETS:
        raise ValueError("target must be 'hd' or 'classic'")
    if not engine.available():
        raise ValueError(engine.INSTALL_HINT)
    if dbc_dir:
        _refuse_overwrite(dbc_dir, os.path.join(out_dir, "DBFilesClient"))

    log(f"Opening {install_dir} ...")
    bfa = BfaInstall(install_dir, dbd_dir, listfile, product=product)
    bfa_race_id, race_row = _find_race(bfa, race)
    cfs = race_row["ClientFileString"]
    sex_name = SEX_NAMES[sex_id]
    res = CharacterResult(race=cfs, sex=sex_name, race_id=race_id, source="retail" if bfa.retail else "bfa")
    rc = retail_tables.read_character(bfa.table, bfa_race_id, sex_id, cfs) if bfa.retail else None
    layout_id = rc.layout_id if rc else race_row["CharComponentTextureLayoutID"]
    log(f"Race {cfs} ({'retail' if rc else 'BfA'} id {bfa_race_id}), {sex_name} -> 3.3.5 race id {race_id}, "
        f"{target} layout" + (f"; ChrModel {rc.chr_model}" if rc else ""))

    # --- layouts ---
    layouts = {i: r for i, r in bfa.table("CharComponentTextureLayouts")}
    sections = [r for _i, r in bfa.table("CharComponentTextureSections")]
    src = L.layout_from_tables(layouts, sections, layout_id)
    dst = L.TARGETS[target]
    groups = L.build_groups(src, dst)
    identity = L.is_identity(src, dst)
    log(f"  source layout {layout_id} ({src.width}x{src.height}) -> "
        f"{dst.width}x{dst.height}" + (" (same shape: no UV remap)" if identity else ""))

    # --- model ---
    char_dir = os.path.join(out_dir, "Character", cfs, sex_name)
    stem = f"{cfs}{sex_name}"
    if rc:
        names = _listfile_names(listfile, {rc.model_fdid})
        model_path = names.get(rc.model_fdid, f"FileDataID {rc.model_fdid}")
        model_fdid = rc.model_fdid
    else:
        model_path = f"character/{cfs.lower()}/{sex_name.lower()}/{cfs.lower()}{sex_name.lower()}.m2"
        found = _find_listfile_paths(listfile, {model_path})
        if model_path not in found:
            raise ValueError(f"{model_path} is not in the listfile")
        model_fdid = found[model_path]
    work = os.path.join(out_dir, "_work")
    os.makedirs(work, exist_ok=True)
    src_model = os.path.join(work, f"{stem}.m2")
    write_verified(src_model, bfa.read(model_fdid))
    log(f"Converting {model_path} (wotlkconv, from the install)"
        + (f" - retail's {rc.model_note} body" if rc and rc.model_note else "") + "...")
    # a reshaped retail body (the upright orc male) inherits most sequences from its display
    # model's skeleton; that model's events give them their footstep, swing and hit cues
    donor = bfa.read(rc.display_fdid) if rc and rc.display_fdid and rc.display_fdid != rc.model_fdid else None
    with skeleton.event_donor(donor):
        er = engine.convert_with_wotlkconv(src_model, char_dir, output_stem=stem, listfile_path=listfile,
                                           casc=bfa.casc, on_log=log)
    for n in er.notes:
        if n.level != "info":
            log(f"  [{n.level}] {n.code}: {n.message}")
    if not er.ok:
        raise ValueError(f"model conversion failed: {er.error}")
    res.model = er.output
    res.files += er.written
    skins = sorted(p for p in er.written if p.lower().endswith(".skin"))

    tfd: dict[int, list[tuple[int, int]]] = {}
    for fid, r in bfa.table("TextureFileData"):
        tfd.setdefault(r["MaterialResourcesID"], []).append((r.get("UsageType", 0), r.get("FileDataID", fid)))

    def fdid_of(mat: int) -> int | None:
        files = sorted(tfd.get(mat, []))
        return files[0][1] if files else None

    if rc:
        res.files += _bake_eyes(src_model, er.output, fdid_of(rc.eye_material) if rc.eye_material else None,
                                f"Character\\{cfs}\\{sex_name}\\{stem}Eyes.blp", out_dir, bfa, work, res, log)
    fixup.clear_stale_anim_flags(er.output)
    # every submesh is kept: the client's own HD models (patch-E) draw up to 96 (GoblinFemale), and
    # clamping a Pandaren's 86 to 64 dropped its torso, legs, eyes and belts
    fixup.clear_combiner_combos(er.output, skins)
    stripped = fixup.strip_unfilled_texture_layers(er.output, skins)
    if stripped:
        log(f"  cloak: dropped the empty emblem layer from {stripped} batch(es) (3.3.5 has no guild-emblem texture)")
    all_geosets = set(analyze_skin(skins[0]).geosets) if skins else set()
    if rc:
        # retail's defaults for what 3.3.5 can't switch, its features moved into facial groups
        retail_tables.plan_geosets(rc, all_geosets)
        remap = {g: v for g, v in rc.geosets.items() if g in all_geosets}
    else:
        unmanaged = {g for g in all_geosets if g // 100 >= MANAGED_GEOSET_GROUPS}
        remap = unmanaged_geoset_remap(all_geosets, hole_fill_ratios(er.output, skins[0], unmanaged)) \
            if unmanaged else {}
    if remap:
        fixup.remap_geosets(skins, remap)
        log("  geosets 3.3.5 does not switch: " + ", ".join(
            f"{g}->{'body' if v == 0 else 'hidden' if v is None else v}" for g, v in sorted(remap.items())))
    for rep in fixup.order_skin_indices(skins):
        if rep["indices"] > fixup.SKIN_U16:
            log(f"  {rep['skin']}: {rep['indices']} indices, " + (
                f"switchable geosets ({rep['switchable']}) laid out first" if rep["reordered"]
                else "left as it is (its submeshes share or skip index ranges)"))
        if rep["past_line"] and rep["skin"].endswith("00.skin"):
            res.warnings.append(
                f"{rep['skin']}: switchable geosets {rep['past_line']} start past index 65,535, where the stock "
                "client can never hide them (every cape, eye glow, belt and robe piece at once) - install "
                "the WarcraftXL extension wxl-wide-skin-geosets (retroport-tool\\native)")
    filled = fixup.fill_bone_influences(er.output, skins)
    if filled:
        log(f"  {filled} skin section(s) given the bone influences their vertices weigh (BfA leaves them 0)")
    res.files += _extract_fixed_textures(er.output, out_dir, bfa, listfile, work, log)

    rows = rc.sections if rc else [
        r for _i, r in bfa.table("CharSections")
        if r["RaceID"] == bfa_race_id and r["SexID"] == sex_id and r["BaseSection"] in (0, 1, 2, 3, 4)]
    region = None
    if not identity:
        # a Pandaren's hair draws its skin row's extra texture, which is each colour's hair texture
        extras = {fdid_of(r["MaterialResourcesID"][1]) for r in rows if r["BaseSection"] == 0} - {None}
        hair_tex = {fdid_of(r["MaterialResourcesID"][0]) for r in rows if r["BaseSection"] == 3} - {None}
        try:
            region = split_extra_region(er.output, skins, src, groups, hair_ok=extras <= hair_tex)
        except ExtrasError as e:
            res.warnings.append(f"skin outside the layout's sections left on the body texture: {e}")
        if region and region.found:
            r = region.rect
            res.extra = {"x": r.x, "y": r.y, "w": r.w, "h": r.h, "vertices": region.vertices,
                         "triangles": region.triangles, "submeshes": region.submeshes, "hair_slots": region.hair_slots}
            log(f"  skin outside the layout's sections ({region.vertices} vertices, {region.triangles} triangles: "
                f"toes, pads, tail...): own submeshes ({region.submeshes}) on the skin rows' extra texture, cut from "
                f"({r.x}, {r.y}) {r.w}x{r.h}" + (f"; hair texture slots {region.hair_slots} drawn as hair"
                                                 if region.hair_slots else ""))
            if region.skipped:
                res.warnings.append(f"{region.skipped} triangle(s) outside the layout's sections share vertices "
                                    "with the body and stay on the body texture")
        else:
            region = None

    if not identity:
        rep = remap_model_uvs(er.output, skins, src, dst, groups)
        res.uv = rep.__dict__
        log(f"  UV remap: {rep.remapped} skin vertices moved {rep.per_group}; unchanged: "
            f"{rep.outside} outside any section, {rep.shared} shared with other textures; "
            f"{rep.straddling} triangle(s) straddle two regions")
        if rep.straddling or rep.shared:
            res.warnings.append(f"UV remap: {rep.straddling} straddling triangle(s), {rep.shared} shared vertices")
        if rep.outside:
            res.warnings.append(f"UV remap: {rep.outside} skin vertices outside every section (left as-is)")

    # --- textures ---
    log(f"Converting textures for {len(rows)} CharSections row(s)...")
    out_rows, cache = [], {}
    images: dict[int, object] = {}

    def image(fdid: int):
        if fdid not in images:
            p = os.path.join(work, f"{fdid}.blp")
            write_verified(p, bfa.read(fdid))
            images[fdid] = blp.decode(p)
        return images[fdid]

    def write_blp(name: str, img) -> str:
        # Every texture lives in the sex folder under a sex-prefixed name: BfA's male and
        # female hair/scalp textures differ, so race-level names like Hair01_00 would collide.
        rel = "\\".join(["Character", cfs, sex_name, f"{stem}{name}.blp"])
        out = os.path.join(out_dir, *rel.split("\\"))
        if out not in cache:
            data = blp.encode_palettized(img)
            write_verified(out, data, lambda p: blp.verify_blp(p, img.size))
            cache[out] = True
            res.files.append(out)
        return rel

    for r in rows:
        sec, var, col = r["BaseSection"], r["VariationIndex"], r["ColorIndex"]
        mats = list(r["MaterialResourcesID"]) + [0, 0, 0]
        row = _Row(sec, var, col, r["Flags"] & 0x1F)
        tag = f"{var:02d}_{col:02d}"
        if sec == 0:
            skin_fd = fdid_of(mats[0]) if mats[0] else None
            for slot, suffix in ((0, ""), (1, "_Extra")):
                fd = fdid_of(mats[slot]) if mats[slot] else None
                if slot == 1 and region is not None:
                    # the extra texture is the skin's corner outside the layout (extras.py)
                    if skin_fd:
                        row.textures[1] = write_blp(f"Skin{tag}{suffix}", extra_texture(image(skin_fd), src, region.rect))
                    continue
                if not fd:
                    continue
                img = image(fd)
                if identity:
                    img = img.resize((dst.width, dst.height), blp.Image.Resampling.LANCZOS)
                elif img.width * src.height == img.height * src.width:
                    img = convert_composite(img, src, dst, groups)
                # else: a texture of its own (not the layout's shape), drawn as it is
                row.textures[slot] = write_blp(f"Skin{tag}{suffix}", img)
        else:
            if sec == 3 and mats[0]:
                fd = fdid_of(mats[0])
                if fd:
                    row.textures[0] = write_blp(f"Hair{tag}", image(fd))
            by_group: dict = {}
            for slot in range(3):
                target_sec = REGION_SLOTS.get((sec, slot))
                fd = fdid_of(mats[slot]) if mats[slot] and target_sec is not None else None
                if fd:
                    g = group_for(target_sec, groups)
                    if g is None:
                        res.warnings.append(f"section {sec} slot {slot}: no 3.3.5 region for layout section {target_sec}")
                        continue
                    by_group.setdefault(g, []).append((target_sec, image(fd)))
            for g, layers in by_group.items():
                layers.sort(key=lambda t: 0 if t[0] == LOWER else 1)        # lower first, upper on top
                parts = convert_region([img for _s, img in layers], g, dst)
                for dsec, img in parts.items():
                    out_slot = OUT_SLOTS.get((sec, dsec))
                    if out_slot:
                        slot, part = out_slot
                        row.textures[slot] = write_blp(f"{part}{tag}", img)
        out_rows.append(row)
    # 3.3.5 colours hair-textured meshes (beard, brows) from the hair row's texture; BfA leaves
    # bald rows without one, so borrow the same colour from another style
    by_color = {r.color: r.textures[0] for r in out_rows if r.section == 3 and r.textures[0]}
    for r in out_rows:
        if r.section == 3 and not r.textures[0] and r.color in by_color:
            r.textures[0] = by_color[r.color]
    res.textures = len(cache)
    log(f"  wrote {res.textures} texture(s)")

    # --- geosets ---
    if rc:
        hair, extras, facial = list(rc.hair), [], []
    else:
        hair_rows = [r for _i, r in bfa.table("CharHairGeosets")
                     if r["RaceID"] == bfa_race_id and r["SexID"] == sex_id]
        hair = [r for r in hair_rows if r.get("GeosetType", 0) == 0]          # the hair itself
        extras = [r for r in hair_rows if r.get("GeosetType", 0) in FACIAL_SLOT_GROUPS]
        skipped = [r for r in hair if r.get("CustomGeoFileDataID") or r.get("HdCustomGeoFileDataID")]
        hair = [r for r in hair if r not in skipped]
        if skipped:
            res.warnings.append(f"{len(skipped)} hair style(s) use separate custom-geometry files; not ported")
        facial = [r for _i, r in bfa.table("CharacterFacialHairStyles")
                  if r["RaceID"] == bfa_race_id and r["SexID"] == sex_id]
    model_geosets = set(analyze_skin(skins[0]).geosets) if skins else set()
    missing = sorted({r["GeosetID"] for r in hair if r["GeosetID"] > 0 and r["GeosetID"] not in model_geosets})
    if missing:
        res.warnings.append(f"hair geosets {missing} are referenced but not in the model")
    res.sections = [{"section": r.section, "variation": r.variation, "color": r.color, "flags": r.flags,
                     "textures": list(r.textures)} for r in out_rows]
    # BfA sets Showscalp on haired styles too ("draw the scalp under the hair"); in 3.3.5 it
    # means bald, which hides the hair - so only the bald style (geoset 0) keeps it
    res.hair = [{"VariationID": r["VariationID"], "GeosetID": r["GeosetID"], "Showscalp": int(r["GeosetID"] == 0)}
                for r in hair]
    if rc:
        # retail's features rows are 3.3.5's already (retail.py), its eyeballs part of the body
        res.facial = [{"VariationID": r["VariationID"], "Geoset": list(r["Geoset"])} for r in rc.facial]
        res.names = rc.names
        res.warnings += [f"customization: {n}" for n in rc.notes]
    else:
        eyes = 2 if 1702 in model_geosets and 1701 not in model_geosets else None
        res.facial = facial_styles([{"VariationID": r["VariationID"], "Geoset": list(r["Geoset"])} for r in facial],
                                   extras, eyes)

    # --- DBCs ---
    if dbc_dir:
        res.rows = _write_dbcs(dbc_dir, os.path.join(out_dir, "DBFilesClient"), race_id, sex_id,
                               out_rows, res.hair, res.facial)
        res.files += [os.path.join(out_dir, "DBFilesClient", n) for n in
                      ("CharSections.dbc", "CharHairGeosets.dbc", "CharacterFacialHairStyles.dbc")]
        log(f"  DBC rows added: {res.rows}")

    chk = check_model(er.output)
    res.check = [f"{f.severity.value} {f.check}: {f.detail}" for f in chk.report().findings
                 if f.severity.value != "pass"]
    shutil.rmtree(work, ignore_errors=True)        # source extracts; nothing to pack
    return res


FIXED_FDID = re.compile(r"_(\d+)\.blp$", re.I)


def _extract_fixed_textures(m2_path: str, out_dir: str, bfa: BfaInstall, listfile: str, work: str,
                            log: Callable[[str], None]) -> list[str]:
    """The model's fixed (type 0) textures - eye glow, jewelry - copied from the install.
    The engine names them (``<model>_<FileDataID>.blp`` or their listfile path) but doesn't
    write them; a missing one renders green."""
    with open(m2_path, "rb") as fh:
        m2 = fh.read()
    n, off = struct.unpack_from("<II", m2, 0x50)
    names = []
    for i in range(n):
        typ, _flags, ln, lo = struct.unpack_from("<IIII", m2, off + i * 16)
        if typ == 0 and ln > 1:
            names.append(m2[lo:lo + ln].split(b"\x00")[0].decode("latin-1"))
    by_path = _find_listfile_paths(listfile, {nm for nm in names if not FIXED_FDID.search(nm)})
    written = []
    for nm in names:
        dst = os.path.join(out_dir, *nm.replace("/", "\\").split("\\"))
        if os.path.isfile(dst):
            continue
        m = FIXED_FDID.search(nm)
        fdid = int(m.group(1)) if m else by_path.get(nm.lower().replace("\\", "/"))
        if not fdid:
            log(f"  [warn] fixed texture {nm}: not in the listfile, left missing")
            continue
        tmp = os.path.join(work, f"fixed_{fdid}.blp")
        write_verified(tmp, bfa.read(fdid), lambda p: blp.decode(p))
        with open(tmp, "rb") as fh:
            written.append(write_verified(dst, fh.read()))
    if written:
        log(f"  extracted {len(written)} fixed texture(s) (eye glow, jewelry)")
    return written


RETAIL_EYES = 19                 # retail's eye texture type (Shadowlands+); 3.3.5 knows 0-15


def _source_texture_types(model: bytes) -> list[int]:
    """The texture types of a source model (MD21-chunked or plain MD20)."""
    if model[:4] == b"MD21":
        size = struct.unpack_from("<I", model, 4)[0]
        model = model[8:8 + size]
    n, off = struct.unpack_from("<II", model, 0x50)
    return [struct.unpack_from("<I", model, off + i * 16)[0] for i in range(n)]


def _bake_eyes(src_model: str, m2_path: str, fdid: int | None, rel: str, out_dir: str, bfa: BfaInstall,
               work: str, res: CharacterResult, log: Callable[[str], None]) -> list[str]:
    """Retail draws the eyeballs with an eye-colour texture (type 19) 3.3.5 has no slot for;
    the conversion leaves those slots empty (green eyes). Each becomes a fixed texture: retail's
    default eye colour (``fdid``), written to ``rel``."""
    from ..convert.texbake import bake_file
    from ..formats.md20 import read_texture_slots
    with open(src_model, "rb") as fh:
        types = _source_texture_types(fh.read())
    with open(m2_path, "rb") as fh:
        slots = read_texture_slots(fh.read())
    eyes = [s.index for s in slots if s.index < len(types) and types[s.index] == RETAIL_EYES and not s.name]
    if not eyes:
        return []
    if not fdid:
        res.warnings.append(f"eyes: no default eye colour texture; texture slot(s) {eyes} stay empty")
        return []
    tmp = os.path.join(work, f"eyes_{fdid}.blp")
    write_verified(tmp, bfa.read(fdid), lambda p: blp.decode(p))
    with open(tmp, "rb") as fh:
        written = write_verified(os.path.join(out_dir, *rel.split("\\")), fh.read())
    bake_file(m2_path, {i: rel for i in eyes})
    log(f"  eyes: retail's default eye colour baked into texture slot(s) {eyes} ({rel})")
    return [written]


def _write_dbcs(dbc_dir: str, out_dir: str, race_id: int, sex_id: int, rows: list[_Row],
                hair: list[dict], facial: list[dict]) -> dict[str, int]:
    def load(name: str, fields: int) -> DBCFile:
        path = os.path.join(dbc_dir, name)
        if not os.path.isfile(path):
            raise DBCError(f"{name} not found in {dbc_dir}")
        d = DBCFile.load(path)
        if d.field_count != fields:
            raise DBCError(f"{name}: expected {fields} fields (3.3.5a), found {d.field_count}")
        return d

    cs, hg, fh = (load("CharSections.dbc", CHARSECTIONS_FIELDS), load("CharHairGeosets.dbc", HAIR_FIELDS),
                  load("CharacterFacialHairStyles.dbc", FACIAL_FIELDS))
    sections = [r if isinstance(r, dict) else {"section": r.section, "variation": r.variation, "color": r.color,
                                               "flags": r.flags, "textures": r.textures} for r in rows]
    counts = append_customization(cs, hg, fh, race_id, sex_id, sections, hair, facial)
    os.makedirs(out_dir, exist_ok=True)
    cs.save(os.path.join(out_dir, "CharSections.dbc"))
    hg.save(os.path.join(out_dir, "CharHairGeosets.dbc"))
    fh.save(os.path.join(out_dir, "CharacterFacialHairStyles.dbc"))
    return counts


def charsections_layout_problems(cs: DBCFile, races: set[int] | None = None) -> list[str]:
    """Rows that break the layout the client's customization cache needs (decoded from Wow.exe's
    builder): each (race, sex, section) must be ONE contiguous run, or the builder writes past an
    array it sized from a later run. Blizzard's tables always satisfy this (their variation and
    colour order inside a run varies, and the client tolerates that). ``races`` limits the check."""
    problems: list[str] = []
    seen: set = set()
    last = None
    for i, r in enumerate(cs.records):
        section = (r[1], r[2], r[3])
        if races is not None and r[1] not in races:
            last = None
            continue
        if section != last:
            if section in seen:
                problems.append(f"row {i}: race {section[0]} sex {section[1]} section {section[2]} "
                                "appears in more than one run")
            seen.add(section)
        last = section
    return problems


def facial_feature_sections(sections: list[dict], facial: list[dict]) -> list[dict]:
    """``sections`` plus facial-hair texture rows (section 2) for every facial style that has none.

    3.3.5 counts a race's "features" from its section-2 rows whenever it has any
    (CCharacterComponent::GetNumFacialFeaturesForHairColor, 0x4E7DF0), and from its
    CharacterFacialHairStyles rows only when it has none. BfA's Kul Tiran female has one section-2
    variation (her eyebrow texture) and 7 piercing styles, so only the first could be picked; each
    missing style gets the first variation's textures, colour by colour."""
    face_hair = [r for r in sections if r["section"] == 2]
    have = {r["variation"] for r in face_hair}
    if not face_hair:
        return list(sections)
    base = min(have)
    added = [dict(r, variation=v) for v in sorted({f["VariationID"] for f in facial} - have)
             for r in face_hair if r["variation"] == base]
    return list(sections) + added


def append_customization(cs: DBCFile, hg: DBCFile, fh: DBCFile, race_id: int, sex_id: int,
                         sections: list[dict], hair: list[dict], facial: list[dict]) -> dict[str, int]:
    """Append one race/sex's CharSections, CharHairGeosets and CharacterFacialHairStyles rows."""
    if any(r[1] == race_id and r[2] == sex_id for r in cs.records):
        raise DBCError(f"CharSections already has rows for race {race_id} sex {sex_id}; "
                       "use another --race-id or start from a template without them")
    # The client builds its customization cache in one pass that requires every (race, sex,
    # section) to be ONE contiguous run sorted by variation then colour: it sizes a section's
    # variation array from the run it just saw and later writes into it without a bounds check.
    # BfA's row order interleaves sections, which corrupted the heap (crash on exit in
    # CCharacterComponent::Destroy). Blizzard's own tables are ordered this way.
    sections = sorted(facial_feature_sections(sections, facial),
                      key=lambda r: (r["section"], r["variation"], r["color"]))
    hair = sorted(hair, key=lambda r: r["VariationID"])
    facial = sorted(facial, key=lambda r: r["VariationID"])
    next_id = cs.max_id() + 1
    for r in sections:
        cs.add_record([next_id, race_id, sex_id, r["section"], *(cs.add_string(t) for t in r["textures"]),
                       r["flags"], r["variation"], r["color"]])
        next_id += 1
    next_id = hg.max_id() + 1
    for r in hair:
        hg.add_record([next_id, race_id, sex_id, r["VariationID"], r["GeosetID"], r["Showscalp"]])
        next_id += 1
    for r in facial:
        geo = [g if g >= 0 else 0 for g in (list(r["Geoset"]) + [0] * 5)[:5]]
        fh.add_record([race_id, sex_id, r["VariationID"], *geo])
    return {"CharSections": len(sections), "CharHairGeosets": len(hair), "CharacterFacialHairStyles": len(facial)}
