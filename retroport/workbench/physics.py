"""A retail model's physics (its ``.phys``, or the PFDC chunk newer models carry it in), for the 3D preview.

The x64 client simulates these with Jolt (WXL/modules/physics: PHYSICS.md has the data, PhysicsFile.cpp the
reader this follows - our own code): bodies on bones, their shapes, the joints between them. The preview
doesn't simulate; it settles the dynamic bodies once under gravity within their joints' limits (viewer.js
``settle``) - a helm's plumes and tentacles hanging as they rest in the game, not stuck out as modelled.

The file is chunks with their tags stored reversed ("SYHP" for PHYS). A body is on a bone: its space is the
model's axes with its origin at that bone's pivot (``position``), and its shapes and the joints' frames are
in that space. Angles are degrees in the file, radians here.
"""

from __future__ import annotations

import math
import struct

KINEMATIC, DYNAMIC, STATIC = 0, 1, 2
SPHERICAL, SHOULDER, WELD, REVOLUTE, PRISMATIC, DISTANCE = range(6)
RADIANS = math.pi / 180.0


def _tag(name: str) -> bytes:
    return name[::-1].encode("ascii")


def _v3(data: bytes, at: int) -> list[float]:
    return list(struct.unpack_from("<3f", data, at))


def _unit(v: list[float]) -> list[float] | None:
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 1e-12 and math.isfinite(n) else None


def _frame_z(data: bytes, at: int) -> tuple[list[float], list[float]]:
    """A frame's Z axis (normalised: some files scale the axes) and its origin."""
    z = _unit(_v3(data, at + 24)) or [0.0, 0.0, 1.0]
    return z, _v3(data, at + 36)


def chunk(m2: bytes, name: str) -> bytes | None:
    """A chunked M2's chunk (``PFDC``: a .phys inside it), else None."""
    want, at = name.encode("ascii"), 0
    while at + 8 <= len(m2):
        tag, size = m2[at:at + 4], struct.unpack_from("<I", m2, at + 4)[0]
        if at + 8 + size > len(m2):
            return None
        if tag == want:
            return m2[at + 8:at + 8 + size]
        if tag == b"MD20":                      # a plain M2: no chunks
            return None
        at += 8 + size
    return None


def _chunks(data: bytes) -> dict[bytes, bytes]:
    out, at = {}, 0
    while at + 8 <= len(data):
        tag, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        if tag == b"\0\0\0\0" or at + 8 + size > len(data):
            break                                # a PFDC payload ends in padding
        out.setdefault(tag, data[at + 8:at + 8 + size])
        at += 8 + size
    return out


def _records(c: bytes | None, width: int) -> list[bytes]:
    return [c[i:i + width] for i in range(0, len(c) - width + 1, width)] if c else []


