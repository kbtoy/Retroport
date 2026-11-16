"""What client a game folder holds - read from its program, not from the program's name.

Players' clients are not all Ultra WoW. A plain wowdecomp build is called WowClient64.exe too, and like
Blizzard's own Wow.exe it reads only 3.3.5 data: retail's own files (its DB2 tables, its models, its
FileDataIDs) can't show in it, whatever the patch holds. So Install goes only into the client that draws
them, and Settings says what it found instead of taking the folder on the program's name.

What tells them apart (checked on the real programs, 2026-11-15):
- the machine in the program's header: x64 (0x8664) or 32-bit (0x14C);
- ``ULTRA_MARK``: Ultra WoW's own log line (every archive's path tables, since 2026-11-03 - the Next
  client of 11-04 has it, the Test client of 10-26 doesn't);
- ``WXL_MARK``: Furioz's native WarcraftXL modules (retail tables and models read by the program
  itself) - in Ultra WoW and in the wowdecomp-dx11 fork it is built on;
- the link date: Blizzard's 3.3.5a Wow.exe is from 2010, every rebuilt client is years newer;
- WarcraftXL's DLLs beside the program (the 32-bit route that injects them into Blizzard's Wow.exe).
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

from . import edition
from .retailpack import FOLDER_MARK, LEGACY_PATCH, MERGE_MARK

# the programs a 3.3.5 client folder may start: Ultra WoW's and wowdecomp's two targets, then Blizzard's
EXES = ("WowClient64.exe", "WowClient32.exe", "Wow64.exe", "Wow32.exe", "Wow.exe")
ULTRA_MARK = MERGE_MARK
WXL_MARK = b"wxlRetailDb2"
BLIZZARD_BEFORE = 1325376000                # 2012-01-01: a program linked before this is Blizzard's own
MACHINES = {0x8664: "x64", 0x14C: "x86"}
INJECTED = ("WarcraftXL.dll", "WotLKExtensions.dll",
            os.path.join("Extensions", "wxl-equip-plus", "wxl-equip-plus.dll"))
# this edition's client and the other edition, by the client's machine
WANT = "x86" if edition.KEY == "32bit" else "x64"
ULTRA = {"x64": "Ultra WoW x64", "x86": "Ultra WoW 32-bit"}
WORKBENCH = {"x64": "Retroport Workbench x64", "x86": "Retroport Workbench 32-bit"}
KINDS = ("ultra", "wxl", "plain", "blizzard", "unknown", "none")

_SEEN: dict[tuple, tuple] = {}


@dataclass
class Client:
    """One folder's client: its program (``exe``, a file name), its machine, what it is (``kind``, one of
    ``KINDS``), whether it opens folder MPQs, and the WarcraftXL DLLs beside it."""
    exe: str = ""
    arch: str = ""
    kind: str = "none"
    folder_mpqs: bool = False
    injected: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """What it is, in words."""
        arch = "32-bit" if self.arch == "x86" else self.arch
        if self.kind == "ultra":
            return ULTRA[self.arch]
        if self.kind == "wxl":
            return f"a WarcraftXL {arch} client ({self.exe}) that isn't a current Ultra WoW"
        if self.kind == "plain":
            return f"a plain 3.3.5 client ({self.exe}, {arch} - like a wowdecomp build)"
        if self.kind == "blizzard":
            return "Blizzard's 3.3.5a Wow.exe" + (" with WarcraftXL" if self.injected else "")
        if self.kind == "unknown":
            return f"{self.exe}, which isn't a Windows program this can read"
        return ""

    @property
    def ok(self) -> bool:
        """Whether Install can go into it (``problem`` says why not)."""
        return not self.problem

    @property
    def problem(self) -> str:
        """Why Install can't go into this client ("" when it can)."""
        if self.kind == "none":
            return (f"Install puts items into {edition.CLIENT_NAME}: choose its folder (with {edition.CLIENT_EXE}) "
                    "in Settings")
        if self.kind == "blizzard" and self.injected:
            return (f"this folder's client is {self.name}: WarcraftXL reads some retail data, but not retail's own "
                    f"files as Install writes them for Ultra WoW. Install needs {ULTRA[WANT]}")
        if self.kind in ("plain", "blizzard"):
            return (f"this folder's client is {self.name}: it reads only 3.3.5 data, so retail's own files can't show "
                    f"in it. Install needs {ULTRA[WANT]}")
        if self.kind == "unknown":
            return f"{self.exe} here isn't a Windows program this can read: Install needs {ULTRA[WANT]}"
        if self.arch != WANT:
            if self.kind == "ultra":
                return f"this folder's client is {self.name}: {WORKBENCH[self.arch]} installs into it"
            return (f"this folder's client is {self.name}, {'a 32-bit' if self.arch == 'x86' else 'an x64'} client: "
                    f"{WORKBENCH[self.arch]} installs into {ULTRA[self.arch]}")
        if self.exe != edition.CLIENT_EXE:
            return f"Install looks for {edition.CLIENT_EXE}; this folder's {self.name} is {self.exe}"
        return ""

    @property
    def note(self) -> str:
        """What else to know about a client Install can go into ("" when nothing)."""
        out = []
        if self.ok and self.kind == "wxl":
            out.append("it reads retail's files, but only the top archive's path tables (Install uses "
                       f"{LEGACY_PATCH}), and looks made for the current Ultra WoW may not all show")
        if self.injected and self.kind in ("ultra", "wxl"):
            out.append(f"{', '.join(os.path.basename(p) for p in self.injected)} in this folder isn't needed - "
                       "Ultra WoW has its features built in")
        return "; ".join(out)

    def view(self) -> dict:
        """For the page."""
        return {"exe": self.exe, "arch": self.arch, "kind": self.kind, "name": self.name, "ok": self.ok,
                "problem": self.problem, "note": self.note, "folder_mpqs": self.folder_mpqs,
                "injected": [os.path.basename(p) for p in self.injected]}


