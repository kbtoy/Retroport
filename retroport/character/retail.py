"""Retail (9.0+) playable characters, read as the BfA tables the converter knows.

Shadowlands replaced CharSections, CharHairGeosets and CharacterFacialHairStyles with one
customization system: a race/sex is a ChrModel (its display, body texture layout and
skeleton); its options (ChrCustomizationOption) have choices, and each choice's elements
(ChrCustomizationElement) set a geoset, a texture (a material on one of the layout's texture
targets, ChrModelTextureLayer) or a conditional body model. An element can apply only
alongside another choice (``RelatedChrCustomizationChoiceID``): a Mag'har face texture is
drawn per skin colour.

3.3.5 has five customization axes: skin colour, face, hair style, hair colour and "features"
(CharacterFacialHairStyles: one geoset value for each of groups 1, 3, 2, 16 and 17). This
module projects a retail ChrModel onto them (``read_character``):

* **skin colour** - the option that sets the body's base texture (the layout's TextureType 1
  layer 0); its rows also carry the underwear textures (LegUpper -> NakedPelvisSkin,
  TorsoUpper -> NakedTorsoSkin).
* **face** - the option texturing the face sections (9/10) on the lowest layer; one row per
  face and skin colour, from the face element related to that skin colour.
* **hair style / hair colour** - the hair geosets (group 0) and the hair texture (TextureType 6).
* **features** - combinations of up to two geoset options (``FEATURES`` per race and sex, else
  the first two in the facial groups): a Mag'har male's Beard x Sideburns. An option outside
  groups 1/2/3/16 (a Mag'har female's earrings, group 35) is renumbered into a facial group the
  model leaves free (``FREE_FACIAL_GROUPS``), so the features slot can switch it; a choice that
  needs ear geosets 3.3.5 never shows (703: stretched ears) is left out.
* everything else is fixed at retail's default: groups 3.3.5 never switches (20 and up: tusks,
  necklace, eyeballs) keep the default choice's piece, or xx01 where no option sets one; the
  eye colour is the default choice's texture, baked into the eyeball batches as a fixed texture
  (3.3.5 has no eye texture type, 19 - the "green eyes"); retail's death-knight eye glow (1701)
  becomes 1703, the geoset 3.3.5 shows on death knights, and the unlockable eye geosets go.

A choice counts when a new character can pick it: no requirement, or a class requirement that
admits a class other than the death knight. Transmog-only, unlockable (achievement, quest,
appearance) and death-knight-only choices are skipped. Choices are taken in retail's UI order
(``UiOrderIndex``), which is the order the 3.3.5 arrows step through.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

DB2_TABLES = ("ChrModel", "ChrRaceXChrModel", "ChrCustomizationOption", "ChrCustomizationChoice",
              "ChrCustomizationElement", "ChrCustomizationGeoset", "ChrCustomizationMaterial",
              "ChrCustomizationReq", "ChrCustomizationCondModel", "ChrModelTextureLayer",
              "CreatureDisplayInfo", "CreatureModelData")

# per (ClientFileString, sex): the body-shaping choices to take instead of retail's default
# (option name -> choice name): the user picked the Mag'har male's upright stance (2026-10-14)
BODY_CHOICES: dict[tuple[str, int], dict[str, str]] = {("MagharOrc", 0): {"Hunched": "Upright"}}
# per (ClientFileString, sex): the options 3.3.5's features slot combines (first major)
FEATURES: dict[tuple[str, int], tuple[str, ...]] = {("MagharOrc", 0): ("Beard", "Sideburns"),
                                                     ("MagharOrc", 1): ("Earrings", "Nose Ring")}
# CharacterFacialHairStyles.Geoset[i] sets geoset group FACIAL_GROUPS[i] (convert.FACIAL_SLOT_GROUPS)
FACIAL_GROUPS = (1, 3, 2, 16, 17)
# where an option outside the facial groups goes, first free first: 3.3.5's own Orc female wears
# her earrings in group 3
FREE_FACIAL_GROUPS = (3, 2, 1, 16)
# 3.3.5 switches geoset groups 0-18 (convert.MANAGED_GEOSET_GROUPS); higher ones always draw
MANAGED = 19
EARS = 7
SHOWN_EARS = 702                     # the ear geoset 3.3.5 shows (every client race model has it)
EYE_GLOW = 17
RETAIL_DK_GLOW, CLIENT_DK_GLOW = 1701, 1703
# unswitchable groups whose retail default is more than xx01: the face (32) draws 3201, a piece
# every face shape shares, and the first face shape, 3202 (a Human's Face Shape option picks
# 3202-3204; a race without the option draws 3202 - the Mag'har's whole face, 1,968 triangles;
# wow.export shows every 32xx by default)
GROUP_DEFAULTS = {32: (1, 2)}
PLAYABLE_FLAGS = 17                  # CharSections.Flags of the client's own HD player rows
DK_CLASS_BIT = 1 << 5                # ChrClasses 6
REQ_CLASS = 3                        # ChrCustomizationReq.ReqType: a class requirement
FACE_SECTIONS = 0x200 | 0x400        # TextureSectionTypeBitMask bits 9 (FaceUpper), 10 (FaceLower)
PELVIS, TORSO = 0x20, 0x08           # LegUpper (5), TorsoUpper (3)


class RetailError(ValueError):
    pass


@dataclass
class RetailCharacter:
    """One retail race/sex as the converter's inputs (BfA table shapes)."""
    race_id: int
    sex: int
    chr_model: int
    layout_id: int
    model_fdid: int
    model_note: str = ""
    # the ChrModel display's own model: the body when no choice reshapes it; else the model whose
    # skeleton the chosen body's inherits from (its events fill the inherited sequences')
    display_fdid: int = 0
    # CharSections-shaped: BaseSection, VariationIndex, ColorIndex, Flags, MaterialResourcesID[3]
    sections: list[dict] = field(default_factory=list)
    # CharHairGeosets-shaped: VariationID, GeosetID, GeosetType
    hair: list[dict] = field(default_factory=list)
    # 3.3.5 CharacterFacialHairStyles rows: VariationID, Geoset[5]
    facial: list[dict] = field(default_factory=list)
    # applied to the converted skins: geoset -> new id, 0 (body) or None (hidden)
    geosets: dict[int, int | None] = field(default_factory=dict)
    # the eye texture (retail's default eye colour), baked into the type-19 slots
    eye_material: int | None = None
    # barber shop names: {"hair": {variation: name}, "facial": {variation: name}}
    names: dict[str, dict[int, str]] = field(default_factory=lambda: {"hair": {}, "facial": {}})
    notes: list[str] = field(default_factory=list)


