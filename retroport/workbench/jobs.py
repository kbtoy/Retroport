"""What an install job needs besides its own work: its state, the client it goes into, whether the
game is running, and small JSON and file helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from . import edition


@dataclass
class Job:
    name: str
    state: str = "running"       # running, ok, failed, stopped
    started: float = field(default_factory=time.time)
    ended: float = 0.0
    step: str = ""
    done: list = field(default_factory=list)   # the steps this job has passed, in order


def is_client(root: str) -> bool:
    """Whether the folder holds the client this edition installs into (``edition.CLIENT_EXE``)."""
    return bool(root) and os.path.isfile(os.path.join(root, edition.CLIENT_EXE))


def wow_running() -> bool:
    """Whether the client (or any 3.3.5 game program) is running: Install and Undo wait for it to close."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True).stdout.lower()
        return any(f'"{exe.lower()}"' in out for exe in ("Wow.exe", edition.CLIENT_EXE))
    except OSError:
        return False


def load_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)


def remove_any(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
