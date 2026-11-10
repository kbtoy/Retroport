"""The 3D preview as the x64 client draws: which display models are collections, the physics it hangs, the
particle and ribbon data the viewer plays, and a mount's state kit."""

import math
import struct
import types

from retroport.workbench import models as M
from retroport.workbench import physics as P
from retroport.workbench import server as S


def _row(mr, mt, mm=(0, 0)):
    """A display row: model resources, materials, model types, then geoset groups and the rest at 0."""
    return [mr[0], mr[1], mm[0], mm[1], mt[0], mt[1], *(0,) * 6, *(0,) * 6, 0, 0, 0]


def _index(displays, model_files, comp_models=None, collections=()):
    return M.DisplayIndex({"displays": {str(k): v for k, v in displays.items()},
                           "model_files": {str(k): v for k, v in model_files.items()},
                           "comp_models": {str(k): v for k, v in (comp_models or {}).items()}, "tex_files": {},
                           "comp_tex": {}, "sections": {}, "model_mat": {}, "collection_files": sorted(collections)})


# -- collections, as RetailItemIndex.cpp's Attach decides ------------------------------------------
def test_a_belts_race_and_sex_collection_is_skinned_whatever_its_model_type_says():
    # Fierce Gladiator's Plate Girdle: a buckle, and a collection per race and sex - both ModelType 0
    idx = _index({1: _row((10, 11), (0, 0))}, {10: [100], 11: [200, 201]},
                 {200: [1, 0, 0, -1], 201: [32, 0, 0, -1]}, collections={200, 201})
    got = idx.models(1, 32, 0, 6)
    assert [(m["fdid"], m["type"], m["attach"]) for m in got] == [(100, M.ATTACHED, 53), (201, M.COLLECTION, -1)]


def test_a_collection_folder_belt_made_for_the_waist_point_is_hung_there():
    idx = _index({1: _row((10, 0), (0, -1))}, {10: [300]}, collections={300})
    assert [(m["type"], m["attach"]) for m in idx.models(1, 1, 0, 6)] == [(M.ATTACHED, 53)]
    idx = _index({1: _row((10, 0), (1, -1))}, {10: [300]}, collections={300})
    assert idx.models(1, 1, 0, 6)[0]["type"] == M.COLLECTION                  # ModelType 1 says skinned


def test_a_helm_is_a_collection_only_in_the_folder_and_by_its_model_type():
    rows = {1: _row((10, 0), (0, -1)), 2: _row((10, 0), (1, -1)), 3: _row((11, 0), (1, -1)), 4: _row((10, 10), (0, 0))}
    idx = _index(rows, {10: [400], 11: [401]}, collections={400})
    assert (idx.models(1, 1, 0, 1)[0]["type"], idx.models(1, 1, 0, 1)[0]["attach"]) == (M.ATTACHED, 11)
    assert idx.models(2, 1, 0, 1)[0]["type"] == M.COLLECTION
    assert idx.models(3, 1, 0, 1)[0]["type"] == M.ATTACHED                    # ModelType 1 outside the folder
    assert [m["attach"] for m in idx.models(4, 1, 0, 1)] == [11, 55]          # a second model: the head's top


def test_shoulders_hang_by_their_side_cloaks_by_model_type_and_held_items_wait_for_their_hand():
    idx = _index({1: _row((10, 10), (0, 0)), 2: _row((12, 0), (1, -1)), 3: _row((12, 0), (4, -1)), 4: _row((13, 0), (0, -1))},
                 {10: [500, 501], 12: [600], 13: [700]}, {500: [0, 2, 0, 0], 501: [0, 2, 0, 1]}, collections={500, 501, 700})
    assert [(m["position"], m["type"], m["attach"]) for m in idx.models(1, 1, 0, 3)] == [(0, M.ATTACHED, 6), (1, M.ATTACHED, 5)]
    assert idx.models(2, 1, 0, 16)[0]["type"] == M.COLLECTION
    assert (idx.models(3, 1, 0, 16)[0]["type"], idx.models(3, 1, 0, 16)[0]["attach"]) == (M.ATTACHED, 12)
    assert idx.models(4, 1, 0, 13)[0]["attach"] == -1                         # the server's hand point
    assert idx.models(4, 1, 0, 0)[0]["type"] == M.COLLECTION                  # no slot given: by its folder


