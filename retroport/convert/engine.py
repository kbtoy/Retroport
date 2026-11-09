"""wotlkconv as retroport's conversion engine (the MD21 -> MD20 step).

wotlkconv (github.com/Bar3b0n3s/Converter, MIT) is a native Python converter:
it merges ``.skel`` skeletons (parent chains included), flattens chunked
``.anim`` files, resolves TXID textures, rewrites modern ``.skin`` headers and
names every companion the way 3.3.5a globs for it. Used here in place of the
MultiConverter exe, it removes the external tool, its 260-character path limit
and the unconverted skins/anims it leaves behind.

Its listfile loads all ~2.2M rows (about 19 s and 400 MB), so each conversion
gets a *scoped* listfile instead: the FileDataIDs the model and its skeleton
chain reference are collected first, and the community listfile is streamed
once for just those (twice if a parent skeleton turns up more ids).
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Callable

from ..formats.verify import m2_problems
from ..safeio import write_verified
from .texbake import resolve_fdids

# chunks whose payload is FileDataIDs (u32s; AFID's u16 pairs only add harmless extras)
_FDID_CHUNKS = {b"TXID", b"SFID", b"AFID", b"SKID", b"BFID", b"PFID", b"GPID", b"RPID", b"SKPD"}
_MAX_SKEL_DEPTH = 4


def available() -> bool:
    try:
        import wotlkconv  # noqa: F401
    except ImportError:
        return False
    return True


INSTALL_HINT = ("wotlkconv is not installed - run:  pip install -e \"I:\\WoW Modding\\Converter\"  "
                "(or pip install git+https://github.com/Bar3b0n3s/Converter)")


@dataclass
class EngineNote:
    level: str          # info | lossy | warn | error
    code: str
    message: str
    file: str = ""


@dataclass
class EngineResult:
    ok: bool
    status: str = ""                  # wotlkconv status: ok / lossy / passthrough / failed
    output: str | None = None         # the converted .m2
    written: list[str] = field(default_factory=list)
    notes: list[EngineNote] = field(default_factory=list)
    error: str = ""


def chunk_fdids(data: bytes) -> set[int]:
    """Every u32 in a chunked M2/.skel's FileDataID chunks (over-collecting is harmless)."""
    ids: set[int] = set()
    pos = 0
    while pos + 8 <= len(data):
        magic = data[pos:pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        start, end = pos + 8, min(pos + 8 + size, len(data))
        if magic in _FDID_CHUNKS:
            ids.update(v for v in struct.unpack_from(f"<{(end - start) // 4}I", data, start) if v)
        if magic not in (b"MD21",) and not magic.isalnum():
            break
        pos = pos + 8 + size
    return ids


def _find_by_basename(roots: list[str], name: str) -> str | None:
    low = name.lower()
    for root in roots:
        for dirpath, _d, files in os.walk(root):
            for f in files:
                if f.lower() == low:
                    return os.path.join(dirpath, f)
    return None


def scoped_listfile(model_data: bytes, roots: list[str], listfile_path: str | None,
                    overrides_path: str | None = None,
                    read_fdid: Callable[[int], bytes | None] | None = None):
    """A wotlkconv Listfile holding only the ids this model (and its skeletons) use.
    Skeletons are read from disk under ``roots``, or with ``read_fdid`` (e.g. from a
    game install) when given."""
    return scoped_listfile_for([model_data], roots, listfile_path, overrides_path, read_fdid)


def scoped_listfile_for(models: list[bytes], roots: list[str], listfile_path: str | None,
                        overrides_path: str | None = None,
                        read_fdid: Callable[[int], bytes | None] | None = None):
    """``scoped_listfile`` for many models at once: the community listfile is streamed once for
    all of them (a batch of hundreds converts in seconds instead of seconds each)."""
    from wotlkconv.listfile import Listfile

    lf = Listfile(listfile_path or "<none>")
    if not (listfile_path and os.path.isfile(listfile_path)):
        return lf
    wanted: set[int] = set()
    for model_data in models:
        wanted |= chunk_fdids(model_data)
    known: dict[int, str] = {}
    for _ in range(_MAX_SKEL_DEPTH):
        missing = wanted - known.keys()
        if not missing:
            break
        known.update(resolve_fdids(missing, listfile_path, overrides_path))
        # follow skeletons: their AFID/BFID/SKPD name more ids
        more: set[int] = set()
        for fdid, path in known.items():
            if path.lower().endswith(".skel"):
                if read_fdid is not None:
                    skel = read_fdid(fdid)
                    if skel:
                        more |= chunk_fdids(skel)
                    continue
                found = _find_by_basename(roots, os.path.basename(path.replace("\\", "/")))
                if found:
                    with open(found, "rb") as fh:
                        more |= chunk_fdids(fh.read())
        if more <= wanted:
            break
        wanted |= more
    lf.update(f"{fdid};{path.replace(chr(92), '/')}\n" for fdid, path in known.items())
    return lf


def convert_with_wotlkconv(model_path: str, out_dir: str, *, output_stem: str | None = None,
                           listfile_path: str | None = None, overrides_path: str | None = None,
                           search_roots: list[str] | None = None, options: dict | None = None,
                           on_log: Callable[[str], None] | None = None, casc=None,
                           data: bytes | None = None, listfile=None) -> EngineResult:
    """Convert one model (plus its skins/anims/skeleton) into ``out_dir``.

    ``options`` are wotlkconv ``Options`` fields (e.g. ``{"strip_particles": True}``).
    Every file is written through retroport's verified writer; the model must come
    out structurally clean. ``casc`` (a wotlkconv ``CascStorage``) lets skins, skeletons
    and animations come straight from a game install. ``data`` is the model's bytes when
    they aren't on disk at ``model_path`` (only its name is used then), and ``listfile`` a
    wotlkconv Listfile already scoped for it (``scoped_listfile_for``, for batches)."""
    log = on_log or (lambda m: None)
    if not available():
        return EngineResult(ok=False, error=INSTALL_HINT)
    from wotlkconv.m2 import convert_m2
    from wotlkconv.options import Options
    from wotlkconv.resolve import AssetSource

    from . import skeleton
    skeleton.install()                  # a skeleton plays the sequences it lacks from its parent
    if data is None:
        with open(model_path, "rb") as fh:
            data = fh.read()
    roots = [os.path.dirname(os.path.abspath(model_path)), *(r for r in (search_roots or []) if r)]
    reader = None
    if casc is not None:
        reader = lambda fdid: casc.try_read_file_id(fdid)[0]   # noqa: E731
    lf = listfile
    if lf is None:
        lf = scoped_listfile(data, roots, listfile_path, overrides_path, read_fdid=reader)
        if listfile_path:
            log(f"  wotlkconv: scoped listfile with {len(lf)} entr{'y' if len(lf) == 1 else 'ies'} for this model")
    opts = Options(**(options or {}))
    source = AssetSource(lf, roots=roots, casc=casc)
    stem = output_stem or os.path.splitext(os.path.basename(model_path))[0]

    try:
        out, res, companions = convert_m2(data, os.path.basename(model_path), opts, lf,
                                          source=source, output_stem=stem)
    except Exception as exc:                          # parse errors on bad input
        return EngineResult(ok=False, error=f"wotlkconv could not convert the model: {type(exc).__name__}: {exc}")

    result = EngineResult(ok=res.ok and bool(out), status=res.status.value)
    result.notes = [EngineNote(n.level, n.code, n.message, os.path.basename(model_path)) for n in res.notes]
    if not result.ok:
        result.error = next((n.message for n in res.notes if n.level == "error"), "conversion failed")
        return result

    os.makedirs(out_dir, exist_ok=True)
    m2_out = os.path.join(out_dir, stem + ".m2")

    def clean_model(p: str) -> None:
        with open(p, "rb") as fh:
            problems = m2_problems(fh.read())
        if problems:
            raise ValueError("wotlkconv output failed verification: " + "; ".join(sorted(problems)))

    write_verified(m2_out, out, clean_model)
    result.output = m2_out
    result.written.append(m2_out)
    for c in companions:
        result.notes += [EngineNote(n.level, n.code, n.message, c.filename) for n in c.result.notes
                         if n.level != "info"]
        if not c.data:                                # a companion that failed or was unavailable
            continue
        path = os.path.join(out_dir, os.path.basename(c.filename))
        write_verified(path, c.data)
        result.written.append(path)
    return result
