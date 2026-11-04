"""Retail's mounts: the catalog the Mounts page browses, and the rows a 3.3.5 client and an
AzerothCore server need to ride one - the same for both install routes (``mountpack`` runs them).

A retail mount (Mount) is a spell (SourceSpellID) that shows one of its displays (MountXDisplay ->
CreatureDisplayInfo: a model, CreatureModelData, and up to four skin textures) and flies when its
type (MountTypeXCapability -> MountCapability) can. In 3.3.5 a mount is:

* a spell like the stock epic mounts (23229 Swift Brown Steed on the ground, 32242 Swift Blue
  Gryphon in the air): aura 78 "mounted" naming a creature, and the speed auras - in the client's
  Spell.dbc (to cast it), with its icon (SpellIcon.dbc) and a SkillLineAbility row in skill line 777
  (the spellbook's Mounts tab); and in the server's (``spell_dbc``);
* the creature the aura names (``creature_template`` and its model), whose display is a
  CreatureDisplayInfo row - textures by name in the model's own folder, its parts by the packed
  CreatureGeosetData (a nibble per geoset group 1-8: show group*100 + n) - and a CreatureModelData
  row, in the client's tables and the server's (``creaturedisplayinfo_dbc``, ``creaturemodeldata_dbc``);
* its sounds: retail's CreatureSoundData row (CreatureDisplayInfo.SoundID, else its model's) as a
  3.3.5 one - each of its sound kits a SoundEntries row with retail's .ogg files (the client's FMOD
  plays Ogg Vorbis; ``race.sounds`` does the same for a race's voice), its footsteps by terrain
  (FootstepTerrainLookup) where 3.3.5 hasn't got them; a mounted player sounds like the mount;
* an item that teaches it (spell 483 "Learning", then the mount spell), named as retail's own, its
  bag icon retail's (an ItemDisplayInfo row of its own: ``with_item_displays``).

The client tables are whole files: the route's patch carries each with the client's rows (as the
patch finds them) plus the mounts', so it must outrank every archive holding one of them
(``TABLES``). The item display table is the exception - the item kit's patch holds it above the
mounts' (``mountpack.place_item_rows`` adds the rows to whichever archive is on top). Ids come from
one registry (``<data>/mount-ids.json``) so a mount keeps its spell, creature and item ids from
install to install - players keep the mounts they learned.
"""

from __future__ import annotations

import gzip
import json
import os
import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field

CATALOG_VERSION = 2
SOURCE_TABLES = ("Mount", "MountXDisplay", "MountTypeXCapability", "MountCapability", "CreatureDisplayInfo",
                 "CreatureModelData", "CreatureDisplayInfoGeosetData", "SpellMisc", "ItemEffect", "ItemXItemEffect",
                 "ItemSearchName", "CreatureSoundData", "FootstepTerrainLookup", "SoundKit", "SoundKitEntry")
SOURCES = {0: "Drop", 1: "Quest", 2: "Vendor", 3: "Profession", 4: "Pet battle", 5: "Achievement", 6: "World event",
           7: "Promotion", 8: "Trading card game", 9: "Shop", 10: "Discovery", 11: "Trading Post"}
KINDS = ("ground", "flying")
FLIES = 0x2                                 # MountCapability.Flags: the capability flies

# the client tables a mount adds rows to (a route's patch must be their highest holder), and the
# item display table (the route's patch carries it, but another may hold it above - see the module doc)
TABLES = ("Spell", "SpellIcon", "SkillLineAbility", "CreatureDisplayInfo", "CreatureModelData", "SoundEntries",
          "CreatureSoundData", "FootstepTerrainLookup")
ITEM_TABLE = "ItemDisplayInfo"
TEMPLATE_SPELL = {"ground": 23229, "flying": 32242}         # Swift Brown Steed, Swift Blue Gryphon
TEMPLATE_MODEL = {"ground": "creature\\ridinghorse\\ridinghorse.mdx", "flying": "creature\\drakemount\\drakemount.mdx"}
ITEM_ICONS = {"ground": ("ability_mount_ridinghorse", "inv_misc_key_14"),
              "flying": ("ability_mount_drake_proto", "ability_mount_gryphon_01", "inv_misc_key_14")}
RIDING = {"ground": (150, 40), "flying": (300, 70)}          # RequiredSkillRank (Riding 762), RequiredLevel
LEARNING = 483                                              # the stock "Learning" spell items teach with
MOUNT_SKILL = 777                                           # SkillLine "Mounts" (the spellbook's Mounts tab)
FOLDER = "creature\\retroport\\"            # every mount file goes under it: no stock file is replaced
ID_BASE, ITEM_BASE = 250000, 990000

# Spell.dbc (3.3.5, 234 fields - spell_dbc's columns in order)
SPELL_FIELDS = 234
SPELL_MISC_1, SPELL_ICON, SPELL_ACTIVE_ICON = 110, 133, 134
SPELL_NAME, SPELL_SUBTEXT, SPELL_DESCRIPTION, SPELL_AURA_TEXT = 136, 153, 170, 187
# CreatureModelData (28 fields) and CreatureDisplayInfo (16)
CMD_NAME, CMD_SCALE, CMD_COLLISION, CMD_MOUNT_HEIGHT, CMD_GEOBOX, CMD_EFFECT_SCALES, CMD_MISSILE = 2, 4, 14, 16, 17, 23, 25
CDI_FIELDS, CMD_FIELDS = 16, 28
CDI_COLUMNS = ("ID", "ModelID", "SoundID", "ExtendedDisplayInfoID", "CreatureModelScale", "CreatureModelAlpha",
               "TextureVariation_1", "TextureVariation_2", "TextureVariation_3", "PortraitTextureName", "BloodLevel",
               "BloodID", "NPCSoundID", "ParticleColorID", "CreatureGeosetData", "ObjectEffectPackageID")
