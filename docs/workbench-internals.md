# Retroport Workbench - internals

A developer's reference: how the Workbench reads its data, builds its catalog, draws its previews
and drives the backport kit. For using it, see the [README](../README.md).

## How it's built

An application for anyone with a 3.3.5a client: `Retroport Workbench.exe` opens it in a window of
its own (Edge's app mode - no console, no browser tab; the server behind it listens on
`http://127.0.0.1:8335/` only). Closing the window closes it - after an Install that's running
has finished; started again while it runs, it opens another window on it. Its log is
`%USERPROFILE%\.retroport\workbench\workbench.log`.

- **Game data from wago.tools by default** - nothing to install: retail's tables (as wago's CSV)
  and its files by FileDataID at the newest live build, and BfA 8.3.7's for the bodies the
  character view dresses (`retroport/workbench/wago.py`; checked row-for-row and byte-for-byte
  against local installs at 12.1.5.70391 and 8.3.7.35435 - wago's tables also carry hotfixes).
  Everything fetched is kept on disk, so it opens again while wago is down.
- **Or your own installs** (Settings): a retail and a BfA install read directly - faster, and
  independent of wago; they need WoWDBDefs' definitions and the community listfile.
- **Settings** (the first run opens it): the 3.3.5a client folder, the server's dbc folder, where
  the items come from, the kit's project. Each Browse button opens Windows' own folder picker,
  and each field says what it found there.
- **The kit and Equip Plus are fetched, never bundled - and always the workbench's own copies**: the
  first Install downloads the retail backport kit (it carries no license, so it can't be passed on
  or changed and passed on) and Equip Plus's tools from their authors' GitHub at the commits this
  workbench is checked with (`retroport/workbench/deps.py`), into `<data>\deps`. No setting points
  the workbench at another copy (the Backport Helper's kit, a clone with edits of its own): what
  runs is the same for everyone, and a fix to how the kit runs lives in `kitlocal`.
- **What `kitlocal` changes in the kit's run** - in its process only, the kit's files untouched;
  each is a wrapper around the kit's own function, and each a fix to offer the kit's author:
  * open-folder patches: WarcraftXL clients mount a FOLDER named like an archive
    (`Data\patch-H.MPQ\...`, as Equip Plus installs its pieces); the kit's client reader is shown them;
  * a model the client holds as retail's (MD21) over a 3.3.5 (MD20) copy is read as the 3.3.5 one:
    the x64 client mounts retail bodies (its patch-R) over the 3.3.5 ones, and the kit, which reads
    only MD20 bodies, found no Kul Tiran or Pandaren body there - while the client places a 3.3.5
    helm by the 3.3.5 body beneath anyway (its helmet lift);
  * its export of retail's 3D pieces (`build --extension`) leaves helms out - their own model is the
    3.3.5 row's - and with them the part some helms wear of the set's shared body model (the Damned
    Necrolyte skull's hood, group 27). The kit's own export runs once more on just those parts
    (shown as slot `head_collection`, filtered by the head's groups), and after Equip Plus's
    converter (which only knows the body slots) `eprows.add` gives its patch the rows: the hood on
    attachment 19 and the helm's own model as its 3.3.5 row has it (Equip Plus draws only the rows of
    a display that has any);
  * cached tables an older kitlocal wrote with an `ID` column wago's don't have (ModelFileData,
    TextureFileData - newtech called the column new retail technology) are put right;
  * a sequence a model calls external but keys nothing for is made resident, and a model gets only
    the `.anim` files of sequences it streams (the kit copied a source model's every `.anim` to each
    per-race helm and the audit wanted thousands nobody had made: "C1/C2 closure ... .anim missing");
  * the build plan forgets displays no longer selected (the audit checked every display the plan
    ever held);
  * its `tables` step numbers items and displays around every id any of the workbench's projects
    ever gave (`--ids <data>\item-ids.json`, `retroport/workbench/itemids.py`): the kit only skips
    the ids its scanned client tables still hold, so a look taken out - or installed by another
    project, whose patch the new one's tables replace - left its numbers free for another look,
    while the server and players' bags kept the old item (a new project gave Dread Gladiator's
    weapons the numbers an earlier one had given Embered Guise of the Wight). Now no new look gets
    another's id, and a look that comes back gets its first ids again where no row of the client
    and no other look of the project has them. The workbench adds a project's `ids.json` to the
    registry after each tables step;
  * a helm that sits a little off a client body ("P1 placement") is a note, `P1 placement
    (warning)`, not a failure - prove-gates' own audit runs in a process of its own, unwrapped, so
    its planted misplaced helm is still caught;
  * prove-gates plants where the audit can see it (below).
- **The kit's gates, answered on the page**: newtech stopping on retail features the kit hasn't seen
  runs its own `newtech --learn` and the check again (`Kit.learn`); an audit that stops the install
  is listed on the Backport page by piece (`Kit.audit_notes`: a line's display from the
  `d<display>` it names or the model/texture its file was made from) with *Leave this piece out* -
  the basket entry keeps a `leave_out` list, and the kit selects that entry as its other looks
  (`--display` each; the select arguments are recorded with the selection, so leaving a piece out or
  putting it back is a new selection).
- **Its `prove-gates` (which plants 8 known defects in a copy of the build
  and expects the audit to catch each) is shown only the models a planted defect can show in: the
  manifest also lists files the build made but doesn't ship (a shoulder's untrimmed source beside
  its trimmed variant), and the "flying part" defect (M8) moves a model's first keyed bone, which a
  trimmed variant may not skin a single vertex to. Planted there, the defect moves nothing the
  audit reads and prove-gates calls the audit broken ("M8 motion MISSED"); the audit itself is not
  touched.

From a checkout: `python packaging/build_release.py --launcher-only` builds `Retroport Workbench.exe`
next to the code (it runs the `pythonw` on PATH), or run `retroport workbench` / `Workbench.bat` in a
console - with `--bfa` / `--retail <install> --dbd ... --listfile ...` to read local installs:

```
retroport workbench --bfa "<BfA install>" --retail "<retail install>" --client "<3.3.5 client>" ^
    --dbd "<WoWDBDefs\definitions>" --listfile "<listfile.csv>"
```

Options are remembered in `%USERPROFILE%\.retroport\workbench.json`. **A release** -
`python packaging/build_release.py` - is a folder and its zip: the launcher (built with the C#
compiler every Windows has), Python's official embeddable package with retroport's dependencies
and numpy, and the code (retroport, wotlkconv); it imports and serves the page with its own Python
before it's zipped. It holds nothing of Blizzard's, the kit's or Equip Plus's.

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
  12.1.5; still found by id). Ids are the game's own - the ones the retail backport kit's
  `select --set/--item` takes.
