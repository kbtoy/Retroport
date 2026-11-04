"""The retail backport kit, driven from the workbench: its project, its steps, install and undo.

The kit (wow-retail-backport) and Equip Plus's tools are run as programs, never imported or
copied: the kit through ``kitlocal`` (retail from the local install) when the project is pinned to
that install's build, else as it is (wago.tools). What the console Backport Helper does, the page
does the same way, so either can carry on from the other:

* the kit and Equip Plus's tools are always the workbench's own copies, downloaded by the first
  Install at the commits ``deps`` pins - the same code for everyone, whatever else is on the disk;
* settings come from the helper's ``%USERPROFILE%\\.wxl-equip-plus\\helper.json`` (client Data,
  project, server dbc) unless the workbench's own settings say otherwise;
* the kit's ``newtech`` stopping on retail features it hasn't seen is answered with its own
  ``newtech --learn`` and the check again (the audit still checks every file the build makes);
* the steps are the kit's (its ledger ``<work>/reports/steps.json`` says which passed); a re-scan
  moves the kit's own patch out of Data while it reads the client, as the helper does;
* install backs up what it replaces under ``<work>/backups/<time>/`` with an ``install.json``
  record (the helper's format, plus the basket it put in) and points the helper's ``last_backup``
  at it, so either one's Undo puts it back. It converts the kit's 3D pieces for Equip Plus, places
  the kit's patches, clears the client's Cache, and merges the server's Item/ItemDisplayInfo.dbc.
  It never runs SQL: the item SQL is shown for you to apply.

The page's Install button is ``go``: project, selection, steps and install in one job, each only
when it's needed (an unchanged basket isn't selected or built again).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field

from . import deps
from . import eprows as EP
from . import itemids
from . import kitlocal as KL

HELPER_SETTINGS = os.path.join(os.path.expanduser("~"), ".wxl-equip-plus", "helper.json")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STEPS = ["fetch", "newtech", "measure", "build", "tables", "audit", "prove-gates", "pack", "sheet"]
ORDER = ["scan", "select", *STEPS]
STEP_WORDS = {
    "scan": "Read the client (races, bodies, tables)",
    "select": "Work out every file the selection needs",
    "fetch": "Get the retail files",
    "newtech": "Check for retail technology the kit doesn't know",
    "measure": "Measure how helms sit on your bodies",
    "build": "Convert models and textures",
    "tables": "Write the item tables and server SQL",
    "audit": "Check for crashes, holes, floating parts",
    "prove-gates": "Prove the checks themselves work",
    "pack": "Pack the patch",
    "sheet": "Draw the preview pictures (into the project's sheets folder)",
}
SERVER_TABLES = ("Item", "ItemDisplayInfo")


@dataclass
class KitSettings:
    bp: str = ""                 # the kit's scripts\bp.py (the workbench's own copy)
    work: str = ""               # the kit project folder
    client_data: str = ""        # the 3.3.5 client's Data folder
    server_dbc: str = ""         # the server's dbc folder ("" = leave the server alone)
    tools: str = ""              # Equip Plus's tools folder (the workbench's own copy)
    local: bool = True           # retail from the local install when the project is pinned to its build
    armor_pieces: bool = True    # Equip Plus: also the pieces skinned to retail's HD skeletons
    equip_plus: str = "auto"     # its 3D pieces: "auto" (when the client has Equip Plus), "on", "off"


def _load_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)


OWN_COPIES = ("bp", "tools")      # never a setting: always the workbench's own copies


def helper_defaults(data_dir: str = "") -> KitSettings:
    """The Backport Helper's settings as the kit's, where it has any (never its kit: the workbench
    runs its own copies, ``deps``), else a project folder of the workbench's own."""
    h = _load_json(HELPER_SETTINGS, {}) or {}
    work = h.get("work", "") or (os.path.join(data_dir, "backport-project") if data_dir else "")
    return KitSettings(bp=deps.entry(data_dir, "kit") if data_dir else "", work=work,
                       client_data=h.get("client_data", ""), server_dbc=h.get("server_dbc", ""),
                       tools=os.path.dirname(deps.entry(data_dir, "equip-plus")) if data_dir else "",
                       armor_pieces=bool(h.get("armor_pieces", True)))


def python_exe() -> str:
    """The Python the kit and Equip Plus's tools run with: this one - its console twin when this is
    pythonw (the workbench without a window of its own), so their output can be read."""
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        twin = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(twin):
            return twin
    return exe


X64_EXE = "WowClient64.exe"       # the x64 3.3.5 client (wowdecomp-dx11): Equip Plus's rows built in
CLIENT_EXES = ("Wow.exe", X64_EXE)


def is_x64_client(root: str) -> bool:
    """Whether the client folder holds the x64 client (it draws Equip Plus's pieces itself)."""
    return bool(root) and os.path.isfile(os.path.join(root, X64_EXE))


def wow_running() -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True).stdout.lower()
        return any(f'"{exe.lower()}"' in out for exe in CLIENT_EXES)
    except OSError:
        return False