def _shape_mass(kind: int, index: int, density: float, parts: dict) -> tuple[float, list[float]] | None:
    """A shape's mass (its volume by its density) and centre, in its body's space."""
    density = density if density > 0 and math.isfinite(density) else 1000.0
    if kind == 1 and index < len(parts["caps"]):
        a, b, r = parts["caps"][index]
        h = math.dist(a, b)
        return density * (math.pi * r * r * h + 4.0 / 3.0 * math.pi * r ** 3), [(a[k] + b[k]) / 2 for k in range(3)]
    if kind == 2 and index < len(parts["sphs"]):
        c, r = parts["sphs"][index]
        return density * 4.0 / 3.0 * math.pi * r ** 3, c
    if kind == 0 and index < len(parts["boxs"]):
        origin, half = parts["boxs"][index]
        return density * 8.0 * abs(half[0] * half[1] * half[2]), origin
    if kind == 3 and index < len(parts["hulls"]):
        pts = parts["hulls"][index]
        if not pts:
            return None
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        vol = 0.6 * (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])   # a hull fills about this much of its box
        return density * vol, [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    return None


def read(data: bytes) -> dict | None:
    """The physics as the preview settles it - {"mode", "bodies": [{"type", "bone", "position", "mass", "com"
    (in its body's space), "gravity"}], "joints": [{"a", "b", "kind", "anchor_a", "anchor_b", "axis_a",
    "axis_b" (Z: a shoulder's twist, a revolute's hinge), "lower", "upper", "cone", "motor"}]} - else None."""
    c = _chunks(data)
    phys = c.get(_tag("PHYS"))
    if not phys or len(phys) < 2:
        return None
    mode = struct.unpack_from("<I", c[_tag("PHYT")])[0] if len(c.get(_tag("PHYT"), b"")) >= 4 else 4
    bodies_raw, width = None, 0
    for name, w in (("BDY4", 0x30), ("BDY3", 0x2C), ("BDY2", 0x28), ("BODY", 0x24)):
        if c.get(_tag(name)):
            bodies_raw, width = _records(c[_tag(name)], w), w
            break
    if not bodies_raw:
        return None
    shp = _tag("SHP2") if c.get(_tag("SHP2")) else _tag("SHAP")
    shapes = [struct.unpack_from("<HH", r) + struct.unpack_from("<f", r, 0x10) for r in
              _records(c.get(shp), 0x20 if shp == _tag("SHP2") else 0x14)]
    parts = {"caps": [(_v3(r, 0), _v3(r, 12), struct.unpack_from("<f", r, 24)[0]) for r in _records(c.get(_tag("CAPS")), 0x1C)],
             "sphs": [(_v3(r, 0), struct.unpack_from("<f", r, 12)[0]) for r in _records(c.get(_tag("SPHS")), 0x10)],
             "boxs": [(_v3(r, 36), _v3(r, 0x30)) for r in _records(c.get(_tag("BOXS")), 0x3C)], "hulls": []}
    plyt = c.get(_tag("PLYT"))
    if plyt and len(plyt) >= 4:
        count = struct.unpack_from("<I", plyt)[0]
        at = 4 + count * 0x50
        if count <= 4096 and at <= len(plyt):
            for i in range(count):
                vertices, faces, edges = (struct.unpack_from("<I", plyt, 4 + i * 0x50 + o)[0] for o in (0, 0x10, 0x28))
                block = vertices * 12 + faces * 17 + edges * 4
                if at + block > len(plyt):
                    break
                parts["hulls"].append([_v3(plyt, at + v * 12) for v in range(vertices)])
                at += block
    bodies = []
    for r in bodies_raw:
        kind, bone = struct.unpack_from("<HH", r)
        first, count = struct.unpack_from("<Hxxi", r, 0x10)
        gravity = struct.unpack_from("<f", r, 0x18)[0] if width >= 0x1C else 1.0
        mass, com = 0.0, [0.0, 0.0, 0.0]
        for s in shapes[first:first + max(0, count)]:
            got = _shape_mass(s[0], s[1], s[2], parts)
            if got:
                mass += got[0]
                com = [com[k] + got[0] * got[1][k] for k in range(3)]
        bodies.append({"type": kind if kind in (KINEMATIC, DYNAMIC) else STATIC, "bone": bone,
                       "position": [round(v, 6) for v in _v3(r, 4)], "mass": round(mass, 6),
                       "com": [round(v / mass, 6) for v in com] if mass > 0 else [0.0, 0.0, 0.0],
                       "gravity": round(gravity, 6) if math.isfinite(gravity) else 1.0})
    raw: dict[int, list[bytes]] = {}
    for kind, name, w in ((SHOULDER, "SHJ2", 0x7C), (SHOULDER, "SHOJ", 0x74), (WELD, "WLJ3", 0x74), (WELD, "WLJ2", 0x70),
                          (WELD, "WELJ", 0x68), (REVOLUTE, "REV2", 0x78), (REVOLUTE, "REVJ", 0x70), (PRISMATIC, "PRS2", 0x80),
                          (PRISMATIC, "PRSJ", 0x78), (SPHERICAL, "SPHJ", 0x1C), (DISTANCE, "DSTJ", 0x1C)):
        if kind not in raw and c.get(_tag(name)):
            raw[kind] = _records(c[_tag(name)], w)
    joints = []
    for r in _records(c.get(_tag("JOIN")), 0x10):
        a, b = struct.unpack_from("<II", r)
        kind, index = struct.unpack_from("<HH", r, 0xC)
        recs = raw.get(kind) or []
        if index >= len(recs) or a >= len(bodies) or b >= len(bodies):
            continue
        p = recs[index]
        j = {"a": a, "b": b, "kind": kind, "lower": 0.0, "upper": 0.0, "cone": 0.0, "motor": 0,
             "axis_a": [0.0, 0.0, 1.0], "axis_b": [0.0, 0.0, 1.0]}
        if kind in (SPHERICAL, DISTANCE):
            j["anchor_a"], j["anchor_b"] = _v3(p, 0), _v3(p, 12)
        else:
            (j["axis_a"], j["anchor_a"]), (j["axis_b"], j["anchor_b"]) = _frame_z(p, 0), _frame_z(p, 0x30)
            if kind == SHOULDER:
                lo, hi, cone, _torque, motor = struct.unpack_from("<4fI", p, 0x60)
                j.update(lower=lo * RADIANS, upper=hi * RADIANS, cone=cone * RADIANS, motor=motor & 0xFF)
            elif kind == REVOLUTE:
                lo, hi, _torque, motor = struct.unpack_from("<3fI", p, 0x60)
                j.update(lower=lo * RADIANS, upper=hi * RADIANS, motor=motor & 0xFF)
            elif kind == PRISMATIC:
                j["motor"] = p[0x74]
        for k in ("anchor_a", "anchor_b", "axis_a", "axis_b"):
            j[k] = [round(v, 6) for v in j[k]]
        for k in ("lower", "upper", "cone"):
            j[k] = round(j[k], 6) if math.isfinite(j[k]) else 0.0
        joints.append(j)
    if not any(b["type"] == DYNAMIC for b in bodies):
        return None
    return {"mode": mode, "bodies": bodies, "joints": joints}