- **Basket**: kept in the workbench folder; what the next Install adds to the game, to look over
  first. Each entry shows the looks it brings as the kit selects them - one per model: a set's
  pieces, every version of an item (an item set: of each of its items) - and opens in the drawer from
  its name or any look; one whose looks all come with another entry already says so, one that shares
  some says with which. × removes (with Undo); Empty the basket empties it.
- **In your game**: installs add up. What Install builds (`Workbench.install_list`) is what the last
  install put in the game - the entries recorded in its `install.json`, kept by every install - minus
  what's marked *take out* (`<project>\workbench-take-out.json`), then the basket; a basket entry
  stands for the game's entry of the same key (a piece left out of something installed copies its
  entry into the basket). An install that worked takes what it installed out of the basket and
  clears the take-outs; every install, worked or not, goes into `<data>\basket-history.json` (the
  last five: when, the result and the step it stopped at, the basket, what was taken out) - the
  Basket's *History*, each with *Put back in the basket*. Installs it has no record of (made before it
  kept one, or undone: Undo keeps an install's record as `install.json.undone`) come from the
  project's own records, each one's basket worked out as what it added to the install before it.
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
  priority 4, over its dark inside, priority 0). Armor drawn on the body shows its section textures. Icons and
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
  data has those boots), what a helm hides (HelmetGeosetData). ModelType 0
  models hang on body points (helm 11, shoulders 6/5, buckle 53...); ModelType 1 *collections* are
  skinned to the body's bones by bone name hash - one collection is shared by many items, and each
  shows only the parts of the body groups its slot controls (at 1 + its AttachmentGeosetGroup
  value). A model of its own (a helm, shoulders) shows its slot's groups at 1 + the higher of its
  AttachmentGeosetGroup and the display's GeosetGroupOverride - the Heroic and Mythic tier looks'
  bigger x02 parts (the Damned Necrolyte skull's flame wings), as the kit builds them - and the rest
  of its geosets. A piece opens on its own with a Back button.
- **Backport**: one **Install** puts the basket into the client and the server - it fetches the kit
  and Equip Plus the first time, creates the kit's project if there's none, has the kit `select` the
  basket when it changed since the last selection
  (which un-ticks every later step in the kit's ledger; an unchanged basket isn't selected or built
  again), runs every step that hasn't passed (scan when needed, with the kit's own patch out of Data
  meanwhile, then fetch ... sheet), then installs; its progress is ticked off step by step, the log
  is folded below, and a step that fails stops it before anything is installed. The folders are in
  Settings; the kit's own steps - *redo from here*, *Build only* - are folded away. The kit's
  preview pictures (its sheet step) stay in the project's `sheets` folder; the page only opens it
  (`/api/kit/open-sheets`, Explorer). Install / Undo work the Backport
  Helper's way (backups under
  `<project>\backups\<time>\install.json`, the helper's `last_backup` updated, so either tool undoes
  the other's): Equip Plus's 3D-piece patch, the kit's patches into Data, the client's Cache cleared,
  the server's Item/ItemDisplayInfo.dbc merged when a server dbc folder is set. The item SQL is never
  run - its `SOURCE` line is shown to apply yourself.

