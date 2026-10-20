"""retroport race: the race's own helmets from BfA (helmets.py)."""

import math
import struct

import pytest

from retroport.dbc import DBCFile
from retroport.race import helm, helmets


def test_bfa_finds_each_helmets_model_for_the_race_by_its_resources():
    variants = {"helm_a": [100], "helm_b": [300], "helm_c": [400]}
    model_file_data = [{"FileDataID": f, "ModelResourcesID": r} for f, r in
                       ((100, 7), (200, 7), (201, 7), (202, 7), (300, 8), (301, 8), (400, 9))]
    comp = {100: {"RaceID": 1, "GenderIndex": 0, "ClassID": 0},
            200: {"RaceID": 32, "GenderIndex": 0, "ClassID": 0},
            202: {"RaceID": 32, "GenderIndex": 0, "ClassID": 12},          # a class's own model comes second
            201: {"RaceID": 32, "GenderIndex": 1, "ClassID": 0},
            301: {"RaceID": 32, "GenderIndex": 1, "ClassID": 12},          # only a class's: still taken
            300: {"RaceID": 1, "GenderIndex": 0, "ClassID": 0}}
    found = helmets.race_models(variants, model_file_data, comp, 32)
    assert found == {("helm_a", 0): 200, ("helm_a", 1): 201, ("helm_b", 1): 301}   # helm_c: no model for race 32


def test_what_a_helmet_hides_on_the_race_is_bfas_and_nothing_where_bfa_has_no_row_for_it():
    rows = [{"RaceID": 32, "HideGeosetGroup": 0, "HelmetGeosetVisDataID": 246},
            {"RaceID": 32, "HideGeosetGroup": 7, "HelmetGeosetVisDataID": 246},
            {"RaceID": 1, "HideGeosetGroup": 1, "HelmetGeosetVisDataID": 247}]
    assert helmets.race_hides(rows, 32) == {246: {0, 7}, 247: set()}


def test_the_clients_helmets_are_the_model_names_with_a_template_model(tmp_path):
    idi = DBCFile(25)
    for i, name in enumerate(("Helm_A_01.mdx", "helm_a_01.mdx", "Sword_B.mdx", "Helm_C.mdx", "")):
        r = [0] * 25
        r[0], r[1] = i + 1, idi.add_string(name)
        idi.add_record(r)
    have = {"Item\\ObjectComponents\\Head\\Helm_A_01_HuM.m2", "Item\\ObjectComponents\\Head\\Helm_C_HuF.m2"}
    assert helmets.helmet_bases(idi, have.__contains__, "Hu") == ["Helm_A_01", "Helm_C"]
    listfile = tmp_path / "listfile.csv"
    listfile.write_text("100;item/objectcomponents/head/helm_a_01_hum.m2\n"
                        "200;item/objectcomponents/head/helm_a_01_kt_m.m2\n"
                        "201;item/objectcomponents/head/helm_a_01_hum00.skin\n"
                        "300;item/objectcomponents/head/helm_c_za_f.m2\n"
                        "400;item/objectcomponents/head/helm_other_hum.m2\n")
    assert helmets.listfile_variants(str(listfile), ["Helm_A_01", "Helm_C"]) == {"helm_a_01": [100, 200], "helm_c": [300]}


def _quaternion_key(degrees: float) -> bytes:
    half = math.radians(degrees) / 2
    return struct.pack("<4h", *(helm._compress(v) for v in (0.0, math.sin(half), 0.0, math.cos(half))))


def _chunk(magic: bytes, payload: bytes) -> bytes:
    return magic + struct.pack("<I", len(payload)) + payload


