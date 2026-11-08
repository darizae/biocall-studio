"""Native macOS-only PyInstaller onedir BioCall Studio .app."""
import sys
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("Build this spec on a genuine macOS runner.")
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
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BioCall Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="BioCall Studio",
)
app = BUNDLE(
    coll,
    name="BioCall Studio.app",
    icon=str(ROOT / "assets" / "branding" / "icons" / "icon.icns"),
    bundle_identifier="io.github.darizae.biocall-studio",
    info_plist={
        "CFBundleName": "BioCall Studio",
        "CFBundleDisplayName": "BioCall Studio",
        # Apple bundle versions are numeric; --version preserves full PEP 440 prerelease.
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "CFBundleGetInfoString": "BioCall Studio 0.1.0a1",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
)