**Retail from your own install.** With `--retail`, a kit project pinned to that install's build
reads retail locally: `retroport/workbench/kitlocal.py` runs the kit unchanged and answers its
downloads (`wago._get`) from the install - tables as wago's CSV (checked text-identical to wago's
on ChrRaces, ParticleColor, ItemNameDescription, HelmetGeosetData at 12.1.5.70391), files by
FileDataID (byte-identical). What the install can't give - another build, a table its listfile
doesn't name, an encrypted file, the community listfile - still goes to wago.tools; each run
ends with a count of what came from where. wago's tables also carry Blizzard's hotfixes, which an
install's own tables don't (2 of ParticleColor's 2,122 rows at 12.1.5).

## The Stats step

The kit makes every look a cosmetic copy (its SQL says so: *any class, any race, level 1, no stats*),
one item per retail display id (`ids.json` maps display -> entry). The Stats page
(`static/stats.js`) gives each piece of the basket its game values,
kept in `<data>/item-stats.json`: item level, required level, quality and binding are *for every
piece* (`global`) only; armor type and the role the stats are for are for every piece unless a
piece sets its own; classes are each piece's own; stats, armor, damage, durability and price are
stored per piece as numbers. (An earlier version's every-piece classes, and a piece's own levels,
quality and binding, are tidied into that when the page loads.) The piece's model is shown under its
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

Right after the kit writes its item tables (`Kit.hooks["tables"]`, so the SQL is there even when a
later step stops) and again after its steps (`Kit.hooks["built"]`): a piece whose armor type changed
gets that subclass and material in the kit's `out/dbc/Item.dbc` (from the kit's own values, so it's
idempotent; after the steps, the kit packs again when the table changed); `out/sql/retroport-items.sql`
is the kit's SQL followed by one `UPDATE item_template` per piece - the file the Backport page shows.
A look the kit named after another retail item that shares it gets the name the Basket and Stats
show (`Workbench.look_names`; a name typed on the Stats page wins). The UPDATEs are AzerothCore's columns (it has no `StatsCount`: it counts the stats it loads), each
value kept inside its column's range (`itemstats.LIMITS`; `BuyPrice` as the int32 the worldserver
reads it as) - MySQL refuses a whole UPDATE with one value out of range, and the piece would stay
the kit's level-1 copy. After
the patches are placed (`Kit.hooks["installed"]`): the item sets (ids from 3000, kept per set in
`<data>/item-set-ids.json`) are added to the client's own `ItemSet.dbc` - read from below the kit's
patch - written *into* the kit's patch (`retroport.mpq.add_files`: the file is stored after the
archive's data, new hash and block tables follow, the header is changed last), and merged into the
server's `ItemSet.dbc` (backed up; Undo restores it).

## Looks built outside the workbench

The Backport Helper adds each selection to its project (`select --add`); the workbench uses the
same project and selects exactly the basket. So `Kit.foreign_looks` lists the displays the
project ever built (`ids.json` keeps them all) that the basket lacks and the workbench never chose
(`workbench-basket.json` "known"): the Basket offers to bring them in (as `look` entries, selected
with `--display`) or let them go (`/api/kit/let-go`), and Install waits until one is chosen.

## Equip Plus

