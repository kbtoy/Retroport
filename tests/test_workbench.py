"""The workbench: a catalog built from a source's tables, its searches, and the local server's API."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from retroport.workbench import catalog as C
from retroport.workbench import server as W

PLATE_HELM, PLATE_HELM_2, CLOTH_ROBE, STAFF, RING, TEST_LEGS, MONSTER_HELM = 101, 102, 103, 104, 105, 106, 107


class FakeSource:
    """What build_catalog reads: tables by name (a missing one is empty) and a build."""
    key, build = "bfa", "8.3.7.35435"
    spec = C.SourceSpec("bfa", "BfA", "X:\\bfa")

    def __init__(self):
        items = {PLATE_HELM: (4, 4, 1, 900), PLATE_HELM_2: (4, 4, 1, 901), CLOTH_ROBE: (4, 1, 20, 902),
                 STAFF: (2, 10, 17, 903), RING: (4, 0, 11, 904), TEST_LEGS: (4, 1, 7, 905), MONSTER_HELM: (4, 4, 1, 906)}
        names = {PLATE_HELM: ("Helm of the Tester", 4, 7, 1), PLATE_HELM_2: ("Helm of the Tester", 4, 7, 1),
                 CLOTH_ROBE: ("Robe of Bytes", 3, 6, 128), STAFF: ("Staff of Mocks", 2, 6, -1),
                 RING: ("Band of Nothing", 4, 7, -1), TEST_LEGS: ("[DNT] Test Legs", 1, 7, -1)}
        self.tables = {
            "Item": [(i, {"ClassID": c, "SubclassID": s, "InventoryType": inv, "IconFileDataID": icon})
                     for i, (c, s, inv, icon) in items.items()],
            "ItemSearchName": [(i, {"Display_lang": n, "OverallQualityID": q, "ExpansionID": e, "AllowableClass": a,
                                    "RequiredLevel": 50, "ItemLevel": 400}) for i, (n, q, e, a) in names.items()],
            # the two helms share a look; the first has a heroic one too
            "ItemModifiedAppearance": [(1, {"ItemID": PLATE_HELM, "ItemAppearanceModifierID": 0, "ItemAppearanceID": 50}),
                                       (2, {"ItemID": PLATE_HELM, "ItemAppearanceModifierID": 1, "ItemAppearanceID": 51}),
                                       (3, {"ItemID": PLATE_HELM_2, "ItemAppearanceModifierID": 0, "ItemAppearanceID": 50}),
                                       (4, {"ItemID": CLOTH_ROBE, "ItemAppearanceModifierID": 0, "ItemAppearanceID": 52}),
                                       (5, {"ItemID": STAFF, "ItemAppearanceModifierID": 0, "ItemAppearanceID": 53})],
            "ItemAppearance": [(a, {"DefaultIconFileDataID": 1000 + a, "ItemDisplayInfoID": 2000 + a}) for a in (50, 51, 52, 53)],
            # a set in two versions (normal 10, heroic 11 whose parent is 10) and a cloth one
            "TransmogSet": [(10, {"Name_lang": "Tester's Battleplate", "ClassMask": 1, "TransmogSetGroupID": 7,
                                  "ItemNameDescriptionID": 0, "ParentTransmogSetID": 0, "ExpansionID": 7,
                                  "PatchIntroduced": 80300, "UiOrder": 1}),
                            (11, {"Name_lang": "Tester's Battleplate", "ClassMask": 1, "TransmogSetGroupID": 7,
                                  "ItemNameDescriptionID": 3, "ParentTransmogSetID": 10, "ExpansionID": 7,
                                  "PatchIntroduced": 80300, "UiOrder": 2}),
                            (12, {"Name_lang": "Byte Regalia", "ClassMask": 128, "TransmogSetGroupID": 0,
                                  "ItemNameDescriptionID": 0, "ParentTransmogSetID": 0, "ExpansionID": 6,
                                  "PatchIntroduced": 70000, "UiOrder": 3})],
            "TransmogSetItem": [(1, {"TransmogSetID": 10, "ItemModifiedAppearanceID": 1}),
                                (2, {"TransmogSetID": 11, "ItemModifiedAppearanceID": 2}),
                                (3, {"TransmogSetID": 12, "ItemModifiedAppearanceID": 4})],
            "TransmogSetGroup": [(7, {"Name_lang": "Test Raid"})],
            "ItemNameDescription": [(3, {"Description_lang": "Heroic"})],
            "ItemSet": [(5, {"Name_lang": "Classic Mocks", "ItemID": [STAFF, CLOTH_ROBE, 0]})],
        }

    def table(self, name):
        return self.tables.get(name, [])


def _catalog():
    cat = C.build_catalog(FakeSource())
    cat.in_client = {STAFF}
    return cat


def test_the_catalog_keeps_named_items_with_a_look_and_their_appearances():
    cat = _catalog()
    assert sorted(cat.by_id) == [PLATE_HELM, PLATE_HELM_2, CLOTH_ROBE, STAFF, TEST_LEGS]   # no ring, no unnamed helm
    helm = cat.item_detail(PLATE_HELM)
    assert (helm["appearance"], helm["icon"], helm["display"]) == (50, 1050, 2050)       # modifier 0 is the default
    assert [(a["modifier"], a["label"]) for a in helm["appearances"]] == [(0, "Normal"), (1, "Heroic")]
    assert [o["id"] for o in helm["same_look"]] == [PLATE_HELM_2]
    assert [s["id"] for s in helm["sets"]] == [10, 11]                    # its heroic look is the heroic set's
    assert cat.item_detail(STAFF)["in_client"] and cat.item_detail(STAFF)["item_sets"] == [{"id": 5, "name": "Classic Mocks"}]


def test_an_items_locked_versions_and_blizzards_internal_sets_are_left_out():
    src = FakeSource()
    t = src.tables
    # the robe's 12.0 "VFX unlock" looks: locked behind a player condition, one only in a [DNT] set, one in
    # none; and an open look of its own no set names
    t["ItemModifiedAppearance"] += [(6, {"ItemID": CLOTH_ROBE, "ItemAppearanceModifierID": 157, "ItemAppearanceID": 54}),
                                    (7, {"ItemID": CLOTH_ROBE, "ItemAppearanceModifierID": 158, "ItemAppearanceID": 55}),
                                    (8, {"ItemID": CLOTH_ROBE, "ItemAppearanceModifierID": 8, "ItemAppearanceID": 56})]
    t["ItemAppearance"] += [(54, {"DefaultIconFileDataID": 1054, "ItemDisplayInfoID": 2054, "TransmogPlayerConditionID": 150132}),
                            (55, {"DefaultIconFileDataID": 1055, "ItemDisplayInfoID": 2055, "TransmogPlayerConditionID": 150131}),
                            (56, {"DefaultIconFileDataID": 1056, "ItemDisplayInfoID": 2056})]
    t["TransmogSet"] += [(13, {"Name_lang": "[DNT] 12.0 Mythic VFX Unlock - All Items", "ClassMask": 0, "TransmogSetGroupID": 0,
                               "ItemNameDescriptionID": 0, "ParentTransmogSetID": 0, "ExpansionID": 11,
                               "PatchIntroduced": 120000, "UiOrder": 4})]
    t["TransmogSetItem"] += [(4, {"TransmogSetID": 13, "ItemModifiedAppearanceID": 6})]
    cat = C.build_catalog(src)
    robe = cat.item_detail(CLOTH_ROBE)
    assert [(a["modifier"], a["appearance"], a["label"]) for a in robe["appearances"]] == \
        [(0, 52, "Normal"), (8, 56, "Version 2")]
    assert [s["id"] for s in robe["sets"]] == [12]                       # not the [DNT] set


def test_item_search_filters_and_hides_test_items():
    cat = _catalog()
    ids = lambda **kw: sorted(r[0] for r in cat.search_items(**kw)[1])
    assert ids(q="helm tester") == [PLATE_HELM, PLATE_HELM_2]
    assert len(ids(slot="head", armour="plate", looks=True)) == 1                         # one per look
    assert ids(slot="chest") == [CLOTH_ROBE] and ids(weapon=10) == [STAFF]
    assert ids(cls=8) == [CLOTH_ROBE, STAFF]                                              # mage: its robe, an any-class staff
    assert TEST_LEGS not in ids() and TEST_LEGS in ids(junk=True)
    assert ids(q=str(STAFF)) == [STAFF] and ids(q="52") == [CLOTH_ROBE]                   # by item or appearance id
    assert ids(quality=4) == [PLATE_HELM, PLATE_HELM_2]


def test_sets_come_as_families_with_their_versions():
    cat = _catalog()
    total, cards = cat.search_sets()
    assert total == 2 and [c["id"] for c in cards] == [10, 12]                            # newest expansion first
    assert cards[0]["variants"] == 2 and cards[0]["armour"] == 4 and cards[0]["group"] == "Test Raid"
    heroic = cat.set_detail(11)
    assert heroic["label"] == "Heroic" and [f["id"] for f in heroic["family"]] == [10, 11]
    assert heroic["pieces"][0]["appearance"] == 51 and heroic["pieces"][0]["icon"] == 1051
    assert [c["id"] for c in cat.search_sets(cls=8)[1]] == [12]
    assert [c["id"] for c in cat.search_sets(armour="cloth")[1]] == [12]
    assert cat.search_item_sets("mocks")[1][0]["items"] == [STAFF, CLOTH_ROBE]


def test_a_fragment_folds_into_the_set_that_holds_its_looks():
    def s(i, looks, label="", group=""):
        return {"id": i, "name": "Gladiator's Chain", "label": label, "group": group,
                "pieces": [{"appearance": a} for a in looks]}
    full, elite = s(1, [1, 2, 3], "Gladiator", "Season 2"), s(2, [4, 5, 6], "Elite", "Season 2")
    bundle, again, own = s(3, [4, 5]), s(4, [1, 2, 3]), s(5, [7])        # two elite slots; the set listed twice; a look of its own
    C.fold_fragments([full, elite, bundle, again, own])
    assert bundle["covered_by"] == 2 and again["covered_by"] == 1
    assert not any("covered_by" in x for x in (full, elite, own))          # versions are labelled: never folded


def test_a_sets_pieces_come_one_per_look_under_its_primary_item():
    pieces = [{"item": 1, "appearance": 10, "display": 100, "flags": 0},  # a Faceguard...
              {"item": 2, "appearance": 10, "display": 100, "flags": 1},  # ...and the Helm the set marks primary
              {"item": 3, "appearance": 11, "display": 101, "flags": 1},
              {"item": 4, "appearance": 12, "display": 101, "flags": 0}]  # another appearance of the same model
    assert [(p["item"], [a["item"] for a in p["also"]]) for p in C.looks_of(pieces)] == [(2, [1]), (3, [4])]


def test_the_basket_plan_shows_each_entrys_looks_its_overlaps_and_the_changes():
    cat = _catalog()
    e = lambda kind, i, **kw: {"kind": kind, "source": "bfa", "id": i, "name": f"{kind} {i}", **kw}
    basket = [e("set", 10), e("item", PLATE_HELM), e("item", STAFF), e("itemset", 5, items=[STAFF, CLOTH_ROBE])]
    installed = [e("set", 10), e("item", RING)]
    plan = C.plan_basket({"bfa": cat}, basket, installed)
    sets, helm, staff, mocks = plan["entries"]
    assert [l["display"] for l in sets["looks"]] == [2050] and sets["items"] == 1
    # an item brings every version; its normal look came with the set already, its heroic one is its own
    assert [(l["display"], l["label"]) for l in helm["looks"]] == [(2050, "Normal"), (2051, "Heroic")]
    assert helm["shares"] == ["set 10"] and not helm["covered"]
    assert mocks["covered"] is False and mocks["shares"] == ["item 104"]          # the robe is its own
    assert plan["looks"] == 4 and plan["items"] == 3                              # 2050, 2051, 2053, 2052
    assert [x["new"] for x in plan["entries"]] == [False, True, True, True]
    assert [r["id"] for r in plan["removed"]] == [RING]
    # a source still loading, an id it doesn't have
    later = C.plan_basket({"bfa": cat}, [e("item", 999), {**e("item", 1), "source": "retail"}])
    assert [x["state"] for x in later["entries"]] == ["missing", "loading"] and not later["known"]


def test_a_catalog_survives_its_cache():
    cat = _catalog()
    again = C.Catalog.from_json(json.loads(json.dumps(cat.to_json())))
    assert again.items == cat.items and again.set_detail(11) == cat.set_detail(11)


def test_the_server_answers_searches_and_keeps_the_basket(tmp_path):
    wb = W.Workbench(W.Settings(data=str(tmp_path)))
    wb.catalogs["bfa"] = _catalog()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), W.make_handler(wb))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    get = lambda path: json.loads(urllib.request.urlopen(base + path).read())
    try:
        assert get("/api/items?source=bfa&q=robe")["items"][0]["id"] == CLOTH_ROBE
        assert get("/api/set?source=bfa&id=11")["label"] == "Heroic"
        assert get("/api/sets?source=bfa&kind=itemset")["sets"][0]["name"] == "Classic Mocks"
        assert get("/api/meta")["slots"]["1"] == "Head"
        req = urllib.request.Request(base + "/api/basket", data=json.dumps([{"kind": "set", "id": 10}]).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req).read()
        assert get("/api/basket") == [{"kind": "set", "id": 10}]
        assert (tmp_path / "basket.json").is_file()
        try:
            urllib.request.urlopen(base + "/static/../server.py")
            assert False, "a path outside static/ was served"
        except urllib.error.HTTPError as e:
            assert e.code == 404
        assert b"Retroport Workbench" in urllib.request.urlopen(base + "/").read()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_one_set_in_many_colours_is_one_family():
    from retroport.workbench import catalog as C
    def s(i, name, slots=(5, 7), exp=10, label="", root=None):
        return {"id": i, "name": name, "label": label, "root": root or i, "expansion": exp, "ui_order": 0,
                "pieces": [{"slot": x} for x in slots]}
    sets = [s(1, "Aquatic Sweatsuit"), s(2, "Azure Sweatsuit"), s(3, "Brick Sweatsuit"), s(4, "Azure Sweatsuit"),
            s(5, "Heritage of the Dark Iron"), s(6, "Heritage of the Kul Tiran"), s(7, "Heritage of the Mag'har"),
            s(8, "Prowler's Pink Headgear", (1,)), s(9, "Prowler's Plum Headgear", (1,)),
            s(10, "Crimson Sweatsuit", exp=9), s(11, "Normal Thing", label="Normal"), s(12, "Snowy Thing", root=11)]
    C.fold_variants(sets)
    by = {x["id"]: x for x in sets}
    assert [by[i]["root"] for i in (1, 2, 3, 4)] == [1, 1, 1, 1]
    assert [by[i]["label"] for i in (1, 2, 3, 4)] == ["Aquatic", "Azure", "Brick", "Azure 2"]
    assert by[1]["family_name"] == "Sweatsuit"
    assert all(by[i]["root"] == i for i in (5, 6, 7, 8, 9, 10))          # not colours; only two; another expansion
    assert by[12]["root"] == 11 and not by[12].get("family_name")       # a family already
    before = [dict(x) for x in sets]
    C.fold_variants(sets)
    assert sets == before                                                # running it again changes nothing
