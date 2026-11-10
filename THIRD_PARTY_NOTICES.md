# Credits and third-party notices

Retroport Workbench stands on other people's work. Thank you to everyone below.

## Licenses in this repository

- **Retroport Workbench and the rest of retroport** (everything not listed otherwise) - MIT, see
  [LICENSE](LICENSE).
- **The WarcraftXL client plugins** in `native/wxl-*` - GPL-3.0-or-later (they build against
  WarcraftXL's GPL-3.0 headers); the license text is [native/COPYING](native/COPYING).
- **The glue screens** in `retroport/glue/ui` (`CharacterCreate` and `CharacterSelect`, `.lua` and
  `.xml`) are modified from Blizzard Entertainment's own 3.3.5a and Battle for Azeroth UI code; the
  MIT license covers retroport's changes only, the rest remains Blizzard's. They belong to the
  repository's command-line race tools (`retroport glue`) and are left out of Workbench releases.

## Code adapted into retroport

Parts of retroport are adapted from **[Conjure](https://github.com/TheDaveCalaz/Conjure)** by TheDaveCalaz
(MIT License). Adapted code is marked in each module docstring:

- `retroport/dbc.py` - WDBC engine, CreatureModelData/DisplayInfo row layouts, TextureVariations
- `retroport/sql.py` - AzerothCore repoint SQL
- `retroport/formats/md20.py` - texture-path baking, animation-table classifier
- `retroport/convert/texbake.py` - in-game path rules
- `retroport/check.py` - multi-LOD vertex-span gate, external .anim checks
- `retroport/safeio.py` - verify-before-success / never-overwrite-input rules

Conjure license:

```
MIT License

Copyright (c) 2026 TheDaveCalaz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```

## Included in this repository

- **[wotlkconv (Converter)](https://github.com/Bar3b0n3s/Converter)** by the Converter contributors
  (MIT) - retroport's conversion engine and its game-file readers (CASC, DB2, M2, BLP). An unchanged
  copy is kept in `wotlkconv/` with its license (`wotlkconv/LICENSE`) and the commit it was copied
  from (`wotlkconv/VENDORED.md`), so retroport never depends on that repository being online.

## Earlier Workbenches

Retroport Workbench 32-bit runs no other tool. Earlier Workbenches (the `main` branch) downloaded and
ran **[wow-retail-backport](https://github.com/Kirazul/wow-retail-backport)** by **Kirazul** (no
license: all rights stay with its author) and the tools of
**[Equip Plus (wxl-equip-plus)](https://github.com/TheDaveCalaz/wxl-equip-plus)** by **TheDaveCalaz**
(GPL-3.0), the extension of **[WarcraftXL](https://github.com/WarcraftXL/wxl-core)** (GPL-3.0) - the
framework retroport's `native/wxl-*` plugins are built on too. Thank you to both.

## Bundled in the release

The release zip carries these, unchanged, each with its license file (in
`runtime\Lib\site-packages\*.dist-info`, `runtime\LICENSE.txt` and `licenses\`):

| Package | License | Home |
|---|---|---|
| wotlkconv (Converter), as above | MIT | https://github.com/Bar3b0n3s/Converter |
| Python 3.14 (embeddable package) | PSF-2.0 | https://www.python.org |
| Pillow | MIT-CMU | https://python-pillow.github.io |
| pydantic, pydantic-core, typing-inspection | MIT | https://github.com/pydantic/pydantic |
| Typer, annotated-doc | MIT | https://github.com/fastapi/typer |
| Rich | MIT | https://github.com/Textualize/rich |
| Click | BSD-3-Clause | https://github.com/pallets/click |
| markdown-it-py, mdurl | MIT | https://github.com/executablebooks/markdown-it-py |
| Pygments | BSD-2-Clause | https://pygments.org |
| shellingham | ISC | https://github.com/sarugaku/shellingham |
| annotated-types | MIT | https://github.com/annotated-types/annotated-types |
| typing-extensions | PSF-2.0 | https://github.com/python/typing_extensions |

## Data and knowledge

- **[wago.tools](https://wago.tools)** - retail and BfA game tables and files by FileDataID, at any
  build: the Workbench's default data source for browsing.
- **[WoWDBDefs](https://github.com/wowdev/WoWDBDefs)** - the DB2 definitions local installs are read with.
- **[wow-listfile](https://github.com/wowdev/wow-listfile)** - the community listfile that names game files.
- **[wowdev.wiki](https://wowdev.wiki)** - the M2, BLP, DB2, CASC and client documentation much of
  retroport is built from.
- **[WoW Blender Studio](https://gitlab.com/skarnproject/blender-wow-studio)** by **Skarn**
  (`io_scene_wmo`) - its M2 shader tables are what the Workbench's 3D viewer follows to combine a
  model's textures; retroport's Blender decimation also reads `.m2` through it.

## Tools the repository's command-line code works with

Not used by Retroport Workbench, but by the other tools in this repository
([docs/command-line-tools.md](docs/command-line-tools.md)). Credit to each tool's original authors.

- **wow.export** by Kruithne (https://github.com/Kruithne/wow.export) - extracting retail models.
- **MultiConverter** - an alternative M2 conversion engine retroport can drive.
- **M2Mod** and its **WoWTools** Blender plugin - the `.m2` <-> `.m2i` round trip for poly reduction.
- **[Blender](https://www.blender.org)** - headless decimation.
- **TrinityCore** - a server the command-line tools' SQL can be written for.

## The server

- **[AzerothCore](https://github.com/azerothcore/azerothcore-wotlk)** - the server the Workbench's
  item SQL is written for; `native/mod-retroport-racials` is an AzerothCore module.

## Not affiliated with Blizzard

retroport is a fan tool, not affiliated with or endorsed by Blizzard Entertainment. It ships no
Blizzard art, models, sounds or game data: those are read at run time from wago.tools or the user's
own installs, for their own use. The one exception is the glue screen UI code noted above. World
of Warcraft and its assets are trademarks and copyright of Blizzard Entertainment.