Its 3D pieces need WarcraftXL with Equip Plus in the client
(`Extensions\wxl-equip-plus\wxl-equip-plus.dll`). `KitSettings.equip_plus` is `auto` (run its
converter when the client has it), `on` or `off`; without it the kit's patch alone is installed,
which a stock client draws.

**Live physics** (Equip Plus 1.3.0, experimental): the kit ports retail's Domino engine and
documents the client-mod contract (its `references/client-extension.md` section 5); Equip Plus 1.3.0
runs it, from `DBFilesClient\WXLEquipPlusPhysics.phy2`, which its converter (`physics_table.py`)
writes into the Equip Plus patch from the kit's `.phys` data. So the converter Install runs must be
1.3.0 or newer: `deps.PINNED` holds its commit, a fetched copy carries the commit it is
(`.retroport-ref`) and is fetched again when the pin moves. The client's DLL is new enough when it names that table. The switch
is the client's: `[Physics] Enabled` and `[Fit] RetargetPivots` / `RetargetScale` in
`Extensions\wxl-equip-plus\WXLExtendedEquipment.ini`, which Settings changes in place
(`Kit.set_equip_plus_options`: those keys only, a copy of the file kept the first time).

## The x64 client

A client folder with `WowClient64.exe` (the x64 3.3.5 client built from wowdecomp-dx11) is a
client like a `Wow.exe` one: Settings names it, *close World of Warcraft* waits for either exe, and
Install puts the same patches in its `Data`. Its Equip Plus is built in - it reads Equip Plus 1.2's
`WXLItemDisplayModels.csv` rows itself (`WXL/modules/equipment/EquipPlus.cpp`), with no INI and no
live physics yet - so `equip_plus_client()` says `builtin` and the pieces are made for it.

That client's `Data` may be hard links to another client's archives: Install removes an archive
before copying the new one in (and Undo the same), so the other client keeps its own.

