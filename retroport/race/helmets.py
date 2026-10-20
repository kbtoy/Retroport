"""The race's own helmets from BfA, converted for 3.3.5.

A 3.3.5 helmet is one model per race and sex: ItemDisplayInfo names ``<Base>.mdx`` and the client
loads ``Item\\ObjectComponents\\Head\\<Base>_<ClientPrefix><M|F>.m2``, the prefix being the
wearer's race's (ChrRaces). BfA made Kul Tirans their own version of nearly every helmet, each
refitted by hand to their heads - deeper and wider than a Human's, the cheek guards longer, the
back down to the shoulders - and hangs them from the head bone's pivot, tipped 2.8 degrees down.
No one transform of a Human helmet matches them: the best per-axis fits of two helmets differ by
a quarter in height. Human helmets fitted to the cranium (helm.py) left the male's riding high,
with a gap at the back of his neck, next to BfA's own in wow.export (twelfth client test). So a
race BfA gave helmets wears those, under BfA's prefix (``Kt``), and its body keeps BfA's
helmet attachment.

Each helmet the client has for the look template (``<Base>_HuM.m2``) is found in BfA through the
listfile name of any of its race variants, ModelFileData's ModelResourcesID (shared by all the
variants) and ComponentModelFileData (the race and sex of each), and converted with wotlkconv.
The few BfA has no version of for the race (2 of 279 in the WarcraftXL client) get the
template's model carried to where helm.py fits it on the race's head, so no helmet goes missing.
Textures the models name that the client lacks are taken from BfA too.

M2 (12340): 0x1C sequences (0x40: +0x20 box, +0x38 radius), 0x2C bones (0x58: +4 flags, +0x10
translation track, +0x4C pivot), 0x3C vertices (48: +0 position, +20 normal), 0x44 skin count,
0x50 textures (16: +0 type, +8 name), 0xA0 box, 0xB8 radius; 0xE0 collision vertices, 0xF0
attachments, 0x100 events, 0x108 lights, 0x110 cameras, 0x120 ribbons, 0x128 particles. BfA's
character models keep bones and attachments in a ``.skel`` (SKID): SKB1 bones and SKA1
attachments, each an M2Array pair at the chunk's start, offsets from the chunk's data.
"""

from __future__ import annotations

import math
import os
import re
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..convert import engine, fixup
from ..dbc import DBCFile
from ..formats import blp
from ..listfile import Listfile
from ..safeio import write_verified
from . import helm

HEAD = "Item\\ObjectComponents\\Head\\"
SEXES = ("M", "F")
_VARIANT = re.compile(r"^item[\\/]objectcomponents[\\/]head[\\/](?P<base>.+)_(?:[a-z]{2}[mf]|[a-z]{2}_[mf])\.m2$")
_TEXTURE_FILE = 0                        # an M2 texture of type 0 names its file
# skin batches (24 bytes: +0 flags, +2 shader, +4 submesh, +0xA material, +0xC layer, +0xE texture
# count, +0x10/0x12/0x14 texture, coordinate and weight lookup indices); WarcraftXL's helmets drop
# BfA's 0x40 and 0x80 batch flags
BATCH = 24
MODERN_BATCH_FLAGS = 0xC0
# BfA shader-table entries (0x8000 + index) drawn as diffuse and reflection through these combiner
# ops, the diffuse alpha blended over them: Opaque_Mod2xNA_Alpha, its three-texture _Add variant
# (the third dropped) and Opaque_AddAlpha_Alpha; 0x8001 (Opaque_AddAlpha) adds the reflection as a
# layer of its own
ENV_COMBOS = {0x8000: (1, 4), 0x8003: (1, 4), 0x8002: (1, 3)}
SHADER_ADD_LAYER = 0x8001
# in a scene, every Opaque_AddAlpha entry adds its second texture as a layer: 0x8001 and 0x8005 (the
# reflection map, or the diffuse's UVs again), 0x800A and 0x800F (_Wgt: by its texture weight, on the
# first or second UV set) - the Mag'har select scene's bonfire and lamppost glows (0x800A), black
# when 3.3.5 multiplied the glow into the diffuse
SCENE_ADD_LAYERS = {0x8001, 0x8005, 0x800A, 0x800F}
SHADER_TABLE = 0x8000                    # a BfA shader id with this bit indexes retail's shader table;
                                         # one without is its two ops (bits 4-6, then bits 0-2)
