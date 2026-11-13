"""Keep a folder MPQ in step with a package's files, copying only what changed.

The x64 client opens a folder in Data named like a patch MPQ (``Data\\patch-Z.MPQ\\``) as an archive in
that letter's place (above the letters before it, under the ones after) and reads its files from disk. So
an update is copying the files that changed into it - no MPQ to rebuild - and a package's files can be
taken out again.

Each package that syncs into a folder keeps a manifest of what it put there,
``<folder>\\.retroport-sync\\<package>.json`` (the client skips anything starting with "."):

* a file the source has and the folder lacks, or holds different bytes of, is copied (atomically);
* a file the package put there before and its source no longer has is removed - only if it still holds
  what the package put there (else it was changed by hand or by another package: left, and said);
* a file another package's manifest also lists is copied all the same, and said (the later sync wins).

The source is a folder of files at their game paths (a package's ``client\\`` folder, a wow.export
extraction) or a packed ``.MPQ`` (its ``(listfile)`` names the files).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from .safeio import write_verified

MANIFEST_DIR = ".retroport-sync"


def game_key(path: str) -> str:
    """A game path as the client keys it: lower case, backslashes, no leading separators."""
    key = path.replace("/", "\\").lower()
    while key.startswith("\\") or key.startswith(".\\"):
        key = key[1:] if key.startswith("\\") else key[2:]
    return key


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _sha1_file(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SyncResult:
    package: str
    folder: str
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: int = 0
    removed: list[str] = field(default_factory=list)
    left: list[str] = field(default_factory=list)       # removed from the source but changed in the folder: kept
    shared: list[str] = field(default_factory=list)     # also another package's: this one's copy now
    bytes_copied: int = 0
    dry_run: bool = False
    manifest_added: str = ""                            # the package's manifest, when this sync made it (``restore``)


class _Source:
    """The files of a folder or a packed MPQ, by game key."""

    def __init__(self, source: str):
        self.source = source
        self.mpq = None
        self.files: dict[str, str] = {}                 # game key -> path as written (folder) / name (MPQ)
        if os.path.isdir(source):
            for root, dirs, names in os.walk(source):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in names:
                    if name.startswith("."):
                        continue
                    rel = os.path.relpath(os.path.join(root, name), source)
                    self.files[game_key(rel)] = rel.replace("/", "\\")
        elif os.path.isfile(source):
            from .mpq import MPQ
            self.mpq = MPQ(source)
            listing = self.mpq.read("(listfile)")
            if listing is None:
                raise ValueError(f"{source}: no (listfile): the MPQ's files can't be named")
            for line in listing.decode("latin-1").splitlines():
                name = line.strip()
                if name and not name.startswith("(") and self.mpq.has(name):
                    self.files[game_key(name)] = name.replace("/", "\\")
        else:
            raise ValueError(f"{source}: no such folder or MPQ")

    def read(self, key: str) -> bytes:
        name = self.files[key]
        if self.mpq is not None:
            data = self.mpq.read(name)
            if data is None:
                raise ValueError(f"{self.source}: {name} doesn't read")
            return data
        with open(os.path.join(self.source, name), "rb") as fh:
            return fh.read()

    def close(self) -> None:
        if self.mpq is not None:
            self.mpq.close()


def _manifest_path(folder: str, package: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in package)
    return os.path.join(folder, MANIFEST_DIR, f"{safe}.json")


def _load_manifest(folder: str, package: str) -> dict:
    path = _manifest_path(folder, package)
    if not os.path.exists(path):
        return {"package": package, "files": {}}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def manifests(folder: str) -> dict[str, dict]:
    """Every package's manifest in the folder, by package name."""
    out: dict[str, dict] = {}
    base = os.path.join(folder, MANIFEST_DIR)
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if name.endswith(".json"):
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                data = json.load(fh)
            out[data.get("package", name[:-5])] = data
    return out


def game_running() -> bool:
    """Whether the x64 client runs now (Windows): its folder MPQs are listed as it starts."""
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WowClient64.exe", "/NH"], capture_output=True,
                             text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "wowclient64.exe" in out.lower()


def _remove_empty_dirs(folder: str, rel: str) -> None:
    parent = os.path.dirname(os.path.join(folder, rel))
    top = os.path.abspath(folder)
    while os.path.abspath(parent).startswith(top) and os.path.abspath(parent) != top:
        try:
            os.rmdir(parent)
        except OSError:
            return
        parent = os.path.dirname(parent)