@dataclass
class _Option:
    id: int
    name: str
    order: int
    choices: list[dict]                  # playable, in UI order
    all_choices: list[dict]


def _rows(table) -> dict[int, dict]:
    return {i: r for i, r in table}


def _playable(req: dict | None) -> bool:
    """A new character may pick it: no requirement, or only a class one that admits a class
    other than the death knight (retail's DK-only eyes are its own choices)."""
    if req is None:
        return True
    if req.get("ReqType") != REQ_CLASS:
        return False
    if req.get("ReqAchievementID") or req.get("ReqQuestID") or req.get("ReqItemModifiedAppearanceID"):
        return False
    mask = int(req.get("ClassMask", 0)) & 0xFFFFFFFF
    return bool(mask & ~DK_CLASS_BIT)


def _dk_only(req: dict | None) -> bool:
    return bool(req) and req.get("ReqType") == REQ_CLASS and (int(req.get("ClassMask", 0)) & 0xFFFFFFFF) == DK_CLASS_BIT


def _ui_order(c: dict) -> tuple[int, int, int]:
    return int(c.get("UiOrderIndex", 0)), int(c.get("OrderIndex", 0)), int(c["ID"])


class _Model:
    """One ChrModel's options, choices and elements."""

    def __init__(self, table, chr_model: int):
        self.table = table
        reqs = _rows(table("ChrCustomizationReq"))
        self.reqs = reqs
        self.geo = _rows(table("ChrCustomizationGeoset"))
        self.mat = _rows(table("ChrCustomizationMaterial"))
        options = [(i, o) for i, o in table("ChrCustomizationOption") if o["ChrModelID"] == chr_model]
        ids = {i for i, _o in options}
        choices: dict[int, list[dict]] = defaultdict(list)
        for i, c in table("ChrCustomizationChoice"):
            if c["ChrCustomizationOptionID"] in ids:
                choices[c["ChrCustomizationOptionID"]].append(dict(c, ID=i))
        self.choice_ids = {c["ID"] for cs in choices.values() for c in cs}
        self.elements: dict[int, list[dict]] = defaultdict(list)
        for _i, e in table("ChrCustomizationElement"):
            if e["ChrCustomizationChoiceID"] in self.choice_ids:
                self.elements[e["ChrCustomizationChoiceID"]].append(e)
        self.options: list[_Option] = []
        for i, o in sorted(options, key=lambda t: (t[1]["OrderIndex"], t[0])):
            all_c = sorted(choices[i], key=_ui_order)
            ok = [c for c in all_c if _playable(reqs.get(c["ChrCustomizationReqID"]))]
            self.options.append(_Option(i, str(o.get("Name_lang", "")), int(o["OrderIndex"]), ok, all_c))

    def geosets(self, choice: dict, related: set[int] | None = None) -> list[int]:
        """The geosets (group * 100 + id) a choice sets: every one, or with ``related`` only those
        that apply alone or alongside one of those choices (a Mag'har eye colour's blind-eye
        pieces come with the Eyesight choices)."""
        out = []
        for e in self.elements[choice["ID"]]:
            rel = e.get("RelatedChrCustomizationChoiceID") or 0
            if related is not None and rel and rel not in related:
                continue
            g = self.geo.get(e["ChrCustomizationGeosetID"])
            if g:
                out.append(int(g["GeosetType"]) * 100 + int(g["GeosetID"]))
        return out

    def defaults(self) -> set[int]:
        """Each option's default choice (its first playable one)."""
        return {o.choices[0]["ID"] for o in self.options if o.choices}

    def materials(self, choice: dict, related: int | None = None) -> dict[int, int]:
        """texture target -> MaterialResourcesID the choice sets (with ``related``: the elements that
        apply alongside that choice, else those that apply alone)."""
        out = {}
        for e in self.elements[choice["ID"]]:
            m = self.mat.get(e["ChrCustomizationMaterialID"])
            rel = e.get("RelatedChrCustomizationChoiceID") or 0
            if m and (rel == (related or 0) or (related is not None and rel == 0)):
                out.setdefault(int(m["ChrModelTextureTargetID"]), int(m["MaterialResourcesID"]))
        return out

    def related_materials(self, choice: dict) -> dict[int, dict[int, int]]:
        """related choice id -> {target: material} (0: no relation)."""
        out: dict[int, dict[int, int]] = defaultdict(dict)
        for e in self.elements[choice["ID"]]:
            m = self.mat.get(e["ChrCustomizationMaterialID"])
            if m:
                out[e.get("RelatedChrCustomizationChoiceID") or 0][int(m["ChrModelTextureTargetID"])] = \
                    int(m["MaterialResourcesID"])
        return out

    def cond_model(self, choice: dict) -> int:
        for e in self.elements[choice["ID"]]:
            if e.get("ChrCustomizationCondModelID"):
                return int(e["ChrCustomizationCondModelID"])
        return 0

    def by_name(self, name: str) -> _Option | None:
        want = name.lower()
        return next((o for o in self.options if o.name.lower() == want), None)