COMBINE_MOD = 1
COMBINER_COMBOS = 0x08                   # M2 global flag: batches index texture combiner combos
MATERIAL_NO_DEPTH_WRITE = 0x10
BLEND_ALPHA, BLEND_ADD = 2, 4
Z_SOURCE_NONE = 255.0                    # a particle emitter's z-source BfA writes for "none"
CELL_ZERO_TIMES = (0, 16384, 16384, 32767)  # an empty head-cell track as WarcraftXL fills it: cell 0
_UNSUPPORTED = {0xE0: "collision", 0xF0: "attachments", 0x100: "events", 0x108: "lights",
                0x110: "cameras", 0x120: "ribbons", 0x128: "particles"}


class HelmetsError(ValueError):
    pass


# --------------------------------------------------------------------------- which helmets

def helmet_bases(item_display_info: DBCFile, exists: Callable[[str], bool], template_prefix: str) -> list[str]:
    """The helmet models the client has for the look template: each ItemDisplayInfo model name
    (once, case-insensitively, spelled as first seen) with a ``<Base>_<prefix>M.m2`` or ``F``."""
    seen: dict[str, str] = {}
    for r in item_display_info.records:
        for f in (1, 2):
            name = item_display_info.get_string(r[f])
            if name:
                base = os.path.splitext(name)[0]
                seen.setdefault(base.lower(), base)
    return [base for _low, base in sorted(seen.items())
            if any(exists(f"{HEAD}{base}_{template_prefix}{s}.m2") for s in SEXES)]