PLACEMENT_WARNING = "P1 placement (warning)"   # kitlocal's name for a helm that sits a little off
RACE_NAMES = {"Hu": "Human", "Or": "Orc", "Dw": "Dwarf", "Ni": "Night Elf", "Sc": "Undead", "Ta": "Tauren",
              "Gn": "Gnome", "Tr": "Troll", "Be": "Blood Elf", "Dr": "Draenei", "Pa": "Pandaren", "Kt": "Kul Tiran",
              "Go": "Goblin", "Wo": "Worgen"}


def display_of(message: str, plan: dict) -> str:
    """The retail display an audit line is about: named in it (``d751019``, ``display 730387``) or
    the display whose model or texture the file it names was made from; "" when none is."""
    m = re.search(r"\(d(\d+)\b|\bdisplay (\d+)\b", message)
    if m and (m.group(1) or m.group(2)) in plan:
        return m.group(1) or m.group(2)
    low = message.lower()
    for d, p in plan.items():
        row = p.get("row") or {}
        for name in [*(row.get("model") or []), *(row.get("tex") or []), *(row.get("regions") or [])]:
            stem = os.path.splitext(str(name).replace("/", "\\").split("\\")[-1])[0].lower()
            if len(stem) > 5 and stem in low:
                return d
    return ""


def body_of(message: str) -> str:
    """The client body a helm file is for, from its name's race-and-sex suffix (``..._PaM.m2``)."""
    m = re.search(r"_([A-Z][a-z])([MF])\.m2\b", message)
    if not m:
        return ""
    return f"{RACE_NAMES.get(m.group(1), m.group(1))} {'male' if m.group(2) == 'M' else 'female'}"


def basket_args(basket: list[dict]) -> list[str]:
    """The kit's ``select`` arguments for a workbench basket (an item set: its pieces; a look: its
    retail display)."""
    out: list[str] = []
    for e in basket:
        ids = [e["id"]] if e.get("kind") in ("set", "item", "look") else list(e.get("items") or [])
        flag = {"set": "--set", "look": "--display"}.get(e.get("kind"), "--item")
        for i in ids:
            if [flag, str(i)] not in [out[k:k + 2] for k in range(0, len(out), 2)]:
                out += [flag, str(i)]
    return out


@dataclass
class Job:
    name: str
    state: str = "running"       # running, ok, failed, stopped
    started: float = field(default_factory=time.time)
    ended: float = 0.0
    step: str = ""
    done: list = field(default_factory=list)   # the steps this job has passed (or found passed), in order


