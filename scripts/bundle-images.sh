#!/usr/bin/env bash
# Bundle everything the board needs into one file, for boards with no registry access.
#
#   scripts/bundle-images.sh              -> dist/ventuno-demo-<date>.zip
#   OUT=/tmp/demo.zip scripts/bundle-images.sh
#   REGISTRY=myname scripts/bundle-images.sh
#
# The zip holds the four arm64 images as a single gzipped docker-save archive, plus the
# standalone compose file and a note with the two commands to run on the board. The zip
# stores rather than recompresses, because the archive inside is already compressed.
set -euo pipefail

REGISTRY="${REGISTRY:-lbornia}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
OUT="${OUT:-$REPO/dist/ventuno-demo-$(date +%Y%m%d).zip}"

IMAGES=(
    "$REGISTRY/arduino-app-runtime:latest"
    "$REGISTRY/ventuno-demo-app:latest"
    "$REGISTRY/ventuno-demo-booth-ui:latest"
    "$REGISTRY/ventuno-demo-booth:latest"
)
# Included when it has been built. Only a board with no network needs it.
TOOLCHAIN="$REGISTRY/ventuno-demo-toolchain:latest"
if docker image inspect "$TOOLCHAIN" >/dev/null 2>&1; then
    IMAGES+=("$TOOLCHAIN")
    WITH_TOOLCHAIN=1
else
    WITH_TOOLCHAIN=0
    echo "note: no $TOOLCHAIN built, so the bundle will need network for the sketch"
fi

for i in "${IMAGES[@]}"; do
    arch=$(docker image inspect "$i" --format '{{.Architecture}}' 2>/dev/null) || {
        echo "missing image: $i   (run scripts/build-images.sh first)" >&2; exit 1; }
    [ "$arch" = arm64 ] || { echo "$i is $arch, not arm64" >&2; exit 1; }
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$(dirname "$OUT")"

echo "==> saving $(( ${#IMAGES[@]} )) images, this takes a few minutes"
docker save "${IMAGES[@]}" | gzip -1 > "$work/images.tar.gz"

cp "$REPO/deploy/compose.yml" "$work/compose.yml"
[ "$WITH_TOOLCHAIN" = "1" ] && cp "$REPO/deploy/compose.offline.yml" "$work/compose.offline.yml"
cat > "$work/INSTALL.txt" <<TXT
Torizon Photo Booth - offline install

On the board:

  unzip ventuno-demo-*.zip
  docker load -i images.tar.gz
  docker compose -f compose.yml up -d

If this bundle includes compose.offline.yml, the Arduino toolchain is in it too, and the
board needs no network at all:

  docker compose -f compose.yml -f compose.offline.yml up -d

If it does not, a board with no network cannot build the sketch, so start it without the
microcontroller half instead:

  WITHOUT_SKETCH=1 docker compose -f compose.yml up -d

Everything then works except the LED on the microcontroller.

That is all. The App folder, the App Lab runtime, the booth and the panel are all in
the images; nothing is installed into the operating system.

The panel draws straight to KMS and needs the display to itself. That is the normal
state on Torizon OS. On a board running a desktop, stop it first:

  sudo systemctl stop display-manager

To check the board first, copy scripts/check-board.sh across and run it; it only reports.

Stop the demo:
  docker compose -f compose.yml run --rm start-app app stop /var/lib/arduino-apps/apps/photo-booth

Taking the stack down leaves the demo running, because the App's containers are created
on the host daemon rather than inside the runtime:
  docker compose -f compose.yml down
TXT

echo "==> packing"
( cd "$work" && zip -q -0 "$OUT" images.tar.gz compose*.yml INSTALL.txt )
echo
echo "wrote $OUT  ($(du -h "$OUT" | cut -f1))"
