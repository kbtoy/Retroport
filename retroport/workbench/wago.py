"""Game data from wago.tools, for anyone without a local install: a build's tables as wago's CSV
and its files by FileDataID. Retail at its newest live
build (or a pinned one) for the items; BfA 8.3.7 for the bodies the character view dresses.

Everything fetched is kept on disk (``<cache>/wago/<build>/``), so a table or a file is asked for
once, and what was seen before still opens while wago is down. Requests are few at a time and
retried with a pause when wago is busy (it sits behind Cloudflare, which turns floods away).

A table's rows come out as the local reader's do - ``(ID, {column: value})`` with WoWDBDefs'
column names - so the catalog, the 3D previews and the bodies read either source the same way:
wago's array columns (``ModelResourcesID_0``, ``_1``) become one list, and numbers become numbers.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

BASE = "https://wago.tools"
BFA_BUILD = "8.3.7.35435"                   # the BfA client our bodies (and race ports) come from
USER_AGENT = "retroport-workbench/0.1"
TIMEOUT = 90
ATTEMPTS = 4
_slots = threading.BoundedSemaphore(4)      # requests in flight at once, for every source together
ARRAY = re.compile(r"^(.*)_(\d+)$")
INT = re.compile(r"^-?\d+$")
FLOAT = re.compile(r"^-?\d+\.\d+(?:[eE][-+]?\d+)?$|^-?\d+[eE][-+]?\d+$")


class WagoError(RuntimeError):
    """wago.tools could not answer (down, refusing, or no such table or file)."""


class WagoMissing(WagoError, LookupError):
    """wago.tools has no such table or file at that build (it says so; asking again won't help)."""


def http_get(url: str, dest: str) -> None:
    """``url`` saved to ``dest`` (whole, or not at all); retried when wago is busy or unreachable."""
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            with _slots:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    if "/api/casc/" in url and r.headers.get("Content-Type", "").startswith("application/json"):
                        # a file it doesn't have: {"error": "File not found", ...} with a 200
                        raise WagoMissing(f"wago.tools: {_json_error(r.read())} ({url[len(BASE):]})")
                    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                    part = f"{dest}.{threading.get_ident()}.part"
                    try:
                        with open(part, "wb") as fh:
                            while chunk := r.read(1 << 20):
                                fh.write(chunk)
                    except BaseException:
                        _remove(part)
                        raise
            os.replace(part, dest)
            return
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise WagoMissing(f"wago.tools has no {url[len(BASE):]}") from None
            last = e
            if e.code not in (408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524):
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1) ** 2)
    raise WagoError(f"wago.tools did not answer ({_why(last)}): {url}")


def _json_error(body: bytes) -> str:
    try:
        return str(json.loads(body).get("error") or "no such file")
    except (ValueError, AttributeError):
        return "no such file"


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _why(e: Exception | None) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return str(e.reason)
    return f"{type(e).__name__}: {e}" if e else "no answer"


