# Retroport Workbench x64 - internals

A developer's reference: how the Workbench reads its data, builds its catalog, draws its previews
and installs into the x64 client. For using it, see the [README](../README.md).

## How it's built

An application for the x64 3.3.5 client: `Retroport Workbench x64.exe` opens it in a window of its
own (Edge's app mode - no console, no browser tab; the server behind it listens on
`http://127.0.0.1:8335/` only, `edition.PORT`). Closing the window closes it - after an Install
that's running has finished; started again while it runs, it opens another window on it. Its log is
`%USERPROFILE%\.retroport\workbench\workbench.log`. It runs no other tool: no conversion kit, no
WarcraftXL or Equip Plus (the `main` branch's Workbench did).

- **Game data from wago.tools for browsing** - retail's tables (as wago's CSV) and its files by
  FileDataID at the newest live build, and BfA 8.3.7's for the bodies the character view dresses
  (`retroport/workbench/wago.py`; checked row-for-row and byte-for-byte against local installs at
  12.1.5.70391 and 8.3.7.35435 - wago's tables also carry hotfixes). Everything fetched is kept on
  disk, so it opens again while wago is down.
- **Your own installs** (Settings): a retail and a BfA install read directly - faster, and
  independent of wago; they need WoWDBDefs' definitions and the community listfile. Install reads
  retail from your own install only.
- **Settings** (the first run opens it): the x64 client folder and where the items come from. Each
  Browse button opens Windows' own folder picker, and each field says what it found there. A
  setting this Workbench doesn't use (the earlier Workbench's `kit` and `route`) is kept in
  `workbench.json` as it was when it saves (`Settings._others`).

From a checkout: `python packaging/build_release.py --launcher-only` builds the launcher next to the
code (it runs the `pythonw` on PATH), or run `retroport workbench` / `Workbench.bat` in a console -
with `--bfa` / `--retail <install> --dbd ... --listfile ...` to read local installs:

```
retroport workbench --bfa "<BfA install>" --retail "<retail install>" --client "<x64 client>" ^
    --dbd "<WoWDBDefs\definitions>" --listfile "<listfile.csv>"
```

