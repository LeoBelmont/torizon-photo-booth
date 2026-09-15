#!/bin/sh
# Build the booth for a Jetson platform.
#
#   ./build.sh              # orin (default)
#   ./build.sh thor
#   ./build.sh orin --push  # also push to the registry namespace below
#
# Run this on the board, or on any arm64 machine.
set -eu

PLATFORM="${1:-orin}"
case "$PLATFORM" in
  orin|thor) ;;
  -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown platform: $PLATFORM (expected orin or thor)" >&2; exit 2 ;;
esac
PUSH=0
[ "${2:-}" = "--push" ] && PUSH=1

CONTAINERS="${CONTAINERS:-../torizon-containers}"
TRT_DIR="$CONTAINERS/platform-specific/jetson/tensorrt"

REGISTRY="${REGISTRY:-docker.io}"
NAMESPACE="${NAMESPACE:-lbornia}"
if [ "$PLATFORM" = "orin" ]; then
  BASE_NAME="${BASE_NAME:-cuda-dev}"
else
  BASE_NAME="${BASE_NAME:-cuda-dev-$PLATFORM}"
fi
BASE_TAG="${BASE_TAG:-wrynose-rc}"
BASE="$REGISTRY/$NAMESPACE/$BASE_NAME:$BASE_TAG"

TRT_IMAGE="tensorrt-$PLATFORM:local"
BOOTH_IMAGE="${BOOTH_IMAGE:-$NAMESPACE/photo-booth:$PLATFORM}"

echo "platform   $PLATFORM"
echo "base       $BASE"
echo "tensorrt   $TRT_IMAGE"
echo "booth      $BOOTH_IMAGE"
echo

if [ ! -d "$TRT_DIR" ]; then
  echo "no tensorrt container at $TRT_DIR" >&2
  echo "set CONTAINERS to your torizon-containers checkout" >&2
  exit 1
fi

if ! docker image inspect "$BASE" >/dev/null 2>&1; then
  echo "pulling $BASE"
  if ! docker pull "$BASE"; then
    echo >&2
    echo "cannot get $BASE" >&2
    echo "point REGISTRY, NAMESPACE, BASE_NAME or BASE_TAG at wherever the" >&2
    echo "$PLATFORM cuda-dev image lives, for instance the CI registry:" >&2
    echo >&2
    echo "  REGISTRY=registry.gitlab.com \\" >&2
    echo "  NAMESPACE=toradex/rd/torizon-core/packages-and-containers/torizon-containers \\" >&2
    echo "  ./build.sh $PLATFORM" >&2
    exit 1
  fi
fi

echo "==> tensorrt container"
docker build \
  --build-arg REGISTRY="$REGISTRY" \
  --build-arg REGISTRY_NAMESPACE="$NAMESPACE" \
  --build-arg BASE_IMAGE_NAME="$BASE_NAME" \
  --build-arg IMAGE_TAG="$BASE_TAG" \
  -t "$TRT_IMAGE" "$TRT_DIR"

echo "==> booth"
docker build --build-arg TRT_IMAGE="$TRT_IMAGE" -t "$BOOTH_IMAGE" .

if [ "$PUSH" = "1" ]; then
  echo "==> push"
  docker push "$BOOTH_IMAGE"
fi

echo
echo "built $BOOTH_IMAGE"
echo "run it with:  PLATFORM=$PLATFORM docker compose up -d"