CMD_COLUMNS = ("ID", "Flags", "ModelName", "SizeClass", "ModelScale", "BloodID", "FootprintTextureID",
               "FootprintTextureLength", "FootprintTextureWidth", "FootprintParticleScale", "FoleyMaterialID",
               "FootstepShakeSize", "DeathThudShakeSize", "SoundID", "CollisionWidth", "CollisionHeight", "MountHeight",
               "GeoBoxMinX", "GeoBoxMinY", "GeoBoxMinZ", "GeoBoxMaxX", "GeoBoxMaxY", "GeoBoxMaxZ", "WorldEffectScale",
               "AttachedEffectScale", "MissileCollisionRadius", "MissileCollisionPush", "MissileCollisionRaise")
CMD_FLOATS = {4, 7, 8, 9, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27}
CDI_FLOATS = {4}
CDI_SOUND, CMD_SOUND = 2, 13                 # each names a CreatureSoundData row (the display's first)
# CreatureSoundData (38 fields: race.sounds), FootstepTerrainLookup (5: ID, CreatureFootstepID,
# TerrainSoundID, SoundID, SoundIDSplash), ItemDisplayInfo (25: 5 InventoryIcon_1, 12 GroupSoundIndex)
CSD_FIELDS, CSD_FOOTSTEP, CSD_NPC_SOUND, CSD_PET = 38, 9, 23, 37
FTL_FIELDS, IDI_FIELDS, IDI_ICON = 5, 25, 5
IDI_STRINGS = {1, 2, 3, 4, 5, 6, *range(15, 23)}

# mount row: the fields the Mounts page lists, in this order
MOUNT_FIELDS = ("id", "name", "kind", "icon", "spell", "source", "item", "item_name", "quality", "displays",
                "description", "source_text")
F = {name: k for k, name in enumerate(MOUNT_FIELDS)}


def f2u(v) -> int:
    return struct.unpack("<I", struct.pack("<f", float(v or 0.0)))[0]


def u2f(v: int) -> float:
    return struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0]


# -- the catalog ----------------------------------------------------------------------------------
@dataclass
class MountCatalog:
    source: str
    build: str
    mounts: list[list]                                  # MOUNT_FIELDS rows
    displays: dict[int, dict]                           # display id -> {model, textures, scale, alpha, geosets, model_data, sound}
    sounds: dict = field(default_factory=dict)          # the displays' sounds (``sound_bundle``)
    by_id: dict[int, list] = field(default_factory=dict)
    families: dict[int, list[int]] = field(default_factory=dict)    # ``model_families``
    root_of: dict[int, int] = field(default_factory=dict)          # mount -> its family's first

    def __post_init__(self):
        self.by_id = {r[0]: r for r in self.mounts}
        self.families = model_families(self.mounts, self.displays)
        self.root_of = {m: root for root, ids in self.families.items() for m in ids}

    def search(self, q: str = "", kind: str = "", page: int = 0, per: int = 60, junk: bool = False,
               families: bool = True) -> tuple[int, list[dict]]:
        """Mounts matching the search, one card per family: its oldest mount that matches."""
        from .catalog import is_junk
        q = (q or "").strip().lower()
        hits = []
        for r in self.mounts:
            if kind and r[F["kind"]] != kind:
                continue
            if not junk and is_junk(r[F["name"]]):
                continue
            if q and not (q in r[F["name"]].lower() or q == str(r[0]) or q == str(r[F["spell"]])
                          or q in (r[F["item_name"]] or "").lower()):
                continue
            hits.append(r)
        if families:
            first: dict[int, list] = {}
            for r in sorted(hits, key=lambda r: r[0]):
                first.setdefault(self.root_of.get(r[0], r[0]), r)
            hits = list(first.values())
        hits.sort(key=lambda r: (-r[0]))
        return len(hits), [self.row(r) | {"versions": len(self.family(r[0], junk)) if families else 1}
                           for r in hits[page * per:(page + 1) * per]]

    def row(self, r: list) -> dict:
        d = dict(zip(MOUNT_FIELDS, r))
        d["source_label"] = SOURCES.get(d["source"], "")
        d["root"] = self.root_of.get(r[0], r[0])
        return d

    def family(self, mount_id: int, junk: bool = False) -> list[list]:
        """The mount's versions: its family's mounts, oldest first - a placeholder ("[PH] ...") only
        with ``junk`` or when it is the mount itself."""
        from .catalog import is_junk
        ids = self.families.get(self.root_of.get(mount_id, mount_id), [mount_id])
        return [self.by_id[i] for i in ids if i == mount_id or junk or not is_junk(self.by_id[i][F["name"]])]

    def detail(self, mount_id: int) -> dict | None:
        from .catalog import is_junk
        r = self.by_id.get(int(mount_id))
        if r is None:
            return None
        d = self.row(r)
        d["display_rows"] = [dict(self.displays.get(x) or {}, id=x) for x in d["displays"]]
        fam = [self.row(o) for o in self.family(r[0], is_junk(r[F["name"]]))]
        d["family"] = [{k: o[k] for k in ("id", "name", "kind", "icon", "quality", "displays", "source_label")}
                       | {"label": label} for o, label in zip(fam, version_labels([o["name"] for o in fam]))]
        return d

    def to_json(self) -> dict:
        return {"version": CATALOG_VERSION, "source": self.source, "build": self.build, "mounts": self.mounts,
                "displays": {str(k): v for k, v in self.displays.items()}, "sounds": self.sounds}

    @classmethod
    def from_json(cls, d: dict) -> "MountCatalog":
        return cls(d["source"], d["build"], d["mounts"], {int(k): v for k, v in d["displays"].items()},
                   d.get("sounds") or {})


