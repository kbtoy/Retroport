# The command-line tools in this repository

Developer notes on the other code that shares this repository with Retroport Workbench: model
conversion, playable race ports, glue screens and start outfits, run from source with
`python -m retroport.cli`. **They are not part of Retroport Workbench and not in its releases**;
they need local game installs and were tuned on one HD-patched 3.3.5a client.

## What this actually is

**retroport is a conductor, not a converter.** The MD21 → MD20 format work is done by a
conversion engine — by default **[wotlkconv](https://github.com/Bar3b0n3s/Converter)**
(MIT, pure Python, used as a library; retroport carries its own unchanged copy in `wotlkconv/`, so
it never depends on that repository being online), or the MultiConverter exe. retroport runs what
neither does — WotLK render-blocker fixes, texture baking and resizing, diagnostics,
DBC registration — and drives M2Mod + Blender for poly reduction.

Division of labor:

| Job | Who does it |
|-----|-------------|
| **MD21 → MD20, .skel/.anim merge, TXID resolution, `.skin`/`.anim` conversion + 3.3.5 names** | **wotlkconv** (default engine) |
| Fold `.skel` (bones) + `.anim` (animations) into the `.m2`, drop SKID | **retroport** (re-inline, MultiConverter engine) |
| Copy/rename `.skin` files to `<model>NN.skin` next to the `.m2` | **retroport** (stage, MultiConverter engine) |
| Restore the data MultiConverter overwrites with the combiner-combos header | **retroport** (fixup) |
| Clear a combiner table WotLK can't use + reset batch shaders (black-mesh fix) | **retroport** (fixup) |
| Set nViews, clear stale anim flags (a submesh clamp is available, unused for characters) | **retroport** (fixup) |
| Bake in-game paths into type-0 texture slots MultiConverter left empty | **retroport** (texbake) |
| Diagnose triangles / submeshes / textures / bones / skins / LODs / `.anim` files | **retroport** (check) |
| Write CreatureModelData + CreatureDisplayInfo rows, repoint SQL | **retroport** (register) |
| Write ItemDisplayInfo rows (weapons/armor), repoint Item.dbc, item SQL + pack paths | **retroport** (register-item) |
| Convert every 3.3.5 race/gender variant of a helm (+ `-fixhelm` for classic models) | **retroport** (helms) |
| Resize armor textures to their body region, shrink/re-encode object textures (BLP2) | **retroport** (textures) |
| **MD21 → MD20, version → 264, TXID/SFID texture resolution** (alternative engine) | **MultiConverter** (external exe) |
| **`.m2` ↔ `.m2i` + mesh decimation** | **M2Mod** (external exe) **+ Blender** |

Two things retroport does **not** do, despite common assumption: it does not *reduce*
bone count (it only flags it), and it does not fold skins into the `.m2` (only the
skeleton and animations are inlined — skins stay as separate `.skin` files that the
client loads alongside the model, exactly as in modern WoW).

## The pipeline

```
wotlkconv engine:       triage -> [poly-reduce] -> convert (wotlkconv) -> fixup -> texbake -> check
MultiConverter engine:  triage -> [poly-reduce] -> stage skins -> re-inline -> MultiConverter -> fixup -> texbake -> check
```

**Engines.** `PipelineConfig.engine` / GUI Settings → *Conversion engine*:

- **`wotlkconv`** (default) converts the model *and* its companions in one step: merges
  the `.skel` (parent chains too) and its `.anim` data, flattens chunked external `.anim`
  files, rewrites modern `.skin` headers (dropping shadow batches), drops unused LOD
  geometry, resolves TXID textures, and writes everything under the names 3.3.5 globs
  for. Its full listfile load costs ~19 s / 400 MB, so retroport hands it a *scoped*
  listfile: the FileDataIDs the model and its skeleton chain reference, streamed out of
  your listfile in one pass. Its per-file loss notes (`[lossy] m2.texture.type ...`) go
  into the log. Unresolved textures come out as `unknown\<fdid>.blp`; texbake and check
  treat those as unresolved, so `data/overrides.csv` can still fix them.
- **`multiconverter`** — the exe route below (stage + re-inline + MultiConverter). Still
  needed for one thing: MultiConverter's `-fixhelm` refit of helms for *classic* models.

1. **triage** — classify the model (M2 vs M3, version, uses `.skel`).
2. **poly-reduce** *(optional; needs M2Mod + Blender)* — M2Mod exports `.m2`->`.m2i`,
   Blender decimates the `.m2i`, M2Mod compiles it back. This is the standard backport
   route (Blender writes `.m2i`, not a WotLK `.m2` binary, so M2Mod does the compile).
   Runs *before* conversion, on the modern model. M2Mod rejects a reduction that's still
   over the WotLK vertex/index caps, so it fails loudly rather than shipping a broken model.
3. **stage** *(MultiConverter engine)* — copy the model's `.skin` files into the output
   folder as `<model>NN.skin`.
4. **re-inline** *(MultiConverter engine)* — fold `.skel` + `.anim` into a self-contained
   `.m2`, drop SKID (skipped automatically for models with no `.skel`).
5. **convert** — wotlkconv, or MultiConverter. Either way retroport verifies the result
   really became MD20 (`post-convert: chunked=False version=264`).
6. **fixup** — combiner header repair, combiner-flag/shader fix, submesh clamp, nViews,
   stale-flag cleanup.
   - *Combiner header repair:* when MultiConverter adds texture-combiner combos to a model
     that had none, it sets global flag 0x08 and writes the combos field at 0x130 without
     moving the data already there — the first array after the header: on a real 2H axe and
     on hozumonkey the global-loop timestamps, and on a model without global loops the
     sequence table, so the first animation (Stand) loses its id and duration. Verified by
     running MultiConverter on both: flag 0x08 newly set, combos `[1, 4, 1, 1]` / `[1, 4]`
     written over the loops, and the repair restores them byte for byte. retroport keeps the model as MultiConverter received
     it and restores that data from it. `retroport repair` does the same for models converted
     before this fix.
   - *Combiner flag:* a valid table is kept (Blizzard's own 3.3.5 models use one in about one
     model in eight, most often `[1, 4]`: a texture plus an env-mapped reflection). Only a
     table WotLK can't use — empty, out of bounds, values above 7, or batch shaders indexing
     past it — is cleared, with batch shaders reset to 0.
7. **texbake** — the modern model names textures by FileDataID (TXID chunk); MultiConverter
   resolves the ones its listfile knows. For any type-0 slot still empty, retroport reads
   the TXID captured *before* conversion, looks the id up in your listfile (+
   `data/overrides.csv`), and bakes the in-game path into the MD20. Explicit per-slot
   paths (`PipelineConfig.texture_paths` / `retroport bake --slot`) win. Paths that look
   like a location on your disk are refused.
8. **check** — WotLK render-blocker report, including (for converted MD20 models) the
   multi-LOD gate and the external `.anim` check.

### Safety rules (adapted from Conjure)

- The input model's folder is never written to: the pipeline refuses an output folder
  that is the model's own folder, and `register` refuses one equal to the DBC folder.
- Every library edit (fixup, texbake, DBC writes) goes to a temp file, is re-read and
  checked for structural problems the input didn't already have, and only then replaces
  the target. A rejected edit leaves the file untouched and is logged as `REJECTED ...`.
- The converted model + skins are copied to `<out>/_backup/` before fixup/texbake edit them.

## External tools you provide (in GUI Settings)

- **MultiConverter** — the *console* build (e.g. `MultiConverter_Console.exe`); the GUI
  build ignores command-line arguments.
- **M2Mod** — the CLI build (`--m2-to-m2i`, `--m2i-to-m2`, `--txid-remove`). Needs a
  `--mappings-dir` (a folder with the converted listfile) and, for models that share a
  skeleton (a `.skel` with a parent), a `--working-dir` pointed at your extraction root
  so it can resolve the parent `.skel` by its in-game path.
- **Blender + a `.m2i` addon** — WoWTools (the M2Mod Blender plugin, Blender 2.79). The
  decimate script drives its `import.m2i` / `export.m2i` operators.
- **Extraction** is done by **wow.export** (writes the `.manifest.json` retroport reads).

## Install & run

```bash
pip install -e .            # library + `retroport` CLI (pydantic, typer, rich, Pillow) + wotlkconv
pip install -e ".[gui]"     # + PyQt6 desktop app
pip install -e ".[dev]"     # + pytest

retroport-gui               # the desktop app (Convert / Register / Settings tabs)
```

CLI:

```bash
retroport scan  I:\extract --report          # inventory + per-file blockers; --skel-only lists .skel models
retroport inspect  I:\extract\...\foo.m2      # one file, full detail
retroport deps  I:\extract\...\foo.m2         # a model's .skel/.anim deps and whether they're present
retroport reinline  ...\foo.m2 --out I:\conv --json
retroport check  I:\conv\foo.m2               # WotLK render-blocker diagnostics on a converted model
retroport bake  I:\conv\foo.m2 --slot 0=Creature\Foo\foo_skin.blp       # manual texture paths
retroport bake  I:\conv\foo.m2 --source-m2 I:\extract\foo.m2 --listfile listfile.csv   # auto from TXID
retroport repair  I:\conv\foo.m2 --source-m2 I:\extract\foo.m2   # restore data MultiConverter overwrote at 0x130
retroport register --dbc-dir I:\dbc --out I:\patch\DBFilesClient --path Creature\Foo\foo.m2 --m2 I:\conv\foo.m2 --entries 1234
retroport helms I:\extract\item\objectcomponents\head\helm_foo_hum.m2 --out I:\conv\helms --client classic --multiconverter I:\tools\MultiConverter_Console.exe
retroport textures I:\extract\item\texturecomponents --out I:\patch --target classic --max-object 512
retroport register-item --dbc-dir I:\dbc --out I:\patch\DBFilesClient --like-display 782 --from-model I:\extract\axe_foo.m2 --icon INV_Axe_04 --entries 90001 --item-like 1391
```

### Items (`register-item`)

Adds an `ItemDisplayInfo` row for a converted weapon/armor model. Cloning an existing
display of the same kind (`--like-display`, e.g. a Blizzard 2H axe) inherits its sound
group and flags; every value you give overrides it. Names follow Blizzard's rows: model =
bare filename with `.mdx`, textures/icon = bare names (the client picks the folder from the
item type). `--from-model` fills the model name and the texture for the model's type-2
(item skin) slot from the wow.export manifest. Armor uses `--component TorsoUpper=Name`
etc. for the eight body-texture fields.

Why `Item.dbc` is touched too: AzerothCore overwrites `item_template.displayid` with
`Item.dbc`'s DisplayInfoID for any item listed there (`DBC.EnforceItemAttributes`, on by
default), and `creature_equip_template` drops items missing from `Item.dbc`. So `--entries`
repoints existing Item.dbc rows, and new entries get a row copied from `--item-like`.
The result lists the in-MPQ paths to pack (model, `00.skin`, texture, icon).

