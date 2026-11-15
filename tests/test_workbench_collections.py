"""Your own collections: kept by the workbench, and in the basket one entry whose looks are its pieces as picked -
each the version chosen, from its own source, in its own colours where it has them; Stats treats it as a set."""

import threading
import types

from retroport.workbench import catalog as C
from retroport.workbench import itemstats as I
from retroport.workbench import server as S

FEL = {"key": "cfel", "name": "Fel", "colour": {"hue": 140, "sat": 1, "light": 136, "dye": 0}}


class _Cat:
    """An item of two versions (displays 10, 11) and a sword (20)."""
    def looks_for(self, e):
        if e.get("id") == 5:
            return [{"display": 10, "item": 5, "slot": 1, "name": "Hood", "label": "", "icon": 1},
                    {"display": 11, "item": 5, "slot": 1, "name": "Hood", "label": "", "icon": 2}], [5]
        if e.get("id") == 7:
            return [{"display": 20, "item": 7, "slot": 13, "name": "Sword", "label": "", "icon": 3}], [7]
        return [], []


def _collection(**piece_over):
    return {"kind": "collection", "source": "mine", "id": "c1", "name": "Mine", "pieces": [
        {"source": "r", "item": 5, "display": 11, "label": "Mythic", "inv": 1, "slot": "head"} | piece_over,
        {"source": "b", "item": 7, "display": 20, "inv": 13, "slot": "main"}]}


def test_a_collections_looks_are_its_pieces_as_picked():
    plan = C.plan_basket({"r": _Cat(), "b": _Cat()}, [_collection()])
    e, = plan["entries"]
    assert e["key"] == "collection:mine:c1" and e["state"] == "ready"
    assert [(l["display"], l["source"], l["label"]) for l in e["looks"]] == [(11, "r", "Mythic"), (20, "b", "")]
    assert [l["look_key"] for l in e["looks"]] == ["11", "20"] and plan["looks"] == 2 and plan["items"] == 2


def test_a_piece_in_its_own_colours_is_an_item_of_its_own():
    e, = C.plan_basket({"r": _Cat(), "b": _Cat()}, [_collection(colour=FEL)])["entries"]
    assert e["looks"][0]["look_key"] == "11~cfel" and e["looks"][0]["colour_name"] == "Fel"
    assert e["looks"][1]["look_key"] == "20"                         # the sword as made
    # Stats: the collection is a set of its pieces
    assert I.groups_of({"entries": [e]}) == {"11~cfel": "collection:mine:c1", "20": "collection:mine:c1"}


def test_a_source_still_loading_or_a_piece_gone():
    e, = C.plan_basket({"r": _Cat()}, [_collection()])["entries"]
    assert e["state"] == "loading" and [l["display"] for l in e["looks"]] == [11]
    e, = C.plan_basket({"r": _Cat(), "b": _Cat()}, [_collection(display=99)])["entries"]
    assert [l["display"] for l in e["looks"]] == [20]                # a version the item no longer has


def test_collections_are_kept_and_checked(tmp_path):
    wb = types.SimpleNamespace(settings=types.SimpleNamespace(data_dir=str(tmp_path)), _basket_lock=threading.Lock())
    wb.collections = lambda: S.Workbench.collections(wb)
    assert S.Workbench.collections(wb) == {"collections": [], "current": ""}
    doc = {"collections": [{"key": "c1", "name": "Mine", "pieces": [{"slot": "head", "item": 5}]}], "current": "c1"}
    assert S.Workbench.save_collections(wb, doc) == doc
    assert S.Workbench.collections(wb) == doc
    for bad in ({}, {"collections": [{"name": "no key"}]}, {"collections": [{"key": "c", "pieces": "x"}]}):
        try:
            S.Workbench.save_collections(wb, bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
