"""WMO group files -- the actual geometry.

A group is ``MVER`` plus one ``MOGP`` whose payload is a 68-byte header
followed by sub-chunks.  The header size never changed, so the work is in the
sub-chunks:

* ``MOVX`` (32-bit indices) has to become ``MOVI`` (16-bit). When the group
  has more than 65 536 vertices that is impossible, and the group is split into
  several -- see :mod:`wotlkconv.wmo.split`.
* ``MPY2`` (16-bit material ids) has to become ``MOPY`` (8-bit).
* Extra ``MOTV``/``MOCV`` layers beyond the two the old renderer binds are
  dropped, and the header flags that advertise them are corrected to match.
* Shadowlands reused ``MOBA``'s bounding-box bytes for a wide material id, so
  when that layout is detected the id is moved into the material byte 3.3.5a
  reads, and the boxes are recomputed from the geometry rather than left as
  garbage the client would cull against.
"""

from __future__ import annotations

import dataclasses
import struct
from collections.abc import Sequence

from ..chunks import Chunk, ChunkReader, ChunkWriter, report_unknown
from ..errors import MalformedFileError, UnsupportedFormatError
from ..limits import (
    MOBA_FLAG_WIDE_MATERIAL,
    MOBA_SIZE,
    MOGP_HEADER_SIZE,
    MOPY_NO_MATERIAL,
    MPY2_NO_MATERIAL,
    WMO_GROUP_CHUNKS_KNOWN,
    WMO_GROUP_FLAG_HAS_BSP,
    WMO_GROUP_FLAG_HAS_DOODADS,
    WMO_GROUP_FLAG_HAS_LIGHTS,
    WMO_GROUP_FLAG_HAS_PORTAL_BATCHES,
    WMO_GROUP_FLAG_HAS_TWO_MOCV,
    WMO_GROUP_FLAG_HAS_TWO_MOTV,
    WMO_GROUP_FLAG_HAS_VERTEX_COLORS,
    WMO_GROUP_FLAG_HAS_WATER,
    WMO_GROUP_FLAG_MASK,
    WMO_MAX_COLOR_LAYERS,
    WMO_MAX_GROUP_VERTICES,
    WMO_MAX_UV_LAYERS,
    WMO_VERSION,
)
from ..options import Options
from ..report import FileResult, Status
from . import split as splitter
from .bsp import build_bsp

#: Post-Wrath group sub-chunks, with what each one carries.
MODERN_GROUP_CHUNKS = {
    "MOVX": "32-bit triangle indices",
    "MPY2": "16-bit material references",
    "MOC2": "extended vertex colours",
    "MOLS": "spot lights",
    "MOLP": "point lights",
    "MLSS": "light set spline",
    "MLSK": "light set skybox",
    "MLSO": "spot light animation",
    "MLSP": "light spline points",
    "MDAL": "doodad ambient light",
    "MOPL": "terrain cutting planes",
    "MOPB": "prepass batches",
    "MOBS": "shadow batches",
    "MOTA": "tangent arrays",
    "MOQG": "query face flags",
    "MOLM": "lightmap texels",
    "MOLD": "lightmap definitions",
    "MOAM": "ambient colours",
    "MDAI": "doodad ambient",
    "MPBV": "prepass bounds",
    "MPBP": "prepass portals",
    "MPBI": "prepass indices",
    "MPBG": "prepass groups",
    "MOGX": "query face start",
}

ALL_KNOWN = set(WMO_GROUP_CHUNKS_KNOWN) | set(MODERN_GROUP_CHUNKS)


@dataclasses.dataclass
class WmoGroup:
    version: int = WMO_VERSION
    header: bytearray = dataclasses.field(default_factory=lambda: bytearray(MOGP_HEADER_SIZE))
    subchunks: list[Chunk] = dataclasses.field(default_factory=list)
    reverse_magic: bool = True

    @property
    def flags(self) -> int:
        return struct.unpack_from("<I", self.header, 8)[0]

    @flags.setter
    def flags(self, value: int) -> None:
        struct.pack_into("<I", self.header, 8, value & 0xFFFFFFFF)

    @property
    def flags2(self) -> int:
        return struct.unpack_from("<I", self.header, 0x3C)[0]

    def by_name(self, name: str) -> list[Chunk]:
        return [c for c in self.subchunks if c.name == name]


