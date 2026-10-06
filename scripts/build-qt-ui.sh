#!/usr/bin/env bash
# Builds the Qt UI container for arm64 and, optionally, loads it on a board.
#
#   scripts/build-qt-ui.sh                       # build lbornia/ventuno-demo-booth-ui:latest locally
#   BOARD=arduino@192.168.1.50 scripts/build-qt-ui.sh   # ... and docker load it on the board (user torizon on Torizon OS)
#   QT_UI_IMAGE=ghcr.io/<org>/qt-ui:0.1 PUSH=1 scripts/build-qt-ui.sh   # ... and push to a registry
#   DEBIAN_TAG=trixie-slim scripts/build-qt-ui.sh        # another Debian release (default forky-slim)
set -euo pipefail

IMAGE="${QT_UI_IMAGE:-lbornia/ventuno-demo-booth-ui:latest}"
DEBIAN_TAG="${DEBIAN_TAG:-forky-slim}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${PUSH:-0}" = "1" ]; then
    docker buildx build --platform linux/arm64 --build-arg DEBIAN_TAG="$DEBIAN_TAG" -t "$IMAGE" --push "$HERE/../qt-ui"
    exit 0
fi

docker buildx build --platform linux/arm64 --build-arg DEBIAN_TAG="$DEBIAN_TAG" -t "$IMAGE" --load "$HERE/../qt-ui"

if [ -n "${BOARD:-}" ]; then
    echo "Loading $IMAGE on $BOARD ..."
    docker save "$IMAGE" | ssh "$BOARD" docker load
fi