def test_without_a_listfile_model_type_1_alone_says_collection():
    idx = M.DisplayIndex({"displays": {"1": _row((10, 11), (0, 1))}, "model_files": {"10": [1], "11": [2]}, "comp_models": {},
                          "tex_files": {}, "comp_tex": {}, "sections": {}, "model_mat": {}})
    assert idx.collection_files is None
    assert [m["type"] for m in idx.models(1, 1, 0, 6)] == [M.ATTACHED, M.COLLECTION]


def test_the_display_index_reads_the_listfile_for_the_collection_folders(tmp_path):
    listfile = tmp_path / "listfile.csv"
    listfile.write_text("100;item/objectcomponents/waist/buckle_a.m2\n200;item/objectcomponents/collections/belt_hu_m.m2\n"
                        "300;item/objectcomponents/collection/cape_be_m.m2\n9;interface/x.blp\n", encoding="utf-8")
    tables = {"ItemDisplayInfo": [(1, {"ModelResourcesID": [10, 11], "ModelMaterialResourcesID": [0, 0], "ModelType": [0, 0],
                                       "GeosetGroup": [0] * 6, "AttachmentGeosetGroup": [0] * 6, "HelmetGeosetVis": [0, 0]})],
              "ModelFileData": [(1, {"ModelResourcesID": 10, "FileDataID": 100}), (2, {"ModelResourcesID": 11, "FileDataID": 200}),
                                (3, {"ModelResourcesID": 11, "FileDataID": 300}), (4, {"ModelResourcesID": 12, "FileDataID": 400})]}
    src = types.SimpleNamespace(spec=types.SimpleNamespace(label="Retail"), listfile=str(listfile),
                                table=lambda name: tables.get(name, []))
    idx = M.DisplayIndex(M.DisplayIndex.build(src).to_json())               # as the cache keeps it
    assert idx.collection_files == {200, 300}


def test_the_outfit_skins_a_belts_collection_and_hangs_its_buckle_and_a_weapon_in_hand():
    idx = _index({1: _row((10, 11), (0, 0)), 2: _row((12, 0), (0, -1))}, {10: [100], 11: [201], 12: [700]},
                 {201: [32, 0, 0, -1]}, collections={201})
    fake = types.SimpleNamespace(displays=lambda key: idx, race_ids=lambda key, race: (32, 32),
                                 mesh=lambda key, fdid, textures, anim=0: {"fdid": fdid}, display_glows=lambda key, d: [],
                                 race_name=lambda key, r: str(r))
    out = S.Workbench.outfit(fake, "retail", "kt", 0, [(1, 6), (2, 13)])
    belt, weapon = out["pieces"]
    assert [(m["fdid"], m["type"], m["attach"]) for m in belt["models"]] == [(100, M.ATTACHED, 53), (201, M.COLLECTION, -1)]
    assert weapon["models"][0]["attach"] == 1                                 # a one-hand weapon: the right hand


# -- physics -----------------------------------------------------------------------------------------
def _chunk(name, payload):
    return name[::-1].encode("ascii") + struct.pack("<I", len(payload)) + payload


def _frame(z, origin, scale=1.0):
    x = [1.0, 0.0, 0.0] if abs(z[0]) < 0.9 else [0.0, 1.0, 0.0]
    return struct.pack("<12f", *(c * scale for c in x), 0, 0, 0, *(c * scale for c in z), *origin)