def parse_group(data: bytes, name: str = "<wmo group>") -> WmoGroup:
    if len(data) < 8:
        raise MalformedFileError(f"{name}: file is only {len(data)} bytes")
    reader = ChunkReader.auto(data, {"MVER", "MOGP"}, name=name)
    group = WmoGroup(reverse_magic=reader.reverse)
    mogp: Chunk | None = None
    for chunk in reader:
        if chunk.name == "MVER" and len(chunk.data) >= 4:
            group.version = struct.unpack_from("<I", chunk.data, 0)[0]
        elif chunk.name == "MOGP":
            mogp = chunk
    if mogp is None:
        raise UnsupportedFormatError(f"{name}: not a WMO group (no MOGP chunk)")
    if len(mogp.data) < MOGP_HEADER_SIZE:
        raise MalformedFileError(
            f"{name}: MOGP is {len(mogp.data)} bytes, header alone needs "
            f"{MOGP_HEADER_SIZE}")

    group.header = bytearray(mogp.data[:MOGP_HEADER_SIZE])
    inner = ChunkReader(mogp.data, reverse=group.reverse_magic, name=name,
                        start=MOGP_HEADER_SIZE)
    group.subchunks = list(inner)
    return group


# ---------------------------------------------------------------------------
# Sub-chunk downgrades
# ---------------------------------------------------------------------------
def _read_indices(by_name: dict[str, list[bytes]]) -> list[int]:
    """Triangle indices as plain ints, whatever width they were stored at."""
    if "MOVI" in by_name:
        payload = by_name["MOVI"][0]
        count = len(payload) // 2
        return list(struct.unpack_from("<" + "H" * count, payload, 0)) if count else []
    if "MOVX" in by_name:
        payload = by_name["MOVX"][0]
        count = len(payload) // 4
        return list(struct.unpack_from("<" + "I" * count, payload, 0)) if count else []
    return []


def _convert_poly(payload: bytes, triangle_count: int, result: FileResult,
                  name: str) -> bytes | None:
    """MPY2 (uint16 flags + uint16 material) -> MOPY (uint8 + uint8)."""
    if triangle_count <= 0:
        return b""
    stride = len(payload) // triangle_count
    if stride not in (2, 4):
        result.fail("wmo.group.mpy2",
                    f"{name}: MPY2 is {len(payload)} bytes for {triangle_count} "
                    f"triangles, which is neither 2 nor 4 bytes per triangle",
                    stride=stride)
        return None
    if stride == 2:
        return payload[: triangle_count * 2]

    out = bytearray(triangle_count * 2)
    over = 0
    for i in range(triangle_count):
        flags, material = struct.unpack_from("<HH", payload, i * 4)
        if material == MPY2_NO_MATERIAL:
            material = MOPY_NO_MATERIAL  # the same "collision only" face, narrower
        elif material > 0xFF:
            over += 1
            material = MOPY_NO_MATERIAL
        out[i * 2] = flags & 0xFF
        out[i * 2 + 1] = material & 0xFF
    if over:
        result.lossy("wmo.group.material_id",
                     f"{over} triangle(s) referenced a material above 255; "
                     f"3.3.5a stores material ids in a byte, so they were marked "
                     f"collision-only", triangles=over)
    result.lossy("wmo.group.mpy2",
                 f"converted MPY2 to MOPY for {triangle_count} triangles")
    return bytes(out)