def _bones_and_attachments(turn_keys: list[bytes]) -> tuple[bytes, bytes]:
    """SKB1 and SKA1 payloads: bone 0 the head, bone 1 the helmet's (rotation keys ``turn_keys`` on a
    global sequence), attachment 11 on bone 1 at its pivot."""
    pivot = (-0.0663, 0.0, 2.3905)
    skb = bytearray(16)
    bones_at = len(skb)
    skb.extend(bytes(0x58 * 2))
    struct.pack_into("<iIh", skb, bones_at, 6, 0, -1)
    struct.pack_into("<iIh", skb, bones_at + 0x58, -1, helm.BONE_TRANSFORMED, 0)
    struct.pack_into("<3f", skb, bones_at + 0x58 + 0x4C, *pivot)
    keys_at = len(skb)
    skb.extend(b"".join(turn_keys))
    times_at = len(skb)
    skb.extend(struct.pack(f"<{len(turn_keys)}I", *range(len(turn_keys))))
    outer = len(skb)
    skb.extend(struct.pack("<II", len(turn_keys), times_at) + struct.pack("<II", len(turn_keys), keys_at))
    struct.pack_into("<HhIIII", skb, bones_at + 0x58 + 0x24, 1, 0, 1, outer, 1, outer + 8)
    struct.pack_into("<II", skb, 0, 2, bones_at)
    ska = bytearray(16)
    att_at = len(ska)
    ska.extend(struct.pack("<IHH3f", helm.HELM, 1, 0, *pivot) + bytes(0x14))
    lookup_at = len(ska)
    ska.extend(struct.pack("<12h", *([-1] * 11 + [0])))
    struct.pack_into("<IIII", ska, 0, 1, att_at, 12, lookup_at)
    return bytes(skb), bytes(ska)


def test_the_source_attachment_comes_from_the_skeleton():
    skb, ska = _bones_and_attachments([_quaternion_key(2.82)] * 2)
    md20 = bytearray(0x130)
    md20[0:4] = b"MD20"
    files = {1: _chunk(b"MD21", bytes(md20)) + _chunk(b"SKID", struct.pack("<I", 2)),
             2: _chunk(b"SKL1", bytes(8)) + _chunk(b"SKB1", skb) + _chunk(b"SKA1", ska)}
    att = helmets.source_attachment(files.__getitem__, 1)
    assert att.bone == 1 and att.position == pytest.approx((-0.0663, 0.0, 2.3905))
    assert att.flags == helm.BONE_TRANSFORMED
    assert att.keys == {0x10: None, 0x24: _quaternion_key(2.82), 0x38: None}
    skb, ska = _bones_and_attachments([_quaternion_key(2.82), _quaternion_key(5.0)])
    files[2] = _chunk(b"SKB1", skb) + _chunk(b"SKA1", ska)
    with pytest.raises(helmets.HelmetsError, match="animates"):
        helmets.source_attachment(files.__getitem__, 1)