### Helms (`helms`, GUI: Convert > Helm set)

A 3.3.5 helm is one model per race/gender (`<Base>_HuM.m2`, `<Base>_BeF.m2`...);
ItemDisplayInfo names only `<Base>.mdx`. Modern helms use the same suffixes for the
classic races, plus separately-named files for races 3.3.5 lacks (skipped). Point it at
any one variant: it converts all 20 playable-race variants it finds (plus NPC goblin),
reports the missing ones (those characters show no helm), and prints the model name for
`register-item`. Export every race variant from wow.export first.

`--client classic` adds MultiConverter's `-fixhelm` (refits modern helms to the classic
heads); `--client hd` leaves it off for HD character models such as the 3.3.5 HD patch.

### Textures (`textures`, GUI: Textures tab)

- **Armor component textures** (`..._tu_m.blp`, or anything in a `<Section>Texture` folder)
  are resized to the body region they're composited into and written palettized with
  8-bit alpha and full mips, the way Blizzard and the HD patch ship them. Classic
  3.3.5 models use a 256x256 skin (ArmUpper/ArmLower/TorsoUpper/LegUpper/LegLower 128x64,
  Hand/TorsoLower/Foot 128x32); `--target hd` doubles them for 512x512 HD skins. Output goes
  to `Item\TextureComponents\<Section>Texture\` with the name to use in ItemDisplayInfo.
- **Object textures** (weapons, helms...) are copied unchanged when already
  client-compatible; `--max-object N` shrinks larger ones (re-encoded DXT1/DXT5), and
  non-power-of-two sizes are fixed.

The BLP writer is checked against real Blizzard headers, and its output against
BLPConverter. Note that Pillow mis-decodes palettized BLP alpha (it reads the palette's
4th byte; Blizzard stores alpha as a separate plane), so retroport decodes those itself.

### Playable races (`character`)

```bash
retroport character --bfa "I:\WoW Modding\Clients\WorldofWarcraft BFA" --race KulTiran --sex male \
    --out I:\port\KulTiranMale --race-id 33 --listfile listfile.csv --dbd I:\WoW Modding\WoWDBDefs\definitions \
    --dbc-dir I:\WotLK3.3.5_New_HD_Patch_2025-ft-2.0.6\DBFilesClient
```

Ports one race/sex from a local **BfA (8.x) install** - the last expansion whose
characters use 3.3.5's customization system (CharSections textures composited into one
body texture, CharHairGeosets, CharacterFacialHairStyles) - or, with `--retail` in place of
`--bfa`, from a **retail install** (9.0+; see *Retail races* below). Shadowlands+ models add a
separate face mesh and an eye texture type (19) that 3.3.5 can't fill - the "green faces".
Tables are read with WoWDBDefs definitions; files straight from the install (wotlkconv's
CASC reader).

1. **Model** - converted by wotlkconv from the install, fixed up (combiner table check, stale
   anim flags) and written as `Character\<Race>\<Sex>\<Race><Sex>.m2`. Every submesh is kept: the
   client's own HD models draw up to 96 (patch-E's GoblinFemale), and an old clamp to 64 cut a
   Pandaren's 86 down - torso, legs, eyes and belts gone.
2. **Layout remap** - BfA layout 2 (1024x512: every allied race, Goblin, Worgen, Pandaren)
   keeps the body sections at layout 1's pixel positions and puts a 512x512 face across the
   right half; 3.3.5 (and BfA layout 1) composites the face bottom-left. Exact section
   rectangles come from `CharComponentTextureSections`. Only vertices drawn with the body
   texture (type 1) move; a vertex shared with another texture, or a triangle spanning two
   regions that move differently, is reported, never guessed at. Layout-1 races skip this.
   Skin BfA paints outside every section (layout 2's bottom-left corner: a Pandaren's toes,
   claws, paw pads and tail; `character/extras.py`) has no room in 3.3.5's layout - left alone
   its UVs landed in the face, eyes on the toes. Those triangles move to submeshes of their own
   (same geoset, their own vertex window) drawn with the skin row's *extra* texture (type 8,
   the one per-skin-colour texture 3.3.5 draws directly), which becomes that corner of each
   skin colour's texture. A race whose hair drew type 8 (a Pandaren's: each colour's hair
   texture) gets those slots as hair (type 6) - the same textures, picked by Hair Color.
3. **Textures** - every CharSections texture for the race/sex, re-laid with the *same* map
   as the UVs (so features stay aligned): the skin composite re-assembled, the face and
   facial-hair/scalp overlays squeezed into the FaceUpper+FaceLower block and split.
   All written palettized like Blizzard's (facial hair/scalp with 8-bit alpha - never DXT,
   which those overlay slots don't accept), on a maximum-coverage palette: median cut spent the
   256 colours on the big areas and turned small saturated ones (a Pandaren's gold eyes) brown.
   Every texture goes in `Character\<Race>\<Sex>\`
   with a `<Race><Sex>` prefix: BfA's male and female hair/scalp textures differ, so
   Blizzard-style shared race-folder names (`Hair01_00.blp`) would collide between runs.
4. **DBC rows** - CharSections, CharHairGeosets and CharacterFacialHairStyles rows for
   `--race-id`, appended to your client's DBCs (refused if that race/sex already has rows).
   Pass one run's `DBFilesClient` as the next run's `--dbc-dir` to collect both sexes.

`--target classic` writes the 256x256 layout instead of the HD 512x512 one. To make the
race playable, use `race` (below), which runs this for both sexes.

Verified on BfA Kul Tiran male and female: the head now samples 3.3.5's face region, a
client-style composite (skin + FaceLower + FaceUpper) with the model's UV wireframe on top
lines eyes, mouth and ears up exactly, 0 skin vertices shared or outside, 0 straddling
triangles. Still needed: poly reduction (25,226 / 33,741 triangles vs the 21,845 ceiling)
and an in-client test.

#### Retail races (`--retail`)

```bash
retroport race MagharOrc --name "Mag'har Orc" --retail "I:\World of Warcraft" --alliance-id 0 --horde-id 26 \
    --horde-template 2 --look-template 2 --client "F:\Wrath of the Lich King 3.3.5a (wod models)" \
    --server-dbc D:\AC\Build\Data\dbc --out I:\port\MagharOrcRace --listfile listfile.csv --dbd WoWDBDefs\definitions