def model_families(mounts: list[list], displays: dict[int, dict]) -> dict[int, list[int]]:
    """Mounts that are one model in other skins (the drakes, the riding cranes...), by the model of
    each one's first display: {its oldest mount: the family's mounts, oldest first}. A mount whose
    model no other one rides is a family of its own."""
    by_model: dict[int, list[int]] = defaultdict(list)
    for r in mounts:
        shown = r[F["displays"]]
        model = (displays.get(shown[0]) or {}).get("model") if shown else 0
        by_model[model or -r[0]].append(r[0])            # no model: alone
    return {min(ids): sorted(ids) for ids in by_model.values()}


def version_labels(names: list[str]) -> list[str]:
    """Each version's chip: its name without the words every one of them has ("Azure", "Golden"...
    Riding Crane), else the whole name; a label two versions share is numbered (Black Wolf, Black Wolf 2)."""
    common = set.intersection(*(set(n.split()) for n in names)) if names else set()
    short = [" ".join(w for w in n.split() if w not in common) for n in names]
    if not all(short):
        short = list(names)
    seen: dict[str, int] = defaultdict(int)
    out = []
    for s in short:
        seen[s] += 1
        out.append(s if seen[s] == 1 else f"{s} {seen[s]}")
    return out


def mount_kind(caps: list[dict]) -> str:
    """"flying" when any of the type's capabilities flies, else "ground" (3.3.5 knows no others)."""
    return "flying" if any((c or {}).get("Flags", 0) & FLIES for c in caps) else "ground"


def build_catalog(src, log=lambda m: None) -> MountCatalog:
    """Every retail mount of ``src`` with its displays (see the module doc)."""
    t0 = time.time()
    t = {}
    for name in SOURCE_TABLES:
        try:
            t[name] = src.table(name)
        except Exception as e:                        # a table this build lacks leaves its part empty
            log(f"{src.spec.label}: {name}: {e}")
            t[name] = []
    caps = {i: r for i, r in t["MountCapability"]}
    type_caps: dict[int, list] = {}
    for _i, r in t["MountTypeXCapability"]:
        type_caps.setdefault(r["MountTypeID"], []).append(caps.get(r["MountCapabilityID"]))
    displays_of: dict[int, list[int]] = {}
    for _i, r in t["MountXDisplay"]:
        if r["CreatureDisplayInfoID"]:
            displays_of.setdefault(r["MountID"], []).append(r["CreatureDisplayInfoID"])
    icon_of = {}
    for _i, r in t["SpellMisc"]:
        if not r.get("DifficultyID") and r.get("SpellIconFileDataID"):
            icon_of.setdefault(r["SpellID"], r["SpellIconFileDataID"])
    effects = {i: r for i, r in t["ItemEffect"]}
    names = {i: r for i, r in t["ItemSearchName"]}
    item_of: dict[int, int] = {}                       # mount spell -> the item that teaches it
    for _i, r in t["ItemXItemEffect"]:
        e = effects.get(r["ItemEffectID"])
        if e and e.get("TriggerType") == 6 and e.get("SpellID"):
            cur = item_of.get(e["SpellID"])
            if cur is None or (r["ItemID"] in names and cur not in names):
                item_of[e["SpellID"]] = r["ItemID"]
    cdi = {i: r for i, r in t["CreatureDisplayInfo"]}
    cmd = {i: r for i, r in t["CreatureModelData"]}
    geosets: dict[int, list] = {}
    for _i, r in t["CreatureDisplayInfoGeosetData"]:
        geosets.setdefault(r["CreatureDisplayInfoID"], []).append([r["GeosetIndex"], r["GeosetValue"]])

    mounts, displays = [], {}
    for mid, r in t["Mount"]:
        shown = [d for d in dict.fromkeys(displays_of.get(mid, [])) if d in cdi]
        if not r.get("Name_lang") or not shown:
            continue
        spell = r.get("SourceSpellID") or 0
        item = item_of.get(spell, 0)
        n = names.get(item) or {}
        mounts.append([mid, r["Name_lang"], mount_kind(type_caps.get(r.get("MountTypeID"), [])), icon_of.get(spell, 0),
                       spell, r.get("SourceTypeEnum", -1), item, n.get("Display_lang") or "", n.get("OverallQualityID", 4),
                       shown, r.get("Description_lang") or "", r.get("SourceText_lang") or ""])
        for d in shown:
            if d in displays:
                continue
            c = cdi[d]
            m = cmd.get(c.get("ModelID")) or {}
            textures = list(c.get("TextureVariationFileDataID") or [])
            displays[d] = {"model": m.get("FileDataID") or 0, "textures": [x or 0 for x in textures],
                           "scale": c.get("CreatureModelScale") or 1.0, "alpha": c.get("CreatureModelAlpha", 255),
                           "geosets": sorted(geosets.get(d, [])),
                           "model_data": {k: m.get(k) for k in ("ModelScale", "CollisionWidth", "CollisionHeight",
                                                                "MountHeight", "GeoBox", "WorldEffectScale",
                                                                "AttachedEffectScale", "MissileCollisionRadius",
                                                                "MissileCollisionPush", "MissileCollisionRaise")},
                           "sound": c.get("SoundID") or m.get("SoundID") or 0}
    sounds = sound_bundle(t, {v["sound"] for v in displays.values() if v["sound"]})
    log(f"{src.spec.label}: {len(mounts)} mounts, {len(sounds['kits'])} sound kits ({time.time() - t0:.0f} s)")
    return MountCatalog(src.key, src.build, mounts, displays, sounds)


