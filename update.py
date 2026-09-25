"""Checking GitHub for a newer crab, and swapping himself out for it.

The packaged app can't overwrite its own .exe while it's running, so the swap is
handed to a tiny script that waits for him to quit, copies the new build over the
old one, and starts him again.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.0.0"          # bump this and tag the release to match
REPO = "FatBoy721/pixel-buddy"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = {"win32": "PixelBuddy-windows.zip", "darwin": "PixelBuddy-mac.zip"}
TIMEOUT_S = 30
CHUNK = 256 * 1024


def version_tuple(tag):
    """"v1.2.3" -> (1, 2, 3). Anything unparseable sorts lowest."""
    return tuple(int(n) for n in re.findall(r"\d+", tag or "")) or (0,)


def frozen():
    """True in the packaged app; from source there's nothing to swap."""
    return getattr(sys, "frozen", False)


def install_dir():
    """The folder holding the running build (…/dist/Pixel Buddy)."""
    return Path(sys.executable).parent


def latest_release():
    """(tag, download URL, release notes), or None if GitHub has nothing for us.
    A private repo answers 404 here: the caller falls back to the releases page."""
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "pixel-buddy"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        data = json.loads(response.read())
    want = ASSET.get(sys.platform)
    url = next((a["browser_download_url"] for a in data.get("assets", [])
                if a["name"] == want), None)
    return data.get("tag_name", ""), url, (data.get("body") or "").strip()


def check():
    """(tag, url, notes) when GitHub has a newer version, else None."""
    tag, url, notes = latest_release()
    return (tag, url, notes) if version_tuple(tag) > version_tuple(VERSION) else None


def download(url, progress=lambda text: None):
    """Fetch the release zip to a temp file, reporting percentages as it goes."""
    dest = Path(tempfile.mkdtemp(prefix="pixel-buddy-update-")) / "update.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "pixel-buddy"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response, open(dest, "wb") as out:
        total, done, last = int(response.headers.get("Content-Length") or 0), 0, -1
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            pct = int(done * 100 / total) if total else 0
            if pct != last:
                last = pct
                progress(f"Downloading the new me… {pct}%" if total else "Downloading the new me…")
    return dest


def unpack(zip_path):
    """Extract the zip and return the folder that actually holds the new build.
    Zips made by `git archive`-style tools wrap everything in one top folder."""
    out = zip_path.parent / "new"
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(out)
    entries = [p for p in out.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return out


SWAP_BAT = """@echo off
rem Wait for the old crab to quit, put the new one in its place, start him again.
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)
robocopy "{new}" "{target}" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS >nul
start "" "{exe}"
rmdir /s /q "{temp}"
(goto) 2>nul & del "%~f0"
"""

SWAP_SH = """#!/bin/sh
# Wait for the old crab to quit, put the new one in its place, start him again.
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
rm -rf "{target}"
mv "{new}" "{target}"
open "{target}"
rm -rf "{temp}"
rm -- "$0"
"""


def apply_update(new_build):
    """Hand the swap to a detached script and tell the caller to quit now.
    On Mac the thing being replaced is the .app bundle, not the folder inside it."""
    # The swap mirrors a folder, which deletes whatever else is in it. Run from
    # source, sys.executable is the interpreter and the "install dir" would be
    # .venv/Scripts — so refuse outright unless this really is the packaged app.
    if not frozen():
        raise RuntimeError("running from source: nothing to swap (use git pull)")
    target = install_dir()
    exe = sys.executable
    if sys.platform == "darwin":  # …/Pixel Buddy.app/Contents/MacOS/Pixel Buddy
        bundle = next((p for p in Path(exe).parents if p.suffix == ".app"), None)
        if bundle:
            target, exe = bundle, str(bundle)
    temp = new_build.parent.parent
    fields = {"pid": os.getpid(), "new": new_build, "target": target, "exe": exe, "temp": temp}
    if sys.platform == "win32":
        script = temp / "swap.bat"
        script.write_text(SWAP_BAT.format(**fields), encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=subprocess.CREATE_NO_WINDOW
                         | subprocess.DETACHED_PROCESS)
    else:
        script = temp / "swap.sh"
        script.write_text(SWAP_SH.format(**fields), encoding="utf-8")
        script.chmod(0o755)
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True)


def fetch_and_stage(url, progress=lambda text: None):
    """Download + unpack, ready for apply_update(). Returns the new build folder."""
    zip_path = download(url, progress)
    progress("Unpacking…")
    new_build = unpack(zip_path)
    if not any(new_build.iterdir()):
        shutil.rmtree(zip_path.parent.parent, ignore_errors=True)
        raise RuntimeError("the download was empty")
    return new_build


def check_and_stage(progress=lambda text: None):
    """The whole background half of an update: ask GitHub, download, unpack.
    Returns (tag, new build folder), or None when he's already up to date."""
    progress("Asking GitHub…")
    found = check()
    if not found:
        return None
    tag, url, _notes = found
    if not url:
        raise RuntimeError(f"{tag} has no build for this computer")
    progress(f"Found {tag}. Grabbing it…")
    return tag, fetch_and_stage(url, progress)


def demo():
    assert version_tuple("v1.2.3") == (1, 2, 3)
    assert version_tuple("1.10.0") > version_tuple("1.9.9")
    assert version_tuple("") == (0,)
    assert version_tuple("v2.0.0") > version_tuple(VERSION), "release tags must outrank VERSION"
    print(f"running {VERSION}; asking GitHub…")
    try:
        tag, url, _notes = latest_release()
        print(f"  latest tag: {tag or '(none)'}\n  asset: {url or '(no build for this platform)'}")
        print("  newer?", version_tuple(tag) > version_tuple(VERSION))
    except Exception as err:  # noqa: BLE001 - offline / private repo / no releases yet
        print(f"  couldn't reach GitHub releases: {err}")


if __name__ == "__main__":
    demo()