```

Shadowlands dropped CharSections, CharHairGeosets and CharacterFacialHairStyles for one
customization system: a race/sex is a **ChrModel** (display, texture layout, skeleton), its
options' choices set geosets, textures (a material on a texture target of the layout,
ChrModelTextureLayer) or a conditional body model, and an element can apply only alongside
another choice (a Mag'har face texture exists per skin colour). `character/retail.py` projects a
ChrModel onto 3.3.5's five axes and hands the converter the BfA-shaped rows it already knows, so
the layout remap, textures and DBC writing are the BfA path's:

- **Skin colour** - the option setting the layout's base body layer; its rows also carry the
  underwear (LegUpper -> NakedPelvisSkin, TorsoUpper -> NakedTorsoSkin). **Face** - the option on
  the lowest face-section layer, one row per face and skin colour. **Hair style / colour** - the
  group-0 geosets and the TextureType 6 texture.
- **Features** combine up to two geoset options, first major (`retail.FEATURES`): a Mag'har male's
  Beard x Sideburns (30 rows), a female's Earrings x Nose Ring (44). An option outside the facial
  groups 1/2/3/16 is renumbered into a free one (her earrings 35xx -> 3xx, where 3.3.5's own Orc
  female wears hers); a choice needing ears 3.3.5 never shows (703, stretched) is left out.
- **Everything else is retail's default**: a group 3.3.5 never switches (20+) keeps the default
  choice's piece (Natural tusks 4001, no necklace) or, with no option, xx01 - except the face
  group 32, which draws 3201 (shared by every face shape) and 3202, the first face shape: an
  xx01-only rule hid the Mag'har's whole face (1,968 triangles). The eye colour is the default
  choice's texture, baked into the eyeballs' type-19 slots as a fixed texture; retail's
  death-knight glow 1701 becomes 3.3.5's 1703 and the unlockable eyes (1702-1705) go. Hair and
  facial pieces no row selects (a plain Orc's styles on a Mag'har body) are hidden, which also
  moves them out of the switchable range below index 65,535.
- **Choices** count when a new character can take them: no requirement, or a class requirement
  admitting a non-death-knight class. Transmog-only, unlockable (achievement, quest, appearance)
  and DK-only ones are skipped. They are taken in retail's UI order (`UiOrderIndex`).
- **Body** - the ChrModel's display, or a body-shaping choice's conditional model
  (`retail.BODY_CHOICES`: the Mag'har male stands Upright, `orcmaleupright.m2`).
- **Parent skeletons** - a `.skel` plays every sequence it doesn't define from its `SKPD`
  parent: `orcmaleupright.skel` defines 118 and takes the other 256 from `orcmale_hd.skel`.
  wotlkconv's merge fills only empty sections, so the upright male came out with 118 - no
  HandsClosed (15), which the client plays on key bones 8-17 to close the hands on a weapon
  (`CCharacterComponent::ComponentCloseFingers`, 0x004E7700), and most emotes. `convert/skeleton.py`
  wraps that merge (retroport's copy of wotlkconv stays as its repository has it): the parent's
  missing sequences are appended with its keyframes on the child's bones (matched by name hash;
  identical rigs here), each with its own `.anim`, aliases and variation chains re-pointed, bones
  that gain keys given the animated flags (`0x280`), and the sequence lookup rebuilt on the
  client's probe chain (`id % n`, then `+ step^2`; `CM2Model::HasSequence`, 0x00825E00).

The rest of `race` reads retail as it reads BfA, with retail's renames: race masks are
`1 << ChrRaces.PlayableRaceBit` in `RaceMasks[2]` (12.1; a Mag'har's bit is 13, not 35), a race's
voice displays come through ChrRaceXChrModel, barber names are the choices' names (no
BarberShopStyle since 9.0). There is no CharStartOutfit after 10.2, so a retail race wears its
template's start outfits. A retail race wears its ChrModel's helmet fallback in retail - the
Mag'har the Orc's - so the look template's (Orc's) helmets are fitted (scale 1.00).

Verified on Mag'har male (upright) and female: the composite with the UV wireframe lines eyes,
mouth, nostrils, tusks and ears up; 0 vertices outside or shared, 0 straddling. 57k/56k
triangles (retail's full-detail bodies; one piece per group draws at a time); item geosets past
index 65,535 need `wxl-wide-skin-geosets`, as Kul Tiran's do. Racials: retail's whole line, in
3.3.5 terms - Savage Blood (poison, curse and disease durations) and Open Skies (mounted and
flight speed) with their own auras, Sympathetic Vigor's pet health as a pet spell AzerothCore's
`spell_pet_auras` casts on every permanent pet, Ancestral Call one of its four clan buffs at
random (crit 5%, haste 5% - ratings the module scales by level, as retail does - mastery 5% and
versatility 4% damage and healing done, versatility also 2% less damage taken).

### Making it playable (`race`)

```bash
retroport race KulTiran --name "Kul Tiran" --bfa "I:\WoW Modding\Clients\WorldofWarcraft BFA" \
    --client "F:\Wrath of the Lich King 3.3.5a (wod models)" --server-dbc D:\AC\Build\Data\dbc \
    --out I:\port\KulTiranRace --listfile listfile.csv --dbd I:\WoW Modding\WoWDBDefs\definitions
