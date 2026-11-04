# Retroport Workbench

Browse every retail World of Warcraft item and transmog set in 3D, pick the ones you want, and
backport them to your **3.3.5a (Wrath of the Lich King, 12340)** client and your **AzerothCore**
server - in one click, with a backup of everything it changes and an Undo.

## What it does

- **Browse** all of retail's items (about 99,000) and transmog sets (about 5,000). Search by name or
  id (the box at the start of the filters); filter by slot, armor or weapon type, expansion, quality
  and class. A set comes as one card
  with all its versions (Normal, Heroic, Mythic, a PvP season's Gladiator and Elite - and the colours
  of sets retail lists one per colour, like the 18 Sweatsuits), and items your client already has
  are marked.
- **See it in 3D** before you port it, animated, with its glows and moving textures: an item on its
  own, a set dressed on a character of any race your client plays (male or female), weapons and
  other one-kind sets one at a time with ◀ ▶. Every version is a click away under the preview.
- **Mounts** - all of retail's mounts (about 1,700), ground and flying, each in 3D with its looks;
  the mounts of one model in other skins are one card, every version a click away under the preview
  like a set's; put them in the basket like items. In game each is a mount spell like the epic ones, the creature
  you ride with retail's sounds and the item that teaches it, with retail's icon (see [Mounts](#mounts)).
- **Collect** what you like in the **Basket** - what the next install adds to your game. It shows
  every look each entry brings and the entries that overlap, so a mistake is easy to spot and remove
  (with Undo). Below it: what's **in your game** from earlier installs (every install keeps it; *take
  out* removes it at the next one), and **History** - your last five installs (and undos), each with
  *Put back in the basket*.
- **Give them stats** in **Stats** - every piece in the basket (to change something in your game, put
  it back in the basket from the History): item level, required
  level, quality, binding and armor type for every piece; armor type, the role its stats are for,
  which classes may wear it, stats, armor, weapon damage and speed, sockets and socket bonus,
  durability, price and *Unique* piece by piece - its in-game tooltip, and the piece in 3D under it,
  show the result as you go. *Fill in* uses WotLK's own rules (its stat budget for the item level and
  slot, split the way real WotLK items of the role split it, with armor, damage and durability as
  real WotLK items have them), or copy any real WotLK item's numbers. **Item sets** with set bonuses too:
  the bonuses come from your client's own item sets, with their in-game text.
- **Install** with one button, on the **Backport** page. It converts the basket for your client and
  adds it to what's in your game, installs the patch, adds the
  new items to your server's `Item.dbc` and `ItemDisplayInfo.dbc`, backs up everything it replaces,
  and can undo the whole install. It never touches your database: it shows the item SQL for you to
  apply.

## Download and run