def sound_bundle(t: dict[str, list], rows: set[int]) -> dict:
    """The sounds of retail's CreatureSoundData ``rows``, as the catalog keeps them (string keys,
    as JSON has them): {"rows": {row: {"kits": {3.3.5 column: kit}, "footstep": CreatureFootstepID}},
    "footsteps": {footstep: [[TerrainSoundID, kit, splash kit], ...]}, "kits": {kit: [SoundType,
    volume, flags, min distance, cutoff, EAXDef, [[FileDataID, frequency], ...]]}} - every kit a row
    or footstep names that has files."""
    from ..race.sounds import CSD_KIT_COLUMNS
    out_rows, kits = {}, set()
    for i, r in t.get("CreatureSoundData") or []:
        if i not in rows:
            continue
        cols = {}
        for col, (name, idx) in CSD_KIT_COLUMNS.items():
            v = r.get(name, 0)
            v = (list(v or []) + [0] * 5)[idx] if idx is not None else v
            if v:
                cols[str(col)] = v
        out_rows[str(i)] = {"kits": cols, "footstep": r.get("SoundFootstepID") or 0}
        kits |= set(cols.values())
    used = {r["footstep"] for r in out_rows.values() if r["footstep"]}
    steps: dict[str, list] = {}
    for _i, r in t.get("FootstepTerrainLookup") or []:
        if r.get("CreatureFootstepID") in used:
            sound, splash = r.get("SoundID") or 0, r.get("SoundIDSplash") or 0
            steps.setdefault(str(r["CreatureFootstepID"]), []).append([r.get("TerrainSoundID", -1), sound, splash])
            kits |= {sound, splash}
    kits.discard(0)
    files: dict[int, list] = {}
    for i, e in t.get("SoundKitEntry") or []:
        if e.get("SoundKitID") in kits and e.get("FileDataID"):
            files.setdefault(e["SoundKitID"], []).append((i, e["FileDataID"], int(e.get("Frequency") or 1)))
    out_kits = {}
    for i, k in t.get("SoundKit") or []:
        if i in files:
            out_kits[str(i)] = [int(k.get("SoundType") or 0), float(k.get("VolumeFloat") or 1.0), int(k.get("Flags") or 0),
                                float(k.get("MinDistance") or 0.0), float(k.get("DistanceCutoff") or 0.0),
                                int(k.get("EAXDef") or 0), [[f, max(1, w)] for _n, f, w in sorted(files[i])]]
    return {"rows": out_rows, "footsteps": {k: sorted(v) for k, v in steps.items()}, "kits": out_kits}


def load_catalog(src, log=lambda m: None) -> MountCatalog:
    """The source's mounts from the cache when they were read for this build, else read and cached."""
    path = os.path.join(src.cache_dir, f"mounts-{src.key}-{src.build}-v{CATALOG_VERSION}.json.gz")
    if os.path.isfile(path):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                return MountCatalog.from_json(json.load(fh))
        except (OSError, ValueError, KeyError) as e:
            log(f"{src.spec.label}: cached mounts unreadable ({e}); reading them again")
    cat = build_catalog(src, log)
    os.makedirs(src.cache_dir, exist_ok=True)
    with gzip.open(path + ".part", "wt", encoding="utf-8") as fh:
        json.dump(cat.to_json(), fh, separators=(",", ":"))
    os.replace(path + ".part", path)
    return cat


# -- a display in 3.3.5 terms ---------------------------------------------------------------------
def geoset_data(pairs) -> tuple[int, list]:
    """retail's CreatureDisplayInfoGeosetData (GeosetIndex, GeosetValue: show group index+1's
    geoset value) as 3.3.5's packed CreatureGeosetData, and the pairs it can't hold (a group past 8,
    a value past 15)."""
    packed, lost = 0, []
    for index, value in pairs or []:
        if 0 <= index < 8 and 0 < value < 16:
            packed = (packed & ~(0xF << 4 * index)) | (value << 4 * index)
        elif value:
            lost.append([index, value])
    return packed, lost


def geosets_shown(packed: int) -> dict[int, int]:
    """{geoset group: the one geoset it shows} for a packed CreatureGeosetData (3.3.5's
    ApplyMonsterGeosets: group 100-800, a nibble each)."""
    return {g: g * 100 + ((packed >> 4 * (g - 1)) & 0xF) for g in range(1, 9) if (packed >> 4 * (g - 1)) & 0xF}


def relocate(path: str) -> str:
    """Where a mount's file goes in the client: under ``FOLDER``, in its retail folders - so no
    stock file (an old horse's model or skin at the same path) is replaced."""
    p = path.replace("/", "\\").lower()
    if p.startswith(FOLDER):
        return p
    return FOLDER + (p[len("creature\\"):] if p.startswith("creature\\") else p)


def texture_names(model_path: str, textures: dict[int, str]) -> tuple[list[str], dict[str, int]]:
    """A display's skin textures ({slot 0-2: retail path}) as 3.3.5 names them - by name in the
    model's folder - and where each file goes there ({path: slot}); two that share a name in different
    folders keep apart by their slot."""
    folder = model_path.rsplit("\\", 1)[0]
    names, files, used = ["", "", ""], {}, {}
    for slot in sorted(textures):
        if not 0 <= slot < 3 or not textures[slot]:
            continue
        stem = os.path.splitext(textures[slot].replace("/", "\\").rsplit("\\", 1)[-1])[0].lower()
        if used.get(stem, textures[slot]) != textures[slot]:
            stem = f"{stem}_{slot}"
        used[stem] = textures[slot]
        names[slot] = stem
        files[f"{folder}\\{stem}.blp"] = slot
    return names, files


def icon_name(path: str) -> str:
    """An icon's name as SpellIcon and ItemDisplayInfo hold it (no folder, no extension)."""
    return os.path.splitext(path.replace("/", "\\").rsplit("\\", 1)[-1])[0]


# -- ids ------------------------------------------------------------------------------------------
REGISTRY = "mount-ids.json"