class Kit:
    """The kit project the workbench drives. One job at a time; its output goes to ``lines``."""

    def __init__(self, own: dict | None, retail: dict | None, dbd: str, listfile: str, data_dir: str,
                 save: callable = lambda kit_settings: None):
        base = helper_defaults(data_dir)
        for k, v in (own or {}).items():
            if hasattr(base, k) and k not in OWN_COPIES and v not in ("", None):
                setattr(base, k, v)
        self.cfg = base
        self.retail = retail                   # the retail SourceSpec (dict), or None
        self.dbd, self.listfile, self.data_dir = dbd, listfile, data_dir
        self._save = save
        self.lines: list[str] = []
        self.first = 0                          # index of lines[0] (old lines are dropped)
        self.job: Job | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._retail_build = ""
        # the workbench's steps around the kit's: "built" (after the kit's steps, before install;
        # False stops) and "installed" (after the patches are in Data, before the server's tables)
        self.hooks: dict[str, callable] = {}

    # -- state ------------------------------------------------------------------
    def project(self) -> dict | None:
        return _load_json(os.path.join(self.cfg.work, "bp.json")) if self.cfg.work else None

    def ledger(self) -> dict:
        return _load_json(os.path.join(self.cfg.work, "reports", "steps.json"), {}) or {}

    def retail_build(self) -> str:
        if not self._retail_build and self.retail:
            try:
                from pathlib import Path
                from wotlkconv.casc.config import BuildInfo
                b = BuildInfo.load(Path(self.retail["path"]), self.retail.get("product"))
                self._retail_build = b.version or ""
            except Exception:
                self._retail_build = ""
        return self._retail_build

    def local_ok(self) -> bool:
        prj = self.project() or {}
        return bool(self.cfg.local and self.retail and prj.get("build") and prj.get("build") == self.retail_build())

    def patch_name(self) -> str:
        prj = self.project() or {}
        scan = _load_json(os.path.join(self.cfg.work, "client", "scan.json"), {}) or {}
        return prj.get("patch_name") or scan.get("patch_name") or ""

    def last_install(self) -> dict | None:
        root = os.path.join(self.cfg.work, "backups")
        if not os.path.isdir(root):
            return None
        for stamp in sorted(os.listdir(root), reverse=True):
            rec = _load_json(os.path.join(root, stamp, "install.json"))
            if rec:
                return rec | {"backup": os.path.join(root, stamp)}
        return None

    def sheets_folder(self) -> str:
        """Where the kit's sheet step draws its preview pictures ("" when it hasn't yet)."""
        d = os.path.join(self.cfg.work, "sheets") if self.cfg.work else ""
        return d if d and os.path.isdir(d) else ""

    def sql_files(self) -> list[str]:
        """The item SQL to apply: the Stats step's file (the kit's SQL with the stats after it) when
        it's newer than the kit's, else the kit's; and Equip Plus's brought-back items'."""
        out = []
        kit = os.path.join(self.cfg.work, "out", "sql", "item_template.sql")
        ours = os.path.join(self.cfg.work, "out", "sql", "retroport-items.sql")
        if os.path.isfile(ours) and (not os.path.isfile(kit) or _mtime(ours) >= _mtime(kit)):
            out.append(ours)
        elif os.path.isfile(kit):
            out.append(kit)
        rescue = os.path.join(self.cfg.work, "out", "equip-plus-rescue", "sql", "item_template.sql")
        if os.path.isfile(rescue):
            out.append(rescue)
        mounts = (self.last_install() or {}).get("mounts_sql")      # the workbench's mounts (mountpack)
        if mounts and os.path.isfile(mounts):
            out.append(mounts)
        return out

    def client_root(self) -> str:
        return os.path.dirname(os.path.normpath(self.cfg.client_data)) if self.cfg.client_data else ""

    def equip_plus_installed(self) -> bool:
        """Whether the client has WarcraftXL's Equip Plus (it draws the 3D pieces a stock client can't) -
        the x64 client reads Equip Plus's rows itself."""
        root = self.client_root()
        return bool(root) and (is_x64_client(root) or
                               os.path.isfile(os.path.join(root, "Extensions", "wxl-equip-plus", "wxl-equip-plus.dll")))

    def equip_plus_client(self) -> dict:
        """The client's Equip Plus: there at all, its DLL new enough for live physics (1.3.0), and
        the physics and fit options of its WXLExtendedEquipment.ini. The x64 client's is built in
        (``builtin``): Equip Plus 1.2's rows, no live physics and no INI."""
        root = self.client_root()
        folder = os.path.join(root, "Extensions", "wxl-equip-plus") if root else ""
        dll = os.path.join(folder, "wxl-equip-plus.dll")
        out = {"installed": bool(folder) and os.path.isfile(dll), "physics": False, "ini": os.path.join(folder, INI_NAME) if folder else "",
               "options": {"physics": False, "pivots": False, "scale": False}, "builtin": False}
        if is_x64_client(root):
            return out | {"installed": True, "builtin": True, "ini": ""}
        if out["installed"]:
            try:
                with open(dll, "rb") as fh:
                    out["physics"] = b"WXLEquipPlusPhysics.phy2" in fh.read()
            except OSError:
                pass
            ini = _read_ini(out["ini"])
            out["options"] = {"physics": ini.get(("physics", "enabled")) == "1",
                              "pivots": ini.get(("fit", "retargetpivots")) == "1",
                              "scale": ini.get(("fit", "retargetscale")) == "1"}
        return out

    def set_equip_plus_options(self, physics: bool, pivots: bool, scale: bool) -> bool:
        """Equip Plus's live physics and fit options in the client's WXLExtendedEquipment.ini - those
        keys only, the rest of the file as it was (a copy of it kept the first time). True if changed."""
        ep = self.equip_plus_client()
        if not ep["installed"] or ep["builtin"]:
            return False
        want ={("Physics", "Enabled"): physics, ("Fit", "RetargetPivots"): pivots, ("Fit", "RetargetScale"): scale}
        if all(ep["options"][k] == v for k, v in zip(("physics", "pivots", "scale"), want.values())):
            return False
        path = ep["ini"]
        if os.path.isfile(path) and not os.path.isfile(path + ".retroport-backup"):
            shutil.copy2(path, path + ".retroport-backup")
        _write_ini(path, {k: "1" if v else "0" for k, v in want.items()})
        return True

    def equip_plus_wanted(self) -> bool:
        mode = (self.cfg.equip_plus or "auto").lower()
        return mode == "on" or (mode == "auto" and self.equip_plus_installed())

    # -- looks the project holds that the workbench didn't put there --------------------------
    def built_looks(self) -> set[str]:
        """Every retail display this project has built (the kit's ids.json keeps them all)."""
        ids = _load_json(os.path.join(self.cfg.work, "ids.json"), {}) if self.cfg.work else {}
        return {str(d) for d in (ids.get("display") or {})}

    def known_looks(self) -> set[str]:
        """The looks the workbench selected itself, or was told it may drop."""
        rec = _load_json(os.path.join(self.cfg.work, "workbench-basket.json"), {}) if self.cfg.work else {}
        return {str(d) for d in (rec or {}).get("known") or []}

    def foreign_looks(self, basket_looks: set[str]) -> list[str]:
        """Looks the project built - with the Backport Helper, or an earlier tool - that aren't in the
        basket and that the workbench never chose: an Install would take them out of the game."""
        return sorted(self.built_looks() - self.known_looks() - {str(d) for d in basket_looks}, key=int)

    def let_go(self, looks) -> None:
        """The user said those looks may go (they'll be dropped by the next install)."""
        path = os.path.join(self.cfg.work, "workbench-basket.json")
        rec = _load_json(path, {}) or {}
        rec["known"] = sorted(set(map(str, rec.get("known") or [])) | {str(d) for d in looks}, key=int)
        _save_json(path, rec)

    def own_copies(self) -> dict:
        """The kit's and Equip Plus's tools' copies: {name: {label, ref (short), have (downloaded)}}."""
        return {name: {"label": deps.PINNED[name]["label"], "ref": deps.PINNED[name]["ref"][:7],
                       "repo": deps.PINNED[name]["repo"], "have": deps.have(self.data_dir, name)}
                for name in ("kit", "equip-plus")}

    def problems(self) -> list[str]:
        c = self.cfg
        out = []
        if not c.work:
            out.append("no project folder set")
        if not c.client_data or not os.path.isdir(c.client_data):
            out.append("the client's Data folder is not set")
        if sys.version_info < (3, 11):
            out.append("the kit needs Python 3.11 or newer")
        return out

    def client_changed(self) -> bool:
        """The project was made for another client than the one in Settings (the x64 client beside a
        Wow.exe one, say): its bp.json names that client's Data folder."""
        have = (self.project() or {}).get("client_data") or ""
        return bool(have and self.cfg.client_data) and \
            os.path.normcase(os.path.normpath(have)) != os.path.normcase(os.path.normpath(self.cfg.client_data))

    def follow_client(self) -> bool:
        """The project pointed at Settings' client (True when it was made for another one): its
        bp.json names this client, and the other client's measurements (helm placement, body geosets)
        go aside with a copy of its bp.json and scan.json, under backups\\client-<time>, so the kit
        reads and measures this client before it builds for it."""
        if not self.client_changed():
            return False
        work, prj = self.cfg.work, self.project()
        aside = os.path.join(work, "backups", "client-" + time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(aside, exist_ok=True)
        for n in ("bp.json", os.path.join("client", "scan.json")):
            if os.path.isfile(os.path.join(work, n)):
                shutil.copy2(os.path.join(work, n), os.path.join(aside, os.path.basename(n)))
        for n in KL.MEASUREMENTS:
            if os.path.isfile(os.path.join(work, "client", n)):
                shutil.move(os.path.join(work, "client", n), os.path.join(aside, n))
        _save_json(os.path.join(work, "bp.json"), dict(prj, client_data=self.cfg.client_data))
        self.say(f"The project was made for {prj.get('client_data')} - it follows the client in Settings now "
                 f"({self.cfg.client_data}): the kit reads this client and measures its bodies again. The other "
                 f"client's readings are kept in {aside}.")
        return True

    def selected(self) -> dict | None:
        """The basket the kit's selection was made from - while the selection is still that one (the
        console helper may have selected something else since)."""
        rec = _load_json(os.path.join(self.cfg.work, "workbench-basket.json")) if self.cfg.work else None
        if not rec or rec.get("selection_mtime") != _mtime(os.path.join(self.cfg.work, "selection.json")):
            return None
        return rec

    def selected_matches(self, basket: list[dict], args: list[str] | None = None) -> bool:
        """Whether the kit's selection was made from these ``args`` (the basket's own by default; an
        entry with pieces left out is selected as its other looks - the workbench works those out)."""
        rec = self.selected()
        return bool(rec and self.ledger().get("select", {}).get("ok")) and \
            _arg_pairs(rec.get("args") or basket_args(rec["basket"])) == _arg_pairs(args or basket_args(basket))

    def status(self, basket: list[dict] | None = None, args: list[str] | None = None) -> dict:
        prj = self.project()
        led = self.ledger()
        steps = [{"step": s, "words": STEP_WORDS[s], "ok": led.get(s, {}).get("ok"), "at": led.get(s, {}).get("at", "")}
                 for s in ORDER]
        job = asdict(self.job) if self.job else None
        last = self.last_install()
        built = basket is not None and self.selected_matches(basket, args) and all(led.get(s, {}).get("ok") for s in STEPS) \
            and not self.client_changed()
        packed = led.get("pack", {}).get("at", "").replace("-", "").replace(":", "").replace(" ", "-")
        return {"settings": asdict(self.cfg), "problems": self.problems(), "project": prj,
                "retail_build": self.retail_build(), "local": self.local_ok(), "patch_name": self.patch_name(),
                "steps": steps, "job": job, "sheets": self.sheets_folder(), "sql": self.sql_files(),
                "last_install": last, "next_line": self.first + len(self.lines), "selected": self.selected(),
                "equip_plus": {"installed": self.equip_plus_installed(), "wanted": self.equip_plus_wanted()},
                # the basket as it is: built (Install only copies), and in the client already
                "built": built, "installed": bool(built and last and packed and last["time"] >= packed),
                # the kit's measurements: needed once the selection holds something worn on the body
                "measure": {"needed": KL.wears_on_body(self.selection()) if self.cfg.work else False,
                            "done": KL.measured(self.cfg.work) if self.cfg.work else False}}

    def set_settings(self, values: dict) -> None:
        for k, v in values.items():
            if k in KitSettings.__dataclass_fields__ and k not in OWN_COPIES:
                setattr(self.cfg, k, bool(v) if isinstance(getattr(self.cfg, k), bool) else str(v or "").strip())
        self._save(asdict(self.cfg))

    # -- output -----------------------------------------------------------------
    def say(self, text: str) -> None:
        with self._lock:
            for line in str(text).splitlines() or [""]:
                self.lines.append(line)
            if len(self.lines) > 6000:
                drop = len(self.lines) - 5000
                del self.lines[:drop]
                self.first += drop

    def log_since(self, since: int) -> dict:
        with self._lock:
            start = max(since - self.first, 0)
            return {"lines": self.lines[start:], "next": self.first + len(self.lines),
                    "job": asdict(self.job) if self.job else None}

    # -- running ----------------------------------------------------------------
    def kit_command(self, args: list[str], local: bool | None = None) -> list[str]:
        """The kit run through ``kitlocal``: retail from the local install when ``local``, and the
        client's open-folder patches shown to it either way."""
        local = self.local_ok() if local is None else local
        cmd = [python_exe(), "-u", "-m", "retroport.workbench.kitlocal", "--bp", self.cfg.bp]
        if self.data_dir:
            cmd += ["--ids", itemids.path(self.data_dir)]
        if local and self.retail:
            cmd += ["--retail", self.retail["path"], "--product", self.retail.get("product") or "wow",
                    "--dbd", self.dbd, "--listfile", self.listfile, "--cache", os.path.join(self.data_dir, "cache")]
        return cmd + ["--", *args]

    def _run(self, args: list[str], step: str = "", local: bool | None = None, cwd: str | None = None) -> int:
        local = self.local_ok() if local is None else local
        cmd = self.kit_command(args, local)
        self.say(f"$ bp.py {' '.join(args)}" + ("   [retail from the local install]" if local and self.retail else ""))
        if self.job:
            self.job.step = step or args[0]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(cmd, cwd=cwd or os.path.dirname(self.cfg.bp), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._proc = proc
        for line in proc.stdout:
            self.say(line.rstrip("\n"))
        code = proc.wait()
        self._proc = None
        return code

    def _tool(self, script: str, args: list[str]) -> int:
        """One of Equip Plus's tools, as a program."""
        path = os.path.join(self.cfg.tools, script)
        if not os.path.isfile(path):
            self.say(f"!! {script} not found in {self.cfg.tools or '(Equip Plus tools folder not set)'}")
            return 1
        self.say(f"$ {script} {' '.join(args)}")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen([python_exe(), "-u", "-m", "retroport.workbench.runscript", path, *args],
                                cwd=self.cfg.tools, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._proc = proc
        for line in proc.stdout:
            self.say("    " + line.rstrip("\n"))
        code = proc.wait()
        self._proc = None
        return code

    def busy(self) -> bool:
        return bool(self.job and self.job.state == "running")

    def start(self, name: str, fn, *args) -> None:
        if self.busy():
            raise RuntimeError(f"the kit is busy ({self.job.name})")
        problems = [p for p in self.problems() if not (name == "create" and "project" in p)]
        if problems:
            raise RuntimeError("; ".join(problems))
        self.job = Job(name)
        self.say("")
        self.say(f"=== {name} ({time.strftime('%H:%M:%S')}) ===")

        def body():
            try:
                ok = fn(*args)
                if self.job.state == "running":
                    self.job.state = "ok" if ok else "failed"
            except Exception as e:                   # the page shows it; the server stays up
                self.say(f"!! {type(e).__name__}: {e}")
                self.job.state = "failed"
            finally:
                self.job.ended = time.time()
                self.say(f"=== {name}: {self.job.state} ===")
        threading.Thread(target=body, name=f"kit-{name}", daemon=True).start()

    def stop(self) -> None:
        if self.job and self.job.state == "running":
            self.job.state = "stopped"
            if self._proc:
                self._proc.terminate()
            self.say("!! stopped")

    # -- jobs -------------------------------------------------------------------
    def get_tools(self) -> bool:
        """The kit and Equip Plus's tools, downloaded from their GitHub when they aren't here yet (or
        are another commit than the pinned one)."""
        for name in ("kit", "equip-plus"):
            if not deps.have(self.data_dir, name):
                if self.job:
                    self.job.step = "tools"
                try:
                    deps.fetch(self.data_dir, name, self.say)
                except Exception as e:
                    self.say(f"!! {deps.PINNED[name]['label']} could not be downloaded: {e}")
                    return False
        return True

    def create(self) -> bool:
        """A new project pinned to the local retail build (so the kit reads retail from it)."""
        c = self.cfg
        if not c.work:
            self.say("!! choose a project folder first")
            return False
        if self.project():
            self.say(f"the project already exists: {c.work}")
            return True
        args = ["init", "--work", c.work, "--client", c.client_data, "--server", "azerothcore"]
        if self.retail_build():
            args += ["--build", self.retail_build()]
        return self._run(args, local=False) == 0

    def select(self, basket: list[dict], args: list[str] | None = None) -> bool:
        args = args or basket_args(basket)
        if not args:
            self.say("!! the basket is empty")
            return False
        if not self.ledger().get("scan", {}).get("ok") and not self.scan():
            return False
        ok = self._run(["select", "--work", self.cfg.work, *args]) == 0
        if ok:
            sel = _load_json(os.path.join(self.cfg.work, "selection.json"), {}) or {}
            path = os.path.join(self.cfg.work, "workbench-basket.json")
            known = set(map(str, (_load_json(path, {}) or {}).get("known") or [])) | set(map(str, sel.get("displays") or {}))
            _save_json(path, {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "basket": basket, "args": args,
                              "selection_mtime": _mtime(os.path.join(self.cfg.work, "selection.json")),
                              "known": sorted(known, key=int)})
        return ok

    def go(self, basket: list[dict], looks: set[str] | None = None, args: list[str] | None = None) -> bool:
        """The basket into the client and the server in one go: a project if there's none, the kit's
        selection when the basket changed (which un-ticks every step after it), every step that hasn't
        passed, then the install."""
        if not (args or basket_args(basket)):
            self.say("!! the basket is empty")
            return False
        if wow_running():
            self.say("!! close World of Warcraft first: the install replaces files it has open")
            return False
        foreign = self.foreign_looks(looks) if looks is not None else []
        if foreign:
            self.say(f"!! this project holds {len(foreign)} look(s) made outside the workbench (the Backport Helper?) "
                     "that aren't in your basket - an install would take them out of your game. Add them to the "
                     "basket (Basket page), or choose to let them go.")
            return False
        if not self.get_tools():
            return False
        if not self.project():
            self.job.step = "create"
            if not self.create():
                return False
            self.job.done.append("create")
        moved = self.follow_client()
        if moved and not self.scan():
            return False
        if not moved and self.selected_matches(basket, args):
            self.say("The kit's selection is this basket already.")
        elif not self.select(basket, args):
            return False
        self.job.done.append("select")
        if not self.build(then="install"):
            return False
        if self.hooks.get("built") and not self.hooks["built"](self):
            return False
        if not self.install():
            return False
        self.job.done.append("install")
        return True

    def scan(self) -> bool:
        """The kit's scan, with its own installed patch out of Data meanwhile (it must read the client
        without it - the helper does the same)."""
        data, name = self.cfg.client_data, self.patch_name()
        held = []
        hold = os.path.join(self.cfg.work, "backups", "scan-hold")
        if name and os.path.exists(os.path.join(data, name)):
            if wow_running():
                self.say("!! close World of Warcraft first: the kit's patch must move aside while it reads the client")
                return False
            os.makedirs(hold, exist_ok=True)
            shutil.move(os.path.join(data, name), os.path.join(hold, name))
            held.append(name)
            self.say(f"   {name} moved aside while the kit reads the client")
        try:
            return self._run(["scan", "--work", self.cfg.work], step="scan") == 0
        finally:
            for n in held:
                shutil.move(os.path.join(hold, n), os.path.join(data, n))
                self.say(f"   {n} put back")

    def build(self, rerun: str = "", then: str = "") -> bool:
        """Every step the ledger doesn't show passed, in order (``rerun``: that step and the ones after
        it again; ``then``: what comes next, for the last line)."""
        if not self.ledger().get("select", {}).get("ok"):
            self.say("!! nothing selected yet: send the basket to the kit first")
            return False
        if rerun == "scan" or not self.ledger().get("scan", {}).get("ok"):
            if not self.scan():
                return False
        self.job.done.append("scan")
        again = STEPS[STEPS.index(rerun):] if rerun in STEPS else []
        for step in STEPS:
            if self.job.state != "running":
                return False
            if self.ledger().get(step, {}).get("ok") and step not in again and \
                    not (step == "measure" and self.needs_measure()):
                self.job.done.append(step)
                continue
            if not self.step(step) and not (step == "newtech" and self.learn() and self.step(step)):
                self.say(f"!! {step} did not pass - its log: {os.path.join(self.cfg.work, 'logs', step + '.log')}")
                return False
            self.job.done.append(step)
            if step == "tables" and self.hooks.get("tables") and not self.hooks["tables"](self):
                return False
        self.say("Built." if then else f"Built - its preview pictures are in {os.path.join(self.cfg.work, 'sheets')}.")
        return True

    def audit_notes(self) -> dict:
        """The kit's last audit, for the Backport page: helms that sit a little off (warnings) and -
        when it stopped the install - what failed; each with the piece (display) it's about."""
        work = self.cfg.work
        rep = _load_json(os.path.join(work, "reports", "audit.json"), None) if work else None
        if not isinstance(rep, dict):
            return {"warnings": [], "fails": []}
        plan = _load_json(os.path.join(work, "build", "plan.json"), {}) or {}

        def grouped(lines, gate_of=lambda m: "") -> list[dict]:
            out: dict[str, dict] = {}
            for gate, m in lines:
                d = display_of(m, plan)
                items = (plan.get(d) or {}).get("items") or [{}]
                g = out.setdefault(d, {"display": d, "name": items[0].get("name") or (f"Look {d}" if d else "Other files"),
                                       "lines": [], "bodies": [], "gates": []})
                if m not in g["lines"] and len(g["lines"]) < 8:
                    g["lines"].append(m)
                body = body_of(m)
                if body and body not in g["bodies"]:
                    g["bodies"].append(body)
                if gate and gate not in g["gates"]:
                    g["gates"].append(gate)
            return list(out.values())
        warnings = grouped(("", m) for m in (rep.get("notes") or {}).get(PLACEMENT_WARNING, []))
        passed = bool(self.ledger().get("audit", {}).get("ok"))
        fails = [] if passed else grouped((g, m) for g, ms in (rep.get("fails") or {}).items() for m in ms)
        return {"warnings": warnings, "fails": fails}

    def selection(self) -> dict:
        return _load_json(os.path.join(self.cfg.work, "selection.json"), {}) or {}

    def needs_measure(self) -> bool:
        """The selection holds something worn on the body and the client isn't measured yet (kitlocal
        let the measure step pass without measuring while there was nothing to measure for)."""
        return KL.wears_on_body(self.selection()) and not KL.measured(self.cfg.work)

    def step(self, step: str) -> bool:
        """One of the kit's steps, passed (its ledger says so)."""
        extra = ["--extension"] if step == "build" else []
        return self._run([step, "--work", self.cfg.work, *extra], step=step) == 0 and \
            bool(self.ledger().get(step, {}).get("ok"))

    def learn(self) -> bool:
        """newtech stopped: retail uses something the kit hasn't seen (or it has nothing learned for
        this build yet). The kit learns what the project's retail files use - its own ``newtech
        --learn`` - and the check runs again; the audit still checks every file the build makes."""
        new = (_load_json(os.path.join(self.cfg.work, "reports", "newtech.json"), {}) or {}).get("new") or {}
        what = "; ".join(f"{k} {', '.join(map(str, v))}" for k, v in new.items()) if isinstance(new, dict) else ""
        self.say("Retail uses something the kit hasn't seen before" + (f" ({what})" if what else "") +
                 ": the kit learns it for this project and goes on - the audit still checks every file it makes")
        return self._run(["newtech", "--work", self.cfg.work, "--learn"], step="newtech") == 0

    def install(self) -> bool:
        c = self.cfg
        if self.job:
            self.job.step = "install"
        if not self.ledger().get("pack", {}).get("ok"):
            self.say("!! nothing packed yet: build first")
            return False
        if wow_running():
            self.say("!! close World of Warcraft first")
            return False
        out = os.path.join(c.work, "out")
        archives = sorted(f for f in os.listdir(out) if f.lower().endswith(".mpq") and os.path.isfile(os.path.join(out, f)))
        if not archives:
            self.say("!! the kit's out folder holds no patch")
            return False
        # Equip Plus's 3D pieces (a folder patch of their own)
        ep_root = os.path.join(out, "equip-plus")
        before = set(os.listdir(ep_root)) if os.path.isdir(ep_root) else set()
        ep_patch = None
        if self.equip_plus_wanted():
            code = self._tool("backport_to_equipplus.py", ["--work", c.work] + (["--armor-pieces"] if c.armor_pieces else []))
        else:
            code = None
            self.say("   Equip Plus isn't in this client: its 3D pieces (skirts, boot shells, buckles, 3D capes) are "
                     "left out - the items show as a stock client draws them")
        if code in (0, 2) and os.path.isdir(ep_root):
            made = [d for d in os.listdir(ep_root) if d.lower().startswith("patch-") and os.path.isdir(os.path.join(ep_root, d))]
            fresh = [d for d in made if d not in before] or made
            ep_patch = os.path.join(ep_root, sorted(fresh, key=lambda d: os.path.getmtime(os.path.join(ep_root, d)))[-1]) if fresh else None
        elif code is not None and code != 0:
            self.say("   (no Equip Plus pieces were made - see above; the kit's patch installs on its own)")
        if ep_patch and c.armor_pieces:
            EP.add(c.work, ep_patch, self.say)        # helms' and shoulders' collection parts (a hood)

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(c.work, "backups", stamp)
        sel = self.selected()
        record = {"time": stamp, "client": [], "server": [], "added": [], "by": "retroport workbench",
                  "basket": sel["basket"] if sel else None,          # what the patch holds, for the basket page
                  "data": c.client_data}                             # the client it went into (Undo puts back there)
        os.makedirs(os.path.join(backup, "client"), exist_ok=True)

        def place(src: str, name: str) -> None:
            dest = os.path.join(c.client_data, name)
            if os.path.exists(dest):
                _copy_any(dest, os.path.join(backup, "client", name))
                record["client"].append(name)
                _remove_any(dest)
            else:
                record["added"].append(dest)
            _copy_any(src, dest)
            self.say(f"   installed {name}")

        self.say(f"Backing up and installing (backup: {backup})")
        for a in archives:
            place(os.path.join(out, a), a)
        if ep_patch:
            place(ep_patch, os.path.basename(ep_patch))
        if self.hooks.get("installed"):
            self.hooks["installed"](self, record, backup)
        cache = os.path.join(os.path.dirname(c.client_data.rstrip("\\/")), "Cache")
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
            self.say("   cleared the client's Cache folder")
        if c.server_dbc:
            merged = os.path.join(out, "server-dbc")
            if self._tool("merge_server_dbc.py", ["--work", c.work, "--server", c.server_dbc, "--out", merged]) == 0:
                os.makedirs(os.path.join(backup, "server"), exist_ok=True)
                for name in SERVER_TABLES:
                    dest = os.path.join(c.server_dbc, name + ".dbc")
                    shutil.copy2(dest, os.path.join(backup, "server", name + ".dbc"))
                    shutil.copy2(os.path.join(merged, name + ".dbc"), dest)
                    record["server"].append(name + ".dbc")
                    self.say(f"   server: updated {name}.dbc")
            else:
                self.say("!! the server merge failed - the server's dbc folder was not touched")
        _save_json(os.path.join(backup, "install.json"), record)
        helper = _load_json(HELPER_SETTINGS, None)
        if isinstance(helper, dict) and helper.get("work") and os.path.normcase(os.path.abspath(helper["work"])) == \
                os.path.normcase(os.path.abspath(c.work)):
            helper["last_backup"] = backup                     # the helper's Undo knows this install too
            _save_json(HELPER_SETTINGS, helper)
        self.say("Installed. Restart the worldserver, then log in.")
        for sql in self.sql_files():
            self.say(f"Apply this SQL to your world database yourself: {sql}")
        return True

    def undo(self) -> bool:
        rec = self.last_install()
        if not rec:
            self.say("there is no install to undo")
            return False
        if wow_running():
            self.say("!! close World of Warcraft first")
            return False
        backup, c = rec["backup"], self.cfg
        data = rec.get("data") or c.client_data                      # older records: the one client there was
        for n in rec.get("client", []):
            _remove_any(os.path.join(data, n))
            _copy_any(os.path.join(backup, "client", n), os.path.join(data, n))
            self.say(f"   client: put back {n}")
        for p in rec.get("added", []):
            _remove_any(p)
            self.say(f"   client: removed {p}")
        for n in rec.get("server", []):
            shutil.copy2(os.path.join(backup, "server", n), os.path.join(c.server_dbc, n))
            self.say(f"   server: put back {n}")
        os.replace(os.path.join(backup, "install.json"), os.path.join(backup, "install.json.undone"))
        helper = _load_json(HELPER_SETTINGS, None)
        if isinstance(helper, dict) and helper.get("last_backup") == backup:
            helper["last_backup"] = ""
            _save_json(HELPER_SETTINGS, helper)
        self.say("Undone. Clear the client's Cache folder and restart the worldserver; the SQL rows stay "
                 "(they do nothing without the tables and patches).")
        return True


INI_NAME = "WXLExtendedEquipment.ini"
PHYSICS_VERSION = (1, 3, 0)                 # Equip Plus's first with live physics


def version_tuple(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:3])


def _read_ini(path: str) -> dict:
    """{(section, key): value}, lowercased names; a missing file is empty."""
    out, section = {}, ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                t = line.split(";", 1)[0].strip()
                if t.startswith("[") and t.endswith("]"):
                    section = t[1:-1].strip().lower()
                elif "=" in t:
                    k, v = t.split("=", 1)
                    out[(section, k.strip().lower())] = v.strip()
    except OSError:
        pass
    return out


def _write_ini(path: str, values: dict) -> None:
    """``values`` ({(Section, Key): value}) set in the INI at ``path``: a key it has keeps its line's
    place (and comment), a missing one goes at the end of its section, a missing section at the end."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    todo = dict(values)
    section, last_of = "", {}
    for i, line in enumerate(lines):
        t = line.split(";", 1)[0].strip()
        if t.startswith("[") and t.endswith("]"):
            section = t[1:-1].strip()
            last_of[section.lower()] = i
            continue
        if section:
            last_of[section.lower()] = i
        if "=" in t:
            k = t.split("=", 1)[0].strip()
            for (sec, key), v in list(todo.items()):
                if sec.lower() == section.lower() and key.lower() == k.lower():
                    comment = line[line.index(";"):] if ";" in line else ""
                    lines[i] = f"{key}={v}" + (f"          {comment}" if comment else "")
                    del todo[(sec, key)]
    for (sec, key), v in todo.items():
        at = last_of.get(sec.lower())
        if at is None:
            lines += ([""] if lines and lines[-1].strip() else []) + [f"[{sec}]"]
            at = len(lines) - 1
            last_of[sec.lower()] = at
        lines.insert(at + 1, f"{key}={v}")
        for s2, j in last_of.items():
            if j > at:
                last_of[s2] = j + 1
        last_of[sec.lower()] = at + 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(path + ".part", path)


def _mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _arg_pairs(args: list[str]) -> list[tuple[str, str]]:
    return sorted(zip(args[::2], args[1::2]))


def _copy_any(src: str, dst: str) -> None:
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def _remove_any(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