1. Download `Retroport-Workbench-<version>-win64.zip` from the [Releases](../../releases) page.
2. Unpack the **whole** folder anywhere. Keep `runtime\` and `app\` next to the exe.
3. Run **Retroport Workbench.exe**. It opens in a window of its own; closing the window closes it.
   Windows may warn that the program is from an unknown publisher (it isn't code-signed): choose
   *More info*, then *Run anyway*.
4. The first time, **Settings** opens. Choose your 3.3.5a client folder (the one with `Wow.exe`), and
   optionally your server's dbc folder. That's all the setup there is.
5. Find items and sets, add them with **+**, look them over in **Basket**, give them stats in
   **Stats**, then **Backport > Install**. When it's done: apply the item SQL it shows to your world database, restart the
   worldserver, and log in.

## What you need

- **Windows 10 or 11.** The app's window is Microsoft Edge's app mode (Edge comes with Windows).
- **The internet.** Retail's items, models and textures come from [wago.tools](https://wago.tools).
  The first Install also downloads the two programs that do the conversion from their authors'
  GitHub pages (see [Credits](#credits)).
- **A 3.3.5a client** - a stock one works: it shows ported weapons, shields, helms, shoulders and
  every other slot's armor drawn on the body. *Optional:* the extra 3D pieces modern armor adds -
  skirts, collars, hoods, boot shells, belt buckles, 3D capes - need
  [WarcraftXL](https://github.com/WarcraftXL/wxl-core) and
  [Equip Plus](https://github.com/TheDaveCalaz/wxl-equip-plus) in your client. Install adds them when
  your client has Equip Plus, and leaves them out when it doesn't (Settings can turn them on or off).
  The x64 3.3.5 client (`WowClient64.exe`) works too, and draws those pieces itself - or takes
  retail's own items as they are (see [Retail direct](#retail-direct-the-x64-client)).
- **Optionally, an AzerothCore server** whose dbc folder you point it at, so the new items exist on
  the server too.

## Settings

- **3.3.5a client folder** and **server dbc folder** - each *Browse...* opens Windows' folder picker,
  and each field says what it found there.
- **Where the items come from** - *wago.tools* (the default; nothing to install) or *your own retail
  install* (faster, and works while wago.tools is down; it needs the
  [WoWDBDefs](https://github.com/wowdev/WoWDBDefs) definitions folder and the
  [community listfile](https://github.com/wowdev/wow-listfile)). The bodies the character view
  dresses come from BfA 8.3.7, the same way.
- **How Install puts items in** - the *backport kit* (the default: each look converted for any 3.3.5a
  client) or *retail direct* (retail's own items into the x64 client - see below).
- **Backport kit** - the project folder the conversion works in (a folder of its own: the kit fills
  it with its files). The kit and Equip Plus's tools are always the app's own copies, downloaded by
  the first Install at the versions this release is tested with - the same for everyone. Equip
  Plus's 3D pieces (when your client has Equip Plus, always, or never), and its live physics and
  better-fit options in your client.

Everything the app keeps is in your user folder:

| | |
|---|---|
| `%USERPROFILE%\.retroport\workbench.json` | your settings |
| `%USERPROFILE%\.retroport\workbench\` | the cache, your basket, the conversion project, the log (`workbench.log`) |

Everything it downloads is kept, so what you've already looked at still opens while wago.tools is
down.

## How Install works

1. The first time, it downloads the conversion kit and Equip Plus's tools.
2. It converts what's in your game and the basket - only what changed since the last build. Each
   install ticks its steps off as it goes, from a clear list, and a step that fails stops it before
   anything is installed (the log says why). Measuring how helms sit on your client's bodies (a few
   minutes, once per client) waits until something worn on the body is in the basket.
3. It applies the Stats step: the items' stats into the item SQL, a changed armor type into the
   client's and server's item tables, the item sets into their ItemSet tables.
4. It installs: the patch (and Equip Plus's pieces, when your client has Equip Plus) into your
   client's `Data` folder, the new rows into your server's DBCs, and clears the client's cache.
   Everything it replaces is backed up first.
5. You apply the item SQL it shows (`retroport-items.sql`: a `SOURCE` line with a copy button) to
   your world database, and restart the worldserver.

When it worked, the basket empties - what it held is in your game now - and the install goes into
the History (a failed one too, with the step it stopped at).

**Undo last install** puts back everything that install replaced and removes what it added (its
basket stays in the History).

**Coming from the Backport Helper?** The Workbench uses the same conversion project, and an Install
builds exactly what's in the basket. Looks the project built before - with the Backport Helper -
show at the top of the Basket: bring them into the basket to keep them in your game (Install waits
until you've chosen). They're rebuilt as they were, with the same kit and Equip Plus steps.

**Live physics.** Plumes, ribbons and chains can swing as in retail: the kit ports retail's own
Domino physics engine, and Equip Plus 1.3.0 runs it in the client (experimental, off by default).
Install writes each piece's physics data with Equip Plus 1.3.0's tools, and Settings has the switch
(*Live physics*, saved in your client's `WXLExtendedEquipment.ini` - also in Equip Plus's F9 panel in
game) next to its *better fit* options. Your client needs Equip Plus 1.3.0 or newer.

## Retail direct (the x64 client)

The x64 3.3.5 client draws retail's items itself, from retail's own tables and files. With
Settings > *How Install puts items in* > **Retail direct**, Install converts nothing:

1. It reads retail's item tables from your own retail install (Settings > *Where the items come
   from* > *My own install*) and checks each is the layout the client reads.
2. It works out every file the basket's looks name - the models for every race and sex, their
   skins and textures, the body textures, the icons - and puts them, the item tables and the
   client's file-id tables (with the new files added) into `Data\patch-Q.MPQ` (`patch-T.MPQ` in an
   x64 client built before 2026-11-03, which reads only the topmost file-id tables). Where the client
   looks for a file somewhere else than retail keeps it (a helm's texture kept with its set's other
   pieces), the patch has it there too; a check then looks up every file the client will open, as
   the client does.
3. It writes the item SQL (`retail-direct-items.sql` - a `SOURCE` line with a copy button): one
   row per look, its display retail's own. An item's default look keeps its retail item id; its
   other looks get (version + 1) x 1,000,000 + the id - the Mythic skull of the Damned Necrolyte
   is 4271546. The SQL only replaces rows retail direct made itself: an id your database already
   uses for something else stops it with "Duplicate entry".
4. It installs the patch (the one it replaces is backed up; Undo puts it back) and clears the
   client's cache. The server's dbc folder is left alone. It never replaces another tool's patch,
   moves an earlier install of its own at `patch-T.MPQ` to `patch-Q.MPQ`, and then names any file of
   the patch that an archive above it hides (a whole table another tool put higher up).
5. **Check in the client** (after an install) opens the x64 client in its check mode - no login, a
   window that closes by itself, about a second a model - which reads every model the patch holds
   the way play reads them, natively, and compares each with its converted form. The page then says
   how many read as retail has them, how many draw differently and which the client refuses (play
   converts those on the spot - a short freeze - or leaves them out); the log names each.

There are no measurements, audit or Equip Plus pieces - nothing is converted - and the Stats step
applies as usual (its item sets are the kit's only). These items show retail's looks only in the
x64 client: a 32-bit client shows them without a model. The x64 client reads the file-id tables of
every archive (2026-11-03), so other packs' new files - the races', the undead's - and this patch's
all resolve; an older client reads only the topmost copy (install again after `patch-R.MPQ` is made
again, there). Retail direct keeps its own
install, history and Undo (in `%USERPROFILE%\.retroport\workbench\direct`), apart from the kit's.

## Mounts

The **Mounts** page lists retail's mounts with their source (drop, vendor, achievement...) and shows
each one in 3D - a mount with several looks has a chip for each, and the one picked is the one you
ride. Mounts that are one model in other skins - the ten riding cranes, the drakes, the Qiraji
battle tanks - are one card ("10 versions"), like a set's versions: a chip under the preview for
each (Azure, Golden, Regal...), and **Add all 10 versions** puts every one in the basket. Each
version is a mount of its own in game. In the basket a mount is an entry of its own; Install makes it
with either way in:

- **Backport kit**: each model converted for any 3.3.5a client (its skins, animations and textures
  with it), in a patch of its own, `Data\patch-M.MPQ`.
- **Retail direct**: retail's own models (the x64 client draws them as they are), in the route's
  patch (`patch-Q.MPQ`).

Either way every model and skin goes under `Creature\Retroport\` - an old horse or drake keeps its
3.3.5 model for the NPCs that use it - and each mount becomes:

- a **spell** like the epic mounts (ground 100%; flying 280% where flying is allowed, 100% on the
  ground) with retail's icon, in the spellbook's Mounts tab;
- the **creature** you sit on (`creature_template`, its display and model) with **retail's sounds**:
  its footsteps on each kind of ground, wing flaps, jumps, snorts and calls - retail's own `.ogg`
  files at retail's paths (3.3.5 plays Ogg; it never had those files, so nothing of yours is
  replaced). While you ride, you sound like the mount;
- the **item that teaches it**, with retail's name and **retail's icon** in your bags: Riding 150 and
  level 40 for a ground mount, Riding 300 and level 70 for a flying one.

The client's tables are in the patch; the server's rows are in the SQL Install shows
(`retroport-mounts.sql` / `retail-direct-mounts.sql`: AzerothCore's `spell_dbc`,
`creaturedisplayinfo_dbc`, `creaturemodeldata_dbc`, `creature_template`, `item_template`). It ends
with `.learn` and `.additem` lines for a GM. A mount keeps its spell, creature and item numbers from
install to install (`%USERPROFILE%\.retroport\workbench\mount-ids.json`), so players keep the
mounts they learned. Mounts are made from your own retail install (Settings > *Where the items come
from* > *My own install*).

The mounts' patch holds whole copies of the client's spell, creature and sound tables, made from
what's under it. If another patch under it changes them afterwards - a race package installed again
into `patch-H.MPQ` - the Backport page says so: Install again, or that patch's new rows stay hidden.

The items' bag icons are rows of the client's item display table, which the item kit's own patch
holds above the mounts' (`patch-Y.MPQ`, say). So Install adds those rows to that patch - as the
Stats step adds item sets - backing it up first when the same install didn't just put it there;
Undo puts it back. If another install replaces that patch later, the Backport page says the icons
went with it: Install again.

## Troubleshooting

- **The window doesn't appear.** Look at `%USERPROFILE%\.retroport\workbench\workbench.log`. Without
  Edge, the app opens in your default browser instead.
- **"Port 8335 is taken"** - another program uses the port the app listens on (only on your own
  machine, `127.0.0.1`). Close it and start the app again.
- **The first look at things is slow** - models and textures are being downloaded; they're kept
  for next time.
- **wago.tools is down** - Settings > *Where the items come from* > *My own install*.
- **Install stopped** - open the log under the Install button; nothing was installed by that run.
  Close World of Warcraft before installing: it holds the files Install replaces.
- **Install stopped at prove-gates: "M8 motion MISSED <- the gate is broken"** - a false alarm in
  0.1.0 (the kit's self-test planted a fault in a part of a model the patch doesn't ship); 0.2.0
  plants it where the check can see it. Update the app and Install again.
- **The kit's audit stopped the install** - the Backport page names each piece it stopped on, with
  *Leave this piece out*: the rest of its set installs, and the Basket page can put it back. A helm
  that only sits a little off on some bodies (often a race your client added) doesn't stop the
  install: it's listed as a warning - look at its picture (*preview pictures folder*: the kit draws
  one of each piece into the project's `sheets` folder).
- **"Retail uses something the kit hasn't seen before"** - new retail technology: the kit learns it
  for your project and goes on; the audit still checks every file it makes.
- **Which copy of the app is running?** - the version is next to the name at the top (hover it for
  the folder it runs from). Starting another copy while one runs asks to replace it.
- **The item SQL fails** - it's written for AzerothCore's world database. Install again after
  updating: older versions wrote a `StatsCount` column AzerothCore doesn't have, and a sell price can
  no longer go past what the column holds (429,496 gold).
- **Items ported before show a red question mark** - before 0.3.0 each install replaced what the
  last one put in, so earlier baskets' items lost their looks in the client while the server and
  your bags kept them; and a new project could give their numbers to other items. Put those sets in
  the basket again and Install: the Workbench now remembers every number any of your projects gave
  and gives a returning look its old numbers, so the items you carry show again.
- **A helm shows its mask but not its hood** (the Damned Necrolyte skull) - earlier versions left out
  a helm's part of its set's shared body model. Update, put the set in the basket again and Install
  (with Equip Plus in your client, or the x64 client).
- **Switched to another client** - Settings' client folder is the one Install builds for: the next
  Install reads the new client and measures its bodies again (a few minutes), and Undo always puts
  files back into the client that install went into.
- **Items are level 1 with no stats** - the conversion makes cosmetic copies; give them stats in
  **Stats** and Install again (the Backport page says how many pieces still have none).
- **No 3D preview** - the preview needs WebGL 2; update your graphics driver.
- **A mount's tables are hidden by patch-X** - an archive above the mounts' patch holds the
  client's spell, creature or sound tables, so the mounts' rows would never show; Install stops and
  names it.
- **A mount's item shows a red question mark** - its icon row was in a patch another install
  replaced since (the Backport page says which): Install again.
- **A mount is quieter than in retail** - 3.3.5 plays up to 10 files per sound (retail's footsteps
  have up to 20, the first 10 are kept), and a sound whose files your retail install keeps encrypted
  is left out.
- **A mount stands still or slides** - the converter keeps retail's animations; 3.3.5 plays ids up to
  505 only, and a model whose walk or run uses a newer id doesn't animate there (it still carries you).
- **Retail direct: "this client and retail build don't go together"** - your retail install
  updated and changed an item table's layout; the x64 client reads the one it was built for.
- **Retail direct: "display ... is a row of your client's ItemDisplayInfo.dbc"** - 3.3.5 or the
  kit already uses that number, and the client draws its row instead of retail's look.

## Building from source

Python 3.11 or newer (3.14 is what it's tested with):

```
git clone https://github.com/kbtoy/Retroport
cd Retroport
python -m pip install -e ".[dev]"
python -m pytest -q tests

