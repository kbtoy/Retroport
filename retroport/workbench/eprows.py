"""Equip Plus rows for a helm that also wears a collection part (the workbench's, not Equip Plus's tool).

Some helms come in two parts: their own model, which the kit builds into the 3.3.5 ItemDisplayInfo
row, and a part of the set's shared body model (a *collection*) - the Damned Necrolyte skull's
hood is group 27 of the set's body model, which also carries the robe's clasp, the gloves and the
belt chains. The kit's export leaves helms out, and Equip Plus's converter
(``backport_to_equipplus.py``) only knows the body slots, so that part never reached the game: the
skull mask floated on a bald head.

``kitlocal.attached_collections`` has the kit export those parts as it exports any other piece
(``out\\extension\\extension.json``, packed into ``<patch>-ext.MPQ``). After Equip Plus's converter
has made its folder patch, ``add`` puts each of them in it the way that patch holds the others:

* the model and its skin under ``Item\\ObjectComponents\\<the piece's folder>\\<stem>_<Race><Sex>.m2``
  (Equip Plus's legacy suffix: one row, a file per race and sex), with the textures it names;
* the texture retail gives the display's model in its item-texture slot (type 2), ``<ns>_<fdid>.blp``
  in that folder, made 3.3.5-ready by the Converter's BLP code when the patch hasn't got it already;
* rows in ``DBFilesClient\\WXLItemDisplayModels.csv`` for the display's new id, slot Head: the
  collection part on attachment 19 (skinned to the body, as Equip Plus attaches collections) - and
  the helm's own model as its 3.3.5 row has it (``Head\\<ns>\\<helm>.mdx``, ``_<Race><Sex>`` files, its
  texture, the helmet point 11), because Equip Plus draws only the rows of a display that has any.

Both Equip Plus in a Wow.exe client and the x64 client (its rows built in) read those rows.
"""

from __future__ import annotations

import csv
import glob
import io
import json
import os
import re
import struct

SLOT_NAMES = {"head": "Head"}
COLUMNS = ["DisplayID", "ItemID", "Slot", "Layer", "Side", "Folder", "Model", "Texture", "Geosets", "Attach",
           "SuffixPolicy", "TexturePolicy", "Flags"]
CSV_NAME = os.path.join("DBFilesClient", "WXLItemDisplayModels.csv")
COLLECTION_ATTACH, HELMET_ATTACH = "19", "11"
RETAIL_TAG = re.compile(r"_[a-z]{2}_[mf](?=_|$)")        # a retail cut's own race and sex ("..._hu_m__...")


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def textures(model: bytes) -> list[tuple[int, str]]:
    """(type, file name) of each texture an MD20 model lists ("" for a replaceable one)."""
    if model[:4] != b"MD20":
        return []
    n, at = struct.unpack_from("<II", model, 0x50)
    out = []
    for i in range(n):
        kind, _flags, length, name_at = struct.unpack_from("<IIII", model, at + i * 16)
        out.append((kind, model[name_at:name_at + length].rstrip(b"\0").decode("latin-1") if length else ""))
    return out


def stem_of(model_path: str, prefix: str, sex: str) -> tuple[str, str]:
    """(folder under Item\\ObjectComponents, stem): the kit's piece ``...\\<name>_<Prefix><Sex>__src__s<hash>.m2``
    as the one Equip Plus row all its races and sexes share, ``<stem>.mdx`` -> ``<stem>_<Prefix><Sex>.m2``."""
    parts = model_path.replace("/", "\\").split("\\")
    folder = "\\".join(parts[2:-1])
    base = parts[-1][:-3]
    token = f"_{prefix}{sex}"
    at = base.rfind(token)
    if at >= 0:
        base = base[:at] + base[at + len(token):]
    return folder, RETAIL_TAG.sub("", base, count=1)


def colourway(display: dict, k: int, race: int) -> int | None:
    """The texture retail gives model ``k`` of this display in its item-texture slot (type 2): the
    race's own, else the one for every race."""
    rows = [(int(t.get("race") or 0), int(t["fdid"])) for t in display.get("model_tex", []) if t.get("k") == k]
    rows += [(int(t.get("race") or 0), int(t["fdid"])) for t in display.get("extra_tex", [])
             if t.get("model") == k and t.get("type") == 2]
    for want in (race, 0):
        for r, fdid in rows:
            if r == want:
                return fdid
    return rows[0][1] if rows else None


def helm_row(new_id, plan_row: dict) -> dict | None:
    """The helm's own model as an Equip Plus row, from the kit's 3.3.5 row (``Backport\\helm_..mdx``
    under Item\\ObjectComponents\\Head, its texture beside it); None when it has no model or its
    texture lives in another folder (a row names one folder for both)."""
    model = ((plan_row or {}).get("model") or [""])[0].replace("/", "\\")
    tex = ((plan_row or {}).get("tex") or [""])[0].replace("/", "\\")
    if not model:
        return None
    sub, _sep, name = model.rpartition("\\")
    tsub, _sep, tname = tex.rpartition("\\")
    if tex and tsub != sub:
        return None
    return {"DisplayID": str(new_id), "ItemID": "", "Slot": "Head", "Layer": "Base", "Side": "C",
            "Folder": "Head" + (f"\\{sub}" if sub else ""), "Model": name, "Texture": tname, "Geosets": "",
            "Attach": HELMET_ATTACH, "SuffixPolicy": "Legacy", "TexturePolicy": "Exact", "Flags": ""}