def _rotate(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def test_a_template_helmet_is_carried_to_where_the_fit_puts_it_from_the_sources_attachment():
    pivot = (-0.0663, 0.0, 2.3905)
    fit = helm.HelmFit(scales=(1.29, 1.52, 1.21), spot=(-0.059, 0.0, 2.678), old=pivot, bone=1,
                       scaled_bone=True, turn=-8.2)
    source = helm.Attachment(1, pivot, helm.BONE_TRANSFORMED, {0x10: None, 0x24: _quaternion_key(2.82), 0x38: None})
    linear, offset = helmets.carry_transform(fit, pivot, source)
    r_b = helmets._matrix(helm._quaternion(struct.unpack("<4h", source.keys[0x24])))
    c, n = math.cos(math.radians(fit.turn)), math.sin(math.radians(fit.turn))
    for h in ((0.1, 0.0, 0.0), (0.0, 0.2, -0.1), (-0.15, -0.05, 0.3)):
        carried = [a + b for a, b in zip(_rotate(linear, h), offset)]
        # the client: pivot + R (P + h' - pivot); the fit: spot + R_fit S_fit h
        landed = [p + q for p, q in zip(pivot, _rotate(r_b, [a + b - p for a, b, p in zip(source.position, carried, pivot)]))]
        s = [f * v for f, v in zip(fit.scales, h)]
        wanted = [fit.spot[0] + c * s[0] + n * s[2], fit.spot[1] + s[1], fit.spot[2] - n * s[0] + c * s[2]]
        assert landed == pytest.approx(wanted, abs=1e-5)


def _helmet(particles: int = 0) -> bytes:
    m2 = bytearray(0x130)
    m2[0:4] = b"MD20"

    def array(slot: int, payload: bytes, count: int) -> None:
        struct.pack_into("<II", m2, slot, count, len(m2))
        m2.extend(payload)
    verts = b""
    for p, nrm in (((0.1, 0.0, 0.0), (1.0, 0.0, 0.0)), ((0.0, 0.1, 0.2), (0.0, 0.0, 1.0))):
        rec = bytearray(48)
        struct.pack_into("<3f", rec, 0, *p)
        struct.pack_into("<3f", rec, 20, *nrm)
        verts += bytes(rec)
    array(0x3C, verts, 2)
    bone = bytearray(0x58)
    struct.pack_into("<iIh", bone, 0, -1, 0, -1)
    array(0x2C, bytes(bone), 1)
    array(0x1C, bytes(0x40), 1)
    name = b"item\\objectcomponents\\head\\glow.blp\0"
    tex_at = len(m2) + 32
    array(0x50, struct.pack("<IIII", 2, 0, 0, 0) + struct.pack("<IIII", 0, 0, len(name), tex_at), 2)
    m2.extend(name)
    struct.pack_into("<I", m2, 0x128, particles)
    return bytes(m2)


def test_carrying_moves_points_turns_normals_and_refits_the_bounds():
    turn = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]       # 90 degrees about z
    out = helmets.carry(_helmet(), [[2 * v for v in row] for row in turn], [0.0, 0.0, 1.0])
    n_v, o_v = struct.unpack_from("<II", out, 0x3C)
    assert struct.unpack_from("<3f", out, o_v) == pytest.approx((0.0, 0.2, 1.0))
    assert struct.unpack_from("<3f", out, o_v + 20) == pytest.approx((0.0, 1.0, 0.0))
    assert struct.unpack_from("<3f", out, o_v + 48) == pytest.approx((-0.2, 0.0, 1.4))
    assert struct.unpack_from("<6f", out, 0xA0) == pytest.approx((-0.2, 0.0, 1.0, 0.0, 0.2, 1.4))
    n_s, o_s = struct.unpack_from("<II", out, 0x1C)
    assert struct.unpack_from("<6f", out, o_s + 0x20) == pytest.approx((-0.2, 0.0, 1.0, 0.0, 0.2, 1.4))
    _n, o_b = struct.unpack_from("<II", out, 0x2C)
    assert struct.unpack_from("<3f", out, o_b + 0x4C) == pytest.approx((0.0, 0.0, 1.0))
    with pytest.raises(helmets.HelmetsError, match="particles"):
        helmets.carry(_helmet(particles=1), turn, [0.0, 0.0, 0.0])
    assert helmets.texture_names(_helmet()) == ["item\\objectcomponents\\head\\glow.blp"]


def _layered(textures: int, materials: list[tuple[int, int]], combos: tuple[list[int], list[int], list[int]],
             batches: list[tuple[int, int, int, int, int]]) -> tuple[bytes, bytes, bytes]:
    """(model, converted skin, BfA skin): ``batches`` as (BfA shader, texture count, material,
    flags, texture lookup index); the converted skin has the shaders dropped as wotlkconv drops
    them (0 for the shader table's entries and any id past 0xFF) and BfA's flags kept."""
    from wotlkconv.m2.model import M2Model
    from wotlkconv.m2.write import write_md20
    model = M2Model(version=264)
    model.textures = [{"type": 2, "flags": 0, "filename": ""}] + [
        {"type": 0, "flags": 0, "filename": f"item/objectcomponents/head/layer{i}.blp"} for i in range(1, textures)]
    model.materials = [{"flags": f, "blending_mode": b} for f, b in materials]
    model.texture_combos, model.texture_coord_combos, model.texture_weight_combos = combos
    model.texture_transform_combos = [0xFFFF] * len(combos[0])
    model.num_skin_profiles = 1

    def skin(converted: bool) -> bytes:
        out = bytearray(b"SKIN" + bytes(0x2C))
        records = b""
        for i, (shader, count, material, flags, lookup) in enumerate(batches):
            kept = 0 if converted and (shader & 0x8000 or shader > 0xFF) else shader
            records += struct.pack("<BBHHHhHHHHHHH", flags, 0, kept, i, 0, -1, material, 0, count, lookup, 0, 0, 0)
        struct.pack_into("<II", out, 0x24, len(batches), len(out))
        return bytes(out + records)
    return write_md20(model), skin(True), skin(False)


