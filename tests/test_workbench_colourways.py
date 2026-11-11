"""Colourways: a player's own colours for a version of an item or a set - an extra item in game, beside the
look it was made from, with the colours the client recolours it by (retailpack.COLOUR_TABLE)."""

import types

from retroport.workbench import catalog as C
from retroport.workbench import itemstats as I
from retroport.workbench import retailpack as RP

FEL = {"key": "cfel", "name": "Fel", "colour": {"hue": 140, "sat": 1, "light": 180, "dye": 0}, "parts": {"armor": "off"}}


class _Cat:
    """A catalog's looks_for: an item's two versions, a set's two pieces."""
    def looks_for(self, e):
        if e["kind"] == "item":
            return [{"display": 10, "item": 5, "name": "Cord", "label": "Gladiator"},
                    {"display": 11, "item": 5, "name": "Cord", "label": "Elite"}], [5]
        return [{"display": 20, "item": 6, "name": "Hood"}, {"display": 21, "item": 7, "name": "Mantle"}], [6, 7]


def test_a_colourway_is_an_entry_and_a_look_of_its_own():
    basket = [{"kind": "item", "source": "r", "id": 5, "name": "Cord"},
              {"kind": "item", "source": "r", "id": 5, "name": "Cord (Elite - Fel)", "look": 11, "colour": FEL},
              {"kind": "set", "source": "r", "id": 9, "name": "Set (Fel)", "colour": FEL}]
    assert C.entry_key(basket[1]) == "item:r:5~cfel" and C.entry_key(basket[0]) == "item:r:5"
    plan = C.plan_basket({"r": _Cat()}, basket)
    plain, way, sett = plan["entries"]
    assert [l["look_key"] for l in plain["looks"]] == ["10", "11"]
    assert [l["look_key"] for l in way["looks"]] == ["11~cfel"]                   # the one version it was made of
    assert way["looks"][0]["colour"] == FEL and way["looks"][0]["colour_name"] == "Fel"
    assert not way["covered"] and plan["looks"] == 5                               # not "comes with the plain one"
    assert [l["look_key"] for l in sett["looks"]] == ["20~cfel", "21~cfel"]
    assert I.groups_of(plan) == {"20~cfel": "set:r:9~cfel", "21~cfel": "set:r:9~cfel"}
    # new colours: a new stamp, so the build is out of date
    again = dict(way["looks"][0], colour=dict(FEL, colour=dict(FEL["colour"], hue=20)))
    assert C.look_stamp(way["looks"][0]) != C.look_stamp(again) and C.look_stamp(plain["looks"][0]) == "10"


def test_a_colourway_gets_an_entry_of_its_own_kept_between_installs():
    spare = {}
    a = RP.colour_entry(5, 0, "cfel", spare)
    assert a == RP.SPARE and RP.colour_entry(5, 0, "cfel", spare) == a
    assert RP.colour_entry(5, 0, "cvoid", spare) == a + 1 and RP.colour_entry(5, 3, "cfel", spare) == a + 2


def test_the_colour_table_names_each_parts_colour_or_none():
    own = dict(FEL, parts={"armor": "off", "ribbons": {"hue": 10, "sat": 0.5, "light": 128, "dye": 1}})
    pieces = [types.SimpleNamespace(entry=16000000, display=722371, colour=own),
              types.SimpleNamespace(entry=5, display=11, colour=None)]
    text = RP.colour_table(pieces).decode()
    line = [l for l in text.splitlines() if not l.startswith("#")]
    # its own display id, the retail display it recolours, then the parts
    assert line == ["16000000\t722371\t-\t140,1,180,0\t140,1,180,0\t10,0.5,128,1"]
    assert RP.colour_table([types.SimpleNamespace(entry=5, display=11, colour=None)]) is None


def test_a_colourways_item_row_has_its_own_display():
    def piece(entry, colour):
        return RP.Piece(entry, 5, 722371, 0, "Cord", 4, 4, 1, -1, 6, 0, 0, colour=colour)
    way, plain = piece(16000000, FEL), piece(5, None)
    assert way.shown == 16000000 and plain.shown == 722371
    assert dict(zip(RP.COLUMNS, way.values()))["displayid"] == 16000000
    sql = RP.item_sql([way, plain], [], "12.1.5", "now")
    assert "(16000000,16000000)" in sql and "(5,722371)" in sql