retroport race Pandaren --alliance-id 24 --horde-id 25 ...       # same options, the next free ids
```

Converts both sexes (as `character`) and adds everything a selectable race needs, as an
Alliance race (`--alliance-id`, default 22) and a Horde twin (`--horde-id`, default 23; `0`
leaves a side out) that share the models and textures - 3.3.5 fixes a race's faction in
ChrRaces, so "either faction" means two race ids. Race ids must be 1-32: client and
AzerothCore race masks are 32-bit (a race 53 would silently share race 21's bit).

The client is only read. Every DBC is built on the copy the client actually loads, found
in the order the client reads archives (`patch*.MPQ` folders first, then lettered/numbered
patches, then lettered/numbered locale patches, then the stock chain); `INSTALL.txt` lists
each source.

- **ChrRaces** - copies the faction template (`--alliance-template 1` Human,
  `--horde-template 2` Orc: faction, language, intro); name, `ClientFileString` = the BfA
  folder name; customization labels from `--look-template`; helmets (`ClientPrefix`) the
  race's own BfA prefix (`Kt`) when it has its own helmets (below), else the look template's.
- **CreatureDisplayInfo / CreatureModelData** - base displays cloned from the look
  template's (sound, collision), pointing at the new models.
- **CharBaseInfo** - every class any race has (all ten with ARAC); **CharStartOutfit** -
  the template's outfits, each item shown with its own display from the client's Item.dbc
  (ARAC's Human and Undead hunters show their shirt as robe pants).
- **SkillRaceClassInfo, SkillLineAbility, Faction** - wherever a race mask includes the
  template, the new race is added (languages, racials, weapon skills, reputations).
- **HelmetGeosetVisData** (client) - a helmet hides the new race's hair, facial hair, ears and
  eye glow as BfA's HelmetGeosetData has it for the race (the ids are 3.3.5's own; for the classic
  races BfA's rows and 3.3.5's masks agree on 97% of them), or, for a race wearing the look
  template's helmets, wherever it hides the look template's. These masks are `1 << race`, not the
  race masks' `1 << (race - 1)` (the client tests them at 0x4EF1D6); without its bit a Kul Tiran
  female's hair came through every helmet.
- **Voice** - the race's own sounds from BfA (`race/sounds.py`): each BfA sound kit becomes a
  `SoundEntries` row with its `.ogg` files, as they are (the 3.3.5 client's FMOD plays Ogg
  Vorbis; BfA's volumes and distances are on 3.3.5's scale - Human's are identical in both).
  **EmotesTextSound** gets the race's emote sounds (emotes 3.3.5 lacks, like /forthealliance,
  are skipped), **VocalUISounds** its spoken errors ("My inventory is full"; the enums match),
  and a new **CreatureSoundData** row per sex its attack, wound and death sounds, set on the
  new models (a 3.3.5 player's come from `CreatureModelData.SoundID`). Without BfA data the
  look template's voice is cloned instead. Race ids 22+ also need the client extension
  [`native/wxl-race-emote-sounds`](../native/wxl-race-emote-sounds): the client plays emote
  sounds for races 0-21 only.
- **NameGen** - random names: BfA's own for the race (its own rows, else its neutral race's - a
  Pandaren's 1000 a sex), else the look template's.
- **BarberShopStyle** - the race's hair-style and facial-hair rows from BfA's own table (real
  names, e.g. "Swabbed", "Clydesdale"), limited to the converted variations; the same ids on
  client and server (the server validates a barber request by row id, race and sex).
- **CharSections, CharHairGeosets, CharacterFacialHairStyles** - the converted rows, once per id.
- **Character-create UI** - `MAX_RACES` and race buttons; buttons laid out by faction at
  runtime (rows tighten for a 6th race per side); the race icons from BfA's atlas spliced
  into `UI-CharacterCreate-Races.blp` (existing icons stay byte-identical); BfA's race
  description; the template's racial text per faction; on the BfA-style screen of a glue package,
  the race's head for its customize zoom. Patches sit in tagged `-- [retroport]` blocks.
- **Select scene** - BfA's own for the race (ChrRaces.SelectScreenFileDataID, `UI_<Race>`: a Kul
  Tiran's is the docks of Boralus), converted with its textures into the race's
  `Interface\Glues\Models\UI_<Race>\` (a race folder for `install`, like `Character\<Race>\`) and
  drawn as WarcraftXL draws BfA's models (`helmets.redraw_scene`: Boralus' fires' particle
  emitters fixed as the helmets' are).
  Character select stands the race's characters in it, and 3.3.5's own create screen its new ones.
  Without one the race borrows the look template's scene; either way it plays the look template's
  music (character select plays it by the race's own name) until its own is ported.
- **Racials** (`race/racials.py`, `spells.py`, `visuals.py`; `--template-racials` keeps the
  template's) - BfA's own "Racial - <Race>" skill line (a Kul Tiran's 2723: Haymaker, Brush It Off,
  Child of the Sea, Jack of All Trades, Rime of the Ancient Mariner) in place of the faction
  template's (Human's or Orc's racial line is no longer copied onto the race). Each ability is BfA's
  spell as a 3.3.5 Spell.dbc row under BfA's own id, client and server: effects and auras whose ids
  mean the same in 3.3.5 kept, Versatility as damage and healing done, an aura or a passive's dummy
  the server module does (a Pandaren's Bouncy, Epicurean) as a dummy aura with BfA's amount, a
  skill 3.3.5 lacks (Gourmand's BfA cooking) and others dropped and reported; a crowd control BfA
  breaks with a proc charge (Quaking Palm) breaks on damage as 3.3.5's own (Gouge) do;
  more than three effects split into hidden companion spells; cast time, range, cooldown, levels,
  BfA's icon (re-encoded with mips) and tooltip (`$s1` following its effect, `$<damage>` as
  `${$AP*0.75}`). A skill line of BfA's id teaches them to the race's ids; AzerothCore teaches it
  to existing characters at login. Its visuals are BfA's: each SpellVisualEvent's kit as the 3.3.5
  kit of that moment (precast, cast, impact, aura), its models converted into `Spells\` (an
  attachment offset moved into the model), the client's own where it has the file (the stun
  swirl), its sounds, and its animation (BfA's SpellVisualAnim: Quaking Palm's palm strike,
  SpecialUnarmed, and the target's Stun) or the ones the model has for it (Haymaker's wind-up and
  punch, BfA 1446 and 1444). 3.3.5 plays no animation id past 505, whatever AnimationData holds (the
  unit stands), so those take 3.3.5's spare spell animations, CustomSpell01-10 (213-222), that
  the race's body models leave free - a Kul Tiran's Haymaker 213, its wind-up 214 - and the
  body sequences move there (`anims.renumber_sequences`; the BfA id stays in the sequence's
  padding, so rebuilds start from BfA's). Tooltips name what 3.3.5 does:
  Versatility N% reads as damage and healing done N%, damage taken N/2% less. Ratings
  (`MOD_RATING`, 189) keep the bits 3.3.5 shares (crit, haste, hit...); mastery and versatility
  rating become damage and healing done. A rating retail scales by level is held as the percent
  it is worth at retail's top level (`gametables/SpellScaling` x the effect's coefficient /
  `gametables/CombatRatings`: a Mag'har's clan buffs 4.9-5.1%, 4.2% versatility), and the module
  makes a crit or haste one the rating giving that percent at the player's level. An aura retail
  puts on the pet (Sympathetic Vigor's pet health) is a dummy aura on the caster and a pet spell
  bound by `spell_pet_auras`. Everything the port
  adds sits in the race's own id block (200000 + race id x 1000) per table, so rebuilds keep their
  ids. What BfA scripts on the server (Brush It Off's heal, Versatility's damage taken; a
  Pandaren's half falling damage, doubled rested experience, stronger Well Fed buffs; a Mag'har's
  Ancestral Call picking its buff, and the buff's rating by level) is the
  AzerothCore module [`native/mod-retroport-racials`](../native/mod-retroport-racials), bound by the race's SQL;
  `server\<Race>_racials_characters.sql` (optional, characters database) takes the template's
  racials from characters made before.
- **Start outfits** (`race/items.py`; `--template-outfits` keeps the template's) - the armour BfA's
  character creation dresses the race in, class by class (a Kul Tiran warrior: Warsinger's plate),
  in place of the template's 3.3.5 armour, whose 128x64 textures a BfA body's 512x512 skin draws
  at twice their size. A race BfA dresses alike in every class gets the sets `items.KITS` names: a
  Pandaren the Wandering Isle's quest rewards, a set of its own per class (red and gold plate;
  white, blue and green cloth; white, teal and red leather; a rogue BfA's Trainee's). Each piece
  drawn on the body becomes an item and display of the race's own (its id block: 222000 on for a
  Kul Tiran; a piece keeps the id an earlier build gave it) with BfA's textures for the race and
  each sex (256x128 a section, the HD layout's own, palettized) under the race's name, BfA's
  first three geoset groups, name and icon; a class BfA has none for borrows an outfit of its
  armour, a death knight keeps 3.3.5's, weapons stay the template's unless `items.KITS` names
  BfA's own a level 1 character of the class can wield (a Pandaren's Trainee's sword, crossbow and
  axe, daggers, mace and book, mace and shield, staff - models converted as the helmets are, with
  3.3.5's start weapon damage and speed; a hunter's shot becomes arrows). A held piece takes what
  3.3.5's own of its kind mostly have: sheath, equip sounds and the display's spell visual - a
  ranged weapon's shot animation lives there (a crossbow's: LoadRifle, then AttackRifle). The
  create screen draws an outfit entry by the slot type the entry gives, so a second one-hander
  and a held book are entered as off-hand weapons (the server reads only the item ids). They are start gear as
  3.3.5's is - white, item level 1, the armour every wearer has at level 1 - on Item.dbc and
  ItemDisplayInfo.dbc (client and server) and in `item_template`. A belt's model (a Pandaren
  cord's knot and jade disc, which 3.3.5 never draws for a belt) is baked into the bodies as a
  belt geoset of its own per texture, 1811 on (`race/buckles.py`), the belt's display naming it;
  a rebuild unbakes the bodies first.
- **Server** - the same DBC edits on the server's own DBCs, and `<Race>_race.sql`
  (+ `_undo.sql`): `playercreateinfo` (+ action, item), `player_race_stats`, and the new
  race's bit wherever the template's is set in skills, spells, quests, items, `spell_area`,
  `mail_level_reward` and race conditions; `creature_model_info` for the new displays; with its
  own racials, the racial skill in `playercreateinfo_skills`, Haymaker's attack power in
  `spell_bonus_data`, and the module's scripts (`spell_script_names`, `spell_proc`); with its own
  outfits, their `item_template` rows.

Rebuild after changes with `--reuse` (skips the character conversion) and, once installed,
`--replace`, which first removes the previous build of those race ids from the base DBCs.
A rebuild over an installed package reproduces it exactly (rows, UI files, atlas) - also for a
race with others installed after it (Kul Tiran under Pandaren): its rows are rebuilt where they
were, under the later races' rows, with the ids they had, so those races' packages stay current.
In a table nothing points at by id (NameGen, CharSections, ...) a rebuild that adds rows gives the
extra ones ids above every row; one that would need ids a later race has elsewhere (sounds,
displays) is refused - `--on-top` then puts the race after every other (new ids), and the races
built after it are rebuilt on top of it.

**Installing (`install`)** - the build records a SHA-256 of every file it was built on.

```bash
retroport install I:\port\KulTiranRace --client "F:\Wrath of the Lich King 3.3.5a (wod models)" \
    --patch patch-H.MPQ --server-dbc D:\AC\Build\Data\dbc --clean          # plan only