def _skin_batches(skin: bytes) -> list[tuple]:
    n, o = struct.unpack_from("<II", skin, 0x24)
    return [struct.unpack_from("<BBHHHhHHHHHHH", skin, o + i * 24) for i in range(n)]


def test_bfas_reflection_shaders_are_drawn_as_warcraftxls_helmets_draw_them():
    from wotlkconv.m2.model import parse_md20
    # a plate (0x8000: diffuse x reflection, the diffuse over it by its alpha) and an eye glow (0x10)
    m2, skin, source = _layered(2, [(0, 0), (16, 2)], ([0, 1], [0, 0xFFFF], [0]),
                                [(0x8000, 2, 0, 0x90, 0), (0x10, 1, 1, 0x10, 0)])
    out, (out_skin,), redrawn = helmets.wotlk_layers(m2, [skin], [source])
    model = parse_md20(out)
    assert model.global_flags & helmets.COMBINER_COMBOS and model.texture_combiner_combos == [1, 4]
    batches = _skin_batches(out_skin)
    assert len(batches) == 3 and redrawn == 2
    base, over, glow = batches
    assert (base[0], base[2], base[8], base[6], base[7]) == (0x10, 0, 2, 0, 0)            # Mod, Mod2x
    assert (over[2], over[8], over[6], over[7], over[3]) == (0, 1, 1, 1, base[3])          # diffuse, alpha, layer 1
    assert model.materials[over[6]] == {"flags": 16, "blending_mode": 2}
    assert (glow[2], glow[8]) == (0, 1)                                                    # combos[0]: Mod
    again = helmets.wotlk_layers(out, [out_skin], [source])
    assert again == (out, [out_skin], 0)                                                   # a table already: as it is


def test_0x8001_adds_the_reflection_as_a_layer_and_others_keep_the_diffuse():
    from wotlkconv.m2.model import parse_md20
    m2, skin, source = _layered(3, [(1, 0)], ([0, 1, 2], [0, 0xFFFF, 0], [0, 0]),
                                [(0x8001, 2, 0, 0xD0, 0), (0x0E, 2, 0, 0x80, 1)])
    out, (out_skin,), redrawn = helmets.wotlk_layers(m2, [skin], [source])
    model = parse_md20(out)
    assert not model.global_flags & helmets.COMBINER_COMBOS and redrawn == 2
    base, glow, plain = _skin_batches(out_skin)
    assert (base[0], base[2], base[8], base[9]) == (0x10, 0, 1, 0)
    assert (glow[8], glow[9], glow[10], glow[11], glow[7]) == (1, 1, 1, 1, 1)              # reflection, its coordinates
    assert model.materials[glow[6]] == {"flags": 16, "blending_mode": 4}                   # added
    assert (plain[0], plain[8], plain[9]) == (0, 1, 1)                                     # one texture, the diffuse
    with pytest.raises(helmets.HelmetsError, match="batches"):
        helmets.wotlk_layers(m2, [skin], [source[:0x24] + struct.pack("<II", 1, struct.unpack_from("<I", source, 0x28)[0]) + source[0x2C:]])


