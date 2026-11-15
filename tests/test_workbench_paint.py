"""The studio's paint baked at Install (paint.py) as the preview paints it (colour.js), and the colour table's
effect and paint columns the client reads."""

import io
import types

from PIL import Image

from retroport.formats import blp as BLP
from retroport.workbench import paint as P
from retroport.workbench import retailpack as RP

K = {"hue": 25, "sat": 0.95, "light": 120, "dye": 0}
BASE = {"hue": 270, "sat": 1, "light": 150, "dye": 0.3}
# four texels of art; the mask over the last three at 255, 128 and 40 (colour.js maskToRuns of it)
ART = bytes([128, 102, 77, 255, 230, 230, 217, 255, 26, 51, 153, 255, 5, 5, 5, 255])
OP = {"tex": 1, "size": [4, 1], "rect": [1, 0, 3, 1], "runs": "/wEAgAEAKAEA", "colour": K, "ref": 0.4321}


def test_the_bake_paints_as_the_preview_does():
    # colour.js paintImage of the same, in the browser: the art in BASE, the op over it
    assert list(P.paint_rgba(ART, 4, 1, [OP], BASE)) == [89, 115, 212, 255, 253, 198, 192, 255, 138, 33, 125, 255, 10, 5, 15, 255]
    # colour.js paintTexel and apply of one colour
    assert P.paint_texel((0.5, 0.4, 0.3), K, 0.4321) == (0.9884256868301112, 0.6259639795798642, 0.5959428692614455)
    assert all(abs(a - b) < 1e-12 for a, b in zip(P.apply((0.5, 0.4, 0.3), BASE),
                                                   (0.3489418828270858, 0.4506129301794973, 0.8347598488301784)))


def test_a_mask_reads_back_and_one_of_another_size_is_left_out():
    assert P.runs_to_mask([1, 0, 3, 1], OP["runs"]) == (1, 0, 3, 1, bytearray([255, 128, 40]))
    assert bytes(P.paint_rgba(ART, 4, 1, [dict(OP, size=[8, 2])], None)) == ART


def test_a_painted_copy_sits_beside_its_texture():
    assert P.painted_path("item\\texturecomponents\\torsouppertexture\\foo_m.blp", 16000123) == \
        "item\\texturecomponents\\torsouppertexture\\foo_p16000123_m.blp"
    assert P.painted_path("item/objectcomponents/weapon/sword_01.blp", 5) == "item\\objectcomponents\\weapon\\sword_01_p5.blp"
    assert P.painted_path("item\\x\\cape_u.blp", 7) == "item\\x\\cape_p7_u.blp"


def _blp(colour=(128, 102, 77, 255), size=(8, 8)) -> bytes:
    return BLP.encode_dxt(Image.new("RGBA", size, colour))


def test_install_bakes_each_painted_texture_once_a_colourway():
    runs = P.base64.b64encode(bytes([255, 64, 0])).decode()             # all 64 texels of an 8x8
    way = {"key": "c1", "name": "Red", "colour": BASE, "parts": {"armor": "off"},
           "paint": [{"tex": 42, "size": [8, 8], "rect": [0, 0, 8, 8], "runs": runs, "colour": K, "ref": 0.5},
                     {"tex": 99, "size": [8, 8], "rect": [0, 0, 8, 8], "runs": runs, "colour": K, "ref": 0.5}]}
    pieces = [types.SimpleNamespace(entry=16000001, name="Hood", colour=way),
              types.SimpleNamespace(entry=16000002, name="Plain", colour={"colour": BASE})]
    said = []
    made, swaps = P.bake(pieces, {42: "item\\objectcomponents\\head\\hood_01.blp"},
                         lambda f: (_blp(), "") if f == 42 else (None, "missing"), said.append)
    assert swaps == {16000001: {42: "item\\objectcomponents\\head\\hood_01_p16000001.blp"}}
    path, = made
    img = BLP.decode_bytes(made[path]).convert("RGBA")
    art = BLP.decode_bytes(_blp()).convert("RGBA").getpixel((3, 3))      # the art as the texture holds it
    want = tuple(round(v * 255) for v in P.paint_texel(tuple(c / 255 for c in art[:3]), K, 0.5))
    assert img.size == (8, 8) and all(abs(a - b) <= 8 for a, b in zip(img.getpixel((3, 3))[:3], want))   # DXT1's steps
    assert any("99" in s for s in said)                                    # a texture the look hasn't: said, left out


def test_the_colour_table_names_effects_and_painted_textures():
    way = {"key": "c1", "colour": {"hue": 140, "sat": 1, "light": 180, "dye": 0},
           "fx": {"893889": {"hue": 10, "sat": 0.5, "light": 128, "dye": 0}, "1118649": "off", "5": "off"}}
    pieces = [types.SimpleNamespace(entry=16000000, display=722371, colour=way)]
    paths = {893889: "Spells/Fire_Glow.BLP", 1118649: "item\\objectcomponents\\weapon\\felo_glow.blp"}
    text = RP.colour_table(pieces, paths, {16000000: {7413812: "item\\objectcomponents\\weapon\\felo_p16000000.blp"}}).decode()
    line, = [l for l in text.splitlines() if not l.startswith("#")]
    fields = line.split("\t")
    assert fields[6] == "item\\objectcomponents\\weapon\\felo_glow=-|spells\\fire_glow=10,0.5,128,0"   # 5: no path, left out
    assert fields[7] == "7413812=item\\objectcomponents\\weapon\\felo_p16000000.blp"
