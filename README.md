# Retroport Workbench 32-bit

Browse every retail World of Warcraft item, transmog set and mount in 3D, pick the ones you want, and
install them into the **32-bit 3.3.5 client (Ultra WoW 32-bit)** - with the SQL for your
**AzerothCore** server, a backup of everything it changes and an Undo.

Ultra WoW 32-bit is the x64 client's source built as a 32-bit program, so it draws retail's items
itself, from retail's own tables and files, and nothing is converted: Install puts retail's own
models, textures and tables into the client as they are. No other tool is downloaded or run - no
conversion kit, no WarcraftXL or Equip Plus.

This is the `32bit` branch, made from the `x64` branch (the Workbench for Ultra WoW x64); the two
differ in `retroport/workbench/edition.py` and their docs. The `main` branch keeps the earlier
Workbench, which converted items for any 3.3.5a client through the retail backport kit.

**Not usable yet:** the 32-bit client isn't built. Until it is, nothing here has been tried against
it - what it can hold in a 32-bit program's memory may mean this branch has to install less than the
x64 one does.

**Only for a 32-bit client on a server of its own.** This Workbench keeps its own basket, installs and
item SQL. On the server the x64 clients play on, it and the x64 Workbench would undo each other's
items - each install's SQL deletes every item row that Workbench ever made, then inserts its own list.
A 32-bit client on the same server takes what the x64 Workbench installs instead.

## What it does

- **Browse** all of retail's items (about 99,000) and transmog sets (about 5,000). Search by name or
  id (the box at the start of the filters); filter by slot, armor or weapon type, expansion, quality
  and class. A set comes as one card with all its versions (Normal, Heroic, Mythic, a PvP season's
  Gladiator and Elite - and the colours of sets retail lists one per colour, like the 18
  Sweatsuits), and items your client already has are marked.
