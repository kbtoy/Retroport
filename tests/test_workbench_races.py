"""The races the preview dresses: the client's own and those its wxl-races.cfg adds, one per body (Mag'har apart
from the Orc, Earthen's two ids one), their postures, and a body built from retail's customization tables."""

import os

from retroport.workbench import character as CH

CFG = """# a comment
WXL_M2_RACE_22=32,7
WXL_M2_RACE_23=32,1
WXL_M2_RACE_26=36,1
WXL_M2_RACE_33=85,7,masks=3,family=3,name=Earthen
WXL_M2_RACE_34=84,1,masks=2,family=3,name=Earthen
WXL_M2_RACE_35=9,1,masks=2,name=Goblin
WXL_M2_RACE_40=12,1,nocreate
WXL_M2_RACE_x=1,1
"""
CHR = {1: {"ClientPrefix": "Hu", "Name_lang": "Human"}, 2: {"ClientPrefix": "Or", "Name_lang": "Orc"},
       9: {"ClientPrefix": "Go", "Name_lang": "Goblin"}, 12: {"ClientPrefix": "Xx", "Name_lang": "Hidden"},
       32: {"ClientPrefix": "Kt", "Name_lang": "Kul Tiran"}, 36: {"ClientPrefix": "Mo", "Name_lang": "Mag'har Orc"},
       84: {"ClientPrefix": "Ed", "Name_lang": "Earthen"}, 85: {"ClientPrefix": "Ed", "Name_lang": "Earthen"}}


def _client(tmp_path, monkeypatch):
    (tmp_path / CH.RACES_CFG).write_text(CFG, encoding="utf-8")
    # the client's own ChrRaces/CharBaseInfo: Human, Orc and Mag'har (26 shares the Orc's prefix), Kul Tiran
    monkeypatch.setattr(CH, "client_races", lambda d: [{"prefix": "Hu", "ids": [1]}, {"prefix": "Or", "ids": [2, 26]},
                                                         {"prefix": "Kt", "ids": [22, 23]}])
    return str(tmp_path)


def test_the_cfg_names_each_client_races_body(tmp_path, monkeypatch):
    d = _client(tmp_path, monkeypatch)
    assert CH.race_cfg(d) == {22: 32, 23: 32, 26: 36, 33: 85, 34: 84, 35: 9, 40: 0}
    assert CH.race_cfg(os.path.join(d, "nowhere")) == {}


def test_one_race_per_body_mag_har_apart_earthen_one(tmp_path, monkeypatch):
    got = {r["key"]: r for r in CH.server_races(_client(tmp_path, monkeypatch), CHR)}
    assert list(got) == ["hu", "or", "kt", "mo", "ed", "go"]
    assert got["or"]["client"] == [2] and got["mo"]["client"] == [26] and got["mo"]["retail"] == 36
    assert got["kt"]["client"] == [22, 23] and got["ed"]["client"] == [33, 34] and got["ed"]["name"] == "Earthen"
    assert "xx" not in got                                                      # nocreate: not offered


def test_postures_the_clients_own_first():
    assert [p[0] for p in CH.POSTURES[("or", 0)]] == ["hunched", "upright"]
    assert [p[0] for p in CH.POSTURES[("mo", 0)]] == ["upright", "hunched"]   # the x64 client's Mag'har stands
    assert CH.POSTURES[("sc", 1)][1][2][0] == "client"                        # our own upright undead