Options are remembered in `%USERPROFILE%\.retroport\workbench.json`. **A release** -
`python packaging/build_release.py` - is a folder and its zip named after the edition
(`edition.NAME`): the launcher (built with the C# compiler every Windows has), Python's official
embeddable package with retroport's dependencies, and the code (retroport, wotlkconv); it imports and
serves the page with its own Python before it's zipped. It holds nothing of Blizzard's.

Each source's catalog is built from its own tables once per build (seconds; then under a second
from the cache) - every item with a look and a search name (89,490 in BfA 8.3.7, 99,076 in retail
12.1.5), its appearances and display ids, the transmog sets as families of versions
(Normal/Heroic/Mythic, a PvP set's seasons) and the classic item sets. A partial local retail
install fetches what it doesn't store from Blizzard's CDN, verified and kept in the cache.

- **Items**: search by name or by item, appearance or display id; filter by slot, armor or weapon
  type, expansion, quality, class; *one per look* folds items that share an appearance. Items your
  3.3.5 client already has (same id) are marked; Blizzard's test items are hidden unless asked.
- **Sets & collections**: one card per family with its pieces (a class set names its class: one PvP
  name covers a Hunter's, a Shaman's and an Evoker's looks). Retail lists some sets once per colour
  without linking them as versions (Aquatic, Azure, Brick... Sweatsuit; Prowler's Pink, Plum...
  Headgear): `catalog.fold_variants` makes three or more sets of no family of their own, named alike
  but for one colour word (`COLOR_WORDS` - another word is another set: a race's heritage armor, a
  season's plate), with the same slots and expansion, one family - the colour each one's label, the
  card named without it. The card of the family whose set is open stays marked whichever version is
  shown (`data-root`); the detail lists every version and
  piece, one per look - items that look the same (a Helm and a Faceguard for two armor types) under
  the one the set marks primary, "+1 same look". A set that is only a fragment of another of the
  same name - no version label or group, every look of it in the other (retail sells a PvP season's
  Elite looks two slots at a time as their own sets) - is folded into that one (717 in retail
  12.1.5; still found by id). Ids are the game's own.
- **Basket**: kept in the workbench folder; what the next Install adds to the game, to look over
  first. Each entry shows the looks it brings - one per model: a set's pieces, every version of an item (an item set: of each of its items) - and opens in the drawer from
  its name or any look; one whose looks all come with another entry already says so, one that shares
  some says with which. × removes (with Undo); Empty the basket empties it.
- **In your game**: installs add up. What Install builds (`Workbench.install_list`) is what the last
  install put in the game - the entries recorded in its `install.json`, kept by every install - minus
  what's marked *take out* (`<data>\direct\workbench-take-out.json`), then the basket; a basket entry
  stands for the game's entry of the same key (a piece left out of something installed copies its
  entry into the basket). An install that worked takes what it installed out of the basket and
  clears the take-outs; every install, worked or not, goes into `<data>\basket-history-direct.json`
  (the name the earlier Workbench gave this history; the last five: when, the result and the step it stopped at, the basket, what was taken out) - the
  Basket's *History*, each with *Put back in the basket*. Installs it has no record of (made before it
  kept one, or undone: Undo keeps an install's record as `install.json.undone`) come from the
  install records, each one's basket worked out as what it added to the install before it.
  The Stats page lists the basket's pieces only: something in the game gets new stats by going back
  in the basket.
- **Preview** (in an item's panel, at the top, its versions under it beside the race and sex -
  Normal / Heroic / Mythic, a PvP piece's Gladiator / Elite, named by the set that uses them, one
  per look - each a click away; a set's versions sit there too): its models
  in 3D (WebGL2: left-drag turns, right-drag moves, the wheel zooms, double-click resets), playing
  their Stand animation - bones, scrolling and turning textures, colour and transparency tracks,
  particle emitters - for a race and sex of the ones your 3.3.5 client plays (helms and shoulders
  differ; a race without its own model wears ChrRaces' fallback race's: a Nightborne the Night
  Elf's; heritage armor made for one race shows as theirs, and says so). A piece with no model -
  a cloth cloak (ModelType 5: its texture on the body's cape), armor drawn on the body - shows on
  a character wearing only it, a cloak from behind. Each batch is drawn with the client's
  own combiner for its shader id (the table for 0x8000 ids, the bits for older ones): how its up
  to three textures mix - a glow added over an environment map, a pattern moving under a mask -
  and whether each reads the first UVs, the second or the environment. Shoulders sit as worn; a
  held item stands up facing you: weapons and shields are modelled from the grip along +X, so +X
  goes up (an axe's head, a staff's crown, a shield's top) and you face the flat side (a shield's
  front is +Y; one modelled leaning, as it sits on the forearm, has its long axis stood up - the long
  axis of what it draws, each triangle weighted by its area, so a kite shield's chains and ribbons
  don't outweigh its face); a shield
  or off-hand modelled along Z instead (Shadowlands' PvP ones, lanterns: Dread Gladiator's Barrier,
  Reprieve, Galactic Warmonger's Lantern) has +Z up - a shield's top, the grip an off-hand hangs
  from; guns, bows and crossbows stay level. A texture animation moves the coordinates, not the
  texture: the first UVs by the batch's first transform, the second UVs by its second, an
  environment map by none (two textures on the first UVs move together - Venomous Aspirant's
  Chopper's leaves keep still while its glow, on the second UVs, scrolls). A held piece shown by itself has no race and sex to pick. A see-through batch
  isn't drawn until its texture is loaded (without it, it would be a solid grey card). A model's batches
  are drawn as the client draws them, by priority plane, lowest first (a hood's glowing eyes,
  priority 4, over its dark inside, priority 0). Each material is drawn as the client's
  `CM2SceneRender::SetupMaterial` sets it: the back of a triangle culled unless the material is
  two-sided (flag 0x4), depth tested unless 0x8, written unless 0x10 - whatever the blend (the
  mesh carries `mflags`). Drawn from both sides, a glow shell added twice (the Galactic
  Gladiator's Silk Cord's buckle a flat magenta disc) and a robe's inside showed through it. The
  canvas has no alpha: what a see-through batch left in it let the page show through the model
  (Valeguard Vestments' flaps flickering as the model turned). An emitter of colour slot 11-13
  takes the display's ParticleColor row (`DisplayIndex.particle`, a mount's from its catalog
  display), as the client's `ReplaceParticleColor` gives it. Particles follow WebWowViewerCpp's
  reading of the client (`ParticleEmitter`, its generators): an emitter's frame is its bone's at its
  position turned a quarter about Z; particles start on a plane, a sphere (its angle from the ground
  plane) or along a spline (a candle's wick), live in the world or with flag 0x10 in that frame (a
  flame stays on its wick as the model moves), take the frame's scale with 0x20, lie flat in its XY
  plane with 0x1000 or along their flight with 0x4, draw a head (0x20000) and a streak (0x40000),
  twinkle, spin in radians a second, and a multi-texture emitter (0x10000000: three textures packed 5
  bits each) multiplies its three, the second and third scrolling (the Helmet of the Highlord's eyes:
  drawn by its first texture alone they were one blob); a refraction emitter isn't drawn. Ribbons
  (`CRibbonEmitter`'s way): an edge across the bone's Y at the emitter laid down at its rate as it
  moves, living its lifetime and sinking by its gravity, the texture along them from the newest,
  drawn by each of its materials (an opaque one by alpha). What the client swings with physics
  (`physics.py` reads the model's `.phys` - its PFDC chunk or PFID - as the client's PhysicsFile.cpp)
  hangs as it rests: the viewer turns each dynamic body, with what it carries, about its joint so
  their weight hangs as low as the joint lets it (a shoulder's swing cone and twist, a revolute's
  hinge; a weld, a prismatic or a spring to the rest pose holds), gravity the world's down in the
  part's place, again when that place turns (the Astral Gladiator's Plate Helm's plumes, Malignant
  Vision's Headguard's tentacle - modelled sticking out, hung in the game); the framing takes the
  hung pose. A display's retail glows hang on its
  models' attachment points (`Workbench.display_glows`: `glows.placements` over ItemVisuals and
  ItemVisualsXEffect - what the client draws; the weapon type from the display's first catalog
  item), each its own animated model, scaled, left out of the framing. A version a player can't
  wear isn't listed: an appearance behind a player condition, with no name and in no set players
  see (the 12.0 "VFX unlock" looks, modifiers 154-158; `catalog.build_catalog`'s `wearable`), and
  an item's sets leave out Blizzard's internal "[DNT]" ones. Armor drawn on the body shows its section textures. Icons and
  textures a source can't open (BfA 8.3.7 keeps its last sets' art encrypted) come from the other
  source.
- **A set of one kind** - weapons, masks, cloaks, shoulders - shows its pieces one at a time in that
  preview, ◀ ▶ (or the arrow keys) in the row under it to step through, the piece shown marked in
  the list.
- **On a character** (in any other set's panel, above its pieces): the set's first piece of each slot on
  BfA's body of the race and sex - `<race><sex>_hd.m2` for the classic races (the plain one is the
  pre-WoD model on the 512x512 layout), Kul Tiran and Pandaren their own - animated. Its skin is
  composited as the client does (CharSections skin, face, scalp, underwear on the race's layout -
  the HD rows, BaseSection 5-9, where the race has them - then each piece's section textures in
  dressing order); geosets from the race's hair and facial
  hair, then each piece's GeosetGroup values (a value the BfA body has no geoset for - retail has
  more boot shapes - takes the nearest below; retail's boots say -1, no feet, where its newer
  bodies' boots cover them, and BfA's body keeps its feet for the boot's foot texture, as BfA's own
  data has those boots), what a helm hides (HelmetGeosetData). Which models hang on body points and
  which are *collections* skinned to the body's bones (by bone name hash) is the x64 client's call
  (`DisplayIndex.placement`, RetailItemIndex.cpp's `Attach`): a collection is a file the listfile puts
  in objectcomponents\collection(s)\ (`DisplayIndex.collection_files`, read when the index is built) -
  a helm's only when ModelType says 1 too, a belt's when ModelType 1 or made by race and sex (its
  flaps: ModelType says 0 on 11,500 retail collections; hung on the buckle point they floated off a
  Kul Tiran), a cloak's by ModelType 1 alone, shoulders never - and the rest hang where the client
  hangs them (helm 11 and a second model 55, shoulders 6/5 by side, chest 34, buckle 53, legs 9/10,
  feet 47/48, wrists 3/4, hands 1/2, cloak 12; held items in hand). One collection is shared by many items, and each
  shows only the parts of the body groups its slot controls (at 1 + its AttachmentGeosetGroup
  value). A model of its own (a helm, shoulders) shows its slot's groups at 1 + the higher of its
  AttachmentGeosetGroup and the display's GeosetGroupOverride - the Heroic and Mythic tier looks'
  bigger x02 parts (the Damned Necrolyte skull's flame wings), as the x64 client draws them - and the rest
  of its geosets. A piece opens on its own with a Back button.
- **Install**: one button puts what's in the game and the basket into the client (see [Install](#install));
  its progress is ticked off step by step, the log is folded below, and a step that fails stops it
  before anything is installed. *Build only* stops before the install. The item SQL is never run -
  its `SOURCE` line is shown to apply yourself.

## The Stats step

Install makes every look a cosmetic copy (any class, any race, level 1, no stats), one item per
retail display. The Stats page (`static/stats.js`) gives each piece of the basket its game values,
kept in `<data>/item-stats.json`. A value comes from the piece, else its basket set, else the basket
(`itemstats.effective`): `global` is for everything; `groups[<basket key>]` is a basket set's own
(item level, required level, quality, binding, armor type, the role, classes) - the page lists each
set as one, picked to set its values and fill in its stats together; `broken` lets its pieces be
edited one by one. Item level, required level, quality and binding are a piece's own only once its set
is broken, or when it is in no set (`SET_FIELDS`); armor type, role and classes a piece can always
set; stats, armor, damage, durability and price are stored per piece as numbers. A look's set is the
first basket set holding it (`groups_of`, worked out again when Install writes the SQL): a look two
sets share is one item in game and takes the first set's values. (An earlier version's every-piece
classes are tidied into each piece when the page loads.) The piece's model is shown under its
tooltip - the workbench's one viewer, which moves there from the item panel.

- **Fill in** follows WotLK's rules, from `retroport/workbench/wotlk.py` - Wrath Classic's tables
  (3.4.5.63697) on wago.tools, cached as one reference: the stat budget (`RandPropPoints`, by item
  level, quality and slot group), weapon damage per second (`ItemDamageOneHand`, `TwoHand`,
  `Ranged`, `Wand` and the caster tables), and armor, durability, speed and sell price as the real
  items of the same class, subclass, slot and quality have them (the median at each item level, a
  curve to interpolate). Stats are the budget split the way real items of the role split it, in
  WotLK's costs (a point of Stamina 2/3, attack power 1/2, spell power 6/7; the 1.5-power sum):
  an item-level-264 leather chest comes out Agility 159, Stamina 156, attack power 184 and two ratings
  at 104/92, armor 665, durability 120 - Sanctified Shadowblade Breastplate has 162, 162, 184,
  108/92, 665, 120. Caster weapons carry their power as spell power (2.41 x the slot-0 budget: 741
  at 264, as Frozen Bonespike and Nibelung). A piece filled in follows its level, quality, type
  and role as they change, until a number is edited by hand.
- **Copy a WotLK item** takes a real item's numbers (`/api/stats/reference`: the reference's 26,550
  equippable WotLK items, same slot first).
- **Set bonuses** are spells the 3.3.5 client has: every bonus of its own `ItemSet.dbc`, its
  `Spell.dbc` description with `$s1`, `$h`, `$d` and `$12345s1` filled in (`itemstats.spell_text`),
  or any spell by id. **Socket bonuses** are the enchantments real WotLK items use as one.

Install's SQL (`Direct.write_sql`) is the item rows followed by one `UPDATE item_template` per piece
(`itemstats.updates`); a look named after another retail item that shares it gets the name the
Basket and Stats show (`Workbench.look_names`; a name typed on the Stats page wins). The UPDATEs are
AzerothCore's columns (it has no `StatsCount`: it counts the stats it loads), each value kept inside
its column's range (`itemstats.LIMITS`; `BuyPrice` as the int32 the worldserver reads it as) - MySQL
refuses a whole UPDATE with one value out of range. Item sets are laid out on the page but not
installed: they need rows in the client's and the server's `ItemSet.dbc`, which Install doesn't make
yet (`itemstats.set_rows` / `itemset_dbc` can).

## Colourways

A player's own colours for a version of an item or a set (after Kirazul's Eclipse - its weapon and gear
colours - our own code from its design). The maths is `static/colour.js` (`Colour.apply`), the same in GLSL
in `viewer.js` (`RECOLOUR`): a colour is a hue, a saturation, a brightness (0-255, 128 as made) and a dye;
a texel goes to OKLab, keeps its lightness (times the brightness), takes the hue, and keeps its
colourfulness relative to the most its lightness and hue allow in sRGB (found by bisection) times 1.25
and the saturation - grey stays grey, so only what was coloured changes - dye pushing it to the colour's
own saturation; near white stays whiter (`1 - 0.35 smoothstep(0.8, 1, L)`), and an overbright colour is
recoloured at 1 and scaled back. A colourway (`colourway.js`) is `{key, name, colour, parts}`, each of
armor, glows, particles and ribbons "same" (the colourway's colour), "off" (as made) or its own colour.

- **The page**: under an item's or a set's preview, the *Colours* section makes a colourway of the version
  shown (`colourSection`, `colourEditor`): the wheel (each point drawn as the colour it gives), Brightness,
  Dye, ten presets, the parts' chips. The 3D view takes it at once (`previewColour`, `Viewer.setColour`):
  a model's lit colour by its armor colour, the glow a combiner adds and a batch that adds itself (blend
  3/4/7, an unlit see-through one) and an item glow's models by its glows', emitters and ribbons by
  theirs; the body's painted armor and a cloak's cape are composited again in its armor colour (canvas,
  `Colour.image`, memoised by colour).
- **The basket**: a colourway is an entry of its own - `{kind, source, id, colour}` (an item's also its
  `look`, the version's display) - keyed `kind:source:id~<colourway key>` (`catalog.entry_key`). Its looks
  (`plan_basket`) carry the colourway and a look key `display~<key>` (`catalog.look_key`), so it is never
  "covered" by the plain version; a build's record keeps `look_stamp` (the key and a hash of the colours:
  new colours, built again).
- **Install**: each colourway look is an item of its own (`retailpack.colour_entry`: numbered from
  16,000,000 like the spare looks, kept per item, modifier and colourway in `ids.json`), named after its
  colours ("Galactic Gladiator's Silk Cord (Fel)"), its description the version and colourway's names;
  the Stats step keys it by its look key. Its item_template row has a display id of its own
  (`retailpack.colour_display`: its entry, past retail's display ids and 3.3.5's; `Piece.shown`). The
  patch holds `DBFilesClient\WxlItemColours.txt` (`retailpack.colour_table`): a line a colourway - its own
  display, the retail display it recolours, then its armor's, glows', particles' and ribbons' colours, each
  `hue,saturation,brightness,dye` or `-`. The x64 client draws that display as the retail one, recoloured,
  wherever the item is drawn (worn, character select, inspect, another player): all it has there is the
  display id.

## The x64 client

A client folder with `WowClient64.exe` (`edition.CLIENT_EXE`: the x64 3.3.5 client built from
wowdecomp-dx11) is what Install goes into: Settings names it, *close World of Warcraft* waits for it
(or a `Wow.exe`), and Undo puts files back into the client the install went into (its record's
`data`). Its `Data` may be hard links to another client's archives: Install removes an archive before
copying the new one in (and Undo the same), so the other client keeps its own.

## Install

Install is `direct.Direct` (one job at a time; the Install page, the history, what's in the game,
take-outs and Undo all read its records in `<data>\direct`). `retailpack` is the pure part (the
client's rules, the walk, the tables, the SQL, the patch writer), `direct` the job, `jobs` the job
state and the small file helpers, `edition` which client this Workbench installs into
(`CLIENT_EXE`) and its name and port.

What the x64 client reads (wowdecomp-dx11-next, read-only reference): `WXL/modules/db2/items`
loads retail's `item`, `itemappearance`, `itemmodifiedappearance`, `itemdisplayinfo`,
`itemdisplayinfomaterialres`, `itemdisplayinfomodelmatres`, `modelfiledata`, `texturefiledata`,
`componentmodelfiledata`, `componenttexturefiledata`, `helmetgeosetdata`, `helmetanimscaling` and
`particlecolor` (`RetailSchemas.hpp`; `retailpack.TABLES` holds their layout hashes - 12.1.5's) and turns each
FileDataID into a path with `DBFilesClient\ModelFilePath.db2` / `TextureFilePath.db2`
(`FdidCompat.cpp`; WDC1, inline id + string offset - patch-R's, written by retroport-native's
`x64_retail_pack.py`). A display id its ItemDisplayInfo.dbc has is drawn from that row instead
(`ItemGraphOwnsDisplay`). Item rows missing from Item.dbc come from retail's item.db2 with the
item's default look (modifier 0 first, then OrderIndex); the server's item query wins for the
display (`VisibleItem_C::GetDisplayID`). `modules/equipment/EquipmentAttachments.cpp` draws the
models: it opens `Item\ObjectComponents\<folder>\<name>.m2` (folder = the one after
objectcomponents, name = after `collections\` or the file's name), a model's own texture
(ModelMaterialResourcesID, the first TextureFileData row) by its name *in the model's folder*, and
material textures (body layers, ModelMatRes) at their full paths. A retail display's particle
colours (ItemDisplayInfo.ParticleColorID) come from retail's `particlecolor` (the item worker loads
it, retail tree c4f46d0): `ApplyItemVisual` gives them to the item model's emitters of colour slot
11-13. The synthesized native row keeps that id 0.

Install (`Direct.go`):

1. **read** - the thirteen tables from the local install (`Source.raw_table`, encrypted sections
   zeroed), each layout checked; eight read into rows. Then the glow tables (`glows.TABLES`: ten,
   29 MB in 12.1.5): all of them, or none - with a warning - when one is another layout or
   unreadable. `Direct.read_glows` walks them (`glows.index`: visual -> its models) once per
   retail build, kept in `direct\glows-<build>.json` (the kit tables take about half a minute).
2. **collect** - one `Piece` per (retail item, display) of the plan; its entry
   (`retailpack.entry_for`): the item id for its default look unless the client's Item.dbc has it,
   else (modifier + 1) x 1,000,000 + id, past modifier 14 numbered from 16,000,000 (`ids.json`
   `spare`). Files: each display's models (every race and sex), its textures, each model's
   companions (SFID/TXID/BFID/SKID/PFID/RPID/GPID, recursively) and the looks' icons; names from
   the listfile, unnamed ones beside their model as `wxl_<fdid>`, a display model outside
   objectcomponents moved to `objectcomponents\wxl\` (the client can't reach it otherwise). A
   FileDataID the client's path tables already have keeps that path, and isn't shipped when the
   client holds the file. Aliases: a model where the client looks for it (a sub-folder), a model's
   texture beside it (`alias_for` - one look in nine needs one; the Damned Necrolyte skull's lives
   in collections\). A display the client's ItemDisplayInfo.dbc has is reported. A look's glows
   (`glows.for_look`, see below) add their models, walked after the displays' own files, so a
   file both need is the display's. A file only a glow brings, whose path holds another file of
   the client's (3.3.5's own spell models and textures), moves under `retroport\` after its
   first folder (`glows.relocate`). The client finds it by FileDataID, and a model's skins get a
   copy under its new name.
3. **pack** - `out\patch-Q.MPQ` (`retailpack.patch_for`: patch-T for a client without the path-table merge) (stored, written as it goes; an alias shares its file's block): a
   manifest (`retroport\direct.json` - Install replaces only a patch that has one), the tables,
   the path tables (the client's, read with Install's own patches set aside, plus the new rows), the files, the
   aliases. Then `check`: every path `retailpack.lookups` says the client opens, and each glow
   model with its skin 0, looked for in the patch and the client. And `out\view-models.txt`: each model with the textures it wears - an
   item's own (type 2) and its ItemDisplayInfoModelMatRes types (3, 4, 24: `Graph.worn`), a mount's
   skins (11, 12, 13 and a fourth's 5: `mounts.SKIN_TYPES`) - in the list the x64 client's login-screen viewer reads
   (retroport-native `tools\x64_model_view.py --list`: the build's look checked without logging in).
4. **sql** - `out\sql\retail-direct-items.sql`: `DELETE ... WHERE (entry, displayid) IN` the pairs
   Install ever wrote (`ids.json` `owned`), then one INSERT (in the format `itemstats.kit_items`
   reads) - the label of a non-default look ("Mythic") as its description - then
   `itemstats.updates` for each piece (no item sets: those need ItemSet.dbc rows).
5. **install** - `Data\patch-Q.MPQ` (an earlier own patch-T moved into the backup) replaced (removed first: hard links), the old one in
   `direct\backups\<time>\client\`, the record in `install.json`, Cache cleared.

`out\build.json` records what was built (looks, build, client, steps, entries, a summary - with
`glows`, `glow_models` and `glows_drawn`); the page calls it built while those match the basket.

### Item glows

How the client draws a retail display's ItemVisual (the Retail tree, read-only reference): it
writes 0 into the native row's `m_itemVisual` (`NativeItemRows.cpp`) and asks its own graph
(`WXL/modules/db2/items/ItemVisualGraph.cpp`). The graph is loaded at start from `itemvisuals`
and `itemvisualsxeffect`, its kits filtered out of `spellvisualkitmodelattach`,
`spellvisualkiteffect`, `spellproceduraleffect` and `spellvisualeffectname`, positioners from
`positioner*` and `transformmatrix`. `EquipmentAttachments.cpp`'s `ApplyItemVisual` then hangs
the models on every item model the client builds (weapons, shoulders, helms and the retail-only
pieces). A 3.3.5 ItemVisuals.dbc row of the same id wins, so an enchant (SpellItemEnchantment's
visual) is still 3.3.5's. Each model is found by FileDataID through the path tables. The routes
(`glows.index`):

- **point** - ItemVisuals.ModelFileID[0..4] at attachment points 0-4: drawn;
- **effect** - an ItemVisualsXEffect row's AttachmentModelFileID at its AttachmentID, scaled: drawn
  for a weapon whose subclass is the row's DisplayWeaponSubclassID. A row with -1 (any item - 577 of
  the model rows of the visuals 12.1.5's displays use) isn't drawn: the client takes no wildcard
  (`glows.ANY_ITEM`). A row for another
  weapon type isn't the look's at all, and isn't shipped (`for_look`);
- **kit** - the models of ItemVisuals.SpellVisualKitId1/2 and of an effect row's SpellVisualKitID:
  the kit's own ModelAttach rows, plus those a type-2 KitEffect row names, each
  SpellVisualEffectName.ModelFileDataID at the row's AttachmentID. `glows.kit_skip` mirrors the
  client's refusals. It draws a still model only, with ModelPosition 0, and retail sets -1 on
  47,564 of 47,710 effect names, so today it draws none (`glows.MODEL_POSITION`). Type-1 rows
  (procedural effects) carry no model; the client's `ProceduralEnchants.cpp` reads them from the
  shipped tables.

Every model of a look's glows ships, drawn or not, so a client that learns more needs only
itself. 12.1.5: 380 of 403 visuals have a model, 2,855 displays name one of 211.

## Mounts

`mounts` is the pure part (the catalog, 3.3.5's rules, the client rows, the SQL), `mountpack` the
job Install calls (`build`), the staleness check (`stale`) and the items' rows (`place_item_rows`).

**Catalog** (`mounts-<source>-<build>-v2.json.gz` in the cache, read after the item catalog): every
Mount with a display (MountXDisplay -> CreatureDisplayInfo -> CreatureModelData), its kind ("flying"
when any MountCapability of its MountTypeXCapability rows has Flags & 2), icon (SpellMisc of its
SourceSpellID, difficulty 0), source (SourceTypeEnum), the item that teaches it (ItemXItemEffect ->
ItemEffect TriggerType 6 with that spell; named by ItemSearchName) and per display: model,
TextureVariationFileDataID (4 - 3.3.5 has 3), scale, alpha, CreatureDisplayInfoGeosetData pairs and
the model data the rows copy (scale, collision, MountHeight, GeoBox, effect scales, missile collision)
and its CreatureSoundData row (CreatureDisplayInfo.SoundID, else its model's). `sounds`
(`mounts.sound_bundle`) keeps what those rows need: each row's kits by 3.3.5 column
(`race.sounds.CSD_KIT_COLUMNS`) and its SoundFootstepID, each footstep's FootstepTerrainLookup rows
(terrain, kit, splash kit), each kit's SoundKit values and SoundKitEntry files (FileDataID,
frequency). The page's preview draws the model with textures 11/12/13 and a fourth on type 5 (as
the client's skin table puts it), the geosets the packed data shows, its emitters of colour slot
11-13 in the display's particle colours, and its state kit as the x64 client draws it
(DisplayStates.cpp): the kit's models at their points (255, none, is the base 19 - the root where the
mount hasn't one), each placed as `EnchantModelTimeline`'s Placement does (scale, roll, pitch, the yaw
backwards, the offset with Y turned round), faded by its alpha and playing its animation; its
gradient in place of each batch's combiner (Gradient.ps.hlsl: the lit texel's luminance on the
three-colour ramp, a fresnel rim to the edge colour, the alpha faded up the model's reach - the
sequence's bounds - opaque and alpha-keyed batches blended by alpha); else its dissolve, the blend
style alone (flag 0x2000, as the client: Dissolve.ps.hlsl - the three layers projected over the model,
scaled and scrolling, ModX, the value at its end, a fresnel tint).

**Families** (`mounts.model_families`, worked out when the catalog loads - nothing cached): the
mounts whose first display has one model, rooted at the oldest (lowest Mount id); a mount with no
model is alone. `MountCatalog.search` gives one card per family - its oldest mount that matches -
with `root` and `versions`; `detail` gives `family`, each with its chip label (`mounts.version_labels`:
the name without the words every version's has, else the whole name; a repeat numbered).
Placeholders ("[PH] ...") count only with the page's test-mounts box, or when it is the mount opened.

**A basket entry** is `{"kind": "mount", "source", "id", "display", "mount_kind", ...}`;
`catalog.plan_basket` gives it no looks and a `mount` field.

**3.3.5 rows** (`mounts.client_tables`, from the client as Install's patch finds it):

- Spell - a copy of 23229 (ground) or 32242 (flying) with the mount's id, EffectMiscValue_1 = its
  creature, its icon (a SpellIcon row of the retail icon, or the stock row of the same name), name
  and description; SkillLineAbility - a copy of the stock row in skill line 777;
- CreatureDisplayInfo - model data id, retail scale and alpha, TextureVariation names, packed
  CreatureGeosetData (nibble per group 1-8: `(GeosetIndex + 1) * 100 + GeosetValue`, 0 none);
- a fourth skin (109 of retail's mount displays: the Molten Cormaera's body glow, on the model's
  type 5 texture) has no TextureVariation column: `mounts.skin_table` writes it in the patch's
  `DBFilesClient\WxlCreatureDisplaySkins.txt` (`display<TAB>type<TAB>name`, a comment line first),
  which the x64 client's ReplaceMonsterSkin reads (retail tree `WXL/modules/retail-models/DisplaySkins.cpp`);
  the file goes beside the other skins. A stock client draws without it. Install carries it as a made
  file (`Files.made`);
- a state kit (CreatureDisplayInfo.StateSpellVisualKitID: 57 of retail's mount displays - a war
  mount's banner, a spectral mount's mist, a fish's whiskers): `mounts.state_attachments` reads the
  models it attaches (SpellVisualKitEffect type 2 -> SpellVisualKitModelAttach ->
  SpellVisualEffectName; scale = the attach row's times the effect's, as the client's item kits take
  it; one placed by a positioner, varied at random, or swapping a texture or dissolving is left out)
  into the catalog's display (`state`); Install packs those models with the mount's own files
  and `mounts.state_table` lists them in `DBFilesClient\WxlCreatureDisplayStates.txt` (a line a model:
  display, "attach", attachment (255: none), path, scale, alpha, offset, yaw/pitch/roll, animation,
  start, end), which the x64 client's ReplaceMonsterSkin reads (retail tree
  `WXL/modules/retail-models/DisplayStates.cpp`). The same table carries
  the state kit's gradient (`mounts.state_gradients`: GradientEffect, a "gradient" line), the display's
  MountMaxBankingAngle where it isn't retail's usual 45 (a "bank" line) and the state kit's dissolve
  (`mounts.state_dissolves`: SpellVisualKitEffect type 11 -> DissolveEffect -> TextureBlendSet; a
  "dissolve" line - projection, ramp, start/end/fade-in, flags, fresnel, tint, intensity, ModX, scale,
  then each of three layers' path and scale/scroll), whose three layer textures Install packs
  in their own retail folders under `creature\retroport\`. The client draws only the dissolves with flag
  0x2000 (the Void mounts');
- particle colours - a display's retail ParticleColor row (`mounts.particle_colors_of`: Start, MID,
  End, three ARGB each - 3.3.5's layout; 137 of 12.1.5's 1,912 mount displays have one) goes in the
  client's `ParticleColor.dbc` under the mount's own id, and its CreatureDisplayInfo.ParticleColorID
  names it. The client gives a model's emitters of colour slot 11-13 those colours
  (CharacterComponent.cpp `ReplaceParticleColor`); without them the Molten Cormaera's six flame
  emitters lost theirs. Only stock locale archives hold the table, below Install's patch. An archive
  above it holding the table leaves the colours out, with a note, and the mount still goes in;
- CreatureModelData - the stock row of the same model stem (an old mount), else the kind's
  (RidingHorse / DrakeMount) for footprints and blood, with retail's size fields and
  ModelName `creature\retroport\...\<stem>.mdx`;
- sounds (`mountpack._sounds`) - a SoundEntries row per retail kit (`race.sounds.Kit`: retail's
  SoundType, volume, flags, distances, EAXDef; up to 10 files, the ones that read as Ogg, under one
  folder - a kit spread over several gets `sound\retroport\<kit>\`); a CreatureSoundData row with the
  mount's id - the template model's row (impact type, fidget delays) with every sound column
  retail's or 0 - named by both CreatureDisplayInfo.SoundID and CreatureModelData.SoundID (the
  client takes the display's, then the model's; a mounted player's sounds are the mount's); its
  SoundFootstepID retail's when 3.3.5's FootstepTerrainLookup has it or gets it: a footstep it lacks
  gets retail's rows for terrains 0..TerrainTypeSounds' highest id (the client sizes its array by
  that - a higher one would write past it), else the template's. The model's own events ($FL0/$FR0
  footfalls, $FSD, $WNG, $FD1-5) play those columns;
- ItemDisplayInfo - the item's own row (`mounts.with_item_displays`): the stock mount item's
  (ITEM_ICONS - its GroupSoundIndex) showing retail's icon. The icon file goes in the patch unless
  the client under it has one of that name.

One number per mount from 250000 is its spell, display, model data, sound data, SkillLineAbility row
and creature (`mounts.allocate`: the first no client table and no other mount uses); its item entry
from 990000, reserved in `item-ids.json` (which the earlier Workbench's projects also kept their ids in). `<data>\mount-ids.json`
also keeps the item's ItemDisplayInfo id (`display`), SpellIcon ids, SoundEntries ids per retail kit
(`sounds`), FootstepTerrainLookup ids per footstep and terrain (`footsteps`) - a row with one of them
in the base is an earlier install's and goes (`mounts.owned_ids`) - and `owned`, the (id, marker)
pairs the SQL wrote, deleted first next time.

**SQL** (`mounts.mount_sql`): the rows read back from the client tables just made - spell_dbc (all
234 columns in Spell.dbc's order; the schema's float columns as floats), creaturedisplayinfo_dbc,
creaturemodeldata_dbc - then creature_template (+ creature_template_model, creature_model_info) and
item_template (class 15/5, spell 483 then the mount spell with trigger 6, Riding 150/300, its own
ItemDisplayInfo row - or a stock mount item's when retail gives it no icon). The server reads no
sound or item display rows (AzerothCore loads ItemDisplayInfo but never looks a display up). It is
`<data>\direct\out\sql\retail-direct-mounts.sql`.

**Files**: models and skins under `creature\retroport\` (`mounts.relocate`); sounds at retail's
listfile paths (`.ogg`: 3.3.5 has none) - a nameless one `sound\retroport\<fdid>.ogg` - as FileDataIDs
Install copies (marked "sound": no path-table rows). The model and everything it names (SFID/TXID/AFID/BFID/SKID/SKPD/PFID/RPID/GPID, recursively) at their
relocated listfile paths as path-table rows - the x64 client finds skins, animations and skeletons by
name beside the model - and the display's skins under their TextureVariation names.

**The patch**: Install adds the files, path rows and tables to its patch (`patch-Q.MPQ`). `build` stops when an archive above the patch
(by name rank, whether or not the patch is there yet) holds one of `mounts.TABLES`. The status
compares the basket's mounts with the last install's `mounts`, and `mountpack.stale` names a lower
archive holding a table that is newer than the installed patch (a race package installed again; the
item display table only while no archive above holds one).

**The items' rows** (`mountpack.place_item_rows`, after the patch is in): the patch carries
ItemDisplayInfo too, but an older tool's item patch may hold it above (both test clients: the earlier
Workbench's kit patch, patch-Y).
The rows go into the archive the client reads it from when that outranks the patch - a packed
`Data\patch-<x>.MPQ` (a folder or another archive can't take them: `build` then gives the items a
stock icon) - with every row of the registry's display ids replaced. The archive is backed up into the
install's record unless the same install placed it (its own record covers it), then copied,
the copy given the table (`mpq.add_files`) and put in place of the original (a hard link's other
client keeps its own). The record keeps `item_rows` (archive -> size and mtime) and `item_ids`:
`mountpack.item_rows_gone` tells the page when the archive changed since and lost the rows, and
Undo leaves an archive that changed since as it is (`Direct.install`, `Direct.undo`).

## Client check (0.5.0)

`Direct.client_check` writes the installed patch's `.m2` list to `<work>\client-check\models.txt` and runs
`WowClient64.exe -windowed` (`edition.CLIENT_EXE`) with `WXL_RETAIL_MODEL_CHECK=<that folder>`, `WXL_NATIVE_RETAIL_MODELS=1` and
`WXL_LOG_FLUSH=1` (the client's model check mode, retroport-native `x64_native_model_check.py`): at the login
screen it reads each model natively and through the converter, writes `check.txt` (`<model>\t<same|DIFFERS|
other: not read>`) and exits. The client's `Logs\*.log` are copied aside first and put back; new
`Errors\*Crash.txt` files fail the job. The result goes into `out\build.json` (`summary.client_check`) for the page.
`Direct.check_shadowed` (after each install) lists the patch's files `ClientData(top=patch).shadowed_by` finds
in an archive above it; the path tables are left out where `retailpack.merges_path_tables` (the exe holds
FdidCompat.cpp's log line `MERGE_MARK`).