retroport install ... --apply                                               # do it
retroport uninstall I:\port\KulTiranRace\installs\<time>.json               # undo
```

A modified DBC/UI file is installed only while the copy the client (or server) loads is still
the one the package was built on; if you changed it since, the plan marks it `stale` and nothing
is copied - rebuild with `--reuse --replace` to fold your changes in. Model and texture files
replace only copies in the race's own folder or the race's own helmets
(`Item\ObjectComponents\Head\*_KtM.m2`, `_KtF`, their skins); a different file anywhere else is a
`conflict`. Replaced files (and, with `--clean`, leftovers: files in the race folder or among its
helmets that the package doesn't contain, and files an earlier install of the package added that
it no longer holds and that nothing changed since) go to `<package>\backups\<time>\` first;
`uninstall` restores them and refuses if you edited an installed file afterwards. The package
touches nothing else of the client's: its race's files, its helmets, the sounds, the DBCs and
the create-screen UI.

The worldserver reads its DBCs and the race SQL only at startup: restart it after installing a
package that changes `server\dbc` (the plan lists them) or after applying the SQL. Client-only
changes (models, helmets, textures, client DBCs, UI) need only a client restart.

**Geosets 3.3.5 doesn't switch** - 3.3.5 hides geosets 0-2000 and shows one value per group
0-18; ids above 2000 are never hidden, so every variant of BfA's groups 20+ draws at once. Per
such group the converter keeps the piece that fills a hole in the default body (its open
edges meet the body's: Kul Tiran 2001 feet, 2201 torso) and hides the others. The belt group
(18) is the client's, as in BfA: a belt whose display has `GeosetGroup[0]` 1 shows the Kul
Tiran band (1802), 2 the sash (1803), 0 (most belts) only its texture.

**Skins past 65,535 indices** - a Kul Tiran skin has 75k-101k indices; the high 16 bits of each
submesh's start live in its `level` field (WarcraftXL draws that), but the client matches geosets
on `(level << 16) | id`, so a switchable geoset starting past index 65,535 can never be hidden
(every cape at once, death-knight eye glow on every class, both belt meshes). The converter keeps
the body first and the switchable geosets right after it; the rest is the WarcraftXL extension
[`native/wxl-wide-skin-geosets`](../native/wxl-wide-skin-geosets), which repeats each show/hide for the
shifted ids. Both Kul Tirans need it.

The submesh array is put in the same order as the index buffer. When the client draws a model
without merging its batches, it rebuilds the index buffer submesh by submesh in array order and
writes each start back as 16 bits, keeping the file's `level`; WarcraftXL then draws from
`(level << 16) | start`, which is right only when the two orders agree. With them apart, a Kul
Tiran's unmerged draws took ears, eyes, belts and body pieces from the wrong place or past the
end of the buffer. That is also why the face vanished in the sixth test with the body past the
line: the cause was the mismatch, not the body's position.

**Animations** - 3.3.5 blends into and out of a sequence only when it has flag 0x80; BfA blends
everything and its flags came over without it, so /cry, /chicken (and /taunt), /shy and /dance
snapped back to standing. BfA also repeats some emotes as short cycles, where 3.3.5 plays a one-shot
sequence `replay` times (the male's /cry: a 0.67 s sob, played once). `race` copies the look
template's blend bits per animation and repeats one-shot emotes shorter than 60% of the template's
(`race/anims.py`); combat and movement animations are never repeated.

**Helmets** - a race BfA gave helmets of its own wears those (`race/helmets.py`). A 3.3.5 helmet
is one model per race and sex, `Item\ObjectComponents\Head\<Base>_<ClientPrefix><M|F>.m2`, and
BfA made Kul Tirans their own version of nearly every helmet, each refitted by hand to their
heads: deeper and wider than a Human's, the cheek guards longer, the back down to the shoulders,
hung from the head bone's pivot (the neck joint) tipped 2.8 degrees down. No one transform of a
Human helmet matches them - the best per-axis fits of two helmets differ by a quarter in height -
and Human helmets fitted to the male's cranium still rode high, with a gap at the back of his
neck, next to BfA's own in wow.export (twelfth client test).

- **Which:** every helmet the client has for the look template (`<Base>_HuM.m2`, read from its
  ItemDisplayInfo model names) is looked up in BfA through the listfile name of any of its race
  variants, ModelFileData's ModelResourcesID (shared by the variants) and ComponentModelFileData
  (race and sex of each). In the WarcraftXL client that is 279 helmets: BfA has 277 male and 278
  female Kul Tiran versions.
- **How:** each is converted (wotlkconv; one scoped listfile for the whole batch) to
  `<Base>_KtM.m2` / `_KtF.m2` with its skins, `ChrRaces.ClientPrefix` is set to BfA's prefix
  (`Kt`), and both bodies get BfA's own attachment 11 back - undoing a fit an earlier build
  made. Textures the models name that the client lacks (3) come from BfA as they are.
- **Shaders:** wotlkconv keeps a BfA batch's textures but drops a shader 3.3.5 lacks, and 3.3.5
  draws a two-texture batch with no combiner table as the diffuse times the reflection map: 308 of
  the helmets came out nearly black, and eye glows under a raw BfA id (0x10) slid with the camera.
  Each batch is redrawn the way WarcraftXL's own helmets draw BfA's (all 279 compared): a
  reflection shader (0x8000, 0x8003: combiner ops Mod, Mod2x; 0x8002: Mod, Add) draws diffuse and
  reflection together and then the diffuse again, alpha blended, so the reflection shows only
  where the diffuse is clear; 0x8001 draws the diffuse and adds the reflection as a layer; any
  other draws its diffuse alone. BfA's 0x40/0x80 batch flags are dropped, as WarcraftXL drops
  them (618 batches in all).
- **Particles:** as WarcraftXL carries BfA's emitters (all 86 helmets with emitters compared): a
  z-source of 255 (BfA's "none") becomes 0, and on a one-cell texture the head and tail cells
  are 0 (an empty head-cell track filled with 0). BfA's Kul Tiran versions ask for cell 1 of a
  one-cell texture, which 3.3.5 samples past the texture's edge: the T10 warrior helm's glowing
  eyes didn't show (418 emitters in all). BfA's Human helmets put through the converter and these
  passes match WarcraftXL's own in every emitter field but data BfA itself changed.
- **Bone influences:** BfA's skins leave each section's `boneInfluences` at 0 (its renderer reads
  the weights) and wotlkconv copies it; 3.3.5 picks a section's vertex path by it, and
  WarcraftXL's log names each such Kul Tiran helmet section as one its shadow draw "would have
  been camera-locked". Every section with weighted vertices gets the count its vertices weigh
  (1 for a rigid helmet), as WarcraftXL's and the stock helmets carry (`convert/fixup.py`,
  `fill_bone_influences`); the bodies' few such sections (ears, some hair and face pieces) get it
  too. Whether this is also why the T10 warrior helm's eye glows - particles on the helmet's own
  bones, every emitter field as WarcraftXL's - showed only from below (fifteenth client test) is
  for the next test.
- **Missing:** a helmet BfA has no version of for the race (the black bunny ears, the male's
  PvP death knight B_02) gets the look template's model carried to where `race/helm.py` fits it
  on the race's head (below), its vertices moved so that BfA's attachment puts them there.
- **Hidden geosets:** what each helmet hides on the race is BfA's (HelmetGeosetVisData above).
  Which rule a helmet uses is the client's own ItemDisplayInfo: BfA moved some items to newer
  displays that hide less - the T10 warrior helm's items use one hiding only hair and ears, so
  the beard shows in BfA (and wow.export), where 3.3.5's display for them (rule 248) hides the
  beard on every race.

`--template-helmets` (or a race without helmets of its own) wears the look template's instead,
fitted to the race's cranium (`race/helm.py`). The cranium is the top 45% of the skull, and the
skull is the body mesh skinned to the head, with hair left out.

- **Scale:** the helmet is scaled by the head's size against the template's: the cranium's
  front-to-back and side-to-side ratios and the skull's height ratio. A head shaped like the
  template's (ratios within 15% of each other) keeps the helmet's shape, scaled by the mean of the
  first two: x1.34 for the Kul Tiran female. One shaped otherwise is scaled axis by axis: the Kul
  Tiran male's is 1.29 times a Human's front to back, 1.52 across and 1.21 high.
- **Placement:** the helmet's origin sits where the template's sits relative to its own
  cranium, times that scale - or higher, where the race's brow ridge sits higher on its skull
  than the template's would scaled (the Kul Tiran male's forehead is short for his skull), until
  its brow line meets his and a quarter of his crown-to-brow distance further.
- **Turn:** the helmet faces the way the cranium does: the template's cranium, scaled, is laid on
  the race's in the side view (a turn about the left-right axis and an offset, by iterative
  closest points, once from the brow up and once from a little below it), and when the two fits
  agree the helmet takes that turn. Then half of how much lower the race holds its head than the
  template in its stand and walk animations is turned back, about the brow ridge (the Kul Tiran
  male: 8.2 degrees front-up in all).
- **How:** the scale (x, y, z) and the turn are constant tracks, on a global sequence, on
  attachment 11's bone, which replace any BfA put there; the attachment is set so that the
  turned, scaled point lands on the fitted spot. The client gives an attached model its bone's
  whole matrix. Only a bone used by nothing else is changed; BfA's models carry one just for the
  helmet.

**Bounds** - a model's header bounding box and sphere are the union of its sequences'. BfA's
include animations 3.3.5 never plays (ids past AnimationData's 505), which put a Kul Tiran
female's radius at 6.1 (Human's: 3.7). The client draws any model whose sphere reaches the liquid
surface under the unit with a clip plane at that surface, and in this client that plane can cut
through the model: standing near water, a Kul Tiran's face, half her belt buckle and slices of
her fingers vanished at some camera angles. `race` sets the header bounds to the union of the
sequences the client can play (`race/bounds.py`; radius 4.3 female, 3.9 male, like Blizzard's
larger races). Shoulders with big particle effects carry radii near 10 of their own, so their
pads can still show it by water on any race.

**Seams** - where geosets meet (the body and a chest, pants or belt piece; a scalp and a
hairline) BfA gives the edge vertices the same rest position but not always the same weights.
Animated, they part: a hairline of ground showed through a Kul Tiran male's waist. `race` gives
each such vertex the weights of the body's vertex at that point (or the lowest geoset's), for
geosets that are shown together and where every skin's palette has the bones (`race/seams.py`).
The male's waist closes; a few seams the low-detail palettes can't express stay as converted.

**Waist texture line** - a Kul Tiran's belly crosses the body texture's TorsoLower/LegUpper line
(y 192 of 512), where a chest's texture meets a pair of pants', as BfA and Blizzard's own HD models
have it, and the converter leaves it there. Two fixes for a thin line of skin there were tried and
dropped (twelfth and thirteenth client tests): moving the waist's vertices two texels into each
texture cut every design crossing the line (a death knight's belt buckle lost four rows across its
middle), and making the client's shirt and pants textures solid on their edge rows - 3,555 shared
item textures - broke the waist on every race, while with Blizzard's own the waist looked right.
The race's package doesn't touch shared item textures.

**Close zoom near water** - see [`native/wxl-water-line`](../native/wxl-water-line): with the camera
zoomed in close the client fades the player model (invisibly at first), its batches turn
transparent, and a transparent model whose bounds cross the water surface under it is cut by a
clip plane at the water line - in this client one that cut the face, belt buckle and fingertips at
some camera angles. The extension draws such models whole.

**Cloaks** - BfA characters draw one cloak variant (geoset 1507) as cape texture + guild
emblem layer (texture types 16-18, which 3.3.5 lacks); the converter drops that empty second
layer, leaving the cape texture (the same repair as the released Mag'har port). The other
cloak geosets use the ordinary cape texture (type 2) and work as in 3.3.5.

**Triangle count** - the 21,845 figure is 65,535 indices / 3. Skins past it store the high
bits of each submesh's index start in its `level` field; independently released ports that
were confirmed in a live (WarcraftXL) client do the same with 23k-35k triangles (Earthen,
Haranir), so `check`'s triangle failure on these models should be confirmed in-game before
reducing anything.

### BfA character create and select (`glue`)

```bash
retroport glue --bfa "I:\WoW Modding\Clients\WorldofWarcraft BFA" --client "F:\Wrath of the Lich King 3.3.5a (wod models)" \
    --out I:\port\BfAGlue --listfile listfile.csv --dbd WoWDBDefs\definitions