def _program(path: str) -> tuple[str, int, set[bytes]]:
    """A program's machine ("x64" / "x86" / ""), link time and which marks it holds; kept per file
    (path, size, time) - a client program is 30 MB, read once."""
    st = os.stat(path)
    key = (os.path.normcase(path), st.st_size, st.st_mtime_ns)
    if key not in _SEEN:
        with open(path, "rb") as fh:
            data = fh.read()
        arch, linked = "", 0
        try:
            if data[:2] == b"MZ":
                at = struct.unpack_from("<I", data, 0x3C)[0]
                if data[at:at + 4] == b"PE\0\0":
                    machine, = struct.unpack_from("<H", data, at + 4)
                    linked, = struct.unpack_from("<I", data, at + 8)
                    arch = MACHINES.get(machine, "")
        except struct.error:
            pass
        _SEEN[key] = (arch, linked, {m for m in (ULTRA_MARK, WXL_MARK, FOLDER_MARK) if m in data})
    return _SEEN[key]


def look(root: str) -> Client:
    """The client in ``root``: this edition's program first (``edition.CLIENT_EXE``), then the others
    (``EXES``)."""
    if not root or not os.path.isdir(root):
        return Client()
    names = [edition.CLIENT_EXE] + [n for n in EXES if n != edition.CLIENT_EXE]
    exe = next((n for n in names if os.path.isfile(os.path.join(root, n))), "")
    injected = [p for p in INJECTED if os.path.isfile(os.path.join(root, p))]
    if not exe:
        return Client(injected=injected)
    try:
        arch, linked, marks = _program(os.path.join(root, exe))
    except OSError:
        return Client(exe=exe, kind="unknown", injected=injected)
    if not arch:
        kind = "unknown"
    elif ULTRA_MARK in marks:
        kind = "ultra"
    elif WXL_MARK in marks:
        kind = "wxl"
    elif arch == "x86" and linked and linked < BLIZZARD_BEFORE:
        kind = "blizzard"
    else:
        kind = "plain"
    return Client(exe=exe, arch=arch, kind=kind, folder_mpqs=FOLDER_MARK in marks, injected=injected)
