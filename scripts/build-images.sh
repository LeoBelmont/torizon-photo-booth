#!/usr/bin/env bash
# Build every image the demo needs, for the board (arm64), and optionally push them.
#
#   scripts/build-images.sh              build all three locally
#   PUSH=1 scripts/build-images.sh       build and push to the registry
#   REGISTRY=myname scripts/build-images.sh   use a different Docker Hub account
#   WITH_TOOLCHAIN=1 scripts/build-images.sh  also build the offline Arduino toolchain
#
# The booth image needs the ONNX models; see scripts/build-booth.sh.
set -euo pipefail

REGISTRY="${REGISTRY:-lbornia}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
load_or_push=(--load)
[ "${PUSH:-0}" = "1" ] && load_or_push=(--push)

echo "==> App Lab runtime"
docker buildx build --platform linux/arm64 "${load_or_push[@]}" \
    -t "$REGISTRY/arduino-app-runtime:latest" "$REPO/runtime"

echo "==> the App itself"
docker buildx build --platform linux/arm64 "${load_or_push[@]}" \
    -f "$REPO/deploy/Dockerfile.app" -t "$REGISTRY/ventuno-demo-app:latest" "$REPO"

# Only needed for boards with no network, and it takes a while, so it is opt-in.
if [ "${WITH_TOOLCHAIN:-0}" = "1" ]; then
    echo "==> Arduino toolchain (about a gigabyte, slow under emulation)"
    docker buildx build --platform linux/arm64 "${load_or_push[@]}" \
        -f "$REPO/deploy/Dockerfile.toolchain" -t "$REGISTRY/ventuno-demo-toolchain:latest" "$REPO"
fi

echo "==> Qt panel"
docker buildx build --platform linux/arm64 "${load_or_push[@]}" \
    -t "$REGISTRY/ventuno-demo-booth-ui:latest" "$REPO/qt-ui"

echo "==> booth backend (needs assets/*.onnx)"
if [ -f "$REPO/assets/inswapper_128.onnx" ]; then
    docker buildx build --platform linux/arm64 "${load_or_push[@]}" \
        -f "$REPO/Dockerfile" -t "$REGISTRY/ventuno-demo-booth:latest" "$REPO"
else
    echo "    skipped: no assets/inswapper_128.onnx in this checkout"
fi

echo
echo "Done. On the board:  docker compose -f deploy/compose.yml up -d"
