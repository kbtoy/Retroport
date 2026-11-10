"""Build the Workbench's release (this edition's: ``edition.NAME``): a folder anyone can unpack and
run, and a zip of it.

    Retroport Workbench x64/
      Retroport Workbench x64.exe   the launcher (packaging/launcher.cs, built with Windows' own C# compiler)
      runtime/                  Python's official embeddable package, with retroport's dependencies
      app/                      the workbench's code: retroport and its copy of wotlkconv, as source
      README.txt, THIRD_PARTY_NOTICES.md, licenses/

It downloads Python's embeddable package from python.org and the dependencies' wheels from PyPI,
at the versions pinned below (the ones the workbench is tested with). It never contains anything of
Blizzard's: game data comes from wago.tools or the user's own installs at run time, and
the glue screen files (retroport/glue/ui, modified from Blizzard's UI code) are left out.

The folder is checked before it's zipped: its own Python imports the workbench and starts it.

usage:  python packaging/build_release.py [--out dist]
        python packaging/build_release.py --launcher-only     (the launcher exe in this checkout,
                                                              running the pythonw on PATH)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from retroport.workbench.edition import NAME  # noqa: E402  (the edition names its release)
PYTHON = "3.14.2"                                       # the embeddable package (its x.y names the wheels)
# its sha256 (the file python.org's downloads API gives MD5 85a5dcd0350f7ca4e2876295b0b281e3 for)
PYTHON_SHA256 = "f05e28d161c6b15af64a7cb7f08b4a22b3a6b03eee71baee24ea557b3bdd5798"
REQUIREMENTS = ["pydantic==2.13.3", "typer==0.25.1", "rich==15.0.0", "pillow==12.2.0"]
CSC = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe")


def say(msg: str) -> None:
    print(msg, flush=True)


def version() -> str:
    for line in open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8"):
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return "0"


def download(url: str, dest: str, sha256: str = "") -> str:
    if not os.path.isfile(dest):
        say(f"  downloading {url}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "retroport-release"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as fh:
            shutil.copyfileobj(r, fh)
        os.replace(dest + ".part", dest)
    digest = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    say(f"  {os.path.basename(dest)}: {os.path.getsize(dest):,} bytes, sha256 {digest}")
    if sha256 and digest != sha256:
        os.remove(dest)
        raise SystemExit(f"{os.path.basename(dest)} is not the file this build pins (sha256 {sha256}) - removed")
    return dest


def icon(dest: str) -> str:
    """The app's icon (static/icon.png) as a Windows .ico."""
    from PIL import Image
    img = Image.open(os.path.join(REPO, "retroport", "workbench", "static", "icon.png")).convert("RGBA")
    img.save(dest, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return dest


def launcher(dest_exe: str, work: str) -> None:
    if not os.path.isfile(CSC):
        raise SystemExit(f"no C# compiler at {CSC} (.NET Framework 4 comes with Windows 10 and 11)")
    ico = icon(os.path.join(work, "icon.ico"))
    source = os.path.join(work, "launcher.cs")              # the launcher named as this edition
    with open(os.path.join(HERE, "launcher.cs"), encoding="utf-8") as fh:
        text = fh.read().replace("Retroport Workbench", NAME)
    with open(source, "w", encoding="utf-8") as fh:
        fh.write(text)
    cmd = [CSC, "/nologo", "/target:winexe", "/optimize+", f"/win32icon:{ico}", f"/out:{dest_exe}",
           "/reference:System.Windows.Forms.dll", source]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"the launcher did not build:\n{out.stdout}{out.stderr}")
    say(f"  {dest_exe}")


def copy_tree(src: str, dest: str, leave_out: tuple[str, ...] = ()) -> None:
    """``src`` copied without caches - nor the folders ``leave_out`` names (relative to ``src``)."""
    plain = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache")
    skip = {os.path.normcase(os.path.join(src, p)) for p in leave_out}

    def ignore(folder, names):
        return set(plain(folder, names)) | {n for n in names if os.path.normcase(os.path.join(folder, n)) in skip}
    shutil.copytree(src, dest, ignore=ignore)


def runtime(dest: str, cache: str) -> None:
    """Python's embeddable package, its path opened to its own site-packages and to ..\\app, and
    the dependencies' wheels unpacked into it."""
    url = f"https://www.python.org/ftp/python/{PYTHON}/python-{PYTHON}-embed-amd64.zip"
    with zipfile.ZipFile(download(url, os.path.join(cache, os.path.basename(url)), PYTHON_SHA256)) as z:
        z.extractall(dest)
    short = "".join(PYTHON.split(".")[:2])
    pth = os.path.join(dest, f"python{short}._pth")
    with open(pth, "w", encoding="utf-8") as fh:
        fh.write(f"python{short}.zip\n.\nLib\\site-packages\n..\\app\nimport site\n")
    site = os.path.join(dest, "Lib", "site-packages")
    say(f"  pip: {' '.join(REQUIREMENTS)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-compile",
                    "--target", site, "--only-binary=:all:", "--platform", "win_amd64", "--implementation", "cp",
                    "--python-version", ".".join(PYTHON.split(".")[:2]), "--cache-dir", os.path.join(cache, "pip"),
                    *REQUIREMENTS], check=True)
    shutil.rmtree(os.path.join(site, "bin"), ignore_errors=True)