def client_blp(raw: bytes, name: str) -> bytes:
    """A retail BLP the 3.3.5 client reads (the Converter's: at most 1024 px, a format it knows)."""
    from wotlkconv.blp.convert import convert_blp
    from wotlkconv.options import Options
    out, _res = convert_blp(raw, name, Options())
    if not out:
        raise ValueError(f"{name}: nothing to convert")
    return out


def add(work: str, patch: str, say=print) -> int:
    """The helms' collection parts the kit exported, with the helms themselves, as rows of Equip
    Plus's folder patch ``patch`` (see the module doc). The number of helms given rows."""
    ext = _load(os.path.join(work, "out", "extension", "extension.json"), {}) or {}
    wanted = {d: e for d, e in ext.items() if e.get("slot") in SLOT_NAMES}
    if not wanted:
        return 0
    archives = sorted(glob.glob(os.path.join(work, "out", "extension", "*-ext.MPQ")), key=os.path.getmtime)
    if not archives:
        say("   ! helms' hoods left out: the kit's 3D-piece archive isn't there")
        return 0
    from ..mpq import MPQ
    ids = (_load(os.path.join(work, "ids.json"), {}) or {}).get("display") or {}
    displays = (_load(os.path.join(work, "selection.json"), {}) or {}).get("displays") or {}
    plan = _load(os.path.join(work, "build", "plan.json"), {}) or {}
    prj = _load(os.path.join(work, "bp.json"), {}) or {}
    ns = str(prj.get("namespace") or "Backport")
    cache = os.path.join(work, "cache", str(prj.get("build") or ""))

    def have(rel: str) -> bool:
        return os.path.isfile(os.path.join(patch, rel))

    def put(rel: str, data: bytes) -> None:
        dest = os.path.join(patch, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)

    rows, helms, problems = [], 0, []
    mpq = MPQ(archives[-1])
    try:
        for d, entry in sorted(wanted.items(), key=lambda kv: int(kv[0])):
            new_id = ids.get(str(d)) or entry.get("new_display")
            if not new_id:
                problems.append(f"display {d}: no new display id (the kit's tables step hasn't numbered it)")
                continue
            own = helm_row(new_id, (plan.get(str(d)) or {}).get("row"))
            if own is None:
                problems.append(f"display {d}: its helm model can't be given an Equip Plus row - its hood is left out")
                continue
            groups: dict[tuple, list] = {}
            for p in entry.get("pieces", []):
                if not p.get("error") and p.get("model"):
                    groups.setdefault((p.get("k", 0), *stem_of(p["model"], p["prefix"], p["sex"])), []).append(p)
            parts = []
            for (k, folder, stem), pieces in sorted(groups.items()):
                item_texture = False
                for p in pieces:
                    model, skin = mpq.read(p["model"]), mpq.read(p["model"][:-3] + "00.skin")
                    if model is None or skin is None:
                        problems.append(f"{p['model']}: not in {os.path.basename(archives[-1])}")
                        continue
                    base = f"Item\\ObjectComponents\\{folder}\\{stem}_{p['prefix']}{p['sex']}"
                    put(base + ".m2", model)
                    put(base + "00.skin", skin)
                    for kind, name in textures(model):
                        item_texture |= kind == 2
                        if kind == 0 and name and not have(name):
                            data = mpq.read(name)
                            if data is None:
                                problems.append(f"{base}.m2 names {name}, which the kit's archive lacks")
                            else:
                                put(name, data)
                texture = ""
                if item_texture:
                    fdid = colourway(displays.get(str(d)) or {}, k, int(pieces[0].get("retail_race") or 0))
                    if not fdid:
                        problems.append(f"display {d}: no texture for its hood - left out")
                        continue
                    texture = f"{ns.lower()}_{fdid}"
                    rel = f"Item\\ObjectComponents\\{folder}\\{texture}.blp"
                    if not have(rel):
                        try:
                            with open(os.path.join(cache, str(fdid)), "rb") as fh:
                                put(rel, client_blp(fh.read(), f"{fdid}.blp"))
                        except (OSError, ValueError) as e:
                            problems.append(f"display {d}: its hood's texture {fdid}: {e} - left out")
                            continue
                parts.append({"DisplayID": str(new_id), "ItemID": "", "Slot": SLOT_NAMES[entry["slot"]], "Layer": "Base",
                              "Side": "C", "Folder": folder, "Model": f"{stem}.mdx", "Texture": texture, "Geosets": "",
                              "Attach": COLLECTION_ATTACH, "SuffixPolicy": "Legacy", "TexturePolicy": "Exact", "Flags": ""})
            if parts:
                rows += [own, *parts]
                helms += 1
    finally:
        mpq.close()
    if rows:
        path = os.path.join(patch, CSV_NAME)
        old = []
        if os.path.isfile(path):
            with open(path, encoding="utf-8", newline="") as fh:
                old = list(csv.DictReader(fh))
        key = lambda r: (r.get("DisplayID"), r.get("Slot"), r.get("Model"))
        mine = {key(r) for r in rows}
        merged = [r for r in old if key(r) not in mine] + rows
        merged.sort(key=lambda r: (int(r.get("DisplayID") or 0), r.get("Model") or ""))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(buf.getvalue())
        say(f"   Equip Plus: {helms} helm(s) with their hood (rows for the helm and its collection part)")
    for p in problems:
        say(f"   ! {p}")
    return helms
