"""A colourway's paint baked into textures, at Install.

The studio (static/studio.js) paints inside a piece - a part, an area, a brush stroke - after Kira's Eclipse
Studio (its findings, our own code). Each stroke is an operation on one of the piece's textures: a mask (a
rectangle of coverage, 0-255, saved as runs: base64 of value u8, count u16 LE pairs, row after row) and its
colour, with ``ref``, the art's mean OKLab lightness under the mask. A painted texel takes the paint's hue and
colourfulness and the paint's lightness times how much lighter or darker the art is there than ``ref`` - easing
toward white above the paint's own lightness, never reaching it - so the part keeps its creases and highlights.

Install bakes them: each texture a colourway paints becomes a copy of it beside it (``painted_path``) - the art
in the colourway's armor colour, then the strokes over it, worked out exactly as colour.js's paintImage works them
for the preview - and the colourway's line in the client's colour table names the copies (``swaps``): the client
draws the colourway with them, and doesn't recolour their armor again.
"""

from __future__ import annotations

import base64
import math
import ntpath

ROOM = 0.6                                       # how far toward white a highlight may go (colour.js ROOM)


# -- the colour maths (colour.js, the same numbers) ------------------------------------------------------------------
def _to_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * max(c, 0.0) ** (1 / 2.4) - 0.055


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1 / 3), x)


def lin_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    l = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def lab_to_lin(L: float, a: float, b: float) -> tuple[float, float, float]:
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def cmax(L: float, h: float) -> float:
    """The most colourful an sRGB colour of lightness L and hue h (radians) can be (bisection on the gamut)."""
    ca, sa = math.cos(h), math.sin(h)
    lo, hi = 0.0, 0.4
    for _ in range(16):
        mid = (lo + hi) / 2
        c = lab_to_lin(L, mid * ca, mid * sa)
        if all(-1e-4 <= v <= 1.0001 for v in c):
            lo = mid
        else:
            hi = mid
    return lo


def light_mul(light: float) -> float:
    return 0.35 + 0.65 * light / 128 if light < 128 else 1 + 0.6 * (light - 128) / 127