def _layers(table, layout_id: int) -> dict[int, dict]:
    """texture target -> its ChrModelTextureLayer row on ``layout_id`` (the lowest layer)."""
    out: dict[int, dict] = {}
    for _i, r in table("ChrModelTextureLayer"):
        if r["CharComponentTextureLayoutsID"] != layout_id:
            continue
        target = r["ChrModelTextureTargetID"]
        target = int(target[0] if isinstance(target, (list, tuple)) else target)
        if target not in out or r["Layer"] < out[target]["Layer"]:
            out[target] = dict(r, target=target)
    return out


def chr_model_for(table, race_id: int, sex: int) -> dict:
    for _i, r in table("ChrRaceXChrModel"):
        if r["ChrRacesID"] == race_id and r["Sex"] == sex:
            for mid, m in table("ChrModel"):
                if mid == r["ChrModelID"]:
                    return dict(m, ID=mid)
    raise RetailError(f"no ChrModel for race {race_id} sex {sex} (ChrRaceXChrModel)")


def _model_fdid(table, display_id: int = 0, model_data_id: int = 0) -> int:
    if display_id:
        cdi = next((r for i, r in table("CreatureDisplayInfo") if i == display_id), None)
        if cdi is None:
            raise RetailError(f"display {display_id} is not in CreatureDisplayInfo")
        model_data_id = cdi["ModelID"]
    cmd = next((r for i, r in table("CreatureModelData") if i == model_data_id), None)
    if cmd is None or not cmd.get("FileDataID"):
        raise RetailError(f"model {model_data_id} is not in CreatureModelData")
    return int(cmd["FileDataID"])


