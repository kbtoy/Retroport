"""The workbench's local web server: the browser page, a JSON API over the catalogs, icons.

Listens on 127.0.0.1 only. Catalogs load in the background, so the page is up at once and shows
their progress. Settings (the installs, the 3.3.5 client, WoWDBDefs, the listfile, where the
workbench keeps its cache and basket) live in ``%USERPROFILE%\\.retroport\\<edition.SETTINGS_FILE>``; the
``retroport workbench`` options update them.

API (GET unless noted):
  /api/status                    sources and their state, the loading log
  /api/meta                      names: slots, armour and weapon types, expansions, classes, qualities
  /api/items?source=&q=&slot=&armour=&weapon=&expansion=&quality=&cls=&looks=&sort=&page=
  /api/item?source=&id=
  /api/sets?source=&q=&expansion=&cls=&armour=&kind=transmog|itemset&page=
  /api/set?source=&id=&kind=
  /api/mounts?source=&q=&kind=&page=        retail's mounts; /api/mount?source=&id= one; /api/mount/preview?source=&display=
  /api/basket                    GET the basket; POST replaces it
  /api/basket/plan               what installing it builds: each entry's looks, overlaps, changes
  /api/basket/leave-out          POST {display, out}: a piece left out of the entries that have it (or put back)
  /api/basket/take-out           POST {key, out}: something in the game taken out by the next install (or kept)
  /api/install                   the install's state; /api/install/log?since= its output;
                                 POST /api/install/run {action: go|build|undo|check|stop}
  /api/settings                  GET the Settings view; POST saves it (a changed source is read again)
  POST /api/pick {folder, title, start}   Windows' folder/file picker on this machine -> {path}
  /api/races                     the races the 3.3.5 client plays (the character view's choices)
  /api/preview?source=&display=&race=&sex=&slot=     a display's models (meshes, Stand) and body textures
  /api/body?race=&sex=           a BfA body: mesh, skin layers, layout, hair, default geosets
  /api/outfit?source=&race=&sex=&items=<display>:<slot>,...   what each piece puts on that body
  /icon/<source>/<fdid>.png      an icon from the source's files (cached as PNG); /tex/... a texture
"""

from __future__ import annotations

import gzip
import io
import json
import mimetypes
import os
import re
import threading
import time
import traceback
import urllib.parse
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import catalog as C
from . import character as CH
from . import direct as DR
from . import edition
from . import glows as GL
from . import itemstats as IS
from . import jobs as J
from . import models as M
from . import mountpack as MP
from . import mounts as MT
from . import pick as P
from . import wotlk as WK

STATIC = os.path.join(os.path.dirname(__file__), "static")
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".retroport", edition.SETTINGS_FILE)
PORT = edition.PORT


def code_stamp() -> float:
    """The newest of the workbench's code files (the page and the server): a running server whose
    files changed since it started is answering with older code than the page it serves."""
    newest = 0.0
    for d in (os.path.dirname(os.path.abspath(__file__)), STATIC):
        for f in os.listdir(d):
            if f.endswith((".py", ".js", ".html", ".css")):
                newest = max(newest, os.path.getmtime(os.path.join(d, f)))
    return newest


STARTED_CODE = code_stamp()
STARTED = time.time()