def _narrow_batch_materials(moba: bytes, result: FileResult) -> bytes:
    """Move each batch's wide material id into the byte 3.3.5a reads.

    A batch flagged :data:`MOBA_FLAG_WIDE_MATERIAL` keeps its material as a
    uint16 inside the bounding box and leaves the old byte at 0.  The bounds
    rebuild overwrites the box, so without this every batch draws with the
    first material.
    """
    out = bytearray(moba)
    moved = over = 0
    for i in range(len(moba) // MOBA_SIZE):
        base = i * MOBA_SIZE
        flags = out[base + 22]
        if not flags & MOBA_FLAG_WIDE_MATERIAL:
            continue
        material = struct.unpack_from("<H", out, base + 10)[0]
        if material > 0xFF:
            # 3.3.5a indexes its material list with this byte unchecked, so an
            # out-of-range value must not be written; the first one is safe.
            over += 1
            material = 0
        out[base + 22] = flags & ~MOBA_FLAG_WIDE_MATERIAL & 0xFF
        out[base + 23] = material
        moved += 1
    if moved:
        result.info("wmo.group.moba_material",
                    f"moved the material of {moved} render batch(es) into the "
                    f"byte 3.3.5a reads", batches=moved)
    if over:
        result.lossy("wmo.group.moba_material_id",
                     f"{over} render batch(es) used a material above 255; "
                     f"3.3.5a stores a batch's material in a byte, so they draw "
                     f"with the first material", batches=over)
    return bytes(out)


def _recompute_batch_bounds(moba: bytes, vertices: bytes, indices: bytes,
                            result: FileResult) -> bytes:
    """Rebuild MOBA bounding boxes from the geometry.

    Shadowlands reused the first twelve bytes of each batch for a wide material
    id, so a straight copy leaves the old client culling against nonsense.
    """
    count = len(moba) // MOBA_SIZE
    vertex_count = len(vertices) // 12
    index_count = len(indices) // 2
    out = bytearray(moba)
    fixed = 0
    for i in range(count):
        base = i * MOBA_SIZE
        start_index, tri_count = struct.unpack_from("<IH", out, base + 12)
        lo = [32767, 32767, 32767]
        hi = [-32768, -32768, -32768]
        seen = False
        for n in range(start_index, min(start_index + tri_count, index_count)):
            vi = struct.unpack_from("<H", indices, n * 2)[0]
            if vi >= vertex_count:
                continue
            x, y, z = struct.unpack_from("<3f", vertices, vi * 12)
            seen = True
            for axis, value in enumerate((x, y, z)):
                iv = int(value)
                lo[axis] = min(lo[axis], iv - 1)
                hi[axis] = max(hi[axis], iv + 1)
        if not seen:
            continue
        clamp = lambda v: max(-32768, min(32767, v))  # noqa: E731
        struct.pack_into("<6h", out, base,
                         clamp(lo[0]), clamp(lo[1]), clamp(lo[2]),
                         clamp(hi[0]), clamp(hi[1]), clamp(hi[2]))
        fixed += 1
    if fixed:
        result.lossy("wmo.group.moba_bounds",
                     f"recomputed bounding boxes for {fixed} render batch(es); "
                     f"the source stored a wide material id in those bytes",
                     batches=fixed)
    return bytes(out)


@dataclasses.dataclass(slots=True)
class GroupFile:
    """One group file produced from a source group."""

    data: bytes
    bounding_box: tuple = (0.0,) * 6
    flags: int = 0
    vertices: int = 0
    triangles: int = 0
    #: 0 for the original group, 1.. for the extra groups a split produced.
    part: int = 0


def _emit_group(header: bytearray, reverse: bool, *, polys: bytes,
                indices: Sequence[int], vertices: bytes, normals: bytes,
                uvs: Sequence[bytes], batches: bytes, colours: Sequence[bytes],
                extras: dict[str, bytes], mobn: bytes = b"",
                mobr: bytes = b"") -> bytes:
    """Write one MVER + MOGP group file from already-prepared arrays.

    The flags that announce optional chunks are set from what is written:
    3.3.5a reads an optional chunk wherever its flag is set without checking
    the name, so a flag left on for a chunk retail moved elsewhere (lights,
    5,850 retail groups) makes it read the next chunk in its place.
    """
    flags = struct.unpack_from("<I", header, 8)[0]
    for present, bit in ((bool(extras.get("MOLR")), WMO_GROUP_FLAG_HAS_LIGHTS),
                         (bool(extras.get("MODR")), WMO_GROUP_FLAG_HAS_DOODADS),
                         (bool(extras.get("MLIQ")), WMO_GROUP_FLAG_HAS_WATER),
                         (bool(mobn), WMO_GROUP_FLAG_HAS_BSP),
                         (False, WMO_GROUP_FLAG_HAS_PORTAL_BATCHES)):
        flags = flags | bit if present else flags & ~bit
    struct.pack_into("<I", header, 8, flags)
    inner = ChunkWriter(reverse=reverse)
    # MOPY, MOVI, MOVT, MONR, MOTV and MOBA are read unconditionally and in
    # this order, so each is written even when it is empty: 3.3.5a's own
    # groups always have all six (an empty MOBA on groups that draw nothing),
    # and a reader missing one takes the next chunk for it.  A group with
    # vertices but no UVs (collision geometry) gets zeroed coordinates, so the
    # coordinate array still matches the vertices.
    inner.add("MOPY", polys)
    inner.add("MOVI", struct.pack("<" + "H" * len(indices), *indices))
    inner.add("MOVT", vertices)
    inner.add("MONR", normals)
    # The order is fixed, not just conventional: 3.3.5a's own groups and
    # Noggit's reader expect the second UV and colour layers at the very end,
    # after the liquid.  A second MOTV straight after the first is read as
    # MOBA, and every batch after it is garbage.
    inner.add("MOTV", uvs[0] if uvs else bytes(8 * (len(vertices) // 12)))
    inner.add("MOBA", batches)
    for name in ("MOLR", "MODR"):
        if extras.get(name):
            inner.add(name, extras[name])
    if mobn:
        inner.add("MOBN", mobn)
        inner.add("MOBR", mobr)
    if colours:
        inner.add("MOCV", colours[0])
    if extras.get("MLIQ"):
        inner.add("MLIQ", extras["MLIQ"])
    for uv in uvs[1:]:
        inner.add("MOTV", uv)
    for colour in colours[1:]:
        inner.add("MOCV", colour)

    outer = ChunkWriter(reverse=reverse)
    outer.add("MVER", struct.pack("<I", WMO_VERSION))
    outer.add("MOGP", bytes(header) + inner.getvalue())
    return outer.getvalue()


def convert_group_parts(data: bytes, source_name: str, opts: Options,
                        result: FileResult | None = None
                        ) -> tuple[list[GroupFile], FileResult]:
    """Downgrade one group, splitting it when it cannot fit 16-bit indices."""
    res = result or FileResult(source=source_name, kind="wmo-group")
    res.kind = "wmo-group"
    res.bytes_in = len(data)

    group = parse_group(data, source_name)
    res.source_version = (f"WMO group v{group.version}, "
                          f"{len(group.subchunks)} sub-chunks")

    by_name: dict[str, list[bytes]] = {}
    for chunk in group.subchunks:
        by_name.setdefault(chunk.name, []).append(chunk.data)

    modern_seen = sorted(n for n in by_name if n in MODERN_GROUP_CHUNKS)
    had_wide_materials = "MPY2" in by_name

    indices = _read_indices(by_name)
    if "MOVX" in by_name:
        res.lossy("wmo.group.movx",
                  f"converted {len(indices)} 32-bit indices to 16-bit MOVI",
                  indices=len(indices))

    triangle_count = len(indices) // 3
    polys = b""
    if "MOPY" in by_name:
        polys = by_name["MOPY"][0]
    elif "MPY2" in by_name:
        converted = _convert_poly(by_name["MPY2"][0], triangle_count, res,
                                  source_name)
        if converted is None:
            return [], res
        polys = converted

    vertices = by_name.get("MOVT", [b""])[0]
    vertex_count = len(vertices) // 12

    batches = by_name.get("MOBA", [b""])[0]
    if batches and had_wide_materials:
        batches = _narrow_batch_materials(batches, res)
    if batches and had_wide_materials and vertices and indices:
        narrow = struct.pack("<" + "H" * len(indices),
                             *(min(i, 0xFFFF) for i in indices))
        batches = _recompute_batch_bounds(batches, vertices, narrow, res)

    uvs = by_name.get("MOTV", [])
    colours = by_name.get("MOCV", [])
    if len(uvs) > WMO_MAX_UV_LAYERS:
        res.lossy("wmo.group.uv_layers",
                  f"dropped {len(uvs) - WMO_MAX_UV_LAYERS} UV layer(s); 3.3.5a "
                  f"binds at most {WMO_MAX_UV_LAYERS}", layers=len(uvs))
        uvs = uvs[:WMO_MAX_UV_LAYERS]
    if len(colours) > WMO_MAX_COLOR_LAYERS:
        res.lossy("wmo.group.color_layers",
                  f"dropped {len(colours) - WMO_MAX_COLOR_LAYERS} vertex-colour "
                  f"layer(s)", layers=len(colours))
        colours = colours[:WMO_MAX_COLOR_LAYERS]

    header = _fix_header(group, uvs, colours, res)
    extras = {name: by_name[name][0] for name in ("MOLR", "MODR", "MLIQ")
              if name in by_name}

    if modern_seen:
        dropped = [n for n in modern_seen if n not in ("MOVX", "MPY2")]
        if dropped:
            report_unknown(res, [c.name for c in group.subchunks], ALL_KNOWN,
                           "world-object group", "wmo.group.chunks_unknown")
            res.lossy("wmo.group.chunks_dropped",
                      "dropped group chunks with no 3.3.5a equivalent: "
                      + ", ".join(f"{n} ({MODERN_GROUP_CHUNKS[n]})"
                                  for n in dropped),
                      chunks=dropped)

    biggest = max(indices, default=-1)
    if vertex_count and biggest >= vertex_count:
        res.fail("wmo.group.bad_index",
                 f"a triangle references vertex {biggest} but the group only "
                 f"has {vertex_count}; the group is corrupt",
                 max_index=biggest, vertices=vertex_count)
        return [], res

    oversized = vertex_count > WMO_MAX_GROUP_VERTICES

    if not oversized:
        mobn = by_name.get("MOBN", [b""])[0]
        mobr = by_name.get("MOBR", [b""])[0]
        if not mobn and indices and vertex_count:
            # Every 3.3.5a group with triangles has a collision tree; without
            # one the client lets players walk through the group.
            positions = [struct.unpack_from("<3f", vertices, i * 12)
                         for i in range(vertex_count)]
            triangles = [tuple(indices[i:i + 3])
                         for i in range(0, len(indices) - 2, 3)]
            mobn, mobr = build_bsp(positions, triangles)
            res.info("wmo.group.bsp_built",
                     f"built a collision tree over {len(triangles)} triangles; "
                     f"the source group shipped none",
                     triangles=len(triangles))
        out = _emit_group(header, group.reverse_magic, polys=polys,
                          indices=indices, vertices=vertices,
                          normals=by_name.get("MONR", [b""])[0], uvs=uvs,
                          batches=batches, colours=colours, extras=extras,
                          mobn=mobn, mobr=mobr)
        res.bytes_out = len(out)
        res.target_version = f"WMO group v{WMO_VERSION}, {vertex_count} vertices"
        if not modern_seen and res.status is Status.OK:
            res.status = Status.PASSTHROUGH
            res.info("wmo.group.passthrough", "already a 3.3.5a group layout")
        return [GroupFile(out, _bounds_of(header), group.flags, vertex_count,
                          triangle_count, 0)], res

    if not opts.split_oversized_groups:
        res.fail("wmo.group.indices",
                 f"{vertex_count} vertices exceeds the "
                 f"{WMO_MAX_GROUP_VERTICES} a 3.3.5a group can index, and "
                 f"--no-split-groups was given",
                 vertices=vertex_count)
        return [], res

    geo = splitter.unpack(vertices, by_name.get("MONR", [b""])[0], uvs, colours,
                          indices, polys, batches)
    pieces = splitter.split(geo)
    res.lossy("wmo.group.split",
              f"{vertex_count} vertices exceeds the "
              f"{WMO_MAX_GROUP_VERTICES} a 3.3.5a group can index, so the "
              f"group was split into {len(pieces)} and their collision trees "
              f"rebuilt",
              vertices=vertex_count, parts=len(pieces))

    out_files: list[GroupFile] = []
    for number, piece in enumerate(pieces):
        piece_header = bytearray(header)
        struct.pack_into("<6f", piece_header, 12, *piece.bounding_box)
        # Liquid is a grid over the original group; duplicating it would render
        # the water several times over, so it stays with the first part.
        piece_extras = dict(extras) if number == 0 else \
            {k: v for k, v in extras.items() if k != "MLIQ"}
        out = _emit_group(piece_header, group.reverse_magic, polys=piece.polys,
                          indices=piece.indices, vertices=piece.vertices,
                          normals=piece.normals, uvs=piece.uvs,
                          batches=piece.batches, colours=piece.colors,
                          extras=piece_extras, mobn=piece.mobn, mobr=piece.mobr)
        out_files.append(GroupFile(out, piece.bounding_box,
                                   struct.unpack_from("<I", piece_header, 8)[0],
                                   piece.vertex_count, piece.triangle_count,
                                   number))

    res.bytes_out = sum(len(f.data) for f in out_files)
    res.target_version = (f"WMO group v{WMO_VERSION}, {len(out_files)} part(s), "
                          f"{vertex_count} vertices")
    res.extra["parts"] = len(out_files)
    return out_files, res


def _bounds_of(header: bytes) -> tuple:
    return struct.unpack_from("<6f", header, 12)


def _fix_header(group: WmoGroup, uvs: Sequence[bytes], colours: Sequence[bytes],
                res: FileResult) -> bytearray:
    """Mask the flags and make the layer bits describe what actually survived."""
    flags = group.flags
    original = flags
    flags &= WMO_GROUP_FLAG_MASK
    if len(uvs) >= 2:
        flags |= WMO_GROUP_FLAG_HAS_TWO_MOTV
    else:
        flags &= ~WMO_GROUP_FLAG_HAS_TWO_MOTV
    if len(colours) >= 2:
        flags |= WMO_GROUP_FLAG_HAS_TWO_MOCV
    else:
        flags &= ~WMO_GROUP_FLAG_HAS_TWO_MOCV
    if colours:
        flags |= WMO_GROUP_FLAG_HAS_VERTEX_COLORS
    else:
        flags &= ~WMO_GROUP_FLAG_HAS_VERTEX_COLORS
    if flags != original:
        res.info("wmo.group.flags",
                 f"group flags 0x{original:08X} -> 0x{flags:08X}")
    group.flags = flags

    header = bytearray(group.header)
    if struct.unpack_from("<I", header, 0x3C)[0] or \
            struct.unpack_from("<I", header, 0x40)[0]:
        # Wrath has no flags2 and reads the last word as padding; Legion's
        # split-group indices would show up there as a huge unknown value.
        struct.pack_into("<II", header, 0x3C, 0, 0)
        res.info("wmo.group.split_index",
                 "cleared Legion split-group indices from the MOGP header")
    return header


def convert_group(data: bytes, source_name: str, opts: Options,
                  result: FileResult | None = None) -> tuple[bytes, FileResult]:
    """Downgrade one group file, keeping only the first part of any split."""
    parts, res = convert_group_parts(data, source_name, opts, result)
    if not parts:
        return b"", res
    if len(parts) > 1:
        res.warn("wmo.group.parts_dropped",
                 f"this group split into {len(parts)}, but only the first is "
                 f"returned here; convert the WMO through its root so the "
                 f"extra groups are registered")
    return parts[0].data, res


def inspect_group(data: bytes, source_name: str) -> dict:
    group = parse_group(data, source_name)
    names: dict[str, int] = {}
    for c in group.subchunks:
        names[c.name] = names.get(c.name, 0) + 1
    return {
        "kind": "wmo-group",
        "version": group.version,
        "flags": f"0x{group.flags:08X}",
        "subchunks": names,
        "modern_subchunks": sorted(n for n in names if n in MODERN_GROUP_CHUNKS) or None,
    }