def _smooth(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _num(k: dict, key: str, default: float) -> float:
    try:
        v = float(k.get(key, default))
    except (TypeError, ValueError):
        return default
    return v if v == v else default


def apply(rgb: tuple[float, float, float], k: dict) -> tuple[float, float, float]:
    """One colour (0-1 sRGB) recoloured by a colourway colour ``k`` (colour.js apply)."""
    m = max(1.0, *rgb)
    L, a, b = lin_to_lab(*(_to_lin(c / m) for c in rgb))
    C, h = math.hypot(a, b), math.atan2(b, a)
    cm = cmax(L, h)
    rel = C / cm if cm > 1e-5 else 0.0
    sat = _num(k, "sat", 1)
    base = min(1.0, max(0.0, rel * 1.25 * sat))
    r = base + (sat - base) * _num(k, "dye", 0)
    r *= 1 - 0.35 * _smooth(0.8, 1, L)
    Lo, ho = min(1.0, L * light_mul(_num(k, "light", 128))), _num(k, "hue", 0) * math.pi / 180
    Co = r * cmax(Lo, ho)
    return tuple(min(1.0, max(0.0, _to_srgb(c))) * m for c in lab_to_lin(Lo, Co * math.cos(ho), Co * math.sin(ho)))


def paint_texel(rgb: tuple[float, float, float], k: dict, ref: float) -> tuple[float, float, float]:
    """A texel of art (0-1 sRGB) painted with ``k`` all the way (colour.js paintTexel at full coverage)."""
    L0 = lin_to_lab(*(_to_lin(c) for c in rgb))[0]
    Lp = min(0.95, max(0.05, 0.72 * light_mul(_num(k, "light", 128))))
    room = (1 - Lp) * ROOM
    L = Lp * L0 / max(ref, 1e-3)
    if L > Lp:
        L = Lp + room * (1 - math.exp(-(L - Lp) / max(room, 1e-4)))
    L = min(1.0, max(0.0, L))
    h = _num(k, "hue", 0) * math.pi / 180
    C = _num(k, "sat", 1) * cmax(L, h)
    return tuple(min(1.0, max(0.0, _to_srgb(v))) for v in lab_to_lin(L, C * math.cos(h), C * math.sin(h)))


def _round(x: float) -> int:
    """JavaScript's Math.round: halves up."""
    return int(math.floor(x + 0.5))


# -- masks and textures ------------------------------------------------------------------------------------------------
def runs_to_mask(rect, runs: str) -> tuple[int, int, int, int, bytearray]:
    """An operation's mask: (x, y, w, h, coverage bytes) from its rectangle and runs (colour.js runsToMask)."""
    x, y, w, h = (int(v) for v in rect)
    data, raw, at = bytearray(w * h), base64.b64decode(runs), 0
    for i in range(0, len(raw) - 2, 3):
        if at >= len(data):
            break
        v, n = raw[i], raw[i + 1] | raw[i + 2] << 8
        end = min(len(data), at + n)
        data[at:end] = bytes([v]) * (end - at)
        at += n
    return x, y, w, h, data


def paint_rgba(rgba: bytes, w: int, h: int, ops: list[dict], base: dict | None) -> bytearray:
    """RGBA pixels painted: the art in ``base`` (the colourway's armor colour; None as made), then each operation
    through its mask, a texel worked out from the art as made and laid over what is there by the mask's coverage
    (colour.js paintImage). An operation made on another size of the texture is left out. Alpha is kept."""
    art = bytes(rgba)
    px = bytearray(art)
    if base:
        memo: dict[int, tuple[int, int, int]] = {}
        for i in range(0, len(px), 4):
            key = art[i] << 16 | art[i + 1] << 8 | art[i + 2]
            out = memo.get(key)
            if out is None:
                out = memo[key] = tuple(_round(v * 255) for v in apply((art[i] / 255, art[i + 1] / 255, art[i + 2] / 255), base))
            px[i:i + 3] = bytes(out)
    for op in ops:
        size = op.get("size")
        if size and (int(size[0]) != w or int(size[1]) != h):
            continue
        colour, ref = op.get("colour") or {}, float(op.get("ref") or 0.5)
        mx, my, mw, mh, mask = runs_to_mask(op["rect"], op["runs"])
        memo = {}
        for j in range(mh):
            ty = my + j
            if ty >= h:
                break
            row = j * mw
            for i in range(mw):
                c = mask[row + i]
                tx = mx + i
                if not c or tx >= w:
                    continue
                o = (ty * w + tx) * 4
                key = art[o] << 16 | art[o + 1] << 8 | art[o + 2]
                out = memo.get(key)
                if out is None:
                    out = memo[key] = paint_texel((art[o] / 255, art[o + 1] / 255, art[o + 2] / 255), colour, ref)
                cov = c / 255
                for q in range(3):
                    px[o + q] = _round(px[o + q] + (out[q] * 255 - px[o + q]) * cov)
    return px


def painted_path(path: str, entry: int) -> str:
    """Where a colourway's painted copy of a texture goes: beside it, its name with ``_p<the colourway's entry>``
    - before a trailing _m / _f / _u (an armor texture's sex), which the client reads off the name."""
    folder, name = ntpath.split(path.replace("/", "\\"))
    stem, ext = ntpath.splitext(name)
    tail = stem[-2:] if len(stem) > 2 and stem[-2] == "_" and stem[-1].lower() in "mfu" else ""
    stem = stem[:-2] if tail else stem
    return f"{folder}\\{stem}_p{entry}{tail}{ext or '.blp'}" if folder else f"{stem}_p{entry}{tail}{ext or '.blp'}"


def ops_of(way: dict | None) -> list[dict]:
    """A colourway's paint operations (well-formed ones)."""
    out = []
    for op in (way or {}).get("paint") or []:
        if isinstance(op, dict) and isinstance(op.get("runs"), str) and isinstance(op.get("rect"), (list, tuple)) \
                and len(op["rect"]) == 4 and int(op.get("tex") or 0) > 0:
            out.append(op)
    return out


def bake(pieces: list, paths: dict[int, str], read, say=print) -> tuple[dict[str, bytes], dict[int, dict[int, str]]]:
    """Each colourway's painted textures: ({path in the patch: BLP}, {colourway entry: {texture FileDataID: its
    painted copy's path}}). ``pieces``: retailpack.Piece (``colour``, ``entry``); ``paths``: where each texture
    is in the patch or the client; ``read(fdid)`` -> (bytes or None, why)."""
    from PIL import Image

    from ..formats import blp as BLP
    from .retailpack import part_colour

    made: dict[str, bytes] = {}
    swaps: dict[int, dict[int, str]] = {}
    for p in pieces:
        way = getattr(p, "colour", None)
        ops = ops_of(way if isinstance(way, dict) else None)
        if not ops:
            continue
        base = part_colour(way, "armor")
        for fdid in sorted({int(op["tex"]) for op in ops}):
            path = paths.get(fdid)
            if not path:
                say(f"!  {p.name}: its painted texture {fdid} isn't one the look has - that paint is left out")
                continue
            data, why = read(fdid)
            if not data:
                say(f"!  {p.name}: texture {fdid} isn't readable ({why}) - its paint is left out")
                continue
            try:
                img = BLP.decode_bytes(data, f"texture {fdid}").convert("RGBA")
            except ValueError as e:
                say(f"!  {p.name}: {e} - its paint is left out")
                continue
            w, h = img.size
            mine = [op for op in ops if int(op["tex"]) == fdid]
            px = paint_rgba(img.tobytes(), w, h, mine, base)
            out = Image.frombytes("RGBA", (w, h), bytes(px))
            target = painted_path(path, p.entry)
            made[target] = BLP.encode_dxt(out)
            swaps.setdefault(p.entry, {})[fdid] = target
        if p.entry in swaps:
            say(f"   {p.name}: {len(ops)} paint stroke(s) baked into {len(swaps[p.entry])} texture(s)")
    return made, swaps

