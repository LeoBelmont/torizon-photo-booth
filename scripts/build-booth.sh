#!/usr/bin/env bash
# Builds the photo booth backend for the Arduino VENTUNO Q (arm64, NPU through QNN).
#
#   scripts/build-booth-ventunoq.sh                 # build lbornia/ventuno-demo-booth:latest
#   PUSH=1 scripts/build-booth-ventunoq.sh          # ... and push
#   BOARD=arduino@<ip> scripts/build-booth-ventunoq.sh   # ... or docker load it on the board
set -euo pipefail
IMAGE="${BOOTH_IMAGE:-lbornia/ventuno-demo-booth:latest}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGS=(--platform linux/arm64 -f "$HERE/../Dockerfile.ventunoq" -t "$IMAGE" "$HERE/..")
if [ "${PUSH:-0}" = "1" ]; then docker buildx build "${ARGS[@]}" --push; exit 0; fi
docker buildx build "${ARGS[@]}" --load
if [ -n "${BOARD:-}" ]; then docker save "$IMAGE" | ssh "$BOARD" docker load; fi