retroport install I:\port\BfAGlue --client "F:\Wrath of the Lich King 3.3.5a (wod models)" --patch patch-H.MPQ --clean
```

Character create and select for every race, laid out as Battle for Azeroth 8.3's (the WoD-BfA
screens Blizzard's art calls "Patchwerk"), on the 3.3.5a glue API (`glue/ui/`):

- **Race and class** - a gender box top left with the Alliance and Horde race columns hanging from
  it on their banners; races 3.3.5 never shipped (any `ClientFileString` but the ten classic ones)
  sit on an "Allied Races" page of their own with BfA's allied banners - but a race BfA lists with
  the classic ones (not flagged allied in its ChrRaces: a Pandaren) goes on the core page, its race
  package adding it to `CHARCREATE_CORE_RACES`; a class column down the
  right edge; race and class info panels behind "More Info"; tooltips with the race's description.
  Laid out as BfA's: race rows 70 apart, each icon on the middle of BfA's 50-unit button; the
  banners (BfA's art is drawn for six races a side, the classic page's with the Pandaren's under
  them) drawn as long as the page's races need, five at least - shorter, not cut, as a cut shows;
  the classes 55 apart down from under the column's title in BfA's order (the Death Knight last),
  each name over its icon's bottom edge as BfA's, title and icons on the column's middle (BfA's sit
  10 right of it: its panel runs on past the screen's edge).
- **Race icons** - every race's from BfA's own atlas (`raceicon-<race>-<sex>`), upscaled to 128
  pixels into one uncompressed texture (`Retroport\RaceIcons.blp`), on 44-unit buttons: 3.3.5's
  64-pixel DXT icons on BfA's 50-unit buttons went soft and blocky at 1440p. A race BfA has no icon
  for keeps its icon in 3.3.5's sheet (`RACE_ICON_TCOORDS`, which race packages add to).
- **Customize** - BfA's second step: the options on a faction-coloured banner below a "Customize"
  box, the name box and its random name at the bottom. BfA picks each style from rendered preview
  models 3.3.5 can't make, so each option keeps 3.3.5's left/right arrows.
- **Customize zoom** (`glue/zoom.py`) - as in BfA, the camera glides to the character's head for
  customization and back for race and class. 3.3.5 has no camera call, but the scene frame's
  `SetCamera(i)` picks any camera of the scene model (CSimpleModel::SetCamera, 0x95F9F0) and
  `SetSequenceTime(id, ms)` plays any of its animations, camera tracks included. So each create
  scene gets 405 cameras - head heights 0.6 to 2.8 yards by 0, 0.3 or 0.6 forward of the feet
  (hunched races) by a view as measured, 1.2 or 1.4 times as wide (`CHARCREATE_ZOOM_WIDE`: dwarves,
  gnomes and the Horde's men came out a bit too close, client test) - and two hour-long animations (Rise and StandWound, ids AnimationData gives no
  flags) in which each glides from the scene's view to its head-and-shoulders view in half a second
  and back; every other per-animation track of the scene plays as in Stand. The client stands the
  character on the scene's attachment 0, turned by that attachment's bone and the facing
  (CCharacterCreation, 0x4E1533 / 0x4E0160) and scaled by that bone (BfA's Horde scene draws every
  character 1.185 times its size, its Alliance scene 1.044), and takes a camera's field of view as
  a diagonal (vertical = fov / sqrt(1 + aspect^2), 0x6BFE00): the views are framed from those. The
  scenes gain a sequence lookup table that finds Stand too: with one the client looks every
  animation up in it (0x8260C0), and a scene it can't find Stand in crashes the client. The screen
  picks the camera for the race's head (`CHARCREATE_ZOOM_HEAD`: the middle of the skin the head
  bone carries, standing - written by the glue build for the ten classic races from the client's
  own models, and by each race package for its own), and reverses a glide from wherever it is.
- **Scenes** - BfA creates every race of a faction in one scene (ChrRaces.CreateScreenFileDataID:
  `UI_Alliance`, `UI_Horde`), converted with wotlkconv, with their textures, and drawn as
  WarcraftXL draws BfA's models (`helmets.redraw_scene`): the Horde scene's sign posts reflect
  through a combiner table as the helmets do (3.3.5 drew them black), and with that table its fire
  glows and flags keep BfA's own two ops (Mod, Mod2x). Music: 3.3.5's Human and Orc tracks until
  BfA's are ported.
- **Character select** - 3.3.5's own screen, which BfA's grew from, with BfA's character rows: the
  selected row glows and the hovered one shines (`Glue-CharacterSelect-Hover`), the class reads in
  its colour, the faction's emblem sits on the row, and a character with a paid service waiting
  (customize, race or faction change) gets BfA's gold-ringed service icon beside it; Back and
  Delete in BfA's corner, AddOns over an Options button where BfA's menu is; the rows 24 in from
  the list's edge and the list 710 tall, as BfA's. GetCharacterInfo names a character's race in
  words, not its faction: a race on both sides under one name (a Kul Tiran) gets no emblem.
- **Select scenes** (`glue/scenes.py`) - each character stands in its race's BfA scene
  (ChrRaces.SelectScreenFileDataID, `UI_Human` ... `UI_Draenei` - the names 3.3.5's are under),
  converted with its textures and drawn as WarcraftXL draws BfA's models; a race package brings its
  own (see `race`). 3.3.5 stands a Gnome in the Dwarf's scene and a Troll in the Orc's
  (GetSelectBackgroundModel, 0x4E36C8): the screen gives each the scene BfA gives it (enUS race
  names), a death knight keeping Acherus. Each scene draws the character at the size its
  attachment 0's bone gives (0.46 for the Tauren's to 2.1 for the Kul Tiran's), and is lit as BfA
  lights it - its own lights, glow 0.3, fog only for the Undead's - where 3.3.5's GlueParent tables
  lit its own scenes.
- **Art** - BfA's `UI-CharacterCreatePatchwerk`, `Frame-Sides`, `ButtonFrame-Mid`, the select
  hover glow and service icons, and the atlas textures BfA's XML addresses through UiTextureAtlas
  (3.3.5 has none): the build looks each `@ATLAS:` / `@COORDS:` piece of the XML up in
  UiTextureAtlasMember and writes file and texture coordinates. BfA's XML also leans on
  relativeKey, KeyValues, mixins and texture sub-levels, which 3.3.5 doesn't read; the rebuild keeps
  BfA's sizes, offsets and coordinates in 3.3.5's dialect. A texture BfA lifts over its frame's
  others with a sub-level sits on a child frame (3.3.5 draws one layer in no fixed order: the Finish
  arrow came and went with the name box's cursor).

**Race packages on the new screens** - the create screen's Lua sets `RETROPORT_GLUE_STYLE`; a race
build on it adds only its icon coordinates and its head for the zoom (and its GlueStrings text):
the screen makes race buttons as it needs them, lays them out by faction and reads
faction-specific racial text (`ABILITY_INFO_<RACE>_<FACTION><n>`) itself. Install the glue package
first, then rebuild each race on top (`race ... --reuse --replace`); the glue build carries the race
blocks of the screen it replaces, so an installed race keeps its icon and zoom in between.
`install` reads a glue package's `package.json` (the files it was built on, and the folders it
owns) as it reads a race's `race.json`.

### Start outfits of a race's own faction (`outfits`)

```bash
retroport outfits --client "F:\Wrath of the Lich King 3.3.5a (wod models)" --server-dbc D:\AC\Build\Data\dbc --out I:\port\StartOutfits
retroport install I:\port\StartOutfits --client "F:\Wrath of the Lich King 3.3.5a (wod models)" --patch patch-H.MPQ --server-dbc D:\AC\Build\Data\dbc
```

Fixes to CharStartOutfit.dbc, the client's (character create shows it) and the server's (AzerothCore
gives its items, Player::Create), built on the copies they load (`race/outfits.py`). An All Races
All Classes patch gives a race a class by copying another race's outfit, sometimes across factions
(its Undead hunter wore the Dwarf's Rugged Trapper's set and blunderbuss, its Blood Elf druid the
Night Elf's): a race/class whose outfit only the other faction wears gets the outfit of the first
race of its own faction with the class. And every item shows its own display (Item.dbc): its Human
and Undead hunters' shirt showed display 9676, not 9976, and they stood shirtless. Install it after
the race packages, then rebuild them on top as on top of the glue package (they keep its rows).

### Retail gear on top: wow-retail-backport and Equip Plus

[wow-retail-backport](https://github.com/Kirazul/wow-retail-backport) converts retail sets, items
and weapons for 3.3.5a from wago.tools; [Equip Plus](https://github.com/TheDaveCalaz/wxl-equip-plus)
(a WarcraftXL extension) draws the 3D pieces a stock client can't - belt buckles, boot shells,
gauntlets, skirts, capes - and its `Backport Helper.bat` runs the kit, converts its 3D pieces and
installs both. They sit on top of the retroport packages:

1. **Order.** glue -> outfits -> race packages (`patch-H.MPQ`, a folder) first, the kit last. The
   kit packs its own `patch-<letter>.MPQ` above every mounted patch (`patch-I` here) with the
   client's Item, ItemDisplayInfo and HelmetGeosetVisData plus its rows - our rows included, since it
   read them from `patch-H`. Equip Plus's pieces go in a folder `patch-W.MPQ` (CSV sidecars, models).
2. **Folder patches.** The client (and WarcraftXL) mounts a folder named like a patch in its name's
   place; the kit's own reader skipped folders, so it saw neither our races nor our tables. The
   local clone's `scripts/lib/client.py` mounts them (`FolderArchive`) - worth sending upstream.
3. **Our races.** The kit matches client races to retail by prefix: Kul Tiran 22/23 (`Kt`) and
   Pandaren 24/25 (`Pa`) get retail's own per-race helm cuts with no `race_map`. Their bodies are
   BfA's HD bodies with every bone's name hash, so Equip Plus binds retail 3D pieces to them as to
   the client's own HD bodies.
4. **Rebuilding a race package later.** Builds read the client as their install patch sees it
   (`--patch`, default `patch-H.MPQ`): a patch that outranks it (the kit's) is left out, so its rows
   never end up in ours. `install` then lists what that patch shadows - the client keeps loading the
   kit's copy of Item.dbc until the kit is rebuilt on top (the helper's Build + Install; it moves its
   patch aside to re-scan). On the server, the helper's `merge_server_dbc` keeps our rows, and a race
   rebuild keeps the kit's.

## Status - validated vs. needs in-client testing

**Validated end-to-end (real files):** re-inline (self-contained `.m2` incl. the parent-
skeleton/child case), MultiConverter conversion (`-> MD20 v264`), combiner-flag fix,
submesh clamp, staging, check.

**Not yet confirmed in a real 3.3.5 client** (WMV loading != client accepting - error 132
is a client-side crash):
- whether MultiConverter's flag-stripping is sufficient for a clean load (test a plain
  converted model first);
- with the MultiConverter engine, whether the staged/clamped modern `.skin` files are
  WotLK-compatible as-is (the wotlkconv engine rewrites them to the 48-byte 3.3.5 header);
- the Blender decimation round-trip (the write-side of Blender is the known weak link;
  M2Mod's cap check is the safety net).

**Validated on a real model (hozumonkey, non-skel):** texbake resolved the empty slot's
FileDataID through the full community listfile and baked it; the new `.anim` check found
that MultiConverter leaves external `.anim` files in Legion's chunked AFM2 format.

**Needs in-client confirmation:** the multi-LOD gate (`lod_unmerged`, from Conjure) fires
when the M2 carries more than 1.5x the vertices skin00 uses. Models that ship a separate
`_lod` skin trip it; whether that actually breaks a 3.3.5 client is untested.

**wotlkconv engine on real models:** a 2H axe (clean check), hozumonkey (its 18 external
`.anim` files now come out flat, no AFM2 warning), and the `.skel`-based Kul Tiran male
(skeleton merged; 276 inline + 57 external animations) all convert to MD20 v264; the
remaining blocker on the last two is the triangle ceiling (poly-reduce).

**Gaps:** MPQ packaging; WMOs and doodads (wotlkconv converts both - not wired into the
pipeline yet); character models (eyes use texture type 19, which wotlkconv empties, and
modern face UVs don't match the 3.3.5 skin layout); bone pruning over the ~256 ceiling. Helms and resized armor
textures still need an in-client check (helm fit with/without `-fixhelm`, texture layout).

**Tool quirk:** MultiConverter reports "No files to convert" when the model path is over
260 characters (Windows MAX_PATH) - keep output folders short. (The wotlkconv engine
doesn't have this limit.)

## Layout

```
retroport/
  models.py            AssetInfo, Finding, ValidationReport, ConversionResult
  pipeline.py          the headless conductor (Pipeline / PipelineConfig)
  check.py             WotLK render-blocker diagnostics (+ LOD gate, .anim checks)
  dbc.py               WDBC engine, CreatureModelData/DisplayInfo registration, TextureVariations
  itemdbc.py           ItemDisplayInfo + Item.dbc writer, pack paths, prefill from a model
  helms.py             helm race/gender variant discovery + batch conversion
  character/           BfA playable-race port: layouts (section remap), model (UV remap),
                       textures (composite/region conversion), convert (orchestration + DBC rows)
  race/                playable race: tables (DBC edits + removal), glue (create-screen UI),
                       icons (DXT atlas splice), sql (AzerothCore), helmets (the race's own from
                       BfA; BfA models drawn as WarcraftXL draws them), helm (template helmets
                       fitted), outfits (start outfits of a race's own faction), build (orchestration)
  glue/                glue-screen packages: build (BfA character create and select: art, atlas
                       pieces, race icons), scenes (BfA's create and select scenes), zoom (the
                       customize zoom's cameras), ui/ (the screens' 3.3.5 XML and Lua)
  mpq.py               read-only MPQ reader + the client's archive priority
  textures.py          armor-region / object texture resize for 3.3.5
  sql.py               AzerothCore creature_template_model repoint SQL
  safeio.py            atomic write-verify-replace, backups
  scan/                chunk-walk classifier
  formats/             binary layer: structs, m2 (MD21), md20 (textures/sequences/bake),
                       skel, anim, verify (structural problem detectors), blp (BLP2 codec)
  convert/
    skel_reinliner.py  the .skel re-inliner  <- the novel native work
    engine.py          wotlkconv engine: scoped listfile, conversion, verified writes
    multiconverter.py  MultiConverter wrapper (console build, output verification)
    m2mod.py           M2Mod wrappers (m2<->m2i, txid-remove) + reduce_model chain
    blender.py         Blender decimate wrapper
    blender_decimate.py  headless Blender script (WoWTools .m2i / WBS .m2 / obj)
    fixup.py           combiner header repair, combiner fix, submesh clamp, nViews, stale-flag cleanup,
                       bone influences
    texbake.py         TXID + listfile -> baked texture paths
    loaders.py         FileDataID loaders over a wow.export extraction
gui/                   PyQt6 shell over pipeline.py
```

See `GUI.md` (here in docs/) for the desktop app and `SKEL_REINLINE.md` for the re-inline algorithm.
Parts are adapted from Conjure (MIT); every project retroport builds on, runs or bundles is credited
in `THIRD_PARTY_NOTICES.md`.