def test_bfas_own_two_op_shaders_go_through_the_table_when_a_reflection_needs_one():
    """The Horde create scene: a sign post's reflection (0x8002) needs the combiner table; its fire
    glows (0x4014: Mod, then Mod2x on the second UV set) keep both textures, their ops in it."""
    from wotlkconv.m2.model import parse_md20
    m2, skin, source = _layered(4, [(0, 0), (0x15, 4)], ([1, 2, 3, 1], [0, 0xFFFF, 0, 1], [0, 0]),
                                [(0x8002, 2, 0, 0x80, 0), (0x4014, 2, 1, 0x88, 2), (0x10, 1, 0, 0x10, 0)])
    assert helmets.needs_layers([source])
    out, (out_skin,), redrawn = helmets.wotlk_layers(m2, [skin], [source], own_ops=True)
    combos = parse_md20(out).texture_combiner_combos
    post, over, fire, plain = _skin_batches(out_skin)
    assert (post[8], tuple(combos[post[2]:post[2] + 2])) == (2, (1, 3))                   # Mod, Add
    assert (over[8], combos[over[2]], over[7]) == (1, 1, 1)                                # the diffuse on top
    assert (fire[8], fire[9], tuple(combos[fire[2]:fire[2] + 2])) == (2, 2, (1, 4))        # both: Mod, Mod2x
    assert (plain[8], combos[plain[2]]) == (1, 1)                                          # Mod
    assert redrawn == 3
    # a helmet's draws its diffuse alone, as WarcraftXL's own helmets do
    out, (out_skin,), _redrawn = helmets.wotlk_layers(m2, [skin], [source])
    _post, _over, fire, _plain = _skin_batches(out_skin)
    assert (fire[8], parse_md20(out).texture_combiner_combos[fire[2]]) == (1, 1)
    # without a reflection there is no table, and a scene draws as converted
    _m2, _skin, plain_source = _layered(4, [(0, 0), (0x15, 4)], ([1, 2, 3, 1], [0, 0xFFFF, 0, 1], [0, 0]),
                                        [(0x4014, 2, 1, 0x88, 2), (0x10, 1, 0, 0x10, 0)])
    assert not helmets.needs_layers([plain_source])


def test_a_scene_without_a_reflection_is_left_as_converted(tmp_path):
    m2, skin, source = _layered(4, [(0, 0), (0x15, 4)], ([1, 2, 3, 1], [0, 0xFFFF, 0, 1], [0, 0]),
                                [(0x4014, 2, 1, 0x88, 2), (0x10, 1, 0, 0x10, 0)])
    path = tmp_path / "UI_Scene.m2"
    path.write_bytes(m2)
    (tmp_path / "UI_Scene00.skin").write_bytes(skin)
    bfa = b"MD21" + struct.pack("<I", len(m2)) + m2 + b"SFID" + struct.pack("<II", 4, 77)
    assert helmets.redraw_scene(str(path), bfa, {77: source}.__getitem__) == (0, 0)
    assert path.read_bytes() == m2 and (tmp_path / "UI_Scene00.skin").read_bytes() == skin
    # with one, it is redrawn
    m2, skin, source = _layered(4, [(0, 0), (0x15, 4)], ([1, 2, 3, 1], [0, 0xFFFF, 0, 1], [0, 0]),
                                [(0x8002, 2, 0, 0x80, 0), (0x4014, 2, 1, 0x88, 2)])
    path.write_bytes(m2)
    (tmp_path / "UI_Scene00.skin").write_bytes(skin)
    bfa = b"MD21" + struct.pack("<I", len(m2)) + m2 + b"SFID" + struct.pack("<II", 4, 77)
    assert helmets.redraw_scene(str(path), bfa, {77: source}.__getitem__) == (2, 0)
    assert len(_skin_batches((tmp_path / "UI_Scene00.skin").read_bytes())) == 3


