"""Hard and soft limits of the 3.3.5a (build 12340) client.

"Hard" means the client will refuse to load or will crash; "soft" means the
asset loads but renders wrongly, or only works because live Blizzard data never
went that far. Everything here is used by the validators so that a conversion
either produces a file the 3.3.5a client accepts, or says clearly why it can't.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Build identity
# ---------------------------------------------------------------------------
TARGET_PATCH = "3.3.5a"
TARGET_BUILD = 12340

# ---------------------------------------------------------------------------
# M2
# ---------------------------------------------------------------------------
M2_VERSION = 264  # 0x108 -- the only MD20 version 3.3.5a loads
#: The highest MD20 version whose struct layout this tool has been written
#: against.  Anything above it is read with the newest schemas available,
#: which is a guess worth saying out loud.
M2_VERSION_NEWEST_KNOWN = 274
M2_MAGIC = "MD20"
#: Legion+ wraps that body in an "MD21" chunk, which must be unwrapped; the
#: chunk names live in wotlkconv.m2.model.KNOWN_M2_CHUNKS.

#: Skin profiles (LOD levels) the client looks for: Model00.skin .. Model03.skin
M2_MAX_SKIN_PROFILES = 4

#: Skin index arrays are uint16, so a profile cannot address more vertices.
M2_MAX_VERTICES = 0xFFFF

#: Bone indices in M2Vertex.bone_indices are uint8 *into the submesh window*,
#: but the global bone array is addressed by uint16 lookups.
#: Above this the 3.3.5a renderer runs out of matrix palette slots in practice.
M2_SOFT_MAX_BONES = 256

#: Per-vertex bone influences supported by the fixed skinning path.
M2_MAX_BONE_INFLUENCES = 4

#: Bones referenced by a single draw call (M2SkinSection.boneCount).
M2_MAX_BONES_PER_SUBMESH = 256

#: Texture units per batch. Legion allows 4, 3.3.5a's combiners handle 2.
M2_MAX_TEXTURE_UNITS = 2

#: M2Material.blending_mode values the client understands: 0 Opaque,
#: 1 AlphaKey, 2 Alpha, 3 NoAlphaAdd, 4 Add, 5 Mod, 6 Mod2x.
M2_MAX_BLEND_MODE = 6
#: Legion added BlendAdd (7); it degrades to plain Add.
M2_BLEND_MODE_FALLBACK = {7: 4}

#: M2Material.flags bits understood by 3.3.5a: unlit, unfogged, two-sided,
#: depth-test-off, depth-write-off. 0x40 and above are Cata+ shadow/blend hints.
M2_MATERIAL_FLAG_MASK = 0x001F

#: M2CompBone.flags bits understood by 3.3.5a:
#:  0x1 ignore parent translate, 0x2 ignore parent scale, 0x4 ignore parent
#:  rotation, 0x8 spherical billboard, 0x10/0x20/0x40 cylindrical billboards,
#:  0x200 transformed. 0x400 (kinematic/physics bone) and 0x1000
#:  (helmet_anim_scaled) arrived with Cataclysm and later.
M2_BONE_FLAG_MASK = 0x000003FF

#: M2 header global flags recognised by 3.3.5a.
#:  0x1 tilt X, 0x2 tilt Y, 0x8 use texture combiner combos, 0x20 load phys (Cata+)
M2_GLOBAL_FLAG_MASK = 0x0000000B
M2_GLOBAL_FLAG_USE_COMBINER_COMBOS = 0x08

#: M2Texture.type values 3.3.5a resolves at runtime. Anything higher is Cata+.
M2_MAX_TEXTURE_TYPE = 15

#: M2Particle.flags bits 3.3.5a's own emitters use: 0x1 through 0x80000, and
#: nothing above (checked across 25,440 genuine 3.3.5a emitters).  Everything
#: higher arrived later, chief among them 0x800000 (gravity stored as packed
#: vectors) and 0x10000000 (multi-texture emitters).
M2_PARTICLE_FLAG_MASK = 0x000FFFFF
M2_PARTICLE_FLAG_COMPRESSED_GRAVITY = 0x00800000
M2_PARTICLE_FLAG_MULTI_TEXTURE = 0x10000000
#: Scale of a packed gravity vector's 16-bit magnitude.
M2_PACKED_GRAVITY_SCALE = 0.04238648

#: M2Sequence.flags bits a 3.3.5a file carries (0x10 is set at runtime, and
#: 0x100/0x200/0x800 are Legion's "in the model", "split blend time" and
#: later additions; none appears in 94,186 genuine 3.3.5a sequences).
M2_SEQUENCE_FLAG_MASK = 0x000000EF
#: Emitter shapes: 1 plane and 2 sphere exist in 3.3.5a; 3 spline (Cata) and
#: 4 bone (Legion) do not.
M2_EMITTER_TYPES_SUPPORTED = (1, 2)
M2_MAX_PARTICLE_BLEND_MODE = 6

#: Particle emitter struct sizes, by source era.
M2_PARTICLE_SIZE_WOTLK = 476
M2_PARTICLE_SIZE_CATA = 492

#: Camera struct sizes: 3.3.5a stores a scalar FoV, Legion+ stores a track.
M2_CAMERA_SIZE_WOTLK = 100
M2_CAMERA_SIZE_LEGION = 116
#: Diagonal FoV used when a Legion FoV track has no usable key.
M2_DEFAULT_FOV = 0.9749309

# ---------------------------------------------------------------------------
# SKIN
# ---------------------------------------------------------------------------
SKIN_MAGIC = "SKIN"
SKIN_HEADER_SIZE_WOTLK = 48
SKIN_HEADER_SIZE_LEGION = 56  # adds M2Array<M2ShadowBatch>

# ---------------------------------------------------------------------------
# BLP
# ---------------------------------------------------------------------------
BLP_COMPRESSION_JPEG = 0      # BLP1 only, never in 3.3.5a assets
BLP_COMPRESSION_PALETTE = 1
BLP_COMPRESSION_DXT = 2
BLP_COMPRESSION_ARGB8888 = 3
BLP_COMPRESSION_ARGB8888_DUP = 4  # seen in Cata+, same payload as 3

#: The alpha_type values inside BLP_COMPRESSION_DXT are enumerated once, in
#: wotlkconv.blp.blp.PreferredFormat; 3.3.5a samples DXT1, DXT3 and DXT5 and
#: has no decoder for Legion's BC5 normal maps.

BLP_MAX_MIPS = 16
#: 3.3.5a's texture cache is sized for 1024; larger works on modern GPUs but
#: blows the client's memory budget on the 32-bit binary.
BLP_SOFT_MAX_DIMENSION = 1024

# ---------------------------------------------------------------------------
# WMO
# ---------------------------------------------------------------------------
WMO_VERSION = 17
#: Versions below this are a different format rather than an older one: the
#: alpha WMO wraps its groups in a MOMO container and shares almost nothing
#: with v17 beyond the magic.
WMO_VERSION_OLDEST_READABLE = 17
#: Chunks the 3.3.5a root parser knows. Anything else is skipped by the client
#: at best and mis-parsed at worst, so the converter drops them.
WMO_ROOT_CHUNKS_KNOWN = (
    "MVER", "MOHD", "MOTX", "MOMT", "MOGN", "MOGI", "MOSB", "MOPV",
    "MOPT", "MOPR", "MOVV", "MOVB", "MOLT", "MODS", "MODN", "MODD",
    "MFOG", "MCVP",
)
WMO_GROUP_CHUNKS_KNOWN = (
    "MVER", "MOGP", "MOPY", "MOVI", "MOVT", "MONR", "MOTV", "MOBA",
    "MOLR", "MODR", "MOBN", "MOBR", "MOCV", "MLIQ",
)
#: SMOMaterial.shader values 3.3.5a implements. Cataclysm and later added
#: everything above this (two-layer terrain, lod water, parallax and so on).
WMO_MAX_SHADER = 6
#: SMOMaterial.blendMode shares M2's blend enum: 0..6.
WMO_MAX_BLEND_MODE = 6
#: SMOMaterial.flags bits: unlit, unfogged, unculled, extlight, SIDN, window,
#: clamp S, clamp T, and one more Blizzard never named.
WMO_MATERIAL_FLAG_MASK = 0x01FF
#: MOHD.flags: attenuate-by-portal, unified render path, liquid type from DBC,
#: do-not-fix-vertex-colour-alpha. Legion reused the upper half for numLod.
WMO_HEADER_FLAG_MASK = 0x000F

#: MOGP.flags bits 3.3.5a understands. 0x08000000 and above are Legion+.
WMO_GROUP_FLAG_MASK = 0x07FFFFFF
WMO_GROUP_FLAG_HAS_BSP = 0x00000001
WMO_GROUP_FLAG_HAS_VERTEX_COLORS = 0x00000004
#: MPBV/MPBP/MPBI/MPBG; no genuine 3.3.5a group has them, and none is written.
WMO_GROUP_FLAG_HAS_PORTAL_BATCHES = 0x00000400
WMO_GROUP_FLAG_HAS_LIGHTS = 0x00000200
WMO_GROUP_FLAG_HAS_DOODADS = 0x00000800
WMO_GROUP_FLAG_HAS_WATER = 0x00001000
WMO_GROUP_FLAG_HAS_TWO_MOCV = 0x01000000
WMO_GROUP_FLAG_HAS_TWO_MOTV = 0x02000000

#: UV and vertex-colour layers the old renderer can bind.
WMO_MAX_UV_LAYERS = 2
WMO_MAX_COLOR_LAYERS = 2

MOHD_SIZE = 64
MOMT_SIZE = 64
MOGI_SIZE = 32
MODD_SIZE = 40
MODS_SIZE = 32
MOLT_SIZE = 48
MFOG_SIZE = 48
MOGP_HEADER_SIZE = 68
MOBA_SIZE = 24
#: Post-Wrath MOBA flag: the batch's material is the uint16 at offset 0x0A,
#: inside the bounding box, and the material byte at 0x17 is left at 0.
MOBA_FLAG_WIDE_MATERIAL = 0x02
#: MPY2's "no material" (a collision-only face); MOPY spells it 0xFF.
MPY2_NO_MATERIAL = 0xFFFF
MOPY_NO_MATERIAL = 0xFF

#: MOHD.nTextures is a uint32 but the client indexes MOTX by byte offset.
WMO_MAX_MATERIALS = 0xFFFF
WMO_MAX_GROUPS = 512
WMO_MAX_DOODAD_SETS = 0xFFFF
#: MOBA batch vertex indices are uint16 relative to the group.
WMO_MAX_GROUP_VERTICES = 0xFFFF

# ---------------------------------------------------------------------------
# ADT
# ---------------------------------------------------------------------------
ADT_VERSION = 18
ADT_CHUNKS_PER_SIDE = 16
ADT_MCNK_COUNT = ADT_CHUNKS_PER_SIDE * ADT_CHUNKS_PER_SIDE
#: 3.3.5a reads one monolithic .adt; Cata+ splits it into _obj0/_obj1/
#: _tex0/_tex1, whose suffixes are enumerated in wotlkconv.detect.
#: Terrain texture layers per MCNK.
ADT_MAX_LAYERS = 4