def app(dest: str, ver: str) -> None:
    """The workbench's code: retroport and its own copy of wotlkconv; ``VERSION`` says which it is."""
    # the glue screens (retroport glue) are modified from Blizzard's own UI code: never in a release
    copy_tree(os.path.join(REPO, "retroport"), os.path.join(dest, "retroport"), leave_out=(os.path.join("glue", "ui"),))
    copy_tree(os.path.join(REPO, "wotlkconv"), os.path.join(dest, "wotlkconv"))
    with open(os.path.join(dest, "retroport", "workbench", "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(ver + "\n")


def notices(dest: str) -> None:
    lic = os.path.join(dest, "licenses")
    os.makedirs(lic, exist_ok=True)
    for src, name in ((os.path.join(REPO, "LICENSE"), "retroport.txt"),
                      (os.path.join(REPO, "wotlkconv", "LICENSE"), "wotlkconv.txt"),
                      (os.path.join(dest, "runtime", "LICENSE.txt"), "python.txt")):
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(lic, name))
    shutil.copy2(os.path.join(REPO, "THIRD_PARTY_NOTICES.md"), os.path.join(dest, "THIRD_PARTY_NOTICES.md"))
    shutil.copy2(os.path.join(HERE, "README.txt"), os.path.join(dest, "README.txt"))


def check(dest: str) -> None:
    """The folder's own Python imports the workbench and serves its page."""
    py = os.path.join(dest, "runtime", "python.exe")
    code = ("import PIL, retroport.workbench.app, retroport.workbench.direct, retroport.workbench.mountpack;"
            "print('imports ok')")
    out = subprocess.run([py, "-c", code], capture_output=True, text=True, cwd=dest)
    if out.returncode != 0:
        raise SystemExit(f"the release's Python can't import the workbench:\n{out.stdout}{out.stderr}")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    home = os.path.join(dest, "..", "check-home")
    shutil.rmtree(home, ignore_errors=True)
    env = dict(os.environ, USERPROFILE=os.path.abspath(home), HOME=os.path.abspath(home))
    serve = ("import sys; from retroport.workbench import server as S; st = S.Settings(); "
             f"S.serve(st, port={port}, open_browser=False)")
    proc = subprocess.Popen([py, "-c", serve], cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=2) as r:
                    meta = json.load(r)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                    page = r.read()
                if meta.get("slots") and NAME.encode() in page:
                    say("  the release's workbench serves its page")
                    return
            except OSError:
                if proc.poll() is not None:
                    break
        raise SystemExit(f"the release's workbench did not answer:\n{proc.stdout.read().decode(errors='replace')}")
    finally:
        proc.kill()
        shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(REPO, "dist"))
    ap.add_argument("--launcher-only", action="store_true")
    a = ap.parse_args()
    if os.name != "nt":
        raise SystemExit("the release is built on Windows (its launcher, its Python)")
    work = os.path.join(a.out, "work")
    os.makedirs(work, exist_ok=True)
    if a.launcher_only:
        launcher(os.path.join(REPO, f"{NAME}.exe"), work)
        return 0
    ver = version()
    dest = os.path.join(a.out, NAME)
    if os.path.exists(dest):
        # moved aside whole first: a folder a running copy of the workbench holds open can't be, and a
        # delete would take what it could and leave that copy half gone
        old = dest + ".old"
        shutil.rmtree(old, ignore_errors=True)
        try:
            os.rename(dest, old)
        except OSError:
            raise SystemExit(f"{dest} is in use - close the {NAME} running from it, then build again")
        shutil.rmtree(old, ignore_errors=True)
    os.makedirs(dest)
    say(f"Building {NAME} {ver} in {dest}")
    say("runtime:")
    runtime(os.path.join(dest, "runtime"), os.path.join(a.out, "cache"))
    say("app:")
    app(os.path.join(dest, "app"), ver)
    notices(dest)
    say("launcher:")
    launcher(os.path.join(dest, f"{NAME}.exe"), work)
    say("check:")
    check(dest)
    archive = os.path.join(a.out, f"{NAME.replace(' ', '-')}-{ver}-win64.zip")
    say(f"zip: {archive}")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for d, _dirs, files in os.walk(dest):
            for f in files:
                full = os.path.join(d, f)
                z.write(full, os.path.join(NAME, os.path.relpath(full, dest)))
    say(f"  {os.path.getsize(archive):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