def rows_from_csv(text: str) -> list[tuple[int, dict]]:
    """wago's CSV as the local reader's rows (see the module doc). A column of whole numbers is
    ints, of decimals floats, anything else - and every ``_lang`` column - text."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    raw = list(reader)
    width = len(header)
    kind = []
    for c, name in enumerate(header):
        values = [r[c] for r in raw if c < len(r) and r[c] != ""]
        if name.endswith("_lang") or not values:
            kind.append(str if name.endswith("_lang") else int)
        elif all(INT.match(v) for v in values):
            kind.append(int)
        elif all(INT.match(v) or FLOAT.match(v) for v in values):
            kind.append(float)
        else:
            kind.append(str)
    # array columns: X_0 .. X_n (contiguous from 0) become one list X
    bases: dict[str, list[tuple[int, int]]] = {}
    for c, name in enumerate(header):
        m = ARRAY.match(name)
        if m:
            bases.setdefault(m.group(1), []).append((int(m.group(2)), c))
    arrays = {b: [c for _i, c in sorted(v)] for b, v in bases.items()
              if sorted(i for i, _c in v) == list(range(len(v)))}
    for cols in arrays.values():                       # one type for an array: a float one is all floats
        t = str if any(kind[c] is str for c in cols) else float if any(kind[c] is float for c in cols) else int
        for c in cols:
            kind[c] = t
    in_array = {c for cols in arrays.values() for c in cols}
    plain = [(c, name) for c, name in enumerate(header) if c not in in_array]
    # the row's id: its ID column - or, where the id is a file's (ModelFileData, TextureFileData),
    # wago names it FileDataID
    key = "ID" if "ID" in header else "FileDataID" if "FileDataID" in header else None
    id_col = header.index(key) if key else None
    if id_col is not None:
        kind[id_col] = int

    def cell(r: list[str], c: int):
        v = r[c] if c < len(r) else ""
        t = kind[c]
        if t is str:
            return v
        if v == "":
            return 0
        return int(v) if t is int else float(v)

    out = []
    for n, r in enumerate(raw):
        if len(r) < width and not any(r):
            continue
        row = {name: cell(r, c) for c, name in plain}
        for b, cols in arrays.items():
            row[b] = [cell(r, c) for c in cols]
        out.append((row[key] if key else n, row))
    return out


def latest_build(cache_dir: str, product: str = "wow", fetch=http_get, max_age: float = 6 * 3600) -> str:
    """The newest build of ``product`` wago knows (asked at most every few hours; the last answer
    when wago is down)."""
    path = os.path.join(cache_dir, "wago", "builds.json")
    known = {}
    try:
        with open(path, encoding="utf-8") as fh:
            known = json.load(fh)
    except (OSError, ValueError):
        pass
    if product in known and time.time() - known.get("at", 0) < max_age:
        return known[product]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fetch(f"{BASE}/api/builds", path + ".new")
        with open(path + ".new", encoding="utf-8") as fh:
            builds = json.load(fh)
        os.remove(path + ".new")
        newest = {p: v[0]["version"] for p, v in builds.items() if isinstance(v, list) and v and v[0].get("version")}
        if product not in newest:
            raise WagoError(f"wago.tools lists no {product} build")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"at": time.time(), **newest}, fh)
        return newest[product]
    except (WagoError, OSError, ValueError, KeyError, IndexError):
        if product in known:
            return known[product]                     # wago down: the build seen last
        raise


class WagoSource:
    """One build's tables and files from wago.tools (the local ``Source``'s interface)."""

    def __init__(self, spec, cache_dir: str, fetch=http_get):
        self.spec = spec
        self.cache_dir = cache_dir
        self._fetch = fetch
        self._build = spec.build or ""

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def build(self) -> str:
        if not self._build:
            self._build = latest_build(self.cache_dir, self.spec.product or "wow", self._fetch)
        return self._build

    def _path(self, *parts: str) -> str:
        return os.path.join(self.cache_dir, "wago", self.build, *parts)

    def open(self):
        return self

    def table(self, name: str) -> list[tuple[int, dict]]:
        path = self._path("db2", f"{name}.csv")
        if not os.path.isfile(path):
            self._fetch(f"{BASE}/db2/{name}/csv?build={self.build}", path)
        with open(path, encoding="utf-8", newline="") as fh:
            return rows_from_csv(fh.read())

    def read(self, fdid: int) -> bytes:
        path = self._path("files", str(int(fdid)))
        if not os.path.isfile(path):
            if os.path.isfile(path + ".missing"):         # asked before: not in this build
                raise WagoMissing(f"file {fdid} is not in {self.build}")
            try:
                self._fetch(f"{BASE}/api/casc/{int(fdid)}?download&version={self.build}", path)
            except WagoMissing:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path + ".missing", "wb").close()
                raise
        with open(path, "rb") as fh:
            data = fh.read()
        if data and not data.strip(b"\0"):            # wago's answer for what Blizzard keeps encrypted
            raise WagoError(f"file {fdid} is encrypted at {self.build}")
        return data