def _section_targets(layers: dict[int, dict], bits: int, texture_type: int = 1) -> list[dict]:
    return sorted((r for r in layers.values() if r["TextureType"] == texture_type
                   and int(r["TextureSectionTypeBitMask"]) & 0xFFFFFFFF != 0xFFFFFFFF
                   and int(r["TextureSectionTypeBitMask"]) & bits), key=lambda r: r["Layer"])


def read_character(table, race_id: int, sex: int, cfs: str, model_geosets: set[int] | None = None,
                   choose: dict[str, str] | None = None, features: tuple[str, ...] | None = None
                   ) -> RetailCharacter:
    """Project a retail race/sex onto 3.3.5's customization (see the module doc). ``table`` reads
    a DB2 table by name ((id, row) pairs). ``model_geosets``: the body model's geosets, when
    known - features are then checked against them; else they are read later (``plan_geosets``)."""
    m = chr_model_for(table, race_id, sex)
    out = RetailCharacter(race_id, sex, m["ID"], int(m["CharComponentTextureLayoutID"]), 0)
    model = _Model(table, m["ID"])
    layers = _layers(table, out.layout_id)

    # --- the body model: the display's, or a body-shaping choice's conditional model ---
    choose = dict(BODY_CHOICES.get((cfs, sex), {}) if choose is None else choose)
    model_data = 0
    for opt_name, choice_name in choose.items():
        opt = model.by_name(opt_name)
        pick = next((c for c in (opt.all_choices if opt else []) if str(c["Name_lang"]).lower() == choice_name.lower()),
                    None)
        if pick is None:
            raise RetailError(f"no choice '{choice_name}' in option '{opt_name}' of ChrModel {m['ID']}")
        cond = model.cond_model(pick)
        if cond:
            row = next((r for i, r in table("ChrCustomizationCondModel") if i == cond), None)
            if row:
                model_data = int(row["CreatureModelDataID"])
                out.model_note = f"{opt.name} = {pick['Name_lang']}"
    out.display_fdid = _model_fdid(table, int(m["DisplayID"]))
    out.model_fdid = _model_fdid(table, 0, model_data) if model_data else out.display_fdid

    # --- which option is which ---
    base = next((r for r in layers.values() if r["TextureType"] == 1 and r["Layer"] == 0), None)
    if base is None:
        raise RetailError(f"layout {out.layout_id} has no base body layer")
    hair_t = {t for t, r in layers.items() if r["TextureType"] == 6}
    eye_t = sorted((r for r in layers.values() if r["TextureType"] == 19), key=lambda r: r["Layer"])
    face_t = _section_targets(layers, FACE_SECTIONS)
    pelvis_t = _section_targets(layers, PELVIS)
    torso_t = _section_targets(layers, TORSO)

    def sets_target(o: _Option, targets: set[int]) -> bool:
        return any(t in targets for c in o.all_choices for rel in model.related_materials(c).values() for t in rel)

    skin = next((o for o in model.options if sets_target(o, {base["target"]})), None)
    hair_color = next((o for o in model.options if sets_target(o, hair_t)), None)
    eye_color = next((o for o in model.options if eye_t and sets_target(o, {eye_t[0]["target"]})), None)
    face = None
    for r in face_t:                                     # the lowest face layer's option: the face itself
        face = next((o for o in model.options if o is not skin and sets_target(o, {r["target"]})), None)
        if face:
            face_target = r["target"]
            break
    hair_style = next((o for o in model.options
                       if any(g // 100 == 0 for c in o.choices for g in model.geosets(c))), None)
    if skin is None or not skin.choices:
        raise RetailError(f"ChrModel {m['ID']}: no skin colour option")

    # --- skin colours: body + underwear ---
    skins = skin.choices
    for ci, c in enumerate(skins):
        mats = model.materials(c)
        out.sections.append(_section(0, 0, ci, [mats.get(base["target"], 0), 0, 0]))
        pel = next((mats[r["target"]] for r in pelvis_t if r["target"] in mats), 0)
        tor = next((mats[r["target"]] for r in torso_t if r["target"] in mats), 0)
        if pel or tor:
            out.sections.append(_section(4, 0, ci, [pel, tor, 0]))
    # --- faces, per skin colour ---
    if face is not None:
        for vi, c in enumerate(face.choices):
            rel = model.related_materials(c)
            for ci, s in enumerate(skins):
                mat = rel.get(s["ID"], {}).get(face_target) or rel.get(0, {}).get(face_target, 0)
                if mat:
                    out.sections.append(_section(1, vi, ci, [mat, 0, 0]))
    else:
        out.notes.append("no face option: faces are the skin texture's own")
    # --- hair: style x colour ---
    styles = hair_style.choices if hair_style else []
    colors = hair_color.choices if hair_color else []
    for vi, c in enumerate(styles):
        gid = next((g for g in model.geosets(c) if g // 100 == 0), 0)
        out.hair.append({"VariationID": vi, "GeosetID": gid, "GeosetType": 0})
        out.names["hair"][vi] = str(c["Name_lang"]) or f"Style {vi + 1}"
        for ci, col in enumerate(colors or [None]):
            mats = model.materials(col) if col else {}
            mat = next((mats[t] for t in sorted(hair_t) if t in mats), 0)
            out.sections.append(_section(3, vi, ci, [mat, 0, 0]))
    # --- eyes: the default colour, fixed ---
    if eye_color is not None and eye_color.choices:
        out.eye_material = model.materials(eye_color.choices[0]).get(eye_t[0]["target"])

    # --- features and the geosets 3.3.5 can't switch ---
    used = {o.id for o in (skin, face, hair_style, hair_color, eye_color) if o}
    geo_options = [o for o in model.options if o.id not in used and o.choices
                   and any(model.geosets(c) for c in o.all_choices)]
    picked = _feature_options(geo_options, model, FEATURES.get((cfs, sex)) if features is None else features)
    out.facial, remap = _features(picked, model, out.names["facial"], out.notes)
    out.geosets.update(remap)
    out.geosets.update(_fixed_geosets([o for o in geo_options if o not in picked], model, out.notes))
    if eye_color is not None:
        out.geosets.update(_fixed_geosets([eye_color], model, []))     # its blind-eye pieces
        out.notes.append(f"'{eye_color.name}' fixed at retail's default colour (a texture baked into the eyeballs: "
                         "3.3.5 has no eye texture)")
    for o in model.options:
        if o.id not in used and o not in geo_options and o.choices and not any(model.cond_model(c) for c in o.all_choices):
            out.notes.append(f"option '{o.name}' ({len(o.choices)} choices) has no 3.3.5 slot: retail's default is drawn")
    if model_geosets is not None:
        plan_geosets(out, model_geosets)
    return out


def _section(section: int, variation: int, color: int, mats: list[int]) -> dict:
    return {"BaseSection": section, "VariationIndex": variation, "ColorIndex": color, "Flags": PLAYABLE_FLAGS,
            "MaterialResourcesID": mats}


def _feature_options(options: list[_Option], model: _Model, names: tuple[str, ...] | None) -> list[_Option]:
    if names:
        picked = [model.by_name(n) for n in names]
        missing = [n for n, o in zip(names, picked) if o is None]
        if missing:
            raise RetailError(f"no option named {missing} for the features slot")
        return [o for o in picked if o in options][:2]
    facial = [o for o in options if all(g // 100 in FACIAL_GROUPS[:4] for c in o.choices for g in model.geosets(c))]
    return facial[:2]


def _features(options: list[_Option], model: _Model, names: dict[int, str], notes: list[str]
              ) -> tuple[list[dict], dict[int, int | None]]:
    """3.3.5 features rows combining ``options`` (first major), and the geoset renumbering that
    puts an option outside the facial groups into a free one."""
    remap: dict[int, int | None] = {}
    taken = set()
    groups = {}
    for o in options:
        gs = {g // 100 for c in o.all_choices for g in model.geosets(c) if g // 100 != EARS}
        if len(gs) != 1:
            raise RetailError(f"option '{o.name}' sets geoset groups {sorted(gs)}; a feature must set one")
        groups[o.id] = gs.pop()
        if groups[o.id] in FACIAL_GROUPS[:4]:
            taken.add(groups[o.id])
    for o in options:
        g = groups[o.id]
        if g in FACIAL_GROUPS[:4]:
            continue
        free = next((f for f in FREE_FACIAL_GROUPS if f not in taken), None)
        if free is None:
            raise RetailError(f"no free facial group for option '{o.name}' (group {g})")
        taken.add(free)
        groups[o.id] = free
        for c in o.all_choices:
            for geo in model.geosets(c):
                if geo // 100 == g and geo % 100:
                    remap[geo] = free * 100 + geo % 100
        notes.append(f"features: '{o.name}' geosets {g}xx renumbered to {free}xx (a facial group 3.3.5 switches)")

    lists = []
    for o in options:
        values = []
        for c in o.choices:
            ears = [g for g in model.geosets(c) if g // 100 == EARS]
            if any(g != SHOWN_EARS for g in ears):
                notes.append(f"features: '{o.name}' choice '{c['Name_lang']}' left out: it needs ears {ears}, "
                             f"3.3.5 always shows {SHOWN_EARS}")
                continue
            value = next((g % 100 for g in model.geosets(c) if g // 100 != EARS), 0)
            values.append((value, str(c["Name_lang"]) or f"{o.name} {len(values) + 1}"))
        lists.append((groups[o.id], values))
    combos: list[tuple[list[tuple[int, int]], list[str]]] = [([], [])]
    for g, values in lists:
        combos = [(geo + [(g, v)], label + [name]) for geo, label in combos for v, name in values]
    rows = []
    for k, (geo, label) in enumerate(combos):
        slots = [0] * 5
        for g, v in geo:
            slots[FACIAL_GROUPS.index(g)] = v
        rows.append({"VariationID": k, "Geoset": slots})
        shown = [n for n in label if n.lower() != "none"]
        names[k] = ", ".join(shown) if shown else "None"
    return rows, remap


def _fixed_geosets(options: list[_Option], model: _Model, notes: list[str]) -> dict[int, int | None]:
    """Unswitchable groups (20+) set by an option 3.3.5 has no slot for: its default choice's
    piece is kept as body, the others hidden. Returns {geoset: 0 | None} for those groups."""
    out: dict[int, int | None] = {}
    defaults = model.defaults()
    for o in options:
        default = set(model.geosets(o.choices[0], related=defaults)) if o.choices else set()
        for c in o.all_choices:
            for g in model.geosets(c):
                if g // 100 >= MANAGED and g % 100:
                    out[g] = 0 if g in default else None
        kept = sorted(g for g in default if g % 100 and g // 100 != EARS)
        notes.append(f"'{o.name}' not offered (3.3.5 has one features slot): fixed at "
                     f"'{o.choices[0]['Name_lang'] or 'default'}'" + (f" (geoset {', '.join(map(str, kept))})" if kept else ""))
        if any(g // 100 < MANAGED for g in kept):
            notes.append(f"'{o.name}': 3.3.5 shows its group only through the features slot, so its default "
                         f"{[g for g in kept if g // 100 < MANAGED]} is not drawn")
    return out


def plan_geosets(ch: RetailCharacter, model_geosets: set[int]) -> None:
    """Complete ``ch.geosets`` for the body model: every other unswitchable group keeps xx01 as
    body (retail's default value; ``GROUP_DEFAULTS`` where it is more) and hides the rest; the eye
    glows as 3.3.5 shows them."""
    moved = {v // 100 for k, v in ch.geosets.items() if v and v // 100 != k // 100}
    clash = sorted(g for g in model_geosets if g // 100 in moved and g not in ch.geosets)
    if clash:
        raise RetailError(f"features: the model already has geosets {clash} in the group a feature was moved to")
    decided = {k // 100 for k in ch.geosets}            # groups an option already set
    for g in sorted(model_geosets):
        grp = g // 100
        if grp < MANAGED or g in ch.geosets:
            continue
        ch.geosets[g] = None if grp in decided else (0 if g % 100 in GROUP_DEFAULTS.get(grp, (1,)) else None)
    if RETAIL_DK_GLOW in model_geosets:
        for g in model_geosets:
            if g // 100 == EYE_GLOW:
                ch.geosets[g] = None
        ch.geosets[RETAIL_DK_GLOW] = CLIENT_DK_GLOW
    # hair and facial pieces no row can select (the plain Orc's hair styles and beards on a Mag'har
    # body) are hidden: 3.3.5 shows those groups only as the rows say, and hidden submeshes go
    # after the drawn ones (fixup.order_skin_indices), which keeps more switchable geometry below
    # index 65,535
    hair = {h["GeosetID"] for h in ch.hair}
    facial = {FACIAL_GROUPS[i] * 100 + v for r in ch.facial for i, v in enumerate(r["Geoset"][:4]) if v}
    unused = []
    for g in sorted(model_geosets):
        new = ch.geosets.get(g, g)
        if not new:
            continue
        if (new // 100 == 0 and new not in hair) or (new // 100 in FACIAL_GROUPS[:4] and new not in facial):
            ch.geosets[g] = None
            unused.append(g)
    if unused:
        ch.notes.append(f"{len(unused)} hair/facial geoset(s) no customization row selects are hidden: {unused}")
