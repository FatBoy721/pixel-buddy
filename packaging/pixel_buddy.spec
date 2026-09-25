# PyInstaller build for Pixel Buddy. Run on the OS you're building for:
#   Mac:      pyinstaller packaging/pixel_buddy.spec   -> dist/Pixel Buddy.app
#   Windows:  pyinstaller packaging\pixel_buddy.spec   -> dist\Pixel Buddy\Pixel Buddy.exe
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
HERE = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "buddy.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets"), "assets")],
    excludes=["tkinter", "PIL", "make_sprites"],  # Pillow only draws sprites at dev time
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Pixel Buddy",
    console=False,  # no terminal window
    icon=str(HERE / ("crab.icns" if sys.platform == "darwin" else "crab.ico")),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Pixel Buddy")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Pixel Buddy.app",
        icon=str(HERE / "crab.icns"),
        bundle_identifier="com.crabman.pixelbuddy",
        info_plist={
            "LSUIElement": True,  # lives on the desktop + menu bar: no Dock icon
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
        },
    )