def load_ids(data_dir: str) -> dict:
    try:
        with open(os.path.join(data_dir, REGISTRY), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    got = got if isinstance(got, dict) else {}
    return {"mounts": {str(k): dict(v) for k, v in (got.get("mounts") or {}).items()},
            "icons": {str(k): int(v) for k, v in (got.get("icons") or {}).items()},
            "sounds": {str(k): int(v) for k, v in (got.get("sounds") or {}).items()},          # retail kit -> SoundEntries
            "footsteps": {str(k): int(v) for k, v in (got.get("footsteps") or {}).items()},    # "footstep:terrain" -> row
            "owned": {str(k): [list(x) for x in v] for k, v in (got.get("owned") or {}).items()
                      if isinstance(v, list)}}


def save_ids(data_dir: str, ids: dict) -> None:
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, REGISTRY)
    with open(path + ".part", "w", encoding="utf-8") as fh:
        json.dump(ids, fh, indent=1, sort_keys=True)
    os.replace(path + ".part", path)


def allocate(ids: dict, mount_id: int, taken: dict[str, set], items_taken: set) -> dict:
    """The mount's ids (kept in ``ids``): one number from 250000 for its spell, display, model data,
    creature and SkillLineAbility row - the first none of the client's tables (``taken``, by table)
    nor another mount has - and an item entry from 990000 the client's Item.dbc and other projects
    (``items_taken``) don't use."""
    key = str(mount_id)
    got = ids["mounts"].get(key)
    if got:
        return got
    mine = {v.get("id") for v in ids["mounts"].values()}
    n = ID_BASE
    while n in mine or any(n in s for s in taken.values()):
        n += 1
    items = {v.get("item") for v in ids["mounts"].values()}
    item = ITEM_BASE
    while item in items or item in items_taken:
        item += 1
    got = ids["mounts"][key] = {"id": n, "item": item}
    return got


def _kept(table: dict, key: str, taken: set) -> int:
    """``table[key]`` (an id kept in the registry), else the first from 250000 neither ``taken`` nor
    in ``table`` - kept there."""
    if key not in table:
        mine = set(table.values())
        n = ID_BASE
        while n in mine or n in taken:
            n += 1
        table[key] = n
    return table[key]


def icon_id(ids: dict, fdid: int, taken: set) -> int:
    return _kept(ids["icons"], str(fdid), taken)


def sound_id(ids: dict, kit: int, taken: set) -> int:
    """The SoundEntries id of retail's sound kit ``kit``."""
    return _kept(ids["sounds"], str(kit), taken)


def footstep_id(ids: dict, footstep: int, terrain: int, taken: set) -> int:
    """The FootstepTerrainLookup id of retail's footstep ``footstep`` on terrain ``terrain``."""
    return _kept(ids["footsteps"], f"{footstep}:{terrain}", taken)


def display_id(ids: dict, mount_id: int, taken: set) -> int:
    """The ItemDisplayInfo id of the mount's item (its bag icon), kept with its other ids."""
    got = ids["mounts"][str(mount_id)]
    if "display" not in got:
        mine = {v.get("display") for v in ids["mounts"].values()}
        n = ID_BASE
        while n in mine or n in taken:
            n += 1
        got["display"] = n
    return got["display"]


def owned_ids(ids: dict) -> dict[str, set[int]]:
    """Every id the registry gave, by table - an earlier install's rows, wherever a copy of them is."""
    mounts = {int(v["id"]) for v in ids["mounts"].values() if v.get("id")}
    return {"SoundEntries": set(ids["sounds"].values()), "FootstepTerrainLookup": set(ids["footsteps"].values()),
            "CreatureSoundData": mounts, ITEM_TABLE: {int(v["display"]) for v in ids["mounts"].values() if v.get("display")}}


# -- a mount as the client and server get it ------------------------------------------------------
@dataclass
class Ride:
    """One mount (one of its displays) with everything the rows need."""
    mount: int
    name: str
    kind: str
    display: int                             # retail's
    id: int                                  # ours: spell, display, model data, creature, SkillLineAbility
    item: int
    model_path: str                          # in the client, ".mdx" as CreatureModelData names it
    textures: list[str]                      # TextureVariation names
    scale: float = 1.0
    alpha: int = 255
    geosets: int = 0
    model_data: dict = field(default_factory=dict)
    icon: int = 0                            # SpellIcon id (0: the template's)
    item_name: str = ""
    quality: int = 4
    item_display: int = 0                    # the item's ItemDisplayInfo row: its own (item_icon), else a stock one
    template_model: list[int] | None = None  # a stock CreatureModelData row its other fields come from
    retail: dict = field(default_factory=dict)   # its retail files: model, textures {slot: path}, texture_ids, icon
    sound_kits: dict[int, int] | None = None     # CreatureSoundData column -> SoundEntries id (None: the template's sounds)
    footstep: int | None = None                  # its CreatureFootstepID (None: the template's)
    item_icon: str = ""                          # the bag icon its own ItemDisplayInfo row shows
    item_template: list | None = None            # the stock mount item's ItemDisplayInfo row that row copies


@dataclass
class Sounds:
    """The mounts' sounds as 3.3.5 rows besides their CreatureSoundData rows."""
    kits: dict[int, object] = field(default_factory=dict)       # SoundEntries id -> race.sounds.Kit
    footsteps: list[list[int]] = field(default_factory=list)    # FootstepTerrainLookup rows


def description(r: Ride) -> str:
    text = f"Summons and dismisses a rideable {r.name}.  This is a very fast mount."
    return text + ("  It flies where flying is allowed." if r.kind == "flying" else "")


def spell_row(spell, template: list[int], r: Ride) -> list[int]:
    """``template`` (a stock mount's Spell.dbc row) as ``r``'s: its id, creature, icon, texts."""
    row = list(template)
    row[0], row[SPELL_MISC_1] = r.id, r.id
    if r.icon:
        row[SPELL_ICON], row[SPELL_ACTIVE_ICON] = r.icon, 0
    row[SPELL_NAME] = spell.add_string(r.name)
    row[SPELL_SUBTEXT] = 0
    row[SPELL_DESCRIPTION] = spell.add_string(description(r))
    return row