python -m retroport.cli workbench                      # run it in a console (opens your browser)
python packaging/build_release.py --launcher-only      # or: Retroport Workbench.exe next to the code
python packaging/build_release.py                      # the release folder and zip, in dist\
```

A release bundles Python's official embeddable package, the dependencies and the code, and checks
that it starts before it's zipped. Pushing a version tag (`v0.2.0`) builds it on GitHub and attaches
the zip to that release.

The Workbench's code is `retroport/workbench/` (the page in `static/`), its game-file readers are
`wotlkconv/` (an unchanged copy of the Converter, see below), and how it all works is in
[docs/workbench-internals.md](docs/workbench-internals.md). The rest of `retroport/` is shared code and
older command-line tools ([docs/command-line-tools.md](docs/command-line-tools.md)).

## Credits

Retroport Workbench is a front end to other people's work:

- **[wow-retail-backport](https://github.com/Kirazul/wow-retail-backport)** by **Kirazul** - the kit
  that converts retail items for 3.3.5a: everything Install builds.
- **[Equip Plus](https://github.com/TheDaveCalaz/wxl-equip-plus)** by **TheDaveCalaz** - the 3D armor
  pieces, and the tools that prepare them and merge the server's DBCs.
- **[WarcraftXL](https://github.com/WarcraftXL/wxl-core)** - the client framework Equip Plus runs on.
- **[wotlkconv (Converter)](https://github.com/Bar3b0n3s/Converter)** by the Converter contributors -
  the readers for the game's files.
- **[wago.tools](https://wago.tools)** - the game data; **[wowdev](https://wowdev.wiki)** -
  WoWDBDefs, the community listfile and the file-format documentation;
  **[WoW Blender Studio](https://gitlab.com/skarnproject/blender-wow-studio)** by **Skarn** - the
  shader tables the 3D preview follows; **[Conjure](https://github.com/TheDaveCalaz/Conjure)** by
  **TheDaveCalaz** - code retroport adapts.

The kit and Equip Plus are downloaded from their authors on first use and never bundled. The full
list, with every bundled library and its license, is [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

MIT - see [LICENSE](LICENSE): use it, change it, share it, sell it, as you like. A few files in this
repository are under other terms; [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) says which.

Retroport Workbench is a fan project, not affiliated with or endorsed by Blizzard Entertainment. It
ships no Blizzard art, models or game data: they're read at run time from wago.tools or your own
installs, for your own use. World of Warcraft and its assets are trademarks and copyright of
Blizzard Entertainment.