def _phys():
    # BDY4 (0x30): type, bone, position, first shape, count, gravity scale, inertia, damping x2, carry, group
    body = "<HH3fHxxi5fH2x"
    bodies = struct.pack(body, 0, 0, 0, 0, 0, 0, 0, 1.0, 1.0, 0, 0, 0, 0x8000) + \
        struct.pack(body, 1, 3, 0, 0, 1, 0, 1, 0.5, 1.0, 0, 0, 0, 0)
    # SHP2 (0x20): kind, index, -, friction, restitution, density, -
    shape = struct.pack("<HH4f3f", 1, 0, 0.0, 0.2, 0.0, 1000.0, 0, 0, 0)
    capsule = struct.pack("<7f", 0, 0, 0, 0, 0, 1, 0.1)
    shoulder = _frame([0, 0, 1], [0, 0, 1], scale=2.0) + _frame([0, 0, 1], [0, 0, 0]) + \
        struct.pack("<4fI2f", -20.0, 20.0, 45.0, 0.0, 0, 1.0, 0.7)
    join = struct.pack("<IIIHH", 0, 1, 0, 1, 0)
    return (_chunk("PHYS", struct.pack("<H", 6)) + _chunk("PHYT", struct.pack("<I", 4)) + _chunk("BDY4", bodies) +
            _chunk("SHP2", shape) + _chunk("CAPS", capsule) + _chunk("SHJ2", shoulder) + _chunk("JOIN", join) + b"\0" * 8)


def test_a_phys_reads_its_bodies_masses_and_a_shoulders_limits():
    ph = P.read(_phys())
    assert ph["mode"] == 4 and [b["type"] for b in ph["bodies"]] == [P.KINEMATIC, P.DYNAMIC]
    hung = ph["bodies"][1]
    assert hung["bone"] == 3 and hung["position"] == [0.0, 0.0, 1.0] and hung["gravity"] == 0.5
    want = 1000 * (math.pi * 0.01 * 1 + 4 / 3 * math.pi * 0.001)
    assert abs(hung["mass"] - want) < 1e-3 and hung["com"] == [0.0, 0.0, 0.5]
    j = ph["joints"][0]
    assert (j["a"], j["b"], j["kind"]) == (0, 1, P.SHOULDER)
    assert j["axis_a"] == [0.0, 0.0, 1.0] and j["anchor_a"] == [0.0, 0.0, 1.0]            # a scaled frame, made unit
    assert abs(j["cone"] - math.radians(45)) < 1e-6 and abs(j["upper"] - math.radians(20)) < 1e-6


def test_a_model_carries_its_phys_in_a_pfdc_chunk_and_one_without_dynamic_bodies_has_none():
    m2 = _chunk("MD21"[::-1], b"MD20" + b"\0" * 12) + b"PFDC" + struct.pack("<I", len(_phys())) + _phys()
    assert P.chunk(m2, "PFDC") == _phys()
    assert P.chunk(b"MD20" + b"\0" * 64, "PFDC") is None                     # a plain M2
    still = _phys().replace(struct.pack("<HH3f", 1, 3, 0, 0, 1), struct.pack("<HH3f", 0, 3, 0, 0, 1))
    assert P.read(still) is None


# -- particles, ribbons, animations ------------------------------------------------------------------
def _model(**over):
    m = types.SimpleNamespace(textures=[{"type": 0, "flags": 0}] * 4, texture_file_ids=[11, 12, 13, 14], particles=[],
                              ribbons=[], texture_transforms=[], colors=[], texture_weights=[],
                              materials=[{"flags": 0x10, "blending_mode": 4}], texture_transform_combos=[3, 0xFFFF],
                              global_flags=0)
    for k, v in over.items():
        setattr(m, k, v)
    return m


def _emitter(**over):
    pe = {"bone": 0, "position": (0, 0, 0), "flags": 0, "emitter_type": 1, "blending_type": 4, "texture": 0,
          "particle_color_index": 0, "texture_dimensions_rows": 1, "texture_dimensions_columns": 1}
    pe.update(over)
    return pe


