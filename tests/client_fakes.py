"""A stand-in client program for tests: a Windows program header (its machine, its link time) and the
marks the Workbench looks for (``clients.look``)."""

import struct

from retroport.workbench import clients as CL
from retroport.workbench import retailpack as RP

MACHINE = {"x64": 0x8664, "x86": 0x14C}
NEW = 1763164800            # 2025-11-15: a rebuilt client
OLD = 1277424000            # 2010-06-25: Blizzard's 3.3.5a Wow.exe


def program(arch: str = CL.WANT, marks: tuple[bytes, ...] = (RP.MERGE_MARK,), linked: int = NEW) -> bytes:
    """An exe's bytes: MZ, the PE header at 0x40 (machine, link time), then the marks."""
    head = bytearray(0x40)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x40)
    pe = b"PE\0\0" + struct.pack("<HHI", MACHINE[arch], 1, linked) + bytes(12)
    return bytes(head) + pe + b"".join(b" " + m for m in marks)


ULTRA = program()                                       # this edition's Ultra WoW: every archive's path tables