def model_row(cmd, template: list[int] | None, r: Ride) -> list[int]:
    """A CreatureModelData row: the stock template's footprints and blood; retail's size and sounds."""
    row = list(template) if template else [0, 0, 0, 1, f2u(1.0), 1] + [0] * 22
    row[0] = r.id
    row[CMD_NAME] = cmd.add_string(r.model_path)
    if r.sound_kits is not None:
        row[CMD_SOUND] = r.id
    m = r.model_data or {}
    if m.get("ModelScale"):
        row[CMD_SCALE] = f2u(m["ModelScale"])
    for i, k in enumerate(("CollisionWidth", "CollisionHeight", "MountHeight")):
        if m.get(k) is not None:
            row[CMD_COLLISION + i] = f2u(m[k])
    box = m.get("GeoBox") or []
    if len(box) == 6:
        row[CMD_GEOBOX:CMD_GEOBOX + 6] = [f2u(x) for x in box]
    for i, k in enumerate(("WorldEffectScale", "AttachedEffectScale")):
        if m.get(k):
            row[CMD_EFFECT_SCALES + i] = f2u(m[k])
    for i, k in enumerate(("MissileCollisionRadius", "MissileCollisionPush", "MissileCollisionRaise")):
        if m.get(k) is not None:
            row[CMD_MISSILE + i] = f2u(m[k])
    return row


def display_row(cdi, r: Ride) -> list[int]:
    return [r.id, r.id, r.id if r.sound_kits is not None else 0, 0, f2u(r.scale or 1.0),
            r.alpha if 0 < r.alpha <= 255 else 255, *(cdi.add_string(n) for n in r.textures[:3]), 0, 1, 0, 0, 0,
            r.geosets, 0]


def sound_row(template: list[int] | None, r: Ride) -> list[int]:
    """``r``'s CreatureSoundData row: the stock template's (its model's: impact type, fidget delays)
    with every sound retail's own - or none, where retail has none - and retail's footsteps."""
    from ..race.sounds import CSD_KIT_COLUMNS
    row = list(template) if template and len(template) == CSD_FIELDS else [0] * CSD_FIELDS
    row[0] = r.id
    for col in CSD_KIT_COLUMNS:
        row[col] = (r.sound_kits or {}).get(col, 0)
    if r.footstep is not None:
        row[CSD_FOOTSTEP] = r.footstep
    row[CSD_NPC_SOUND] = row[CSD_PET] = 0
    return row


def item_display_row(idi, r: Ride) -> list[int]:
    """The item's ItemDisplayInfo row: the stock mount item's (``r.item_template``: its pick-up and
    drop sounds) showing retail's icon."""
    row = [0] * IDI_FIELDS
    for i, v in enumerate((r.item_template or [])[:IDI_FIELDS]):
        if i not in IDI_STRINGS:
            row[i] = int(v)
    row[0], row[IDI_ICON] = r.item_display, idi.add_string(r.item_icon)
    return row


def with_item_displays(data: bytes, rides: list[Ride], ours: set[int]) -> bytes:
    """An ItemDisplayInfo table (``data``, whichever archive holds it) with the mounts' items' rows,
    in place of every row of ``ours`` (an earlier install's)."""
    from ..dbc import DBCFile
    idi = DBCFile.from_bytes(data)
    if idi.field_count != IDI_FIELDS:
        raise ValueError(f"ItemDisplayInfo.dbc has {idi.field_count} fields - not a 3.3.5 client's")
    drop = set(ours) | {r.item_display for r in rides if r.item_icon}
    idi.records = [row for row in idi.records if row[0] not in drop]
    for r in rides:
        if r.item_icon:
            idi.add_record(item_display_row(idi, r))
    return idi.to_bytes()


