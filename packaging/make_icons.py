"""Build the app icons from the crab sprite: crab.ico (Windows) and crab.icns (Mac).

    python packaging/make_icons.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
CRAB = Image.open(HERE.parent / "assets" / "idle_0.png")


def crab(px):
    return CRAB.resize((px, px), Image.NEAREST)  # stays crisp pixel art at every size


crab(256).save(HERE / "crab.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])

if sys.platform == "darwin":
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "crab.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            crab(size).save(iconset / f"icon_{size}x{size}.png")
            crab(size * 2).save(iconset / f"icon_{size}x{size}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "crab.icns")], check=True)
print("icons written to", HERE)