The kit's project remembers its client (`bp.json` `client_data`). When Settings names another one,
the next Install points the project at it (`Kit.follow_client`): the other client's measurements
(`client\helm_shift.json`, `geoset_map.json`) move to `backups\client-<time>\` with copies of its
`bp.json` and `scan.json`, and the kit scans, selects and measures again for this client. Each
install record names the client it went into (`data`), and Undo puts its files back there.

The x64 client can also draw retail's items from retail's own tables and files: that is the second
install route, *retail direct*, below.

## Retail direct

Settings' `route` (`workbench.json`; "" = the kit, "direct") picks what Install runs:
`Workbench.runner()` is the kit or `direct.Direct`, and the Backport page, the history
(`basket-history-direct.json`), what's in the game, take-outs and Undo follow it - each route keeps
its own installs. `retailpack` is the pure part (the client's rules, the walk, the tables, the SQL,
the patch writer), `direct` the job.

What the x64 client reads (wowdecomp-dx11-next, read-only reference): `WXL/modules/db2/items`
loads retail's `item`, `itemappearance`, `itemmodifiedappearance`, `itemdisplayinfo`,
`itemdisplayinfomaterialres`, `itemdisplayinfomodelmatres`, `modelfiledata`, `texturefiledata`,
`componentmodelfiledata`, `componenttexturefiledata`, `helmetgeosetdata` and `helmetanimscaling`
(`RetailSchemas.hpp`; `retailpack.TABLES` holds their layout hashes - 12.1.5's) and turns each
FileDataID into a path with `DBFilesClient\ModelFilePath.db2` / `TextureFilePath.db2`
(`FdidCompat.cpp`; WDC1, inline id + string offset - patch-R's, written by retroport-native's
`x64_retail_pack.py`). A display id its ItemDisplayInfo.dbc has is drawn from that row instead
(`ItemGraphOwnsDisplay`). Item rows missing from Item.dbc come from retail's item.db2 with the
item's default look (modifier 0 first, then OrderIndex); the server's item query wins for the
display (`VisibleItem_C::GetDisplayID`). `modules/equipment/EquipmentAttachments.cpp` draws the
models: it opens `Item\ObjectComponents\<folder>\<name>.m2` (folder = the one after
objectcomponents, name = after `collections\` or the file's name), a model's own texture
(ModelMaterialResourcesID, the first TextureFileData row) by its name *in the model's folder*, and
material textures (body layers, ModelMatRes) at their full paths.

Install (`Direct.go`):

1. **read** - the twelve tables from the local install (`Source.raw_table`, encrypted sections
   zeroed), each layout checked; eight read into rows.
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
   in collections\). A display the client's ItemDisplayInfo.dbc has is reported.
3. **pack** - `out\patch-Q.MPQ` (`retailpack.patch_for`: patch-T for a client without the path-table merge) (stored, written as it goes; an alias shares its file's block): a
   manifest (`retroport\direct.json` - Install replaces only a patch that has one), the tables,
   the path tables (the client's, read with this route's own patches set aside, plus the new rows), the files, the
   aliases. Then `check`: every path `retailpack.lookups` says the client opens, looked for in the
   patch and the client. And `out\view-models.txt`: each model with the textures it wears - an
   item's own (type 2) and its ItemDisplayInfoModelMatRes types (3, 4, 24: `Graph.worn`), a mount's
   three skins - in the list the x64 client's login-screen viewer reads
   (retroport-native `tools\x64_model_view.py --list`: the build's look checked without logging in).
4. **sql** - `out\sql\retail-direct-items.sql`: `DELETE ... WHERE (entry, displayid) IN` the pairs
   this route ever wrote (`ids.json` `owned`), then one INSERT in the kit's format (so
   `itemstats.kit_items` reads it) - the label of a non-default look ("Mythic") as its description
   - then `itemstats.updates` for each piece (no item sets: those need ItemSet.dbc rows).
5. **install** - `Data\patch-Q.MPQ` (an earlier own patch-T moved into the backup) replaced (removed first: hard links), the old one in
   `direct\backups\<time>\client\`, the record in `install.json` (the kit's format), Cache cleared.

`out\build.json` records what was built (looks, build, client, steps, entries, a summary); the
page calls it built while those match the basket. Retail's ItemVisual glows aren't shipped (the
client sets them to 0 for retail rows).

## Mounts

`mounts` is the pure part (the catalog, 3.3.5's rules, the client rows, the SQL), `mountpack` the
job both routes call (`build`), the kit route's patch (`write_patch`, `place`) and the staleness
check (`stale`).

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
frequency). The page's preview draws the model with textures 11/12/13 and the geosets the packed data shows.

**Families** (`mounts.model_families`, worked out when the catalog loads - nothing cached): the
mounts whose first display has one model, rooted at the oldest (lowest Mount id); a mount with no
model is alone. `MountCatalog.search` gives one card per family - its oldest mount that matches -
with `root` and `versions`; `detail` gives `family`, each with its chip label (`mounts.version_labels`:
the name without the words every version's has, else the whole name; a repeat numbered).
Placeholders ("[PH] ...") count only with the page's test-mounts box, or when it is the mount opened.

**A basket entry** is `{"kind": "mount", "source", "id", "display", "mount_kind", ...}`;
`catalog.plan_basket` gives it no looks and a `mount` field, `kit.basket_args` ignores it and
`Workbench.kit_basket` leaves it out (the kit never selects a mount).

**3.3.5 rows** (`mounts.client_tables`, from the client as the route's patch finds it):

- Spell - a copy of 23229 (ground) or 32242 (flying) with the mount's id, EffectMiscValue_1 = its
  creature, its icon (a SpellIcon row of the retail icon, or the stock row of the same name), name
  and description; SkillLineAbility - a copy of the stock row in skill line 777;
- CreatureDisplayInfo - model data id, retail scale and alpha, TextureVariation names, packed
  CreatureGeosetData (nibble per group 1-8: `(GeosetIndex + 1) * 100 + GeosetValue`, 0 none);
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
  that - a higher one would write past it), else the template's. The converter keeps the model's
  events ($FL0/$FR0 footfalls, $FSD, $WNG, $FD1-5), which play those columns;
- ItemDisplayInfo - the item's own row (`mounts.with_item_displays`): the stock mount item's
  (ITEM_ICONS - its GroupSoundIndex) showing retail's icon. The icon file goes in the patch unless
  the client under it has one of that name.

One number per mount from 250000 is its spell, display, model data, sound data, SkillLineAbility row
and creature (`mounts.allocate`: the first no client table and no other mount uses); its item entry
from 990000, reserved in `item-ids.json` so a kit project never gives it to an item. `<data>\mount-ids.json`
also keeps the item's ItemDisplayInfo id (`display`), SpellIcon ids, SoundEntries ids per retail kit
(`sounds`), FootstepTerrainLookup ids per footstep and terrain (`footsteps`) - a row with one of them
in the base is an earlier install's and goes (`mounts.owned_ids`) - and `owned`, the (id, marker)
pairs the SQL wrote, deleted first next time.

**SQL** (`mounts.mount_sql`): the rows read back from the client tables just made - spell_dbc (all
234 columns in Spell.dbc's order; the schema's float columns as floats), creaturedisplayinfo_dbc,
creaturemodeldata_dbc - then creature_template (+ creature_template_model, creature_model_info) and
item_template (class 15/5, spell 483 then the mount spell with trigger 6, Riding 150/300, its own
ItemDisplayInfo row - or a stock mount item's when retail gives it no icon). The server reads no
sound or item display rows (AzerothCore loads ItemDisplayInfo but never looks a display up). Kit route:
`<work>\out\sql\retroport-mounts.sql` (the install record's `mounts_sql`, listed by `Kit.sql_files`);
direct: `<data>\direct\out\sql\retail-direct-mounts.sql`.

**Files**: models and skins under `creature\retroport\` (`mounts.relocate`); sounds at retail's
listfile paths (`.ogg`: 3.3.5 has none) - a nameless one `sound\retroport\<fdid>.ogg` - as FileDataIDs
both routes copy (direct marks them "sound": no path-table rows). Kit route: `converted` runs
`convert.engine.convert_with_wotlkconv` from the CASC install (kept in
`<data>\mounts\converted\<build>-v1\<fdid>\`), then bakes each type-0 texture's relocated path into the
MD20 and converts the textures, the display's skins and a new icon with `eprows.client_blp`. Direct:
the model and everything it names (SFID/TXID/AFID/BFID/SKID/SKPD/PFID/RPID/GPID, recursively) at their
relocated listfile paths as path-table rows - the x64 client finds skins, animations and skeletons by
name beside the model - and the display's skins under their TextureVariation names.

**Patches**: the kit route writes `<data>\mounts\kit\patch-M.MPQ` (manifest `retroport\mounts.json`)
before the kit runs; the kit's `installed` hook (`Workbench._mounts_installed`) places it - or takes the
old one out when the game has no mounts - in the install's record, so the kit's Undo covers it; a
basket of mounts only skips the kit (`_mounts_alone` writes the record itself). The direct route adds
the files, path rows and tables to its `patch-T.MPQ`. `build` stops when an archive above the patch
(by name rank, whether or not the patch is there yet) holds one of `mounts.TABLES`. The status
compares the basket's mounts with the last install's `mounts`, and `mountpack.stale` names a lower
archive holding a table that is newer than the installed patch (a race package installed again; the
item display table only while no archive above holds one).

**The items' rows** (`mountpack.place_item_rows`, after the route's patches are in): the patch
carries ItemDisplayInfo too, but the item kit's patch holds it above (both test clients: patch-Y).
The rows go into the archive the client reads it from when that outranks the patch - a packed
`Data\patch-<x>.MPQ` (a folder or another archive can't take them: `build` then gives the items a
stock icon) - with every row of the registry's display ids replaced. The archive is backed up into the
install's record unless the same install placed it (the kit's own record covers it), then copied,
the copy given the table (`mpq.add_files`) and put in place of the original (a hard link's other
client keeps its own). The record keeps `item_rows` (archive -> size and mtime) and `item_ids`:
`mountpack.item_rows_gone` tells the page when the archive changed since and lost the rows, and the
direct route's Undo leaves an archive that changed since as it is. Kit route: `Workbench._mounts_installed`
(after the item sets); direct: `Direct.install`.

## Client check (0.5.0)

`Direct.client_check` writes the installed patch's `.m2` list to `<work>\client-check\models.txt` and runs
`WowClient64.exe -windowed` with `WXL_RETAIL_MODEL_CHECK=<that folder>`, `WXL_NATIVE_RETAIL_MODELS=1` and
`WXL_LOG_FLUSH=1` (the client's model check mode, retroport-native `x64_native_model_check.py`): at the login
screen it reads each model natively and through the converter, writes `check.txt` (`<model>\t<same|DIFFERS|
other: not read>`) and exits. The client's `Logs\*.log` are copied aside first and put back; new
`Errors\*Crash.txt` files fail the job. The result goes into `out\build.json` (`summary.client_check`) for the page.
`Direct.check_shadowed` (after each install) lists the patch's files `ClientData(top=patch).shadowed_by` finds
in an archive above it; the path tables are left out where `retailpack.merges_path_tables` (the exe holds
FdidCompat.cpp's log line `MERGE_MARK`).
