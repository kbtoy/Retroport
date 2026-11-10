"""Retail's item glows (ItemDisplayInfo.ItemVisual) for the client: the models each visual attaches,
and which of them the client draws.

A retail ItemDisplayInfo row names an ItemVisuals row. The client (wowdecomp-dx11,
WXL/modules/db2/items/ItemVisualGraph.cpp and modules/equipment/EquipmentAttachments.cpp) reads
retail's own tables for it (``TABLES``, whole) and attaches models to the item's model - the way
3.3.5 attaches an enchant's ItemVisualEffects models:

* ``point``: ItemVisuals.ModelFileID[0..4], each at the item model's attachment point 0..4;
* ``effect``: an ItemVisualsXEffect row's AttachmentModelFileID at its AttachmentID, scaled, for a
  weapon of the row's DisplayWeaponSubclassID (-1: any item - which the client doesn't take yet: it
  draws a row only for the one weapon type it names);
* ``kit``: the models of a spell visual kit (ItemVisuals.SpellVisualKitId1/2, an ItemVisualsXEffect
  row's SpellVisualKitID): the kit's SpellVisualKitModelAttach rows and those a SpellVisualKitEffect
  row of type 2 names, each SpellVisualEffectName.ModelFileDataID at the row's AttachmentID - the
  client draws a still one only (``kit_skip``).

The client finds each model by FileDataID through the path tables. Every model a look's visual
attaches goes in the patch with its own files, drawn yet or not: a client that learns the rest needs
no new patch. ``index`` is the pure walk (cached per retail build by ``direct``: the kit tables take
half a minute to read); ``for_look`` picks a look's glows from it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# the tables the client's item visual graph reads, whole (RetailSchemas.hpp): file -> layout
TABLES = {
    "itemvisuals": 0x4D7EF22C, "itemvisualsxeffect": 0x62F4C094,
    "spellvisualkitmodelattach": 0x02CF8554, "spellvisualkiteffect": 0xE3206CA2,
    "spellproceduraleffect": 0xB442AB81, "spellvisualeffectname": 0x2245CEE6,
    "positioner": 0xE0D4FD55, "positionerstate": 0x9CDFBF30, "positionerstateentry": 0x855AA6BC,
    "transformmatrix": 0x45999148,
}
# the ones the walk reads into rows: the WoWDBDefs name -> file
ROWS = {"ItemVisuals": "itemvisuals", "ItemVisualsXEffect": "itemvisualsxeffect",
        "SpellVisualKitEffect": "spellvisualkiteffect", "SpellVisualKitModelAttach": "spellvisualkitmodelattach",
        "SpellVisualEffectName": "spellvisualeffectname"}
INDEX_VERSION = 2
WEAPON = 2                                   # Item.ClassID of a weapon
ANY = -1                                     # DisplayWeaponSubclassID: any item

# why the client doesn't draw a glow model (``Glow.skip``), as the page says it
ANY_ITEM = "for any item (the client draws an effect for one weapon type only)"
MODEL_POSITION = "a kit model with retail's ModelPosition (the client takes only 0)"


@dataclass(frozen=True)
class Glow:
    fdid: int
    route: str                               # "point", "effect" or "kit"
    point: int                               # the attachment point on the item's model
    skip: str = ""                           # why the client doesn't draw it ("" when it does)
    scale: float = 1.0                       # its size on the item, as the client scales it


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def kit_skip(attach: dict, name: dict | None) -> str:
    """Why the client doesn't draw a kit's model (ItemVisualGraph.cpp's ResolveKits): "" when it does.
    It takes a still model only - no flags, anim kit, random variation or texture/dissolve swap, an
    attachment point it knows, a scale and alpha it can use; and ModelPosition 0, where retail's
    rows almost all say -1. A positioner it draws when that stands still, which this doesn't read."""
    if name is None:
        return "no SpellVisualEffectName row"
    if attach.get("Flags") or name.get("Flags"):
        return "flags"
    if attach.get("AnimKitID"):
        return "an anim kit"
    if any(_f(attach.get(f) or 0) != 0 for f in ("YawVariation", "PitchVariation", "RollVariation", "ScaleVariation")) \
            or any(_f(v) != 0 for v in attach.get("OffsetVariation") or []):
        return "random variation"
    if name.get("TextureFileDataID"):
        return "a texture swap"
    if name.get("DissolveEffectID"):
        return "a dissolve"
    if name.get("ModelPosition"):
        return MODEL_POSITION
    point = attach.get("AttachmentID")
    if not isinstance(point, int) or not 0 <= point <= 255:
        return "an attachment point it doesn't know"
    delay, alpha = _f(attach.get("StartDelay") or 0), _f(name.get("Alpha", 1))
    if not 0 <= delay <= 2_147_483:
        return "a start delay"
    if not 0 <= alpha <= 1:
        return "an alpha"
    if any(not math.isfinite(_f(v)) for v in list(attach.get("Offset") or []) + [attach.get(f) or 0 for f in ("Yaw", "Pitch", "Roll")]):
        return "a bad transform"
    return ""


def _scale(*values) -> float:
    """Scales multiplied as the client does: one that isn't a positive number counts as 1."""
    out = 1.0
    for v in values:
        f = _f(v)
        out *= f if math.isfinite(f) and f > 0 else 1.0
    return round(out, 6)


def index(rows: dict[str, list[tuple[int, dict]]]) -> dict[int, list[list]]:
    """{visual id: [[fdid, route, point, subclass, skip, scale], ...]} from the ``ROWS`` tables' rows
    (the kit tables may be left out: the visuals' own models and effect rows then). subclass: None for
    the visual's own models and kits (every item), else the ItemVisualsXEffect row's
    DisplayWeaponSubclassID (-1 any item). Rows without a model are left out; JSON as it is."""
    visuals = {i: r for i, r in rows.get("ItemVisuals", [])}
    effects: dict[int, list[dict]] = {}
    for _i, r in rows.get("ItemVisualsXEffect", []):
        effects.setdefault(r.get("ItemVisualsID") or 0, []).append(r)
    kits = set()
    for v, r in visuals.items():
        kits.update(k for k in (r.get("SpellVisualKitId1"), r.get("SpellVisualKitId2")) if k)
        kits.update(e["SpellVisualKitID"] for e in effects.get(v, []) if e.get("SpellVisualKitID"))
    attaches, by_kit = {}, {}
    for i, r in rows.get("SpellVisualKitModelAttach", []):
        attaches[i] = r
        if r.get("ParentSpellVisualKitID") in kits:
            by_kit.setdefault(r["ParentSpellVisualKitID"], []).append(i)
    for _i, r in rows.get("SpellVisualKitEffect", []):
        kit = r.get("ParentSpellVisualKitID")
        if kit in kits and r.get("EffectType") == 2 and r.get("Effect") in attaches:
            by_kit.setdefault(kit, []).append(r["Effect"])
    names = {i: r for i, r in rows.get("SpellVisualEffectName", [])}

    def kit_models(kit: int) -> list[tuple[int, int, str, float]]:
        out = []
        for a in dict.fromkeys(by_kit.get(kit, [])):
            row = attaches[a]
            name = names.get(row.get("SpellVisualEffectNameID") or 0)
            fdid = (name or {}).get("ModelFileDataID") or 0
            if fdid:
                out.append((fdid, row.get("AttachmentID") or 0, kit_skip(row, name),
                            _scale(row.get("Scale"), name.get("Scale"))))
        return out

    out: dict[int, list[list]] = {}
    for v, r in sorted(visuals.items()):
        glows = [[f, "point", p, None, "", 1.0] for p, f in enumerate(list(r.get("ModelFileID") or [])[:5]) if f]
        for k in dict.fromkeys(k for k in (r.get("SpellVisualKitId1"), r.get("SpellVisualKitId2")) if k):
            glows += [[f, "kit", p, None, s, sc] for f, p, s, sc in kit_models(k)]
        for e in effects.get(v, []):
            sub = e.get("DisplayWeaponSubclassID")
            sub = ANY if sub is None or sub < 0 else sub
            f = e.get("AttachmentModelFileID") or 0
            if f and _f(e.get("Scale", 1)) > 0:
                glows.append([f, "effect", e.get("AttachmentID") or 0, sub, "", _scale(e.get("Scale", 1))])
            if e.get("SpellVisualKitID"):
                glows += [[f, "kit", p, sub, s, sc] for f, p, s, sc in kit_models(e["SpellVisualKitID"])]
        if glows:
            out[v] = glows
    return out


def relocate(path: str) -> str:
    """Where a glow's file goes when the client has another file at its retail path (3.3.5's own spell
    model, which its spells and enchants use): ``retroport\\`` after the first folder, as the mounts'
    ``creature\\retroport\\`` - the client finds it by FileDataID, wherever it is."""
    p = path.replace("/", "\\").lower()
    head, _sep, rest = p.partition("\\")
    if not rest:
        return "retroport\\" + p
    return p if rest.startswith("retroport\\") else f"{head}\\retroport\\{rest}"


def for_look(glows: list[list] | None, item: dict | None) -> list[Glow]:
    """A look's glows from its visual's ``index`` entry, for its retail Item row: the visual's own
    models and kits, the effect rows for any item (which the client doesn't draw yet), and those for
    the item's weapon type when it is a weapon. Each model once (the first that the client draws)."""
    out: dict[int, Glow] = {}
    for g in _applying(glows, item):
        if g.fdid not in out or (out[g.fdid].skip and not g.skip):
            out[g.fdid] = g
    return list(out.values())


def placements(glows: list[list] | None, item: dict | None) -> list[Glow]:
    """What the client hangs on a look's model: each glow it draws (``for_look``'s rules), at every
    point the visual names it - one model on all five points is five. For the preview."""
    return list({(g.fdid, g.point): g for g in _applying(glows, item) if not g.skip}.values())


def _applying(glows: list[list] | None, item: dict | None) -> list[Glow]:
    weapon = (item or {}).get("SubclassID") if (item or {}).get("ClassID") == WEAPON else None
    out = []
    for fdid, route, point, sub, skip, *rest in glows or []:
        if sub == ANY:
            skip = skip or ANY_ITEM
        elif sub is not None and sub != weapon:
            continue                                 # another weapon type's: retail doesn't draw it either
        out.append(Glow(fdid, route, point, skip, rest[0] if rest else 1.0))
    return out