def test_a_scenes_added_glows_are_layers_of_their_own():
    """The Mag'har select scene: a bonfire and a lamppost draw their glow over the diffuse (0x800A,
    Opaque_AddAlpha_Wgt, both on the first UV set) - black when 3.3.5 multiplied them together -
    beside god rays through their mask (0x4011: Mod, Mod) and a cloud (0x10)."""
    from wotlkconv.m2.model import parse_md20
    m2, skin, source = _layered(5, [(0, 0), (0x15, 4)], ([1, 2, 3, 4, 1], [0, 0, 0, 0, 0], [0, 1]),
                                [(0x800A, 2, 0, 0x80, 0), (0x4011, 2, 1, 0x88, 2), (0x10, 1, 1, 0x10, 4)])
    assert helmets.needs_layers([source])
    out, (out_skin,), redrawn = helmets.wotlk_layers(m2, [skin], [source], own_ops=True)
    model = parse_md20(out)
    combos = model.texture_combiner_combos
    assert model.global_flags & helmets.COMBINER_COMBOS and redrawn == 3
    base, glow, rays, cloud = _skin_batches(out_skin)
    assert (base[8], base[9], combos[base[2]]) == (1, 0, 1)                                # the diffuse, Mod
    assert (glow[8], glow[9], glow[10], glow[11], glow[7]) == (1, 1, 1, 1, 1)              # the glow, its UVs, weight
    assert model.materials[glow[6]] == {"flags": 16, "blending_mode": 4}                   # added
    assert (rays[8], rays[9], tuple(combos[rays[2]:rays[2] + 2])) == (2, 2, (1, 1))        # rays x mask
    assert (cloud[8], combos[cloud[2]]) == (1, 1)
    # a helmet's 0x800A draws its diffuse alone, as WarcraftXL's own helmets do
    out, (out_skin,), _redrawn = helmets.wotlk_layers(m2, [skin], [source])
    assert len(_skin_batches(out_skin)) == 3 and _skin_batches(out_skin)[0][8] == 1


def _emitter(rows: int, cols: int, head: list[int], z: float) -> dict:
    """A particle emitter with every field of 3.3.5's layout at its zero, but these."""
    from wotlkconv.m2 import schemas
    from wotlkconv.m2.types import PartTrack, Track
    p = {}
    for name, (kind, fmt) in schemas.PARTICLE_264.fields:
        if kind == "p":
            p[name] = 0 if len(fmt) == 1 else tuple(0.0 for _ in fmt)
        elif kind == "arr":
            p[name] = "" if fmt == "char" else []
        elif kind == "trk":
            p[name] = Track(kind=fmt, timestamps=[[0]], values=[[0.0 if fmt == "f32" else 0]])
        else:
            p[name] = PartTrack(kind=fmt)
    p["texture_dimensions_rows"], p["texture_dimensions_columns"] = rows, cols
    p["head_cell_track"] = PartTrack(kind="u16", times=list(range(len(head))), values=list(head))
    p["z_source"] = Track(kind="f32", timestamps=[[0]], values=[[z]])
    return p


def test_emitters_get_warcraftxls_z_source_and_one_cell_textures_cell_zero():
    from wotlkconv.m2.model import M2Model, parse_md20
    from wotlkconv.m2.write import write_md20
    model = M2Model(version=264)
    model.particles = [_emitter(1, 1, [1, 1], 255.0),          # BfA's Kul Tiran eye glow
                       _emitter(4, 4, [0, 7, 8, 16], 255.0),   # a flipbook keeps its cells
                       _emitter(1, 1, [0, 0], 0.5),            # already fine
                       _emitter(1, 1, [], 0.0)]                # no cells: WarcraftXL's four zeros
    out, changed = helmets.wotlk_particles(write_md20(model))
    glow, book, fine, bare = parse_md20(out).particles
    assert changed == 3
    assert glow["head_cell_track"].values == [0, 0] and glow["z_source"].values == [[0.0]]
    assert book["head_cell_track"].values == [0, 7, 8, 16] and book["z_source"].values == [[0.0]]
    assert fine["z_source"].values == [[0.5]]
    assert (bare["head_cell_track"].times, bare["head_cell_track"].values) == ([0, 16384, 16384, 32767], [0, 0, 0, 0])
    assert helmets.wotlk_particles(out) == (out, 0)            # rebuilding changes nothing
