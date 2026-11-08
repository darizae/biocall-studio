"""Native Windows x86-64 PyInstaller onedir GUI + console Worker pair."""
import sys
from pathlib import Path

if sys.platform != "win32":
    raise SystemExit("Build this spec on a genuine Windows runner.")
if sys.maxsize <= 2**32:
    raise SystemExit("Only x86-64 Windows release runners are supported.")
ROOT = Path(SPEC).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging" / "shared"))
from freezer import ENTRYPOINT, collect_bundle  # noqa: E402

datas, hiddenimports = collect_bundle()
a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
ICON = str(ROOT / "assets" / "branding" / "icons" / "icon.ico")
gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BioCall Studio",
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=ICON,
)
# The GUI is windowed. Private QProcess children need a console subsystem
# executable to expose their JSON stdout/stderr progress streams on Windows.
worker = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BioCall Studio Worker",
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
    icon=ICON,
)
coll = COLLECT(
    gui, worker, a.binaries, a.datas,
    strip=False, upx=False,
    name="BioCall Studio",
)