def client_tables(base: dict[str, bytes], rides: list[Ride], icons: dict[int, str], sounds: Sounds | None = None,
                  owned: dict[str, set[int]] | None = None) -> dict[str, bytes]:
    """Each table of ``TABLES`` (and ``ITEM_TABLE``) as the client has it (``base``) with the mounts'
    rows - a row with one of their ids (``owned``: every id the registry gave, by table) is theirs
    from an earlier install and goes. ``icons``: SpellIcon id -> path, the new icons; ``sounds``:
    the SoundEntries and FootstepTerrainLookup rows."""
    from ..dbc import DBCFile
    from ..race.sounds import Voice, add_sound_entries
    sounds, owned = sounds or Sounds(), owned or {}
    spell = DBCFile.from_bytes(base["Spell"])
    if spell.field_count != SPELL_FIELDS:
        raise ValueError(f"Spell.dbc has {spell.field_count} fields - not a 3.3.5 client's")
    by_spell = {row[0]: row for row in spell.records}
    templates = {k: by_spell.get(v) for k, v in TEMPLATE_SPELL.items()}
    missing = [f"{k} {TEMPLATE_SPELL[k]}" for k, v in templates.items() if v is None and any(r.kind == k for r in rides)]
    if missing:
        raise ValueError(f"the client's Spell.dbc has no stock mount spell to copy ({', '.join(missing)})")
    ours = {r.id for r in rides}
    spell.records = [row for row in spell.records if row[0] not in ours]
    for r in rides:
        spell.add_record(spell_row(spell, templates[r.kind], r))

    sla = DBCFile.from_bytes(base["SkillLineAbility"])
    stock = {row[2]: row for row in sla.records if row[1] == MOUNT_SKILL}
    sla.records = [row for row in sla.records if row[0] not in ours]
    for r in rides:
        row = list(stock.get(TEMPLATE_SPELL[r.kind]) or [0, MOUNT_SKILL, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0])
        row[0], row[2] = r.id, r.id
        sla.add_record(row)

    icon = DBCFile.from_bytes(base["SpellIcon"])
    icon.records = [row for row in icon.records if row[0] not in icons]
    for i, path in sorted(icons.items()):
        icon.add_record([i, icon.add_string(path)])

    cdi = DBCFile.from_bytes(base["CreatureDisplayInfo"])
    cmd = DBCFile.from_bytes(base["CreatureModelData"])
    if cdi.field_count != CDI_FIELDS or cmd.field_count != CMD_FIELDS:
        raise ValueError("the client's CreatureDisplayInfo/CreatureModelData aren't 3.3.5's layout")
    cdi.records = [row for row in cdi.records if row[0] not in ours]
    cmd.records = [row for row in cmd.records if row[0] not in ours]
    for r in rides:
        cmd.add_record(model_row(cmd, r.template_model, r))
        cdi.add_record(display_row(cdi, r))

    se = DBCFile.from_bytes(base["SoundEntries"])
    csd = DBCFile.from_bytes(base["CreatureSoundData"])
    ftl = DBCFile.from_bytes(base["FootstepTerrainLookup"])
    if csd.field_count != CSD_FIELDS or ftl.field_count != FTL_FIELDS:
        raise ValueError("the client's CreatureSoundData/FootstepTerrainLookup aren't 3.3.5's layout")
    drop = owned.get("SoundEntries", set()) | set(sounds.kits)
    se.records = [row for row in se.records if row[0] not in drop]
    add_sound_entries(se, Voice(kits=sounds.kits), {k: k for k in sounds.kits})
    stock_sounds = {row[0]: row for row in csd.records}
    drop = owned.get("CreatureSoundData", set()) | ours
    csd.records = [row for row in csd.records if row[0] not in drop]
    for r in rides:
        if r.sound_kits is not None:
            csd.add_record(sound_row(stock_sounds.get((r.template_model or [0] * CMD_FIELDS)[CMD_SOUND]), r))
    drop = owned.get("FootstepTerrainLookup", set()) | {row[0] for row in sounds.footsteps}
    ftl.records = [row for row in ftl.records if row[0] not in drop]
    for row in sounds.footsteps:
        ftl.add_record(list(row))
    out = {"Spell": spell.to_bytes(), "SkillLineAbility": sla.to_bytes(), "SpellIcon": icon.to_bytes(),
           "CreatureDisplayInfo": cdi.to_bytes(), "CreatureModelData": cmd.to_bytes(), "SoundEntries": se.to_bytes(),
           "CreatureSoundData": csd.to_bytes(), "FootstepTerrainLookup": ftl.to_bytes()}
    if ITEM_TABLE in base:
        out[ITEM_TABLE] = with_item_displays(base[ITEM_TABLE], rides, owned.get(ITEM_TABLE, set()))
    return out


def model_template(cmd_rows: list[list[int]], name_of, retail_path: str, kind: str) -> list[int] | None:
    """The stock CreatureModelData row a mount's other fields (footprints, sounds, blood) come from:
    the one of the same model (an old mount's), else the kind's (a horse's, a drake's)."""
    stem = os.path.splitext(retail_path.replace("/", "\\").rsplit("\\", 1)[-1])[0].lower()
    fallback = None
    for row in cmd_rows:
        name = name_of(row[CMD_NAME]).replace("/", "\\").lower()
        if os.path.splitext(name.rsplit("\\", 1)[-1])[0] == stem:
            return row
        if fallback is None and name == TEMPLATE_MODEL[kind]:
            fallback = row
    return fallback


# -- the server's SQL -----------------------------------------------------------------------------
def _q(s) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"


def _v(v) -> str:
    if isinstance(v, str):
        return _q(v)
    if isinstance(v, float):
        return repr(round(v, 6))
    return str(int(v))


