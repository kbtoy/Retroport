"""``.build.info`` and the build/CDN config files.

A CASC install bootstraps like this::

    .build.info          -> the active build's config hash
    Data/config/xx/yy/…  -> build config: hashes of the root and encoding files
    Data/data/*.idx      -> where an EKey lives inside data.NNN
    Data/data/data.NNN   -> the bytes

``.build.info`` is a ``|``-separated table whose header row carries typed
column names (``Build Key!HEX:16``); the build config is plain
``key = value`` lines where a value may be several space-separated hashes.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from ..errors import MalformedFileError, MissingDependencyError


def parse_build_info(text: str) -> list[dict[str, str]]:
    """Parse ``.build.info`` into one dict per row, keyed by column name."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise MalformedFileError(".build.info is empty")
    # Column names carry a type suffix: "Build Key!HEX:16" -> "Build Key".
    columns = [c.split("!", 1)[0].strip() for c in lines[0].split("|")]
    rows = []
    for line in lines[1:]:
        values = line.split("|")
        if len(values) < len(columns):
            values += [""] * (len(columns) - len(values))
        rows.append(dict(zip(columns, values)))
    return rows


def parse_config(text: str) -> dict[str, list[str]]:
    """Parse a build or CDN config into ``key -> [values]``."""
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.split()
    return out


def config_path(data_dir: Path, key: str) -> Path:
    """Config files are filed under two levels of hash prefix."""
    return data_dir / "config" / key[0:2] / key[2:4] / key


def _proto_fields(data: bytes):
    """(field number, bytes) of a protobuf message's length-delimited fields."""
    def varint(at: int) -> tuple[int, int]:
        value = shift = 0
        while at < len(data):
            byte = data[at]
            at += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value, at
        return value, len(data) + 1

    at = 0
    while at < len(data):
        tag, at = varint(at)
        wire = tag & 7
        if wire == 2:
            size, at = varint(at)
            if at + size > len(data):
                return
            yield tag >> 3, data[at:at + size]
            at += size
        elif wire == 0:
            _, at = varint(at)
        elif wire == 1:
            at += 8
        elif wire == 5:
            at += 4
        else:
            return


def _row_from_product_db(install_dir: Path, product: str,
                         rows: list[dict[str, str]]) -> dict[str, str] | None:
    """A ``.build.info`` row for a product Battle.net left out of it.

    When games share a folder, installing one can rewrite ``.build.info`` with
    that game alone (installing Forever beside retail did) while the other stays
    installed. The launcher's ``.product.db`` beside it still names the product's
    version and build config; its CDN config is the local one from the same
    time, and the hosts are the same for every game in the folder."""
    path = install_dir / ".product.db"
    if not path.is_file():
        return None
    name = product.encode("ascii", "replace")
    head = b"\n" + bytes([len(name)]) + name
    for _field, entry in _proto_fields(path.read_bytes()):
        if entry.startswith(head):
            break
    else:
        return None
    version = re.search(rb"\d+\.\d+\.\d+\.\d+", entry)
    build = re.search(rb"\x72\x20([0-9a-f]{32})", entry)  # field 14: the active build config
    if not version or not build:
        return None
    build_key = build.group(1).decode("ascii")
    data_dir = install_dir / "Data"
    if not config_path(data_dir, build_key).is_file():
        return None
    when = config_path(data_dir, build_key).stat().st_mtime
    cdn_key, nearest = "", None
    for file in (data_dir / "config").rglob("*"):
        if not file.is_file() or file.stat().st_size > 8 << 20:
            continue
        if b"archives = " in file.read_bytes():
            gap = abs(file.stat().st_mtime - when)
            if nearest is None or gap < nearest:
                cdn_key, nearest = file.name, gap
    other = rows[0] if rows else {}
    return {"Product": product, "Branch": other.get("Branch", ""), "Active": "1",
            "Version": version.group().decode("ascii"), "Build Key": build_key,
            "CDN Key": cdn_key, "CDN Hosts": other.get("CDN Hosts", ""),
            "CDN Path": other.get("CDN Path", "")}


@dataclasses.dataclass(slots=True)
class BuildInfo:
    """What the installation says about the build currently checked out."""

    product: str = ""
    branch: str = ""
    version: str = ""
    build_key: str = ""
    cdn_key: str = ""
    root_ckey: str = ""
    encoding_ckey: str = ""
    encoding_ekey: str = ""
    install_ckey: str = ""
    build_name: str = ""
    #: Where the install downloads from, for files it does not store.
    cdn_hosts: list[str] = dataclasses.field(default_factory=list)
    cdn_path: str = ""

    @classmethod
    def load(cls, install_dir: Path, product: str | None = None) -> BuildInfo:
        """Read ``.build.info`` and the build config it points at."""
        info_path = install_dir / ".build.info"
        if not info_path.is_file():
            raise MissingDependencyError(
                f"{install_dir} does not look like a game install: no "
                f".build.info. Point --casc at the folder containing the "
                f"game executable and its Data directory"
            )
        rows = parse_build_info(info_path.read_text(encoding="utf-8",
                                                    errors="replace"))
        chosen = None
        for row in rows:
            if product and row.get("Product", "") != product:
                continue
            if row.get("Active", "1") == "1":
                chosen = row
                break
        if chosen is None and product:
            chosen = _row_from_product_db(install_dir, product, rows)
        if chosen is None:
            if product:
                available = sorted({r.get("Product", "?") for r in rows})
                raise MissingDependencyError(
                    f"no active build for product {product!r}; this install has "
                    f"{', '.join(available)}")
            chosen = rows[0]

        info = cls(
            product=chosen.get("Product", ""),
            branch=chosen.get("Branch", ""),
            version=chosen.get("Version", ""),
            build_key=chosen.get("Build Key", ""),
            cdn_key=chosen.get("CDN Key", ""),
            cdn_hosts=chosen.get("CDN Hosts", "").split(),
            cdn_path=chosen.get("CDN Path", ""),
        )

        data_dir = install_dir / "Data"
        cfg_path = config_path(data_dir, info.build_key)
        if not cfg_path.is_file():
            raise MissingDependencyError(
                f"build config {info.build_key} is missing from {cfg_path}; "
                f"the install may be mid-update or partially repaired")
        cfg = parse_config(cfg_path.read_text(encoding="utf-8", errors="replace"))

        root = cfg.get("root", [])
        encoding = cfg.get("encoding", [])
        install = cfg.get("install", [])
        info.root_ckey = root[0] if root else ""
        info.encoding_ckey = encoding[0] if encoding else ""
        # The encoding file is the one thing referenced by EKey as well, because
        # you need it before you can translate CKeys into EKeys.
        info.encoding_ekey = encoding[1] if len(encoding) > 1 else ""
        info.install_ckey = install[0] if install else ""
        info.build_name = " ".join(cfg.get("build-name", []))
        if not info.root_ckey or not info.encoding_ekey:
            raise MalformedFileError(
                f"build config {info.build_key} lists no root or encoding file")
        return info

    def describe(self) -> str:
        return (f"{self.product or 'wow'} {self.version or '?'} "
                f"({self.build_name or self.build_key[:8]})")