- **See it in 3D** before you install it, animated, with its glows and moving textures: an item on its
  own, a set dressed on a character of any race your client plays (male or female), weapons and
  other one-kind sets one at a time with ◀ ▶. Every version is a click away under the preview. The
  preview draws each piece by the client's own rules: which sides of a surface show, how its glows
  add up, its particles and ribbon trails, the retail glow models the client hangs on an item, which
  pieces are skinned to the body (a belt's flaps) and which hang on it, and what the client swings
  with physics hanging as it rests (a helm's plumes, a tentacle). A mount shows its state kit: a war
  mount's banner, a spectral mount's ghostly shading, a Void-Scarred mount's scrolling void. Only
  versions a player can wear are listed: retail's locked "VFX unlock" looks and Blizzard's internal
  "[DNT]" sets are left out.
- **Mounts** - all of retail's mounts (about 1,700), ground and flying, each in 3D with its looks;
  the mounts of one model in other skins are one card, every version a click away under the preview
  like a set's; put them in the basket like items. In game each is a mount spell like the epic ones,
  the creature you ride with retail's sounds and the item that teaches it, with retail's icon (see
  [Mounts](#mounts)).
- **Collect** what you like in the **Basket** - what the next install adds to your game. It shows
  every look each entry brings and the entries that overlap, so a mistake is easy to spot and remove
  (with Undo). Below it: what's **in your game** from earlier installs (every install keeps it; *take
  out* removes it at the next one), and **History** - your last five installs (and undos), each with
  *Put back in the basket*.
- **Give them stats** in **Stats** - every piece in the basket (to change something in your game, put
  it back in the basket from the History): item level, required level, quality, binding and armor
  type for every piece; armor type, the role its stats are for, which classes may wear it, stats,
  armor, weapon damage and speed, sockets and socket bonus, durability, price and *Unique* piece by
  piece - its in-game tooltip, and the piece in 3D under it, show the result as you go. *Fill in*
  uses WotLK's own rules (its stat budget for the item level and slot, split the way real WotLK
  items of the role split it, with armor, damage and durability as real WotLK items have them), or
  copy any real WotLK item's numbers. (Item sets can be laid out there, but Install doesn't put them
  in the game yet.)
- **Install** with one button, on the **Install** page: retail's own files for what's in your game
  and the basket go into one patch in your client, backed up first and undone in one click. It
  never touches your database: it shows the SQL for you to apply.

## Download and run

1. Download `Retroport-Workbench-32-bit-<version>-win64.zip` from the [Releases](../../releases) page.
2. Unpack the **whole** folder anywhere. Keep `runtime\` and `app\` next to the exe.
3. Run **Retroport Workbench 32-bit.exe**. It opens in a window of its own; closing the window closes it.
   Windows may warn that the program is from an unknown publisher (it isn't code-signed): choose
   *More info*, then *Run anyway*.
4. The first time, **Settings** opens. Choose the 32-bit client's folder (the one with
   `WowClient32.exe`), and set *Retail items* to your own retail install.
5. Find items, sets and mounts, add them with **+**, look them over in **Basket**, give them stats in
   **Stats**, then **Install**. When it's done: apply the SQL it shows to your world database, restart
   the worldserver, and log in with the 32-bit client.

## What you need

- **Windows 10 or 11.** The app's window is Microsoft Edge's app mode (Edge comes with Windows).
- **The 32-bit 3.3.5 client** (`WowClient32.exe`): Ultra WoW built as a 32-bit program.
- **Your own retail install** (the live game), with the [WoWDBDefs](https://github.com/wowdev/WoWDBDefs)
  definitions folder and the [community listfile](https://github.com/wowdev/wow-listfile): Install
  reads retail's tables and files from there. Browsing works from [wago.tools](https://wago.tools)
  before they're set.
- **An AzerothCore server** for the SQL Install writes (you apply it).

## Settings

- **32-bit client folder** - *Browse...* opens Windows' folder picker, and the field says what it found
  there and where Install will put its patch.
- **Where the items come from** - *wago.tools* or *your own retail install* (what Install needs; it is
  also faster, and works while wago.tools is down). The bodies the character view dresses come from
  BfA 8.3.7, the same way.

Everything the app keeps is in your user folder:

| | |
|---|---|
| `%USERPROFILE%\.retroport\workbench-32bit.json` | your settings |
| `%USERPROFILE%\.retroport\workbench-32bit\` | the cache, your basket, the installs and their backups (`direct\`), the log (`workbench.log`) |

They're its own, apart from the x64 Workbench's (`workbench.json`, `workbench\`), so the two run side by
side and never change each other's basket or installs.

## How Install works

1. It reads retail's item tables from your own retail install and checks each is the layout the
   client reads.
2. It works out every file the basket's looks name - the models for every race and sex, their
   skins and textures, the body textures, the icons - and puts them, the item tables and the
   client's file-id tables (with the new files added) into `Data\patch-Q.MPQ` (`patch-T.MPQ` in a
   client built before 2026-11-03, which reads only the topmost file-id tables). Where the client
   looks for a file somewhere else than retail keeps it (a helm's texture kept with its set's other
   pieces), the patch has it there too; a check then looks up every file the client will open, as
   the client does. The basket's mounts go in the same patch (see [Mounts](#mounts)).
   **Retail item glows** come too: a look whose retail display has an ItemVisual (a weapon's
   flames, a shoulder's sparkles) gets retail's glow tables and every glow model its visual
   attaches, with their skins and textures. The client hangs them on the item's model the way 3.3.5
   hangs an enchant's. A glow file whose retail path holds a 3.3.5 file of the client's own goes
   under a `retroport\` folder instead (`spells\retroport\...`), so 3.3.5's own spells and enchants
   keep theirs. The log says how many glow models the client draws today. The client doesn't yet
   draw an effect retail made for any item (only one made for the weapon's own type), or a spell-kit
   model whose ModelPosition retail sets to -1 (nearly all of them). Those models go in the patch
   anyway, so a client that learns them needs no new patch.
3. It writes the item SQL (`retail-direct-items.sql` - a `SOURCE` line with a copy button): one
   row per look, its display retail's own, with the Stats step's numbers. An item's default look
   keeps its retail item id; its other looks get (version + 1) x 1,000,000 + the id - the Mythic
   skull of the Damned Necrolyte is 4271546. The SQL only replaces rows Install made itself: an id
   your database already uses for something else stops it with "Duplicate entry".
4. It installs the patch (the one it replaces is backed up) and clears the client's cache. The
   server's dbc folder is left alone. It never replaces another tool's patch, moves an earlier
   install of its own at `patch-T.MPQ` to `patch-Q.MPQ`, and then names any file of the patch that an
   archive above it hides (a whole table another tool put higher up).
5. **Check in the client** (after an install) opens the 32-bit client in its check mode - no login, a
   window that closes by itself, about a second a model - which reads every model the patch holds
   the way play reads them and compares each with its converted form. The page then says how many
   read as retail has them, how many draw differently and which the client refuses; the log names
   each.

When it worked, the basket empties - what it held is in your game now - and the install goes into
the History (a failed one too, with the step it stopped at). **Undo last install** puts back the patch
that install replaced and removes what it added. **Build only** (under *Install's steps*) stops before
the install, so you can look at the patch and the SQL first.

These items show retail's looks only in Ultra WoW: Blizzard's own client shows them without a
model. The client reads the file-id tables of every archive, so other packs' new files - the
races', the undead's - and this patch's all resolve.

## Mounts

The **Mounts** page lists retail's mounts with their source (drop, vendor, achievement...) and shows
each one in 3D - a mount with several looks has a chip for each, and the one picked is the one you
ride. Mounts that are one model in other skins - the ten riding cranes, the drakes, the Qiraji
battle tanks - are one card ("10 versions"), like a set's versions: a chip under the preview for
each (Azure, Golden, Regal...), and **Add all 10 versions** puts every one in the basket. Each
version is a mount of its own in game.

Install puts retail's own models in its patch - the client draws them as they are - with retail's
fourth skin, state-kit models, gradients, dissolves, banking angles and particle colours (the Molten
Cormaera's flames take theirs from its display) where a mount has them. Every
model and skin goes under `Creature\Retroport\` - an old horse or drake keeps its 3.3.5 model for the
NPCs that use it - and each mount becomes:

- a **spell** like the epic mounts (ground 100%; flying 280% where flying is allowed, 100% on the
  ground) with retail's icon, in the spellbook's Mounts tab;
- the **creature** you sit on (`creature_template`, its display and model) with **retail's sounds**:
  its footsteps on each kind of ground, wing flaps, jumps, snorts and calls - retail's own `.ogg`
  files at retail's paths (3.3.5 plays Ogg; it never had those files, so nothing of yours is
  replaced). While you ride, you sound like the mount;
- the **item that teaches it**, with retail's name and **retail's icon** in your bags: Riding 150 and
  level 40 for a ground mount, Riding 300 and level 70 for a flying one.

The client's tables are in the patch; the server's rows are in the SQL Install shows
(`retail-direct-mounts.sql`: AzerothCore's `spell_dbc`, `creaturedisplayinfo_dbc`,
`creaturemodeldata_dbc`, `creature_template`, `item_template`). It ends with `.learn` and `.additem`
lines for a GM. A mount keeps its spell, creature and item numbers from install to install
(`%USERPROFILE%\.retroport\workbench\mount-ids.json`), so players keep the mounts they learned.

The patch holds whole copies of the client's spell, creature and sound tables, made from what's
under it. If another patch under it changes them afterwards - a race package installed again into
`patch-H.MPQ` - the Install page says so: Install again, or that patch's new rows stay hidden.

The items' bag icons are rows of the client's item display table. When an older tool's item patch
holds that table above Install's (`patch-Y.MPQ`, say), Install adds those rows to it, backing it up
first; Undo puts it back. If another install replaces that patch later, the Install page says the
icons went with it: Install again.

## Troubleshooting

- **The window doesn't appear.** Look at `%USERPROFILE%\.retroport\workbench\workbench.log`. Without
  Edge, the app opens in your default browser instead.
- **"Port 8337 is taken"** - another program uses the port the app listens on (only on your own
  machine, `127.0.0.1`). Close it and start the app again. (The x64 Workbench uses 8335: both run at once.)
- **The first look at things is slow** - models and textures are being read or downloaded; they're
  kept for next time.
- **wago.tools is down** - Settings > *Where the items come from* > *My own install*.
- **Install stopped** - open the log under the Install button; nothing was installed by that run.
  Close World of Warcraft before installing: it holds the files Install replaces.
- **Which copy of the app is running?** - the version is next to the name at the top (hover it for
  the folder it runs from). Starting another copy while one runs asks to replace it.
- **"this client and retail build don't go together"** - your retail install updated and changed an
  item table's layout; the client reads the one it was built for.
- **"display ... is a row of your client's ItemDisplayInfo.dbc"** - 3.3.5 or an older tool already
  uses that number, and the client draws its row instead of retail's look.
- **Items are level 1 with no stats** - give them stats in **Stats** and Install again (the Install
  page says how many pieces still have none).
- **No 3D preview** - the preview needs WebGL 2; update your graphics driver.
- **A mount's tables are hidden by patch-X** - an archive above Install's patch holds the client's
  spell, creature or sound tables, so the mounts' rows would never show; Install stops and names it.
- **A mount's item shows a red question mark** - its icon row was in a patch another install
  replaced since (the Install page says which): Install again.
- **A mount is quieter than in retail** - 3.3.5 plays up to 10 files per sound (retail's footsteps
  have up to 20, the first 10 are kept), and a sound whose files your retail install keeps encrypted
  is left out.

## Building from source

Python 3.11 or newer (3.14 is what it's tested with):

```
git clone https://github.com/kbtoy/Retroport
cd Retroport
git checkout 32bit
python -m pip install -e ".[dev]"
python -m pytest -q tests

python -m retroport.cli workbench                      # run it in a console (opens your browser)
python packaging/build_release.py --launcher-only      # or: the launcher exe next to the code
python packaging/build_release.py                      # the release folder and zip, in dist\
```

A release bundles Python's official embeddable package, the dependencies and the code, and checks
that it starts before it's zipped.

The Workbench's code is `retroport/workbench/` (the page in `static/`; `edition.py` names this one),
its game-file readers are `wotlkconv/` (an unchanged copy of the Converter, see below), and how it all
works is in [docs/workbench-internals.md](docs/workbench-internals.md). The rest of `retroport/` is
shared code and older command-line tools ([docs/command-line-tools.md](docs/command-line-tools.md)).

## Credits

- **[wotlkconv (Converter)](https://github.com/Bar3b0n3s/Converter)** by the Converter contributors -
  the readers for the game's files.
- **[wago.tools](https://wago.tools)** - the game data; **[wowdev](https://wowdev.wiki)** -
  WoWDBDefs, the community listfile and the file-format documentation;
  **[WoW Blender Studio](https://gitlab.com/skarnproject/blender-wow-studio)** by **Skarn** - the
  shader tables the 3D preview follows; **[Conjure](https://github.com/TheDaveCalaz/Conjure)** by
  **TheDaveCalaz** - code retroport adapts.
- The earlier Workbench (`main`) was a front end to **Kirazul**'s
  [wow-retail-backport](https://github.com/Kirazul/wow-retail-backport) and **TheDaveCalaz**'s
  [Equip Plus](https://github.com/TheDaveCalaz/wxl-equip-plus) - thank you to both.

The full list, with every bundled library and its license, is [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

MIT - see [LICENSE](LICENSE): use it, change it, share it, sell it, as you like. A few files in this
repository are under other terms; [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) says which.

Retroport Workbench is a fan project, not affiliated with or endorsed by Blizzard Entertainment. It
ships no Blizzard art, models or game data: they're read at run time from wago.tools or your own
installs, for your own use. World of Warcraft and its assets are trademarks and copyright of
Blizzard Entertainment.