def _signed(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= 1 << 31 else v


def _row_values(dbc, row: list[int], floats: set[int], strings: set[int]) -> list:
    out = []
    for i, v in enumerate(row):
        if i in strings:
            out.append(dbc.get_string(v))
        elif i in floats:
            out.append(u2f(v))
        else:
            out.append(_signed(v))
    return out


SPELL_STRINGS = set(range(SPELL_NAME, SPELL_NAME + 16)) | set(range(SPELL_SUBTEXT, SPELL_SUBTEXT + 16)) | \
    set(range(SPELL_DESCRIPTION, SPELL_DESCRIPTION + 16)) | set(range(SPELL_AURA_TEXT, SPELL_AURA_TEXT + 16))
# Spell.dbc's float fields - spell_dbc's float columns (speed, points per level and combo point,
# radius bonuses, chain amplitude, damage multipliers)
SPELL_FLOATS = {47, 77, 78, 79, 101, 102, 103, 119, 120, 121, 216, 217, 218, 229, 230, 231}


def mount_sql(tables: dict[str, bytes], rides: list[Ride], owned: dict[str, list], build: str, made: str,
              route: str) -> str:
    """The server's rows for ``rides``, read back from the client tables just made (``tables``) so
    both say the same. Only rows the workbench wrote before (``owned``: per table, the [id, marker]
    pairs - either route's, the server is the same) are deleted first: an id the database already
    uses for something else makes the INSERT stop with "Duplicate entry" - nothing of yours is
    replaced."""
    from ..dbc import DBCFile
    spell, cdi, cmd = (DBCFile.from_bytes(tables[n]) for n in ("Spell", "CreatureDisplayInfo", "CreatureModelData"))
    ours = {r.id for r in rides}
    rows = {n: {row[0]: row for row in d.records if row[0] in ours} for n, d in
            (("Spell", spell), ("CreatureDisplayInfo", cdi), ("CreatureModelData", cmd))}
    lines = [f"-- generated by Retroport Workbench ({route}) {made}: {len(rides)} retail mount(s), retail {build}",
             "-- each mount: a spell (spell_dbc), its creature and model (creature_template, creaturedisplayinfo_dbc,",
             "-- creaturemodeldata_dbc) and the item that teaches it (item_template). Restart the worldserver after."]

    def delete(table: str, cols: tuple, now: list, key: str) -> None:
        pairs = sorted({tuple(p) for p in (owned.get(key) or [])} | {tuple(p) for p in now})
        if pairs:
            lines.append(f"DELETE FROM `{table}` WHERE ({', '.join(f'`{c}`' for c in cols)}) IN (" +
                         ",".join("(" + ",".join(_v(x) for x in p) + ")" for p in pairs) + ");")

    def insert(table: str, cols, values: list[list]) -> None:
        if values:
            head = f"INSERT INTO `{table}` " + (f"({','.join(f'`{c}`' for c in cols)}) " if cols else "") + "VALUES"
            lines.append(head + "\n" + ",\n".join("(" + ",".join(_v(x) for x in v) + ")" for v in values) + ";")

    now = {
        "spell_dbc": [[r.id, r.name] for r in rides],
        "creaturedisplayinfo_dbc": [[r.id, r.id] for r in rides],
        "creaturemodeldata_dbc": [[r.id, r.model_path] for r in rides],
        "creature_template": [[r.id, r.name] for r in rides],
        "creature_template_model": [[r.id, r.id] for r in rides],
        "creature_model_info": [[r.id] for r in rides],
        "item_template": [[r.item, r.item_name or r.name] for r in rides],
    }
    delete("spell_dbc", ("ID", "Name_Lang_enUS"), now["spell_dbc"], "spell_dbc")
    insert("spell_dbc", None, [_row_values(spell, rows["Spell"][r.id], SPELL_FLOATS, SPELL_STRINGS) for r in rides])
    delete("creaturedisplayinfo_dbc", ("ID", "ModelID"), now["creaturedisplayinfo_dbc"], "creaturedisplayinfo_dbc")
    insert("creaturedisplayinfo_dbc", CDI_COLUMNS,
           [_row_values(cdi, rows["CreatureDisplayInfo"][r.id], CDI_FLOATS, {6, 7, 8, 9}) for r in rides])
    delete("creaturemodeldata_dbc", ("ID", "ModelName"), now["creaturemodeldata_dbc"], "creaturemodeldata_dbc")
    insert("creaturemodeldata_dbc", CMD_COLUMNS,
           [_row_values(cmd, rows["CreatureModelData"][r.id], CMD_FLOATS, {CMD_NAME}) for r in rides])
    delete("creature_template_model", ("CreatureID", "CreatureDisplayID"), now["creature_template_model"],
           "creature_template_model")
    delete("creature_template", ("entry", "name"), now["creature_template"], "creature_template")
    insert("creature_template", ("entry", "name", "minlevel", "maxlevel", "faction", "unit_class", "unit_flags"),
           [[r.id, r.name, 1, 1, 35, 1, 0] for r in rides])
    insert("creature_template_model", ("CreatureID", "Idx", "CreatureDisplayID", "DisplayScale", "Probability"),
           [[r.id, 0, r.id, 1.0, 1.0] for r in rides])
    delete("creature_model_info", ("DisplayID",), now["creature_model_info"], "creature_model_info")
    insert("creature_model_info", ("DisplayID", "BoundingRadius", "CombatReach", "Gender", "DisplayID_Other_Gender"),
           [[r.id, 1.0, 1.5, 2, 0] for r in rides])
    delete("item_template", ("entry", "name"), now["item_template"], "item_template")
    insert("item_template", ("entry", "class", "subclass", "SoundOverrideSubclass", "name", "displayid", "Quality",
                             "bonding", "stackable", "ItemLevel", "RequiredLevel", "RequiredSkill", "RequiredSkillRank",
                             "AllowableClass", "AllowableRace", "spellid_1", "spelltrigger_1", "spellcharges_1",
                             "spellcooldown_1", "spellcategorycooldown_1", "spellid_2", "spelltrigger_2",
                             "spellcooldown_2", "spellcategorycooldown_2", "description"),
           [[r.item, 15, 5, -1, r.item_name or r.name, r.item_display, min(max(r.quality, 0), 7), 1, 1,
             RIDING[r.kind][1], RIDING[r.kind][1], 762, RIDING[r.kind][0], -1, -1, LEARNING, 0, -1, -1, -1, r.id, 6,
             -1, -1, "Teaches you how to summon this mount."] for r in rides])
    lines.append("-- a GM learns one without its item:  " + "  ".join(f".learn {r.id}" for r in rides[:6]) +
                 ("  ..." if len(rides) > 6 else ""))
    lines.append("-- or gets the item:  " + "  ".join(f".additem {r.item}" for r in rides[:6]) +
                 ("  ..." if len(rides) > 6 else ""))
    return "\n".join(lines) + "\n"


def owned_now(rides: list[Ride], owned: dict[str, list]) -> dict[str, list]:
    """``owned`` with the pairs ``mount_sql`` writes for ``rides`` added (what a later install may
    delete again)."""
    add = {"spell_dbc": [[r.id, r.name] for r in rides],
           "creaturedisplayinfo_dbc": [[r.id, r.id] for r in rides],
           "creaturemodeldata_dbc": [[r.id, r.model_path] for r in rides],
           "creature_template": [[r.id, r.name] for r in rides],
           "creature_template_model": [[r.id, r.id] for r in rides],
           "creature_model_info": [[r.id] for r in rides],
           "item_template": [[r.item, r.item_name or r.name] for r in rides]}
    out = {k: [list(p) for p in v] for k, v in owned.items()}
    for k, pairs in add.items():
        have = {tuple(p) for p in out.get(k, [])}
        out[k] = sorted([list(p) for p in have | {tuple(p) for p in pairs}], key=lambda p: [str(x) for x in p])
    return out


def basket_mounts(entries: list[dict]) -> list[dict]:
    """The mounts of a basket (entries of kind "mount"), once each."""
    out, seen = [], set()
    for e in entries:
        if e.get("kind") == "mount" and (e.get("source"), e.get("id")) not in seen:
            seen.add((e.get("source"), e.get("id")))
            out.append(e)
    return out