class _Retail:
    """A retail source of one race's tables: a skin with two colours, a face for each, a geoset and an eye."""
    def __init__(self):
        el = lambda choice, **f: {"ChrCustomizationChoiceID": choice, "ChrCustomizationGeosetID": 0,
                                  "ChrCustomizationMaterialID": 0, "RelatedChrCustomizationChoiceID": 0} | f
        self.t = {
            "ChrRaceXChrModel": [(1, {"ChrRacesID": 84, "Sex": 0, "ChrModelID": 195})],
            "ChrModel": [(195, {"DisplayID": 7, "CharComponentTextureLayoutID": 185})],
            "CreatureDisplayInfo": [(7, {"ModelID": 8})], "CreatureModelData": [(8, {"FileDataID": 999})],
            "CharComponentTextureLayouts": [(185, {"Width": 1024, "Height": 512})],
            "CharComponentTextureSections": [(1, {"CharComponentTextureLayoutID": 185, "SectionType": 9,
                                                  "X": 0, "Y": 0, "Width": 256, "Height": 128})],
            "ChrModelTextureLayer": [
                (1, {"CharComponentTextureLayoutsID": 185, "ChrModelTextureTargetID": [1, 0], "TextureType": 1,
                     "Layer": 0, "BlendMode": 1, "TextureSectionTypeBitMask": -1}),
                (2, {"CharComponentTextureLayoutsID": 185, "ChrModelTextureTargetID": [4, 0], "TextureType": 1,
                     "Layer": 3, "BlendMode": 15, "TextureSectionTypeBitMask": 0x200}),
                (3, {"CharComponentTextureLayoutsID": 185, "ChrModelTextureTargetID": [25, 0], "TextureType": 19,
                     "Layer": 11, "BlendMode": 1, "TextureSectionTypeBitMask": -1})],
            "ChrCustomizationOption": [(10, {"ChrModelID": 195, "OrderIndex": 0}), (11, {"ChrModelID": 195, "OrderIndex": 1}),
                                       (12, {"ChrModelID": 195, "OrderIndex": 2})],
            "ChrCustomizationChoice": [(100, {"ChrCustomizationOptionID": 10, "OrderIndex": 0, "ChrCustomizationReqID": 141}),
                                       (101, {"ChrCustomizationOptionID": 10, "OrderIndex": 1, "ChrCustomizationReqID": 141}),
                                       (110, {"ChrCustomizationOptionID": 11, "OrderIndex": 0, "ChrCustomizationReqID": 141}),
                                       (120, {"ChrCustomizationOptionID": 12, "OrderIndex": 0, "ChrCustomizationReqID": 146})],
            "ChrCustomizationElement": [
                (1, el(100, ChrCustomizationMaterialID=1)), (2, el(101, ChrCustomizationMaterialID=2)),
                (3, el(110, ChrCustomizationMaterialID=3, RelatedChrCustomizationChoiceID=100)),   # the face of skin 100
                (4, el(110, ChrCustomizationMaterialID=4, RelatedChrCustomizationChoiceID=101)),   # ... and of skin 101
                (5, el(120, ChrCustomizationMaterialID=5, ChrCustomizationGeosetID=1))],
            "ChrCustomizationMaterial": [(1, {"ChrModelTextureTargetID": 1, "MaterialResourcesID": 501}),
                                         (2, {"ChrModelTextureTargetID": 1, "MaterialResourcesID": 502}),
                                         (3, {"ChrModelTextureTargetID": 4, "MaterialResourcesID": 503}),
                                         (4, {"ChrModelTextureTargetID": 4, "MaterialResourcesID": 504}),
                                         (5, {"ChrModelTextureTargetID": 25, "MaterialResourcesID": 505})],
            "ChrCustomizationGeoset": [(1, {"GeosetType": 17, "GeosetID": 3})],
            "TextureFileData": [(i, {"MaterialResourcesID": 500 + i, "FileDataID": 9000 + i, "UsageType": 0}) for i in range(1, 6)],
            "ChrRaces": [(84, {"Name_lang": "Earthen"})],
        }

    def table(self, name):
        return self.t[name]

    def read(self, fdid):
        raise LookupError(fdid)


def test_a_retail_body_wears_each_options_first_choice(monkeypatch):
    from retroport.workbench import models as M
    monkeypatch.setattr(M, "mesh", lambda read, fdid, textures, **k: {"fdid": fdid})
    b = CH.RetailBodies(_Retail()).body(84, 0)
    assert b["mesh"] == {"fdid": 999} and b["source"] == "retail"
    # skin 100 pasted over the whole layout, then ITS face (not skin 101's) blended into section 9
    assert b["skin"] == [[-1, 9001, 1], [9, 9003, 15]]
    assert b["types"] == {"19": 9005} and b["geosets"][17] == 3
    assert b["layout"] == {"width": 1024, "height": 512, "sections": {9: [0, 0, 256, 128]}}