def listfile_variants(listfile: str, bases: Iterable[str]) -> dict[str, list[int]]:
    """FileDataIDs of every race variant the listfile names for each base (lower-case keys)."""
    want = {b.lower() for b in bases}
    found: dict[str, list[int]] = defaultdict(list)
    with open(listfile, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "objectcomponents" not in line.lower():
                continue
            parsed = Listfile._split(line)
            if not parsed:
                continue
            m = _VARIANT.match(parsed[1].lower())
            if m and m.group("base") in want:
                found[m.group("base")].append(parsed[0])
    return dict(found)


def race_models(variants: dict[str, list[int]], model_file_data: Iterable[dict],
                component_model_file_data: dict[int, dict], race: int) -> dict[tuple[str, int], int]:
    """(base, sex: 0 male, 1 female) -> the FileDataID of BfA's model of that helmet for ``race``:
    the variants' ModelResourcesID, and of its models the one ComponentModelFileData gives the
    race and sex (a model for every class before a class's own)."""
    resources = {r["FileDataID"]: r["ModelResourcesID"] for r in model_file_data}
    members: dict[int, list[int]] = defaultdict(list)
    for fdid, res in resources.items():
        members[res].append(fdid)
    out: dict[tuple[str, int], int] = {}
    for base, fdids in variants.items():
        picks: dict[int, tuple[int, int]] = {}
        for res in {resources[f] for f in fdids if f in resources}:
            for fdid in members[res]:
                row = component_model_file_data.get(fdid)
                if row is None or row["RaceID"] != race or row["GenderIndex"] not in (0, 1):
                    continue
                rank = (1 if row.get("ClassID", 0) else 0, fdid)
                if row["GenderIndex"] not in picks or rank < picks[row["GenderIndex"]]:
                    picks[row["GenderIndex"]] = rank
        for sex, (_cls, fdid) in picks.items():
            out[(base, sex)] = fdid
    return out


def race_hides(helmet_geoset_data: Iterable[dict], race: int) -> dict[int, set[int]]:
    """HelmetGeosetVisData id -> the geoset groups a helmet with it hides on ``race``, for every
    id BfA's HelmetGeosetData has rows for (an empty set: the race shows everything). The ids
    are 3.3.5's own: for the classic races BfA's rows and 3.3.5's masks agree on 97% of them."""
    out: dict[int, set[int]] = {}
    for r in helmet_geoset_data:
        groups = out.setdefault(r["HelmetGeosetVisDataID"], set())
        if r["RaceID"] == race:
            groups.add(r["HideGeosetGroup"])
    return out


# --------------------------------------------------------------------------- the source's attachment

def chunks(data: bytes) -> dict[str, bytes]:
    """{magic: payload} of a chunked model or skeleton; a plain MD20 model is its own MD21."""
    if data[:4] == b"MD20":
        return {"MD21": data}
    out, at = {}, 0
    while at + 8 <= len(data):
        size = struct.unpack_from("<I", data, at + 4)[0]
        out[data[at:at + 4].decode("latin-1")] = data[at + 8:at + 8 + size]
        at += 8 + size
    return out


def _constant_key(blob: bytes, track: int, size: int) -> bytes | None:
    """The one key a track holds throughout, or None for no track; a key that changes raises."""
    _interp, gseq, _n_ts, _o_ts, n_vals, o_vals = struct.unpack_from("<HhIIII", blob, track)
    if not n_vals:
        return None
    if gseq < 0:
        raise HelmetsError("the source animates its helmet bone per animation")
    n_keys, o_keys = struct.unpack_from("<II", blob, o_vals)
    keys = {blob[o_keys + k * size:o_keys + (k + 1) * size] for k in range(n_keys)}
    if len(keys) != 1:
        raise HelmetsError("the source animates its helmet bone")
    return keys.pop()


def source_attachment(read: Callable[[int], bytes], model_fdid: int) -> helm.Attachment:
    """Attachment 11 and its bone as the source model ships them (from its .skel when it has
    one, following parent skeletons for the chunks it lacks)."""
    model = chunks(read(model_fdid))
    md20 = model["MD21"]
    bones = attachments = None
    if "SKID" in model:
        skel_id, depth = struct.unpack_from("<I", model["SKID"])[0], 0
        while skel_id and depth < 4 and (bones is None or attachments is None):
            skel = chunks(read(skel_id))
            bones = bones if bones is not None else skel.get("SKB1")
            attachments = attachments if attachments is not None else skel.get("SKA1")
            skel_id = struct.unpack_from("<I", skel["SKPD"], 8)[0] if "SKPD" in skel else 0
            depth += 1
    if bones is None:
        bones, b_at = md20, 0x2C
    else:
        b_at = 0
    if attachments is None:
        attachments, a_at = md20, 0xF0
    else:
        a_at = 0
    n_a, o_a, n_l, o_l = struct.unpack_from("<IIII", attachments, a_at)
    index = struct.unpack_from("<h", attachments, o_l + helm.HELM * 2)[0] if n_l > helm.HELM else -1
    if not 0 <= index < n_a or struct.unpack_from("<I", attachments, o_a + index * 0x28)[0] != helm.HELM:
        raise HelmetsError("the source model has no helmet attachment (11)")
    bone = struct.unpack_from("<H", attachments, o_a + index * 0x28 + 4)[0]
    position = struct.unpack_from("<3f", attachments, o_a + index * 0x28 + 8)
    n_b, o_b = struct.unpack_from("<II", bones, b_at)
    if bone >= n_b:
        raise HelmetsError(f"the source's helmet attachment names bone {bone} of {n_b}")
    record = o_b + bone * 0x58
    keys = {f: _constant_key(bones, record + f, size) for f, size in helm.TRACKS.items()}
    return helm.Attachment(bone, position, struct.unpack_from("<I", bones, record + 4)[0], keys)


# --------------------------------------------------------------------------- a template helmet, carried

def _matrix(q: tuple[float, float, float, float]) -> list[list[float]]:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def _transpose(m):
    return [list(r) for r in zip(*m)]


def _inverse(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise HelmetsError("the helmet transform is singular")
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def carry_transform(fit: helm.HelmFit, pivot: tuple[float, float, float], source: helm.Attachment
                    ) -> tuple[list[list[float]], list[float]]:
    """(A, b): a template helmet's point h, moved to A h + b, lands from the source's own
    attachment where the fit puts h. The fit lays it at spot + R_fit S_fit h; the source's bone
    carries a point p of its helmet to pivot + t + R S (P + p - pivot)."""
    t = list(struct.unpack("<3f", source.keys[0x10])) if source.keys.get(0x10) else [0.0, 0.0, 0.0]
    r = _matrix(helm._quaternion(struct.unpack("<4h", source.keys[0x24]))) if source.keys.get(0x24) \
        else [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    s = struct.unpack("<3f", source.keys[0x38]) if source.keys.get(0x38) else (1.0, 1.0, 1.0)
    back = _mul([[1 / s[0], 0, 0], [0, 1 / s[1], 0], [0, 0, 1 / s[2]]], _transpose(r))   # (R S)^-1
    turn = math.radians(fit.turn)
    c, n = math.cos(turn), math.sin(turn)
    fitted = _mul([[c, 0, n], [0, 1, 0], [-n, 0, c]], [[fit.scales[0], 0, 0], [0, fit.scales[1], 0], [0, 0, fit.scales[2]]])
    lifted = _apply(back, [fit.spot[k] - pivot[k] - t[k] for k in range(3)])
    return _mul(back, fitted), [lifted[k] - (source.position[k] - pivot[k]) for k in range(3)]


def carry(m2: bytes, linear: list[list[float]], offset: list[float]) -> bytes:
    """A helmet model with every point p moved to linear p + offset (normals turned to match) and
    its bounds refitted. Refuses models with emitters, attachments or collision, whose positions
    this doesn't carry."""
    if m2[:4] != b"MD20":
        raise HelmetsError("not an MD20 model")
    for at, what in _UNSUPPORTED.items():
        if struct.unpack_from("<I", m2, at)[0]:
            raise HelmetsError(f"the model has {what}")
    out = bytearray(m2)
    normal = _transpose(_inverse(linear))
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    n_v, o_v = struct.unpack_from("<II", m2, 0x3C)
    for i in range(n_v):
        rec = o_v + i * 48
        p = [a + b for a, b in zip(_apply(linear, struct.unpack_from("<3f", m2, rec)), offset)]
        struct.pack_into("<3f", out, rec, *p)
        nv = _apply(normal, struct.unpack_from("<3f", m2, rec + 20))
        length = math.sqrt(sum(v * v for v in nv)) or 1.0
        struct.pack_into("<3f", out, rec + 20, *(v / length for v in nv))
        lo, hi = [min(a, b) for a, b in zip(lo, p)], [max(a, b) for a, b in zip(hi, p)]
    n_b, o_b = struct.unpack_from("<II", m2, 0x2C)
    for i in range(n_b):
        rec = o_b + i * 0x58
        pivot = [a + b for a, b in zip(_apply(linear, struct.unpack_from("<3f", m2, rec + 0x4C)), offset)]
        struct.pack_into("<3f", out, rec + 0x4C, *pivot)
        _interp, _gseq, _n_ts, _o_ts, n_vals, o_vals = struct.unpack_from("<HhIIII", m2, rec + 0x10)
        for k in range(n_vals):
            n_keys, o_keys = struct.unpack_from("<II", m2, o_vals + k * 8)
            for j in range(n_keys):
                at = o_keys + j * 12
                struct.pack_into("<3f", out, at, *_apply(linear, struct.unpack_from("<3f", m2, at)))
    if n_v:
        radius = math.dist(lo, hi) / 2
        struct.pack_into("<6f", out, 0xA0, *lo, *hi)
        struct.pack_into("<f", out, 0xB8, radius)
        n_s, o_s = struct.unpack_from("<II", m2, 0x1C)
        for i in range(n_s):
            struct.pack_into("<6f", out, o_s + i * 0x40 + 0x20, *lo, *hi)
            struct.pack_into("<f", out, o_s + i * 0x40 + 0x38, radius)
    return bytes(out)


def _batches(skin: bytes) -> list[bytearray]:
    n_b, o_b = struct.unpack_from("<II", skin, 0x24)
    return [bytearray(skin[o_b + i * BATCH:o_b + (i + 1) * BATCH]) for i in range(n_b)]


def _material(model, flags: int, blend: int) -> int:
    """Index of a material with these flags and blend mode, appending one when there is none."""
    for i, m in enumerate(model.materials):
        if (m["flags"], m["blending_mode"]) == (flags, blend):
            return i
    model.materials.append({"flags": flags, "blending_mode": blend})
    return len(model.materials) - 1


def _combo(combos: list[int], ops: tuple[int, ...]) -> int:
    """Index of ``ops`` as a run in the model's texture combiner combos, appending it if missing."""
    for i in range(len(combos) - len(ops) + 1):
        if tuple(combos[i:i + len(ops)]) == ops:
            return i
    combos.extend(ops)
    return len(combos) - len(ops)


def wotlk_layers(m2: bytes, skins: list[bytes], source_skins: list[bytes], *,
                 own_ops: bool = False) -> tuple[bytes, list[bytes], int]:
    """(model, skins, batches redrawn): BfA's batch shaders as WarcraftXL's own helmets draw them.

    The converter keeps a BfA batch's textures but drops its shader (``source_skins`` still has
    it), and 3.3.5 draws a two-texture batch with no combiner table as the diffuse times the
    reflection map: the whole helmet came out nearly black, and a single texture under a raw BfA
    id (0x10, the eye glows) slid with the camera (thirteenth client test). Like WarcraftXL's own
    (all 279 helmets compared): a reflection shader (ENV_COMBOS) draws diffuse and reflection
    through a combiner and the diffuse again on top, alpha blended, so the reflection only shows
    where the diffuse is clear; 0x8001 draws the diffuse and adds the reflection over it; any
    other draws its diffuse alone. Combiner ops: 1 Mod, 3 Add, 4 Mod2x.

    ``own_ops`` (a glue scene; WarcraftXL's helmets have nothing to say about scenes): a two-texture
    id outside the shader table names its own two ops (the Horde create scene's fire glows and
    flags: 0x4014, Mod then Mod2x on the second UV set), and keeps both textures, its ops in the
    table - drawn alone, the fire's mask was gone; and every Opaque_AddAlpha entry
    (``SCENE_ADD_LAYERS``) adds its second texture as 0x8001 does."""
    from wotlkconv.m2.model import parse_md20
    from wotlkconv.m2.write import write_md20

    model = parse_md20(m2)
    if model.uses_combiner_combos:
        return m2, skins, 0
    combos: list[int] = []
    redrawn = 0
    plans = []
    for skin, source in zip(skins, source_skins):
        own, theirs = _batches(skin), _batches(source)
        if len(own) != len(theirs):
            raise HelmetsError(f"{len(own)} batches converted from BfA's {len(theirs)}")
        plan = []
        for batch, original in zip(own, theirs):
            shader = struct.unpack_from("<H", original, 2)[0]
            count, = struct.unpack_from("<H", batch, 0x0E)
            batch[0] &= ~MODERN_BATCH_FLAGS & 0xFF
            plan.append((batch, shader, count))
        plans.append(plan)
    # a table only when some batch combines two textures; then every single texture is Mod
    add_layers = SCENE_ADD_LAYERS if own_ops else {SHADER_ADD_LAYER}
    two = any(count >= 2 and (shader in ENV_COMBOS or own_ops and not shader & SHADER_TABLE)
              for plan in plans for _b, shader, count in plan)
    if two:
        _combo(combos, ENV_COMBOS[0x8000])
    out_skins = []
    for skin, plan in zip(skins, plans):
        batches = []
        for batch, shader, count in plan:
            single = _combo(combos, (COMBINE_MOD,)) if two else 0
            if count >= 2 and shader in ENV_COMBOS:
                struct.pack_into("<H", batch, 2, _combo(combos, ENV_COMBOS[shader]))
                struct.pack_into("<H", batch, 0x0E, 2)
                over = bytearray(batch)
                struct.pack_into("<H", over, 2, single)
                struct.pack_into("<H", over, 0x0E, 1)
                struct.pack_into("<H", over, 0x0A, _material(model, MATERIAL_NO_DEPTH_WRITE, BLEND_ALPHA))
                struct.pack_into("<H", over, 0x0C, struct.unpack_from("<H", batch, 0x0C)[0] + 1)
                batches += [batch, over]
                redrawn += 1
            elif count >= 2 and shader in add_layers:
                struct.pack_into("<H", batch, 2, single)
                struct.pack_into("<H", batch, 0x0E, 1)
                over = bytearray(batch)
                for field, table in ((0x10, model.texture_combos), (0x12, model.texture_coord_combos),
                                     (0x14, model.texture_weight_combos)):
                    at = struct.unpack_from("<H", over, field)[0]
                    if at + 1 < len(table):
                        struct.pack_into("<H", over, field, at + 1)
                struct.pack_into("<H", over, 0x0A, _material(model, MATERIAL_NO_DEPTH_WRITE, BLEND_ADD))
                struct.pack_into("<H", over, 0x0C, struct.unpack_from("<H", batch, 0x0C)[0] + 1)
                batches += [batch, over]
                redrawn += 1
            elif count >= 2 and own_ops and not shader & SHADER_TABLE:
                struct.pack_into("<H", batch, 2, _combo(combos, ((shader >> 4) & 7, shader & 7)))
                batches.append(batch)
                redrawn += 1
            else:
                if count >= 2:
                    struct.pack_into("<H", batch, 0x0E, 1)
                    redrawn += 1
                elif struct.unpack_from("<H", batch, 2)[0] != single:
                    redrawn += 1
                struct.pack_into("<H", batch, 2, single)
                batches.append(batch)
        out = bytearray(skin)
        out.extend(bytes(-len(out) % 16))
        struct.pack_into("<II", out, 0x24, len(batches), len(out))
        out.extend(b"".join(batches))
        out_skins.append(bytes(out))
    if two:
        model.global_flags |= COMBINER_COMBOS
        model.texture_combiner_combos = combos
    return write_md20(model), out_skins, redrawn


def needs_layers(source_skins: list[bytes]) -> bool:
    """Whether a BfA scene's batches draw a reflection 3.3.5 can only draw through ``wotlk_layers``'
    combiner table, or a texture added over the diffuse it can only draw as a layer of its own.
    Without one a converted model's batches draw as BfA's do (a create scene's do)."""
    return any(struct.unpack_from("<H", b, 0x0E)[0] >= 2
               and struct.unpack_from("<H", b, 2)[0] in ENV_COMBOS.keys() | SCENE_ADD_LAYERS
               for skin in source_skins for b in _batches(skin))


def wotlk_particles(m2: bytes) -> tuple[bytes, int]:
    """(model, emitters changed): particle emitters as WarcraftXL's own helmets carry BfA's (all
    86 helmets with emitters compared). A z-source of Z_SOURCE_NONE - BfA's "none" - becomes 0;
    3.3.5 reads it as a point that far above the emitter. And on a texture of one cell every head
    and tail cell is 0: BfA's Kul Tiran versions ask for cell 1 there, past the texture's edge in
    3.3.5, and the T10 warrior helm's glowing eyes didn't show (fourteenth client test); an empty
    head-cell track is filled with cell 0 as WarcraftXL fills it. Animated textures of several
    cells keep their cells, as WarcraftXL's do. BfA's Human helmets run through the converter and
    these passes match WarcraftXL's own in every emitter field but data BfA itself changed."""
    from wotlkconv.m2.model import parse_md20
    from wotlkconv.m2.write import write_md20

    model = parse_md20(m2)
    changed = 0
    for p in model.particles:
        hit = False
        z = p.get("z_source")
        for keys in getattr(z, "values", []):
            for i, v in enumerate(keys):
                if v == Z_SOURCE_NONE:
                    keys[i] = 0.0
                    hit = True
        if p["texture_dimensions_rows"] * p["texture_dimensions_columns"] == 1:
            for name in ("head_cell_track", "tail_cell_track"):
                track = p.get(name)
                if track is not None and any(track.values):
                    track.values = [0] * len(track.values)
                    hit = True
            head = p.get("head_cell_track")
            if head is not None and not head.values:
                head.times, head.values = list(CELL_ZERO_TIMES), [0] * len(CELL_ZERO_TIMES)
                hit = True
        changed += hit
    return (write_md20(model) if changed else m2), changed


def texture_names(m2: bytes) -> list[str]:
    """The files an MD20 model's type-0 textures name."""
    n_t, o_t = struct.unpack_from("<II", m2, 0x50)
    names = []
    for i in range(n_t):
        kind, _flags, length, offset = struct.unpack_from("<IIII", m2, o_t + i * 16)
        if kind == _TEXTURE_FILE and length:
            names.append(m2[offset:offset + length].split(b"\0", 1)[0].decode("latin-1"))
    return names


# --------------------------------------------------------------------------- the whole set

@dataclass
class HelmetSet:
    prefix: str
    own: dict[tuple[str, int], str] = field(default_factory=dict)      # (base, sex) -> converted model
    carried: dict[tuple[str, int], str] = field(default_factory=dict)  # from the template's model
    failed: dict[tuple[str, int], str] = field(default_factory=dict)   # (base, sex) -> why
    textures: list[str] = field(default_factory=list)                  # extracted from BfA
    files: list[str] = field(default_factory=list)
    redrawn: int = 0                                                   # batches given 3.3.5 shaders
    emitters: int = 0                                                  # particle emitters fixed
    influences: int = 0                                                # skin sections given bone influences


def _converted(path: str, source: bytes, read: Callable[[int], bytes]) -> tuple[bytes, list[bytes], list[bytes]]:
    """A converted model, its skins, and the skins of its BfA source (whose batches keep their
    shaders): (model, skins, BfA's skins)."""
    with open(path, "rb") as fh:
        m2 = fh.read()
    count = struct.unpack_from("<I", m2, 0x44)[0]
    skins = []
    for k in range(count):
        with open(f"{path[:-3]}{k:02d}.skin", "rb") as fh:
            skins.append(fh.read())
    sfid = chunks(source).get("SFID", b"")
    if len(sfid) < 4 * count:
        raise HelmetsError("the BfA model names fewer skins than were converted")
    return m2, skins, [read(f) for f in struct.unpack_from(f"<{count}I", sfid)]


def _write_back(path: str, m2: bytes, data: bytes, skins: list[bytes], new_skins: list[bytes]) -> None:
    if data != m2:
        write_verified(path, data)
    for k, (old, new) in enumerate(zip(skins, new_skins)):
        if new != old:
            write_verified(f"{path[:-3]}{k:02d}.skin", new)


def _redraw(path: str, source: bytes, read: Callable[[int], bytes]) -> tuple[int, int, int]:
    """``wotlk_layers`` and ``wotlk_particles`` on a converted model and its skins, from its BfA
    source's skins, and the skins' bone influences filled (fixup.py): (batches redrawn, emitters
    fixed, sections filled)."""
    m2, skins, sources = _converted(path, source, read)
    data, new_skins, redrawn = wotlk_layers(m2, skins, sources)
    data, emitters = wotlk_particles(data)
    _write_back(path, m2, data, skins, new_skins)
    filled = fixup.fill_bone_influences(path, [f"{path[:-3]}{k:02d}.skin" for k in range(len(skins))])
    return redrawn, emitters, filled


def redraw_scene(path: str, source: bytes, read: Callable[[int], bytes]) -> tuple[int, int]:
    """A converted glue scene (a create scene, a race's select scene) and its skins as WarcraftXL
    draws BfA's models, from its BfA source's skins: ``wotlk_layers`` where BfA's shaders need its
    combiner table (the Horde create scene's sign posts, a reflection 3.3.5 drew as the diffuse
    times the reflection map - black), a scene without that drawing as converted; and
    ``wotlk_particles`` (the fires on Boralus' docks). (batches redrawn, emitters fixed)."""
    m2, skins, sources = _converted(path, source, read)
    data, new_skins, redrawn = (wotlk_layers(m2, skins, sources, own_ops=True) if needs_layers(sources)
                                else (m2, skins, 0))
    data, emitters = wotlk_particles(data)
    _write_back(path, m2, data, skins, new_skins)
    return redrawn, emitters


def convert_item_models(models: dict[str, tuple[str, int]], *, client_out: str, read: Callable[[int], bytes], casc,
                        listfile: str, exists: Callable[[str], bool], work_dir: str) -> HelmetSet:
    """Convert BfA's model of each stem (stem -> (client folder, FileDataID)) into that folder of
    ``client_out`` as ``<stem>.m2``, drawn as WarcraftXL draws BfA's (``_redraw``), and extract the
    textures they name that the client lacks. ``own`` and ``failed`` are keyed by stem (a texture's
    failure by "texture <name>")."""
    os.makedirs(work_dir, exist_ok=True)
    out = HelmetSet("")
    data = {}
    for stem, (_folder, fdid) in sorted(models.items()):
        try:
            data[stem] = read(fdid)
        except Exception as e:  # noqa: BLE001 - CASC raises several kinds for a missing file
            out.failed[stem] = f"BfA file {fdid}: {e}"
    lf = engine.scoped_listfile_for(list(data.values()), [work_dir], listfile,
                                    read_fdid=lambda f: casc.try_read_file_id(f)[0])
    wanted: dict[str, int] = {}
    for stem, model in sorted(data.items()):
        folder = os.path.join(client_out, *models[stem][0].rstrip("\\").split("\\"))
        er = engine.convert_with_wotlkconv(os.path.join(work_dir, stem + ".m2"), folder, output_stem=stem,
                                           casc=casc, data=model, listfile=lf)
        if not er.ok:
            out.failed[stem] = er.error
            continue
        out.own[stem] = er.output
        out.files += er.written
        try:
            redrawn, emitters, filled = _redraw(er.output, model, read)
            out.redrawn += redrawn
            out.emitters += emitters
            out.influences += filled
        except (HelmetsError, ValueError, KeyError, struct.error, OSError) as e:
            out.failed[stem] = f"its shaders were left as converted: {e}"
        with open(er.output, "rb") as fh:
            for name in texture_names(fh.read()):
                # one an earlier build extracted is the client's now, once installed: kept
                ours = os.path.isfile(os.path.join(client_out, *name.replace("/", "\\").split("\\")))
                if ours or not exists(name):
                    fdid = lf.id_for(name)
                    if fdid is None:
                        out.failed[stem] = f"texture {name} is in neither the client nor the listfile"
                    else:
                        wanted[name] = fdid
    for name, fdid in sorted(wanted.items()):
        path = os.path.join(client_out, *name.replace("/", "\\").split("\\"))
        try:
            out.files.append(write_verified(path, read(fdid), blp.verify_blp))
            out.textures.append(name)
        except (blp.BLPError, ValueError, OSError) as e:
            out.failed["texture " + name] = str(e)
    return out


def convert_race_helmets(models: dict[tuple[str, int], int], *, prefix: str, client_out: str,
                         read: Callable[[int], bytes], casc, listfile: str, exists: Callable[[str], bool],
                         work_dir: str) -> HelmetSet:
    """Convert BfA's model of each (base, sex) into ``client_out``'s Head folder as
    ``<Base>_<prefix><M|F>``, and extract the textures they name that the client lacks."""
    keys = {f"{base}_{prefix}{SEXES[sex]}": (base, sex) for base, sex in models}
    got = convert_item_models({stem: (HEAD, models[key]) for stem, key in keys.items()}, client_out=client_out,
                              read=read, casc=casc, listfile=listfile, exists=exists, work_dir=work_dir)
    out = HelmetSet(prefix, textures=got.textures, files=got.files, redrawn=got.redrawn, emitters=got.emitters,
                    influences=got.influences)
    out.own = {keys[stem]: path for stem, path in got.own.items()}
    out.failed = {keys.get(stem, (stem, -1)): why for stem, why in got.failed.items()}
    return out


def carry_template_helmet(read_client: Callable[[str], bytes | None], base: str, sex: int, template_prefix: str,
                          prefix: str, linear, offset, client_out: str) -> list[str]:
    """The template's model of ``base`` (with its skins and .anim files), carried by (linear,
    offset) and written as the race's: for a helmet BfA has no version of for the race."""
    name = f"{base}_{template_prefix}{SEXES[sex]}"
    m2 = read_client(HEAD + name + ".m2")
    if m2 is None:
        raise HelmetsError(f"{name}.m2 is not in the client")
    stem = f"{base}_{prefix}{SEXES[sex]}"
    head = os.path.join(client_out, *HEAD.rstrip("\\").split("\\"))
    files = [write_verified(os.path.join(head, stem + ".m2"), carry(m2, linear, offset))]
    for k in range(struct.unpack_from("<I", m2, 0x44)[0]):
        skin = read_client(f"{HEAD}{name}{k:02d}.skin")
        if skin is None:
            raise HelmetsError(f"{name}{k:02d}.skin is not in the client")
        files.append(write_verified(os.path.join(head, f"{stem}{k:02d}.skin"), skin))
    n_s, o_s = struct.unpack_from("<II", m2, 0x1C)
    for i in range(n_s):
        anim, sub, _d, _speed, flags = struct.unpack_from("<HHIfI", m2, o_s + i * 0x40)
        if not flags & helm.SEQ_IN_M2:
            data = read_client(f"{HEAD}{name}{anim:04d}-{sub:02d}.anim")
            if data is not None:
                files.append(write_verified(os.path.join(head, f"{stem}{anim:04d}-{sub:02d}.anim"), data))
    return files
