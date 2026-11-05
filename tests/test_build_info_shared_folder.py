"""Games sharing a folder: Battle.net can leave one out of .build.info (installing Forever beside retail did)."""
import os

import pytest

from wotlkconv.casc.config import BuildInfo
from wotlkconv.errors import MissingDependencyError

RETAIL_BUILD, RETAIL_CDN = "334a36cf5f3c32a5f7a167405487fa14", "a0408f97170527fd6ebd148af45e80b8"
FOREVER_BUILD, FOREVER_CDN = "9006ba6948388dd0d4a0578e64b8a92e", "0e139f0e95542dbe2a5462d8a6b2ebae"
HEADER = ("Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|CDN Key!HEX:16|CDN Path!STRING:0|CDN Hosts!STRING:0|"
          "Version!STRING:0|Product!STRING:0\n")


def field(number, payload):
    assert len(payload) < 128
    return bytes([number << 3 | 2, len(payload)]) + payload


def entry(uid, version, build):
    state = field(10, version.encode()) + field(14, build.encode())
    return field(1, uid.encode()) + field(2, uid.encode()) + field(4, state)


def config(root, key, text, when):
    path = root / "Data" / "config" / key[0:2] / key[2:4] / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (when, when))


@pytest.fixture
def shared(tmp_path):
    (tmp_path / ".build.info").write_text(
        HEADER + f"us|1|{FOREVER_BUILD}|{FOREVER_CDN}|tpr/wow|level3.blizzard.com|1.60.1.70790|wowf\n")
    db = b"".join(field(1, entry(*p)) for p in (("wow", "12.1.5.70391", RETAIL_BUILD),
                                                ("wowf", "1.60.1.70790", FOREVER_BUILD)))
    (tmp_path / ".product.db").write_bytes(db)
    build = "root = aa\nencoding = bb cc\nbuild-name = {}\n"
    config(tmp_path, RETAIL_BUILD, build.format("retail"), 1000000)
    config(tmp_path, FOREVER_BUILD, build.format("forever"), 2000000)
    config(tmp_path, RETAIL_CDN, "archives = 01 02\n", 1000030)
    config(tmp_path, FOREVER_CDN, "archives = 03 04\n", 2000030)
    return tmp_path


def test_a_product_left_out_comes_from_the_product_db(shared):
    info = BuildInfo.load(shared, "wow")
    assert (info.product, info.version, info.build_key) == ("wow", "12.1.5.70391", RETAIL_BUILD)
    assert info.cdn_key == RETAIL_CDN                  # the CDN config from the same time as its build
    assert info.cdn_hosts == ["level3.blizzard.com"] and info.cdn_path == "tpr/wow"
    assert info.build_name == "retail"


def test_a_listed_product_still_reads_its_row(shared):
    info = BuildInfo.load(shared, "wowf")
    assert (info.version, info.build_key, info.cdn_key) == ("1.60.1.70790", FOREVER_BUILD, FOREVER_CDN)


def test_no_product_is_still_the_first_active_row(shared):
    assert BuildInfo.load(shared).product == "wowf"


def test_an_unknown_product_still_says_what_there_is(shared):
    with pytest.raises(MissingDependencyError, match="this install has wowf"):
        BuildInfo.load(shared, "wow_classic")


def test_a_product_whose_build_config_is_gone_is_not_invented(shared):
    (shared / "Data" / "config" / RETAIL_BUILD[0:2] / RETAIL_BUILD[2:4] / RETAIL_BUILD).unlink()
    with pytest.raises(MissingDependencyError, match="no active build"):
        BuildInfo.load(shared, "wow")
