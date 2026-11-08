#!/usr/bin/env bash
# Run on a genuine Mac after the packaging-source PR merge and SHA freeze.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${STUDIO_RELEASE_SHA:?Set the reviewed, frozen main HEAD after spec 04A merges}"
[[ "$(uname -s)" == Darwin ]] || { echo "macOS runner required" >&2; exit 2; }
[[ "$(git rev-parse HEAD)" == "$STUDIO_RELEASE_SHA" ]] || { echo "Wrong SHA" >&2; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo "Checkout must be clean" >&2; exit 2; }
python3 -m pip install -r packaging/requirements-build.txt
mkdir -p build/release-wheels build/source-dist dist/native-macos
gh release download v0.1.0a1 --repo darizae/alp-ui --pattern 'alp_ui-0.1.0a1-py3-none-any.whl' --dir build/release-wheels
gh release download v0.3.0 --repo darizae/bioacoustics-dl-toolbox --pattern 'bioacoustics_dl_toolbox-0.3.0-py3-none-any.whl' --dir build/release-wheels
python3 -m pip install --no-deps build/release-wheels/*.whl
python3 -m build --wheel --outdir build/source-dist
python3 -m pip install -c packaging/constraints-native.txt build/source-dist/biocall_studio-0.1.0a1-*.whl
python3 -m pip check
python3 packaging/shared/verify_inputs.py --frozen --wheelhouse build/release-wheels
python3 -m pip freeze > build/macos-installed-python-freeze.txt
python3 -m PyInstaller --noconfirm --clean \
  --distpath dist/native-macos --workpath build/pyinstaller-macos \
  packaging/macos/biocall.spec
APP="dist/native-macos/BioCall Studio.app"
[[ -d "$APP" && -f "$APP/Contents/MacOS/BioCall Studio" ]] || exit 1
mkdir -p build/dmg-root
rm -rf "build/dmg-root/BioCall Studio.app"
cp -R "$APP" build/dmg-root/
ln -sfn /Applications build/dmg-root/Applications
hdiutil create -ov -format UDZO -volname "BioCall Studio 0.1.0a1" \
  -srcfolder build/dmg-root "dist/native-macos/BioCall-Studio-0.1.0a1-macos.dmg"
shasum -a 256 assets/branding/icons/icon.icns "dist/native-macos/BioCall-Studio-0.1.0a1-macos.dmg"
echo "DEVELOPMENT-ONLY unless the actual app/DMG are Developer-ID signed, hardened,"
echo "notarized, stapled, Gatekeeper tested and legal/owner gates independently cleared."