def app_info() -> dict:
    """Which workbench this is: its version (a release's ``VERSION`` file, else the source tree's
    pyproject.toml), the folder it runs from, and how new its code is."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))                # the source tree, or a release's app\
    version = ""
    try:
        with open(os.path.join(here, "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()
        home = os.path.dirname(root)                             # the release folder (app\ is in it)
    except OSError:
        home = root
        try:
            with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as fh:
                m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M)
            version = (m.group(1) if m else "?") + " (source)"
        except OSError:
            version = "?"
    return {"version": version, "from": home, "code": STARTED_CODE}


# What a fresh install reads: retail's items from wago.tools at its newest build, and the BfA
# bodies the character view dresses from wago at 8.3.7 (no BfA item tab unless asked for).
DEFAULT_SOURCES = [{"key": "retail", "label": "Retail", "kind": "wago", "product": "wow"},
                   {"key": "bfa", "label": "BfA", "kind": "wago", "build": "8.3.7.35435", "browse": False}]


@dataclass
class Settings:
    sources: list[dict] = field(default_factory=list)     # SourceSpec fields (DEFAULT_SOURCES where unset)
    client: str = ""                                        # the 3.3.5 client folder
    dbd: str = ""                                           # WoWDBDefs definitions folder (local installs)
    listfile: str = ""                                      # the community listfile (local installs)
    data: str = ""                                          # cache + basket

    @classmethod
    def load(cls, path: str = SETTINGS_PATH) -> "Settings":
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            out = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()
        # what this workbench doesn't use - an older workbench's settings in the same file - is kept as
        # it was when this one saves
        out._others = {k: v for k, v in raw.items() if k not in cls.__dataclass_fields__}
        return out

    def save(self, path: str = SETTINGS_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**getattr(self, "_others", {}), **asdict(self)}, fh, indent=2)
        os.replace(tmp, path)

    def set_source(self, key: str, label: str, path: str, product: str | None = None, cdn: bool = False) -> None:
        """A local install for ``key`` (the command line's --retail / --bfa)."""
        self.sources = [s for s in self.sources if s.get("key") != key]
        self.sources.append(asdict(C.SourceSpec(key, label, path, product, cdn)))

    def effective_sources(self) -> list[C.SourceSpec]:
        """Retail, BfA (each as set, else its default), then any other source set."""
        have = {s.get("key"): s for s in self.sources}
        specs = [have.get(d["key"], d) for d in DEFAULT_SOURCES] + \
                [s for s in self.sources if s.get("key") not in ("retail", "bfa")]
        return [C.SourceSpec(**{k: v for k, v in s.items() if k in C.SourceSpec.__dataclass_fields__}) for s in specs]

    @property
    def data_dir(self) -> str:
        return self.data or os.path.join(os.path.dirname(SETTINGS_PATH), edition.DATA_FOLDER)

    def source_problem(self, spec: C.SourceSpec) -> str:
        """Why a source can't be read ("" when it can)."""
        if spec.kind != "local":
            return ""
        if not spec.path or not os.path.isfile(os.path.join(spec.path, ".build.info")):
            return f"{spec.label}: {spec.path or '(no folder)'} is not a game install (no .build.info)"
        if not self.dbd or not os.path.isdir(self.dbd):
            return f"{spec.label}: a local install needs the WoWDBDefs definitions folder"
        if not self.listfile or not os.path.isfile(self.listfile):
            return f"{spec.label}: a local install needs the community listfile"
        return ""

    def problems(self) -> list[str]:
        out = []
        if not self.client:
            out.append(f"choose {edition.CLIENT_NAME}'s folder in Settings")
        elif not os.path.isdir(os.path.join(self.client, "Data")):
            out.append(f"{self.client} has no Data folder - is it {edition.CLIENT_NAME}?")
        out += [p for p in map(self.source_problem, self.effective_sources()) if p]
        return out


class Workbench:
    """The sources, their catalogs (loaded in the background) and the basket."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sources: dict[str, object] = {}            # the sources whose items are browsed
        self.catalogs: dict[str, C.Catalog] = {}
        self.mount_catalogs: dict[str, MT.MountCatalog] = {}
        self.state: dict[str, str] = {}
        self.log: list[str] = []
        self.in_client: set[int] = set()
        self._displays: dict[str, M.DisplayIndex] = {}
        self._races: list[dict] | None = None
        self._meshes: dict[tuple, dict] = {}
        self._glows: dict[str, dict[int, list]] = {}       # source -> its item glows by visual (``glows_of``)
        self._race_names: dict[str, dict[int, str]] = {}
        self._specs: dict[str, C.SourceSpec] = {}
        self._client_seen = None
        self.bodies: CH.Bodies | None = None
        self.basket_path = os.path.join(settings.data_dir, "basket.json")
        self._lock = threading.Lock()
        self._basket_lock = threading.Lock()
        self._loading = threading.Lock()
        self.last_hello = self.last_bye = 0.0         # the page's comings and goings (app.py)
        self.quitting = False                         # another copy of the app asked this one to stop

        self.direct = DR.Direct(settings.data_dir, settings.listfile)
        self.direct.mount_catalog = lambda: self.mount_catalogs.get("retail")
        self._reference: dict | None = None
        self._client_options: dict | None = None
        self._options_lock = threading.Lock()
        self.configure()

    def configure(self) -> None:
        """The sources as the settings now say: a source whose settings changed is read again (its
        catalog too); the others keep what they loaded."""
        st, cache = self.settings, os.path.join(self.settings.data_dir, "cache")
        specs = {sp.key: sp for sp in st.effective_sources()}
        for key in list(self._specs):
            if specs.get(key) != self._specs[key]:
                for d in (self.sources, self.catalogs, self.mount_catalogs, self._displays, self.state, self._race_names,
                          self._glows):
                    d.pop(key, None)
        readers = {}
        for key, sp in specs.items():
            if key in self.sources:
                readers[key] = self.sources[key]
            else:
                readers[key] = C.make_source(sp, st.dbd, st.listfile, cache)
                if sp.browse:
                    self.sources[key] = readers[key]
                    self.state[key] = "waiting"
        bfa = specs.get("bfa")
        if bfa and (self._specs.get("bfa") != bfa or self.bodies is None):
            self.bodies = CH.Bodies(readers["bfa"])
        self._specs = specs
        self._races = None
        self._meshes.clear()
        retail = specs.get("retail")
        self.direct.client, self.direct.listfile = st.client, st.listfile
        self.direct.source = readers.get("retail") if retail and retail.kind == "local" else None

    def busy(self) -> bool:
        return self.direct.busy()

    def say(self, msg: str) -> None:
        with self._lock:
            self.log.append(f"{time.strftime('%H:%M:%S')} {msg}")
            del self.log[:-200]

    def load(self) -> None:
        """The client's item ids (marks what 3.3.5 already has), then each waiting source's catalog
        and the tables its 3D previews read. Runs again after the settings change."""
        with self._loading:
            client = self.settings.client
            if client != self._client_seen:
                self._client_seen = client
                self.in_client = set()
                if client and os.path.isdir(client):
                    try:
                        self.in_client = C.client_item_ids(client)
                        self.say(f"3.3.5 client: {len(self.in_client)} item ids")
                    except Exception as e:
                        self.say(f"3.3.5 client: {e}")
                for cat in self.catalogs.values():
                    cat.in_client = self.in_client
            for key, src in list(self.sources.items()):
                if self.state.get(key) != "waiting":
                    continue
                why = self.settings.source_problem(self._specs[key])
                if why:
                    self.state[key] = "failed"
                    self.say(why)
                    continue
                self.state[key] = "loading"
                try:
                    cat = C.load_catalog(src, self.say)
                    cat.in_client = self.in_client
                    if self.sources.get(key) is not src:      # the settings changed meanwhile
                        continue
                    self.catalogs[key] = cat
                    self.state[key] = "ready"
                    self.say(f"{src.spec.label} {cat.build}: {len(cat.items)} items, {len(cat.sets)} sets")
                except Exception as e:
                    if self.sources.get(key) is src:
                        self.state[key] = "failed"
                    hint = " - wago.tools may be down: try again later, or read a local install (Settings)" \
                        if src.spec.kind == "wago" else ""
                    self.say(f"{src.spec.label}: {e}{hint}")
                    traceback.print_exc()
            for key in list(self.catalogs):              # the 3D previews' tables, ready before they're asked for
                try:
                    self.displays(key)
                except Exception as e:
                    self.say(f"{self.sources[key].spec.label} previews: {e}")
            for key in list(self.catalogs):              # the source's mounts (the Mounts page)
                if key in self.mount_catalogs or key not in self.sources:
                    continue
                try:
                    cat = MT.load_catalog(self.sources[key], self.say)
                    self.mount_catalogs[key] = cat
                    self.say(f"{self.sources[key].spec.label} {cat.build}: {len(cat.mounts)} mounts")
                except Exception as e:
                    self.say(f"{self.sources[key].spec.label} mounts: {e}")
            try:                                          # the Stats step's numbers, ready before they're asked for
                self.client_options()
            except Exception as e:
                self.say(f"Stats step: {e}")

    def start(self) -> None:
        threading.Thread(target=self.load, name="catalogs", daemon=True).start()

    # -- the Stats step ------------------------------------------------------------------
    def reference(self) -> dict:
        """WotLK's own numbers (wotlk.py), from the cache or Wrath Classic's tables on wago.tools."""
        with self._options_lock:
            if self._reference is None:
                self._reference = WK.load(os.path.join(self.settings.data_dir, "cache"), self.say)
            return self._reference

    def client_options(self) -> dict:
        """The 3.3.5 client's set bonuses and the socket bonuses WotLK items use (cached)."""
        ref = self.reference()
        with self._options_lock:
            if self._client_options is None:
                if not self.settings.client:
                    return {"bonuses": [], "socket_bonuses": []}
                used = {r[14] for r in ref["items"] if r[14]}
                self._client_options = IS.client_options(self.settings.client, used)
            return self._client_options

    def stats_options(self) -> dict:
        opts = self.client_options()
        return {"classes": IS.CLASSES, "qualities": IS.QUALITIES, "bonding": IS.BONDING, "armour_types": IS.ARMOUR_TYPES,
                "sockets": IS.SOCKETS, "stats": {k: [v[0], v[1], v[2]] for k, v in IS.STATS.items()},
                "tables": WK.tables(self.reference()), "bonuses": opts["bonuses"], "socket_bonuses": opts["socket_bonuses"]}

    def stats_pieces(self) -> dict:
        """The basket's pieces - one per look, as Install makes one item per look - with what the
        catalog knows of each (slot, class and subclass, quality) and its in-game entry once built.
        (Something in the game gets its stats changed by putting it in the basket again.)"""
        plan = C.plan_basket(self.catalogs, self.basket())
        entries = {str(k): v for k, v in (self.direct.built_record().get("entries") or {}).items()}
        in_set = IS.groups_of(plan)
        pieces, seen, groups = [], {}, []
        for e in plan["entries"]:
            cat = self.catalogs.get(e.get("source") or "")
            members = []
            for look in e["looks"]:
                if not look.get("display"):
                    continue
                # a piece is a look Install makes one item of: its key (catalog.look_key) - a colourway's apart from
                # the look it was made from; "look" the display the 3D view shows (in "colour")
                d = str(look.get("look_key") or look["display"])
                if d not in members:
                    members.append(d)
                if d in seen:
                    seen[d]["groups"].append(e["name"])
                    continue
                row = cat.by_id.get(look.get("item")) if cat else None
                name = look.get("name") or f"Look {look['display']}"
                if look.get("colour"):
                    name = f"{name} ({look.get('colour_name') or 'Custom'})"
                # its set: the first basket set holding the look (its values the piece takes), none for an item
                # of its own
                p = {"display": d, "look": look["display"], "colour": look.get("colour"), "item": look.get("item"),
                     "name": name, "label": look.get("label") or "", "icon": look.get("icon") or 0, "quality": look.get("quality"),
                     "inv": look.get("slot") or 0, "cls": row[C.F["cls"]] if row is not None else 0,
                     "sub": row[C.F["sub"]] if row is not None else 0, "source": e.get("source"),
                     "groups": [e["name"]], "group_key": in_set.get(d, ""), "entry": entries.get(d)}
                seen[d] = p
                pieces.append(p)
            if members:
                groups.append({"key": e["key"], "name": e["name"], "set": e["kind"] in IS.SET_KINDS, "pieces": members,
                               "label": e.get("label") or ""})
        return {"pieces": pieces, "groups": groups, "edits": IS.load(self.settings.data_dir),
                "basket_sets": [{"key": e["key"], "name": e["name"],
                                 "pieces": [str(l.get("look_key") or l["display"]) for l in e["looks"] if l.get("display")]}
                                for e in plan["entries"] if e["kind"] in IS.SET_KINDS]}

    def look_names(self) -> dict:
        """The name each look of what Install builds has in the workbench (its first entry's): the
        name the Basket and Stats show, which the item SQL gives it."""
        names: dict = {}
        for e in self.install_plan()["entries"]:
            for look in e["looks"]:
                d = str(look.get("display") or "")
                if d and d != "0" and look.get("name"):
                    names.setdefault(d, look["name"])
        return names

    def install_notes(self) -> dict:
        """For the Backport page: pieces still without stats, looks an install would drop."""
        try:
            got = self.stats_pieces()
            edits = got["edits"]
            without = [p["name"] for p in got["pieces"] if not IS.touched(edits, p["display"], p.get("group_key") or None)]
            return {"stats": {"pieces": len(got["pieces"]), "without": len(without), "names": without[:6]}}
        except Exception as e:
            return {"stats": {"pieces": 0, "without": 0, "names": [], "error": str(e)}}

    # -- what's in the game, what Install builds, what was installed before ------------------------
    # An install adds the basket to what earlier installs put in the game (the last install's record)
    # - minus what's taken out - and the basket empties: what it held is in the game now.
    def in_game(self) -> list:
        """The entries the last install put in the game."""
        return list((self.direct.last_install() or {}).get("basket") or [])

    def _take_out_path(self) -> str:
        return os.path.join(self.direct.work, "workbench-take-out.json")

    def take_out(self) -> list[str]:
        """The keys of entries in the game the next install takes out."""
        got = J.load_json(self._take_out_path(), [])
        return [str(k) for k in got] if isinstance(got, list) else []

    def set_take_out(self, key: str, out: bool) -> None:
        if key not in {C.entry_key(e) for e in self.in_game()}:
            raise LookupError("that isn't in the game")
        keys = set(self.take_out())
        keys = keys | {key} if out else keys - {key}
        J.save_json(self._take_out_path(), sorted(keys))

    def install_list(self) -> list:
        """What Install builds: what's in the game (but what's taken out), then the basket - a basket
        entry stands for the game's entry of the same key (its pieces left out, say)."""
        basket = self.basket()
        skip = {C.entry_key(e) for e in basket} | set(self.take_out())
        return [e for e in self.in_game() if C.entry_key(e) not in skip] + basket

    def install_plan(self) -> dict:
        return C.plan_basket(self.catalogs, self.install_list())

    def history(self) -> list:
        """The last five installs, newest first: the ones this workbench recorded (tried or done), and
        the install records it has none for (made before it kept a history, or undone - Undo keeps a
        record as install.json.undone): each one's basket worked out as what it added to the install
        before it, and what it took out."""
        got = J.load_json(self._history_path(), [])
        rec = [h for h in got if isinstance(h, dict)] if isinstance(got, list) else []
        have = {h.get("time") for h in rec}
        root = os.path.join(self.direct.work, "backups")
        prev: list = []
        for stamp in sorted(os.listdir(root)) if root and os.path.isdir(root) else []:
            for name, undone in (("install.json", False), ("install.json.undone", True)):
                r = J.load_json(os.path.join(root, stamp, name), None)
                if not isinstance(r, dict) or r.get("basket") is None:
                    continue
                keys = {C.entry_key(e) for e in r["basket"]}
                before = {C.entry_key(e) for e in prev}
                t = r.get("time") or stamp
                if t not in have:
                    rec.append({"time": t, "result": "undone" if undone else "installed", "step": "",
                                "basket": [e for e in r["basket"] if C.entry_key(e) not in before],
                                "taken_out": [e for e in prev if C.entry_key(e) not in keys]})
                if not undone:
                    prev = r["basket"]
        return sorted(rec, key=lambda h: str(h.get("time")), reverse=True)[:5]

    def _history_path(self) -> str:
        """The install history (what's in the client) - the name an older workbench gave retail direct's."""
        return os.path.join(self.settings.data_dir, "basket-history-direct.json")

    def after_install(self, ok: bool, basket: list, taken_out: list) -> None:
        """An install ended: it goes in the history (the last five), and when it worked what it
        installed leaves the basket (it's in the game now) and the take-outs are done."""
        job = self.direct.job
        state = "installed" if ok else (job.state if job and job.state == "stopped" else "failed")
        last = self.direct.last_install() if ok else None       # the same time as the install's record
        rec = {"time": (last or {}).get("time") or time.strftime("%Y%m%d-%H%M%S"), "result": state,
               "step": "" if ok else (job.step if job else ""), "basket": basket, "taken_out": taken_out}
        got = J.load_json(self._history_path(), [])
        own = [h for h in got if isinstance(h, dict) and h.get("time") != rec["time"]] if isinstance(got, list) else []
        J.save_json(self._history_path(), [rec, *own][:5])
        if ok:
            done = {C.entry_key(e): e for e in basket}
            self.save_basket([e for e in self.basket() if done.get(C.entry_key(e)) != e])
            if self._take_out_path() and os.path.isfile(self._take_out_path()):
                os.remove(self._take_out_path())

    def install_status(self) -> dict:
        items = self.install_list()
        game = {C.entry_key(e) for e in self.in_game()}
        basket = self.basket()
        plan = C.plan_basket(self.catalogs, items)
        ready = all(e["state"] == "ready" for e in plan["entries"])
        looks = {C.look_stamp(l) for e in plan["entries"] for l in e["looks"] if l.get("display")}
        st = self.direct.status(looks if ready else None, {C.entry_key(e) for e in MT.basket_mounts(items)})
        st["mounts"] = len(MT.basket_mounts(items))
        last = st.get("last_install") or {}
        if last.get("mounts") and last.get("data"):
            changed = MP.stale(last["data"], self.direct.patch_name)
            if changed:
                st["mount_stale"] = changed
                st["installed"] = False
            gone = MP.item_rows_gone(last["data"], last)
            if gone:
                st["mount_icons_gone"] = gone
                st["installed"] = False
        src = self.sources.get("retail")
        if st["mounts"] and (src is None or src.spec.kind != "local"):
            st["mount_problem"] = "Mounts are made from your own retail install: set Retail items to \"My own install\" in Settings."
        return st | {"plan": {
            "basket": len(basket), "adds": sum(1 for e in basket if C.entry_key(e) not in game),
            "in_game": len(game), "take_out": len(set(self.take_out()) & game), "builds": len(items)}}

    def leave_out(self, display, out: bool) -> dict:
        """A piece (retail display) left out of every basket entry that has it - or put back."""
        d = str(int(display))
        basket, hit = self.basket(), 0
        keys = {C.entry_key(e) for e in basket}
        for e in self.in_game():                       # a piece of something in the game: its entry in the
            if C.entry_key(e) not in keys:             # basket stands for it from now on
                basket.append(json.loads(json.dumps(e)))
        plan = C.plan_basket(self.catalogs, basket)
        for e, p in zip(basket, plan["entries"]):
            if d not in {str(l.get("display")) for l in p["looks"] + p.get("left_out", [])}:
                continue
            skip = set(map(str, e.get("leave_out") or []))
            skip = skip | {d} if out else skip - {d}
            if skip:
                e["leave_out"] = sorted(skip, key=int)
            else:
                e.pop("leave_out", None)
            hit += 1
        if not hit:
            raise LookupError(f"no basket entry has look {d}")
        touched = [e for e, p in zip(basket, plan["entries"])
                   if C.entry_key(e) in keys or d in {str(l.get("display")) for l in p["looks"] + p.get("left_out", [])}]
        self.save_basket(touched)
        return self.basket_plan()

    def quit(self) -> None:
        """Another copy of the app takes over (app.py): this one stops - never in an install job."""
        if self.busy():
            raise RuntimeError("the workbench is busy with an install - wait for it to finish")
        self.quitting = True

    def page_seen(self, open_: bool) -> None:
        """A page says it's open (now and then) or that it's closing: the app ends with its last page."""
        with self._lock:
            if open_:
                self.last_hello = time.time()
            else:
                self.last_bye = time.time()

    # -- answers ----------------------------------------------------------------
    def status(self) -> dict:
        return {"sources": [{"key": k, "label": s.spec.label, "path": s.spec.path, "state": self.state.get(k),
                             "build": self.catalogs[k].build if k in self.catalogs else "",
                             "items": len(self.catalogs[k].items) if k in self.catalogs else 0,
                             "sets": len(self.catalogs[k].sets) if k in self.catalogs else 0}
                            for k, s in self.sources.items()],
                "client": self.settings.client, "in_client": len(self.in_client), "log": self.log[-40:],
                "problems": self.settings.problems(), "edition": {"key": edition.KEY, "name": edition.NAME,
                                                                  "client": edition.CLIENT_NAME, "exe": edition.CLIENT_EXE},
                "setup": not self.settings.client, "updated": code_stamp() > STARTED_CODE + 1,
                "app": app_info(), "instance": STARTED, "quitting": self.quitting}

    @staticmethod
    def meta() -> dict:
        return {"slots": C.SLOT_NAMES, "slot_groups": list(C.SLOT_GROUPS), "armour": C.ARMOUR_NAMES,
                "armour_types": list(C.ARMOUR_TYPES), "weapons": C.WEAPON_TYPES, "expansions": C.EXPANSIONS,
                "classes": C.CLASSES, "qualities": {k: {"name": n, "color": c} for k, (n, c) in C.QUALITIES.items()},
                "modifiers": C.MODIFIERS, "item_fields": C.ITEM_FIELDS,
                "item_geosets": {str(k): v for k, v in CH.ITEM_GEOSETS.items()}}

    def reader(self, key: str):
        """A source's reader by key - the BfA one too when it's read for its bodies only."""
        if key in self.sources:
            return self.sources[key]
        if key == "bfa" and self.bodies is not None:
            return self.bodies.src
        return None

    def catalog(self, key: str) -> C.Catalog:
        cat = self.catalogs.get(key) or (next(iter(self.catalogs.values())) if not key and self.catalogs else None)
        if cat is None:
            raise LookupError(f"source {key!r} is not loaded ({self.state.get(key, 'unknown')})")
        return cat

    def icon(self, key: str, fdid: int) -> bytes:
        return self.image("icons", key, fdid)

    def image(self, kind: str, key: str, fdid: int) -> bytes:
        """A PNG of a BLP FileDataID (an icon, a texture), cached on disk - a FileDataID is the same
        file in every build. From the source asked for, else from any other: BfA 8.3.7 keeps the
        art of its last sets encrypted - retail has it open."""
        path = os.path.join(self.settings.data_dir, kind, f"{fdid}.png")
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                return fh.read()
        from ..formats import blp
        first = self.reader(key)
        order = ([first] if first else []) + [s for k, s in self.sources.items() if s is not first]
        last = None
        for src in order:
            try:
                img = blp.decode_bytes(src.read(fdid), f"{kind} {fdid}")
                break
            except Exception as e:                      # encrypted, absent, unreadable: try the next
                last = e
        else:
            raise LookupError(f"{kind} {fdid}: {last}")
        buf = io.BytesIO()
        img.save(buf, "PNG", compress_level=3)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + f".{threading.get_ident()}.part"
        with open(tmp, "wb") as fh:
            fh.write(buf.getvalue())
        os.replace(tmp, path)
        return buf.getvalue()

    def displays(self, key: str) -> M.DisplayIndex:
        src = self.sources.get(key)
        if src is None:
            raise LookupError(f"no source {key!r}")
        if key not in self._displays:
            self._displays[key] = M.load_index(src, os.path.join(self.settings.data_dir, "cache"), self.say)
        return self._displays[key]

    # -- races, bodies, previews ----------------------------------------------------
    def races(self) -> list[dict]:
        """The races the 3.3.5 client plays, one per prefix, named as BfA names them (else the
        retail source), with their ids in BfA (the body) and in each item source."""
        if self._races is None:
            out = []
            if self.settings.client and os.path.isdir(self.settings.client):
                names = {}
                for key in self.sources:
                    try:
                        names.update({p: i for p, i in self.displays(key).prefixes.items() if p not in names})
                    except Exception:
                        pass
                bfa_races = self.bodies.races() if self.bodies else {}
                for r in CH.client_races(self.settings.client):
                    p = r["prefix"].lower()
                    b = bfa_races.get(p)
                    out.append({"key": p, "name": (b[1].get("Name_lang") if b else "") or r["prefix"], "client": r["ids"],
                                "bfa": b[0] if b else 0,
                                "sources": {k: self.displays(k).prefixes.get(p, 0) for k in self.catalogs}})
            if len(self.catalogs) < len(self.sources):
                return out                              # sources still loading: their ids come later
            self._races = out
        return self._races

    def race_ids(self, key: str, race: str) -> tuple[int, int]:
        """A race (prefix, or a number for that source) as (its id in the item source, its BfA id)."""
        if race.isdigit():
            return int(race), int(race)
        r = next((x for x in self.races() if x["key"] == race.lower()), None)
        if r is None:
            raise LookupError(f"no race {race!r}")
        return r["sources"].get(key) or r["bfa"] or 1, r["bfa"]

    def race_name(self, key: str, race: int) -> str:
        """A race id of a source by its ChrRaces name."""
        names = self._race_names.get(key)
        if names is None:
            try:
                names = {i: r.get("Name_lang") or r.get("ClientPrefix") or str(i) for i, r in self.reader(key).table("ChrRaces")}
            except Exception:
                names = {}
            self._race_names[key] = names
        return names.get(race, f"race {race}")

    def mesh(self, key: str, fdid: int, textures: dict, anim: int = 0) -> dict:
        k = (key, fdid, tuple(sorted(textures.items())), anim)
        if k not in self._meshes:
            if len(self._meshes) > 200:
                self._meshes.clear()
            self._meshes[k] = M.mesh(self.reader(key).read, fdid, textures, anim=anim)
        return self._meshes[k]

    def glows_of(self, key: str) -> dict[int, list]:
        """The source's item glows by visual (``glows.index``) over its ItemVisuals and ItemVisualsXEffect
        alone: the kit models it leaves out the client doesn't draw yet, and the kit tables take half a
        minute to read. {} for a source without them (BfA has them too)."""
        if key not in self._glows:
            src = self.reader(key)
            try:
                self._glows[key] = GL.index({n: src.table(n) for n in ("ItemVisuals", "ItemVisualsXEffect")})
            except Exception as e:
                self.say(f"{key}: item glows: {type(e).__name__}: {e}")
                self._glows[key] = {}
        return self._glows[key]

    def display_glows(self, key: str, display: int) -> list[dict]:
        """The glows the client hangs on a display's models (``glows.placements``): each with its model's
        mesh, the attachment point and scale - for the item the display is first the look of (a weapon's
        type picks its effect rows)."""
        visual = self.displays(key).visual.get(display)
        if not visual:
            return []
        cat = self.catalogs.get(key)
        item = None
        if cat is not None:
            first = (cat.display_items().get(display) or [None])[0]
            r = cat.by_id.get(first) if first else None
            item = {"ClassID": r[C.F["cls"]], "SubclassID": r[C.F["sub"]]} if r else None
        out = []
        for g in GL.placements(self.glows_of(key).get(visual), item)[:16]:
            try:
                out.append({"fdid": g.fdid, "point": g.point, "scale": g.scale, "mesh": self.mesh(key, g.fdid, {})})
            except Exception:                           # one glow that won't read never hides the item
                continue
        return out

    def preview(self, key: str, display: int, race: str, sex: int, slot: int = 0) -> dict:
        """An item display's models (as meshes, with Stand) and body textures, for that race and sex;
        ``slot``, the item's inventory type, says which models are collections as the client does."""
        idx = self.displays(key)
        item_race, _bfa = self.race_ids(key, race)
        out = {"display": display, "race": race, "sex": sex, "models": [], "problems": [],
               "body": idx.body_textures(display, item_race, sex), "row": idx.row(display), "made_for": "", "shown_as": "",
               "particle": idx.particle.get(display)}         # its emitters' colours (slots 11-13), as the client's
        found = idx.models(display, item_race, sex, slot)
        races = idx.model_races(display)
        if not found and races:
            # no model for this race (heritage armour is made for one): show another race's - one the
            # 3.3.5 client plays first - and say whose
            played = {r["sources"].get(key) for r in self.races()}
            other = next((r for r in races if r in played), races[0])
            found = idx.models(display, other, sex, slot)
            out["shown_as"] = self.race_name(key, other)
            if len(races) <= 3:
                out["made_for"] = ", ".join(self.race_name(key, r) for r in races)
        for m in found:
            try:
                out["models"].append(m | {"mesh": self.mesh(key, m["fdid"], m["textures"])})
            except Exception as e:                      # one bad model never hides the rest
                out["problems"].append(f"model {m['fdid']}: {type(e).__name__}: {e}")
        out["glows"] = self.display_glows(key, display) if out["models"] else []
        return out

    def mount_catalog(self, key: str) -> MT.MountCatalog:
        cat = self.mount_catalogs.get(key) or (next(iter(self.mount_catalogs.values()), None) if not key else None)
        if cat is None:
            raise LookupError("retail's mounts are still loading" if key in self.catalogs or not key else
                              f"source {key!r} has no mounts loaded")
        return cat

    def mount_preview(self, key: str, display: int) -> dict:
        """A mount's display as the 3D preview draws it: its model (with Stand) wearing the display's
        skins, the parts its geoset data shows, what 3.3.5 can't show of it."""
        cat = self.mount_catalog(key)
        d = cat.displays.get(int(display))
        if d is None:
            raise LookupError(f"no mount display {display}")
        # its skins on the model's texture types as the client puts them: 11-13, and a fourth on type 5
        # (mounts.SKIN_TYPES: the client's ReplaceMonsterSkin, from Install's skin table)
        textures = {MT.SKIN_TYPES[i]: f for i, f in enumerate((d.get("textures") or [])[:len(MT.SKIN_TYPES)]) if f}
        packed, lost = MT.geoset_data(d.get("geosets"))
        out = {"display": int(display), "model": d.get("model"), "textures": [f for f in d.get("textures") or [] if f],
               "geosets": {str(g): v for g, v in MT.geosets_shown(packed).items()}, "problems": [], "mesh": None,
               "particle": d.get("particle"),                 # its emitters' colours (slots 11-13)
               # its state kit as the x64 client draws it (DisplayStates.cpp): the models it hangs on the mount, its
               # gradient shading, and its dissolve - only the blend style's (flag 0x2000), as the client's
               "state": [], "gradient": d.get("gradient"),
               "dissolve": d.get("dissolve") if (d.get("dissolve") or {}).get("flags", 0) & 0x2000 else None}
        if lost:
            out["problems"].append(f"3.3.5 can't choose some of its parts ({lost}): they all show")
        try:
            out["mesh"] = self.mesh(cat.source, d["model"], textures)
        except Exception as e:
            out["problems"].append(f"model {d.get('model')}: {type(e).__name__}: {e}")
        for s in (d.get("state") or [])[:8] if out["mesh"] else []:
            try:
                out["state"].append(s | {"mesh": self.mesh(cat.source, s["model"], {}, s.get("anim") or 0)})
            except Exception as e:                      # one kit model that won't read never hides the mount
                out["problems"].append(f"state kit model {s.get('model')}: {type(e).__name__}: {e}")
        return out

    def body(self, race: str, sex: int) -> dict:
        if self.bodies is None:
            raise LookupError("the character view needs BfA's bodies (Settings: BfA from wago.tools or a local install)")
        _item, bfa = self.race_ids("bfa", race)
        return self.bodies.body(bfa, sex)

    def outfit(self, key: str, race: str, sex: int, items: list[tuple[int, int]]) -> dict:
        """What each (display, inventory type) puts on the body: its geoset values, section textures,
        the body groups a helm hides, and its models - attached at a body point, or a collection
        skinned to the body."""
        idx = self.displays(key)
        item_race, _bfa = self.race_ids(key, race)
        pieces, problems = [], []
        for display, slot in items:
            row = idx.row(display)
            if row is None:
                continue
            piece = {"display": display, "slot": slot, "row": row, "body": idx.body_textures(display, item_race, sex),
                     "hides": idx.helmet_hidden(display, item_race, sex) if slot == 1 else [], "models": [],
                     # a cloak paints the body's cape geosets (M2 texture type 2) with its material
                     "cape": idx.texture(row["materials"][0], item_race, sex) if slot == 16 and row["materials"][0] else 0,
                     "particle": idx.particle.get(display)}       # its emitters' colours (slots 11-13)
            for m in idx.models(display, item_race, sex, slot):
                if m["type"] == M.ATTACHED and m["attach"] < 0:     # a held item: its hand or back
                    m = m | {"attach": CH.ATTACH_POINTS.get(slot, -1)}
                try:
                    piece["models"].append(m | {"mesh": self.mesh(key, m["fdid"], m["textures"])})
                except Exception as e:
                    problems.append(f"display {display} model {m['fdid']}: {type(e).__name__}: {e}")
            piece["glows"] = self.display_glows(key, display) if piece["models"] else []
            races = idx.model_races(display)
            if not piece["models"] and races:               # heritage armour of another race
                piece["made_for"] = ", ".join(self.race_name(key, r) for r in races) if len(races) <= 3 else \
                    "other races"
            pieces.append(piece)
        return {"race": race, "sex": sex, "pieces": pieces, "problems": problems,
                "item_geosets": {str(k): v for k, v in CH.ITEM_GEOSETS.items()}, "dress_order": CH.DRESS_ORDER}

    def run(self, action: str) -> None:
        """Install's jobs: go (build and install), build, undo, check (in the client), stop."""
        d = self.direct
        if action == "stop":
            return d.stop()
        if action in ("go", "build"):
            items, basket = self.install_list(), self.basket()
            plan = C.plan_basket(self.catalogs, items)
            waiting = [e["name"] for e in plan["entries"] if e["state"] != "ready"]
            if waiting:
                raise RuntimeError(f"{waiting[0] or 'an entry'}: its catalog is still loading")
            out = [e for e in self.in_game() if C.entry_key(e) in set(self.take_out())]
            if action == "build":
                return d.start("build", d.go, items, plan, False)

            def go() -> bool:
                ok = False
                try:
                    ok = d.go(items, plan)
                    return ok
                finally:
                    self.after_install(ok, basket, out)
            return d.start("go", go)
        if action == "undo":
            return d.start("undo", d.undo)
        if action == "check":                        # the installed models, read by the client itself
            return d.start("check", d.client_check)
        raise ValueError(f"Install has no {action!r} - it builds everything in one go")

    # -- settings (the page's Settings view) ---------------------------------------
    def settings_view(self) -> dict:
        st = self.settings
        specs = {sp.key: sp for sp in st.effective_sources()}
        src = lambda k: {"kind": specs[k].kind, "path": specs[k].path, "browse": specs[k].browse}
        return {"client": st.client, "retail": src("retail"), "bfa": src("bfa"), "dbd": st.dbd, "listfile": st.listfile,
                "direct": {"work": self.direct.work}, "checks": self.checks(), "first_run": not st.client,
                "data_dir": st.data_dir, "picker": P.available()}

    def checks(self) -> dict:
        """Each setting's folder or file looked at: {name: [ok, what was found]}."""
        st = self.settings
        out: dict[str, list] = {}

        def put(name, ok, text):
            out[name] = [ok, text]
        c = st.client
        if c:
            data = os.path.isdir(os.path.join(c, "Data"))
            exe = J.is_client(c)
            put("client", data and exe, (edition.CLIENT_NAME[0].upper() + edition.CLIENT_NAME[1:] +
                                         (f": {len(self.in_client):,} items" if self.in_client else "")) if data and exe else
                f"no {edition.CLIENT_EXE} here" if data else "no Data folder here")
        for sp in st.effective_sources():
            if sp.kind == "local":
                why = st.source_problem(sp)
                build = ""
                if os.path.isfile(os.path.join(sp.path or "", ".build.info")):
                    try:
                        from pathlib import Path
                        from wotlkconv.casc.config import BuildInfo
                        build = BuildInfo.load(Path(sp.path), sp.product).version
                    except Exception:
                        pass
                put(sp.key, not why, why.split(": ", 1)[-1] if why else f"{sp.label} {build}".strip())
        if st.dbd:
            ok = os.path.isfile(os.path.join(st.dbd, "ChrRaces.dbd"))
            put("dbd", ok, "WoWDBDefs definitions" if ok else "no .dbd files here")
        if st.listfile:
            put("listfile", os.path.isfile(st.listfile), "listfile" if os.path.isfile(st.listfile) else "no such file")
        why = self.direct.problems()
        put("install", not why, why[0] if why else f"Retail's own items go into {edition.CLIENT_NAME}'s " +
            self.direct.patch_name)
        return out

    def apply_settings(self, v: dict) -> None:
        """The Settings view saved: the sources and the client; a changed source is read again."""
        if self.busy():
            raise RuntimeError("an install is running - change the settings when its job is done")
        st = self.settings
        norm = lambda p: os.path.normpath(str(p).strip().strip('"')) if str(p or "").strip() else ""
        st.client = norm(v.get("client", st.client))
        for key, label, product in (("retail", "Retail", "wow"), ("bfa", "BfA", None)):
            x = v.get(key) or {}
            default = next(d for d in DEFAULT_SOURCES if d["key"] == key)
            if x.get("kind") == "local":
                spec = asdict(C.SourceSpec(key, label, norm(x.get("path")), product, key == "retail", "local",
                                           browse=key == "retail" or bool(x.get("browse"))))
            else:
                spec = dict(default, browse=key == "retail" or bool(x.get("browse")))
            st.sources = [s for s in st.sources if s.get("key") != key] + [spec]
        st.dbd, st.listfile = norm(v.get("dbd", st.dbd)), norm(v.get("listfile", st.listfile))
        st.save()
        self.configure()
        self.start()

    def basket_plan(self) -> dict:
        """The basket's entries and their looks; what's in the game (each marked when the next install
        takes it out); the install history."""
        last = self.direct.last_install()
        plan = C.plan_basket(self.catalogs, self.basket())
        game = C.plan_basket(self.catalogs, self.in_game())["entries"]
        out = set(self.take_out())
        keys = {e["key"] for e in plan["entries"]}
        for e in game:
            e["take_out"] = e["key"] in out
        for e in plan["entries"]:
            e["in_game"] = any(g["key"] == e["key"] for g in game)
        plan["in_game"] = [e for e in game if e["key"] not in keys or e["take_out"]]
        plan["installed_at"] = last["time"] if last else ""
        plan["history"] = self.history()
        return plan

    def basket(self) -> list:
        # requests run on threads: a read holding the file open makes Windows refuse a save's replace
        with self._basket_lock:
            try:
                with open(self.basket_path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                return []

    def save_basket(self, entries: list) -> None:
        if not isinstance(entries, list):
            raise ValueError("the basket is a list")
        with self._basket_lock:
            os.makedirs(os.path.dirname(self.basket_path), exist_ok=True)
            tmp = self.basket_path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, indent=1)
            os.replace(tmp, self.basket_path)


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def make_handler(wb: Workbench):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RetroportWorkbench/1"

        def log_message(self, fmt, *args):            # quiet: the page polls
            pass

        def _send(self, body: bytes, ctype: str, status: int = 200, cache: bool = False) -> None:
            zipped = len(body) > 2048 and ctype.startswith(("application/json", "text/")) and \
                "gzip" in (self.headers.get("Accept-Encoding") or "")
            if zipped:
                body = gzip.compress(body, 5)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if zipped:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(json.dumps(obj, separators=(",", ":")).encode("utf-8"), "application/json", status)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                self._route(url.path, q)
            except LookupError as e:
                self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except Exception as e:                      # one bad request never stops the server
                traceback.print_exc()
                self._json({"error": f"{type(e).__name__}: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            try:
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(size) or b"null")
                if url.path == "/api/basket":
                    wb.save_basket(body)
                    self._json({"ok": True, "count": len(body)})
                elif url.path == "/api/quit":                    # another copy of the app takes over
                    wb.quit()
                    self._json({"ok": True})
                elif url.path in ("/api/hello", "/api/bye"):     # a page open / closing (the app's lifetime)
                    wb.page_seen(url.path.endswith("hello"))
                    self._json({"ok": True})
                elif url.path == "/api/stats":
                    IS.save(wb.settings.data_dir, body or {})
                    self._json({"ok": True})
                elif url.path == "/api/basket/take-out":
                    wb.set_take_out(str((body or {}).get("key") or ""), bool((body or {}).get("out", True)))
                    self._json(wb.basket_plan())
                elif url.path == "/api/basket/leave-out":
                    self._json(wb.leave_out((body or {}).get("display"), bool((body or {}).get("out", True))))
                elif url.path == "/api/settings":
                    wb.apply_settings(body or {})
                    self._json(wb.settings_view())
                elif url.path == "/api/pick":
                    b = body or {}
                    patterns = [tuple(x) for x in b.get("patterns") or []] or None
                    self._json({"path": P.pick(bool(b.get("folder", True)), b.get("title", ""), b.get("start", ""), patterns)})
                elif url.path == "/api/install/run":
                    wb.run((body or {}).get("action", ""))
                    self._json(wb.install_status())
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, TypeError) as e:
                self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            except RuntimeError as e:                   # busy, or not set up
                self._json({"error": str(e)}, HTTPStatus.CONFLICT)
            except Exception as e:                      # one bad request never stops the server
                traceback.print_exc()
                self._json({"error": f"{type(e).__name__}: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _route(self, path: str, q: dict) -> None:
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path.startswith("/tex/"):
                parts = path.split("/")                 # /tex/<source>/<fdid>.png
                if len(parts) != 4 or not parts[3].endswith(".png") or not parts[3][:-4].isdigit():
                    raise LookupError("bad texture path")
                return self._send(wb.image("textures", parts[2], int(parts[3][:-4])), "image/png", cache=True)
            if path == "/api/preview":
                return self._json(wb.preview(q.get("source", "") or next(iter(wb.catalogs), ""), _int(q.get("display")) or 0,
                                             q.get("race", "hu"), _int(q.get("sex")) or 0, _int(q.get("slot")) or 0))
            if path == "/api/races":
                return self._json(wb.races())
            if path == "/api/body":
                return self._json(wb.body(q.get("race", "hu"), _int(q.get("sex")) or 0))
            if path == "/api/outfit":
                items = []
                for part in (q.get("items") or "").split(","):
                    d, _sep, slot = part.partition(":")
                    if d.isdigit():
                        items.append((int(d), int(slot) if slot.isdigit() else 0))
                return self._json(wb.outfit(q.get("source", "") or next(iter(wb.catalogs), ""), q.get("race", "hu"),
                                            _int(q.get("sex")) or 0, items))
            if path.startswith("/icon/"):
                parts = path.split("/")                 # /icon/<source>/<fdid>.png
                if len(parts) != 4 or not parts[3].endswith(".png") or not parts[3][:-4].isdigit():
                    raise LookupError("bad icon path")
                return self._send(wb.icon(parts[2], int(parts[3][:-4])), "image/png", cache=True)
            if path == "/api/status":
                return self._json(wb.status())
            if path == "/api/meta":
                return self._json(wb.meta())
            if path == "/api/basket":
                return self._json(wb.basket())
            if path == "/api/settings":
                return self._json(wb.settings_view())
            if path == "/api/stats":
                return self._json(wb.stats_pieces())
            if path == "/api/stats/options":
                return self._json(wb.stats_options())
            if path == "/api/stats/reference":
                return self._json(WK.search(wb.reference(), q.get("q", ""), _int(q.get("inv")) or 0,
                                            _int(q.get("cls")) or 0, _int(q.get("sub")) if q.get("sub") else -1))
            if path == "/api/stats/spell":
                got = IS.spell_lookup(wb.settings.client, _int(q.get("id")) or 0) if wb.settings.client else None
                if got is None:
                    raise LookupError("no such spell in your client")
                return self._json(got)
            if path == "/api/basket/plan":
                return self._json(wb.basket_plan())
            if path == "/api/install":
                return self._json(wb.install_status() | wb.install_notes())
            if path == "/api/install/log":
                return self._json(wb.direct.log_since(_int(q.get("since")) or 0))
            if path == "/api/mounts":
                mc = wb.mount_catalog(q.get("source", ""))
                page = _int(q.get("page")) or 0
                total, rows = mc.search(q.get("q", ""), q.get("kind", ""), page=page, junk=q.get("junk") == "1")
                return self._json({"total": total, "page": page, "source": mc.source, "mounts": rows})
            if path == "/api/mount":
                mc = wb.mount_catalog(q.get("source", ""))
                d = mc.detail(_int(q.get("id")) or 0)
                if d is None:
                    raise LookupError("no such mount")
                return self._json(d | {"source": mc.source})
            if path == "/api/mount/preview":
                return self._json(wb.mount_preview(q.get("source", ""), _int(q.get("display")) or 0))
            cat = wb.catalog(q.get("source", ""))
            page = _int(q.get("page")) or 0
            if path == "/api/items":
                total, rows = cat.search_items(
                    q=q.get("q", ""), slot=q.get("slot", ""), armour=q.get("armour", ""), weapon=_int(q.get("weapon")),
                    expansion=_int(q.get("expansion")), quality=_int(q.get("quality")), cls=_int(q.get("cls")),
                    looks=q.get("looks") == "1", sort=q.get("sort", ""), page=page, junk=q.get("junk") == "1")
                return self._json({"total": total, "page": page, "source": cat.source,
                                   "items": [cat.row_dict(r) for r in rows]})
            if path == "/api/item":
                d = cat.item_detail(_int(q.get("id")) or 0)
                if d is None:
                    raise LookupError("no such item")
                return self._json(d | {"source": cat.source})
            if path == "/api/sets":
                if q.get("kind") == "itemset":
                    total, rows = cat.search_item_sets(q.get("q", ""), page=page)
                else:
                    total, rows = cat.search_sets(q.get("q", ""), expansion=_int(q.get("expansion")),
                                                  cls=_int(q.get("cls")), armour=q.get("armour", ""), page=page,
                                                  junk=q.get("junk") == "1")
                return self._json({"total": total, "page": page, "source": cat.source, "sets": rows})
            if path == "/api/set":
                sid = _int(q.get("id")) or 0
                d = cat.item_set_detail(sid) if q.get("kind") == "itemset" else cat.set_detail(sid)
                if d is None:
                    raise LookupError("no such set")
                return self._json(d | {"source": cat.source, "kind": q.get("kind") or "transmog"})
            raise LookupError(f"no route {path}")

        def _static(self, rel: str) -> None:
            full = os.path.realpath(os.path.join(STATIC, rel))
            if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
                raise LookupError(rel)
            with open(full, "rb") as fh:
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                self._send(fh.read(), ctype)

    return Handler


class _Server(ThreadingHTTPServer):
    # one workbench per port: Windows lets a second server bind a port the first still listens on,
    # and the first goes on answering - with its older code
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def start_server(settings: Settings, port: int = PORT) -> tuple[_Server, Workbench]:
    """The workbench listening on ``port`` (OSError when it's taken), its catalogs loading; the
    caller runs ``serve_forever``."""
    wb = Workbench(settings)
    httpd = _Server(("127.0.0.1", port), make_handler(wb))
    wb.start()
    return httpd, wb


def serve(settings: Settings, port: int = PORT, open_browser: bool = True, log=print) -> None:
    url = f"http://127.0.0.1:{port}/"
    wb = Workbench(settings)
    try:
        httpd = _Server(("127.0.0.1", port), make_handler(wb))
    except OSError as e:
        log(f"Port {port} is in use ({e.strerror or e}): the workbench is probably running already at {url} - "
            "close its window to restart it.")
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        return
    wb.start()
    log(f"{edition.NAME}: {url}  (Ctrl+C stops it)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