def test_a_multi_texture_emitter_names_its_three_textures_and_their_scroll():
    packed = 1 | (2 << 5) | (3 << 10)
    m = _model(particles=[_emitter(flags=M.MULTI_TEXTURE, texture=packed, multi_texture_param_x=(32, 64),
                                   multi_texture_param0=(1, 2, 3, 4), multi_texture_param1=(5, 6, 7, 8),
                                   spline_points=[(0, 0, 1)], wind_vector=(0.5, 0, 0)),
                          _emitter(texture=2)])
    multi, plain = M.model_anims(m, None, None, {})["particles"]
    assert multi["texture"] == 12 and multi["textures"] == [13, 14]
    assert multi["multi"] == [[32, 64], [1, 2, 3, 4], [5, 6, 7, 8]]
    assert multi["spline"] == [[0, 0, 1]] and multi["wind"] == [0.5, 0, 0]
    assert plain["texture"] == 13 and plain["textures"] == [] and plain["multi"] is None


def test_a_ribbon_carries_its_layers_and_its_texture_animation_where_the_model_says_so():
    ribbon = {"bone_index": 2, "position": (0, 0, 1), "texture_indices": [1], "material_indices": [0], "edges_per_second": 30.0,
              "edge_lifetime": 0.5, "gravity": -0.5, "texture_rows": 1, "texture_cols": 2, "priority_plane": 0,
              "texture_transform_lookup_index": 0}
    out = M.model_anims(_model(ribbons=[ribbon]), None, None, {})["ribbons"][0]
    assert out["bone"] == 2 and out["layers"] == [{"texture": 12, "blend": 4, "mflags": 0x10}]
    assert out["cols"] == 2 and out["edges"] == 30.0 and out["uvanim"] == -1          # no flag 0x20000: none
    out = M.model_anims(_model(ribbons=[ribbon], global_flags=0x20000), None, None, {})["ribbons"][0]
    assert out["uvanim"] == 3


def test_a_kit_model_plays_its_animation_and_stand_where_it_has_none():
    seqs = [{"id": 0, "variation_index": 0}, {"id": 5, "variation_index": 0}, {"id": 5, "variation_index": 1}]
    assert M.stand_index(seqs, 5) == 1 and M.stand_index(seqs, 7) == 0 and M.stand_index(seqs) == 0


# -- a mount's state kit --------------------------------------------------------------------------
def test_the_mount_preview_hangs_its_kit_models_and_keeps_the_blend_style_dissolve_alone():
    gradient = {"low": [0, 0, 0.2], "middle": [0, 0.6, 0.7], "high": [1, 1, 1], "split": 0.5, "rim": 0.9, "edge": [1, 1, 1], "flags": 2}
    kit = {"model": 77, "attachment": 16, "scale": 1.0, "alpha": 0.5, "offset": [0, 0, 0], "rotation": [0, 0, 0], "anim": 3,
           "start": -1, "end": -1}
    displays = {1: {"model": 10, "textures": [20, 0, 0, 0], "geosets": [], "state": [kit], "gradient": gradient,
                    "dissolve": {"flags": 8207, "layers": []}},
                2: {"model": 10, "textures": [], "geosets": [], "state": [], "gradient": None, "dissolve": {"flags": 23, "layers": []}}}
    meshes = []

    def mesh(key, fdid, textures, anim=0):
        meshes.append((fdid, anim))
        return {"fdid": fdid}
    fake = types.SimpleNamespace(mount_catalog=lambda key: types.SimpleNamespace(displays=displays, source="retail"), mesh=mesh)
    out = S.Workbench.mount_preview(fake, "retail", 1)
    assert out["gradient"] == gradient and out["dissolve"]["flags"] == 8207
    assert [(s["model"], s["attachment"], s["alpha"], s["mesh"]["fdid"]) for s in out["state"]] == [(77, 16, 0.5, 77)]
    assert (77, 3) in meshes                                                   # the kit's own animation
    assert S.Workbench.mount_preview(fake, "retail", 2)["dissolve"] is None    # the threshold style: the client draws none
