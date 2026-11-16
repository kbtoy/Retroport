"""The server pack: what a server needs before Ultra WoW players can see what Install put in.

One folder (and a zip of it) in the install's work folder, made again each time it's asked for:

- ``sql\\`` - the SQL of the last Install (items and sets, mounts), in the order to apply it;
- ``azerothcore\\ultra-wow-opcodes.patch`` - Ultra WoW sends opcodes of its own (0x521-0x556) once a
  player is in the world, and a stock AzerothCore disconnects any client that sends an opcode it
  doesn't know; the patch gives them table entries (``server_files``, cut from the user's own core,
  commit 18d5b54fcf, checked against a clean copy of the two files);
- ``README.txt`` - applying both, Warden, and what each kind of player client sees.

The Workbench never runs SQL nor touches a server: the pack is for the server's owner to apply.
"""
from __future__ import annotations

import os
import shutil
import time
import zipfile

from . import clients as CL
from . import edition

PACK = "server-pack"                       # in the install's work folder
ZIP = "Retroport-server-pack.zip"          # beside it
PATCH = "ultra-wow-opcodes.patch"
FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_files")


def _slash(path: str) -> str:
    return path.replace("\\", "/")


def readme(folder: str, sql: list[str], client: str, patch: str, folder_patch: bool, version: str) -> str:
    """The pack's README.txt; ``sql`` = the pack's own SQL paths, ``patch`` = the client patch Install made."""
    here, other = CL.WANT, "x86" if CL.WANT == "x64" else "x64"
    exe = {"x64": "WowClient64.exe", "x86": "WowClient32.exe"}
    opcode_patch = os.path.join(folder, "azerothcore", PATCH)
    lines = [
        "RETROPORT SERVER PACK",
        f"Made by {edition.NAME} {version} on {time.strftime('%Y-%m-%d %H:%M')}.",
        "",
        "What is here",
        "  sql\\                                    the SQL from your last Install, for your world database",
        f"  azerothcore\\{PATCH}       the change AzerothCore needs before Ultra WoW can play on it",
        "  README.txt                              this file",
        "",
        "1. Apply the SQL",
    ]
    if sql:
        lines += ["   Apply each file to your world database, in this order - for example in the MySQL client:",
                  "       USE acore_world;"]
        lines += [f"       SOURCE {_slash(p)};" for p in sql]
        lines += ["   (These are paths on the PC that made the pack: use the folder you unpack it to.) Each file first",
                  "   removes the rows earlier installs made, then adds the current ones, so apply only the newest",
                  "   pack's. Restart the worldserver afterwards."]
    else:
        lines += ["   None yet: no Install has written SQL. Install, then make the pack again."]
    lines += [
        "",
        "2. Patch AzerothCore for Ultra WoW (once)",
        "   Ultra WoW - x64 and 32-bit alike - sends opcodes of its own as soon as a player is in the world",
        "   (spell charges, the wardrobe, pings, Paragon and more). A stock AzerothCore closes the connection",
        "   on any opcode it doesn't know, so those players are disconnected right away. The patch gives those",
        "   opcodes (0x521-0x556) entries in the core's opcode table; with nothing to handle them they are",
        "   dropped quietly. It changes two files, Opcodes.h and Opcodes.cpp, and nothing else. Other clients",
        "   never send these opcodes, so it changes nothing for them.",
        "",
        "   In your AzerothCore source folder (the one with src\\ and modules\\):",
        f'       git apply --check "{opcode_patch}"',
        f'       git apply "{opcode_patch}"',
        "   then build and restart the worldserver. --check prints nothing when the patch fits. If it doesn't,",
        "   your core's two opcode files have changed since the patch was made: the patch file shows each line",
        "   to add by hand. Another core (TrinityCore, ...) needs the same opcodes in its own opcode table.",
        "",
        "   Without the patch, each Ultra WoW player can switch those opcodes off instead, with this line in",
        "   WTF\\Config.wtf in their game folder:",
        '       SET wxlCustomOpcodes "0"',
        "   They can then play on an unpatched server, without the wardrobe, spell charges, pings, Paragon and",
        "   the Mythic+ window.",
        "",
        "3. Warden",
        "   Ultra WoW doesn't answer Warden's scans, and AzerothCore disconnects a client that hasn't answered",
        "   after Warden.ClientResponseDelay (600 seconds). In worldserver.conf, either",
        "       Warden.Enabled = 0",
        "   or, to keep Warden for players on Blizzard's Wow.exe,",
        "       Warden.ClientResponseDelay = 0",
        "   (then no client is disconnected for not answering - a cheat that stays silent isn't either).",
        "",
        "4. Your players' clients",
        f"   {CL.ULTRA[here]} ({exe[here]})",
        "       Sees everything Install put in. Each player needs the same client patch in their Data folder:",
        f"       {os.path.join(client, 'Data', patch) if client else os.path.join('Data', patch)}"
        + (" (a folder there: copy the whole folder)." if folder_patch else "."),
        f"   {CL.ULTRA[other]} ({exe[other]})",
        f"       Has its own Workbench, {CL.WORKBENCH[other]}, and plays on a server of its own: two",
        "       Workbenches' SQL on one server would undo each other.",
        "   A plain wowdecomp build, or Blizzard's Wow.exe (with or without WarcraftXL)",
        "       Can't read retail's own files as Install writes them: the items exist for these players, but",
        "       show with a question-mark icon and no model, and the mounts don't show. Ultra WoW shows them.",
        "",
        "   Items, sets, mounts and colourways from the Workbench need no server module - only the SQL above.",
        "   Ultra WoW's other features (the wardrobe, Paragon, saved retail looks, loot beams) each need a",
        "   server module of their own; without it that feature does nothing, and the game plays on.",
        "",
        f"azerothcore\\{PATCH} changes AzerothCore's code, so it is under AzerothCore's",
        "licence: the GNU General Public License, version 2.",
        "",
    ]
    return "\r\n".join(lines)


def build(work: str, sql: list[str], client: str, patch: str, folder_patch: bool, version: str) -> dict:
    """Make the pack in ``work`` (the previous one replaced): {folder, zip, sql (the pack's SQL paths)}."""
    folder = os.path.join(work, PACK)
    fresh = folder + ".new"
    shutil.rmtree(fresh, ignore_errors=True)
    os.makedirs(os.path.join(fresh, "sql"))
    os.makedirs(os.path.join(fresh, "azerothcore"))
    shutil.copy2(os.path.join(FILES, PATCH), os.path.join(fresh, "azerothcore", PATCH))
    names = []
    for i, src in enumerate(sql, 1):
        name = f"{i}-{os.path.basename(src)}"
        shutil.copy2(src, os.path.join(fresh, "sql", name))
        names.append(name)
    sql_paths = [os.path.join(folder, "sql", n) for n in names]
    with open(os.path.join(fresh, "README.txt"), "w", encoding="utf-8", newline="") as fh:
        fh.write(readme(folder, sql_paths, client, patch, folder_patch, version))
    shutil.rmtree(folder, ignore_errors=True)
    if os.path.exists(folder):
        shutil.rmtree(fresh, ignore_errors=True)
        raise RuntimeError(f"the last server pack in {folder} is in use - close its files and make it again")
    os.replace(fresh, folder)
    archive = os.path.join(work, ZIP)
    with zipfile.ZipFile(archive + ".new", "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(folder):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.join("Retroport server pack", os.path.relpath(full, folder)))
    os.replace(archive + ".new", archive)
    return {"folder": folder, "zip": archive, "sql": sql_paths}