def _keep(folder: str, rel: str, backup: str | None) -> None:
    """A file about to be replaced or removed, copied into ``backup`` at its place (``restore`` puts it back)."""
    if not backup:
        return
    src = os.path.join(folder, rel)
    dst = os.path.join(backup, rel)
    if os.path.isfile(src) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def restore(folder: str, backup: str, added: list[str]) -> None:
    """Undo a sync made with ``backup``: the files it added taken out, the ones it replaced or removed (and the
    package's old manifest) put back."""
    for rel in added:
        path = os.path.join(folder, rel)
        if os.path.isfile(path):
            os.remove(path)
            _remove_empty_dirs(folder, rel)
    if os.path.isdir(backup):
        for root, _dirs, names in os.walk(backup):
            for name in names:
                src = os.path.join(root, name)
                dst = os.path.join(folder, os.path.relpath(src, backup))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)


def sync(source: str, folder: str, package: str, dry_run: bool = False, backup: str | None = None) -> SyncResult:
    """Bring ``folder`` (a folder MPQ, made if missing) in step with ``source`` for ``package``. ``backup``: a
    folder each file it replaces or removes (and the package's manifest) is copied into first (``restore``)."""
    if not package:
        raise ValueError("a package name is needed (its manifest keeps what it put in the folder)")
    result = SyncResult(package=package, folder=folder, dry_run=dry_run)
    src = _Source(source)
    try:
        old = _load_manifest(folder, package)
        others = {name: m for name, m in manifests(folder).items() if name != package}
        owned_by_others: dict[str, str] = {}
        for name, m in others.items():
            for key in m.get("files", {}):
                owned_by_others.setdefault(key, name)
        files: dict[str, dict] = {}
        for key in sorted(src.files):
            rel = src.files[key]
            data = src.read(key)
            digest = _sha1(data)
            files[key] = {"path": rel, "size": len(data), "sha1": digest}
            # the folder's copy, wherever its case puts it
            existing = old.get("files", {}).get(key, {}).get("path", rel)
            target = os.path.join(folder, existing)
            if not os.path.exists(target):
                target = os.path.join(folder, rel)
            if key in owned_by_others:
                result.shared.append(f"{rel} (also {owned_by_others[key]})")
            if os.path.exists(target) and os.path.getsize(target) == len(data) and _sha1_file(target) == digest:
                result.unchanged += 1
                files[key]["path"] = os.path.relpath(target, folder)
                continue
            (result.changed if os.path.exists(target) else result.added).append(rel)
            result.bytes_copied += len(data)
            if not dry_run:
                _keep(folder, os.path.relpath(target, folder), backup)
                write_verified(target, data)
            files[key]["path"] = os.path.relpath(target, folder)
        for key, entry in old.get("files", {}).items():
            if key in files:
                continue
            rel = entry.get("path", key)
            target = os.path.join(folder, rel)
            if not os.path.exists(target):
                continue
            if key in owned_by_others:
                continue                                   # another package's now: its file
            if _sha1_file(target) != entry.get("sha1"):
                result.left.append(rel)
                continue
            result.removed.append(rel)
            if not dry_run:
                _keep(folder, rel, backup)
                os.remove(target)
                _remove_empty_dirs(folder, rel)
        if not dry_run:
            manifest_rel = os.path.relpath(_manifest_path(folder, package), folder)
            if os.path.isfile(_manifest_path(folder, package)):
                _keep(folder, manifest_rel, backup)
            else:
                result.manifest_added = manifest_rel
            manifest = {"package": package, "source": os.path.abspath(source), "files": files}
            write_verified(_manifest_path(folder, package), json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
    finally:
        src.close()
    return result


def remove(folder: str, package: str, dry_run: bool = False) -> SyncResult:
    """Take a package's files out of the folder (those still as it put them) and its manifest."""
    result = SyncResult(package=package, folder=folder, dry_run=dry_run)
    old = _load_manifest(folder, package)
    others = {name: m for name, m in manifests(folder).items() if name != package}
    owned_by_others = {key for m in others.values() for key in m.get("files", {})}
    for key, entry in sorted(old.get("files", {}).items()):
        rel = entry.get("path", key)
        target = os.path.join(folder, rel)
        if not os.path.exists(target) or key in owned_by_others:
            continue
        if _sha1_file(target) != entry.get("sha1"):
            result.left.append(rel)
            continue
        result.removed.append(rel)
        if not dry_run:
            os.remove(target)
            _remove_empty_dirs(folder, rel)
    path = _manifest_path(folder, package)
    if not dry_run and os.path.exists(path):
        os.remove(path)
    return result
