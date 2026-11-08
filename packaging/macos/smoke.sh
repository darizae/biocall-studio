#!/usr/bin/env bash
# First COPY the DMG .app to /Applications, then run this native binary preflight.
set -euo pipefail
cd "$(dirname "$0")/../.."
APP="${1:-/Applications/BioCall Studio.app}"
[[ "$(uname -s)" == Darwin ]] || { echo "Native Mac required" >&2; exit 2; }
[[ -d "$APP" ]] || { echo "Install the DMG .app outside the checkout first" >&2; exit 2; }
python3 packaging/shared/native_smoke.py --gui "$APP/Contents/MacOS/BioCall Studio"
