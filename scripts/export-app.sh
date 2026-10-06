#!/usr/bin/env bash
# Zips the Arduino App for "Import an App" in Arduino App Lab (or arduino-app-cli app import).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/../ventuno-demo-app.zip}"
rm -f "$OUT"
(cd "$HERE/../app" && zip -qr "$OUT" . -x '.cache/*' 'data/*' '__pycache__/*' '*/__pycache__/*')
echo "Wrote $OUT"
