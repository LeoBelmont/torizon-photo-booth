#!/bin/sh
# Starts the UI on KMS (EGLFS, default) or inside an existing Wayland compositor
# (QT_QPA_PLATFORM=wayland with WAYLAND_SOCKET as an absolute socket path).
set -eu

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-eglfs}"

wait_for() {
    # $1: a test(1) flag, $2: path, $3: what it is
    i=0
    while ! test "$1" "$2"; do
        i=$((i + 1))
        if [ "$i" -gt 60 ]; then
            echo "$3 $2 not found after 60s" >&2
            exit 1
        fi
        sleep 1
    done
}

case "$QT_QPA_PLATFORM" in
    wayland)
        SOCKET="${WAYLAND_SOCKET:-/run/user/1000/wayland-0}"
        # XDG_RUNTIME_DIR is derived here on purpose: the App Lab orchestrator sets it to
        # /run/user/1000 on every container of an App.
        export XDG_RUNTIME_DIR
        XDG_RUNTIME_DIR="$(dirname "$SOCKET")"
        export WAYLAND_DISPLAY
        WAYLAND_DISPLAY="$(basename "$SOCKET")"
        wait_for -S "$SOCKET" "Wayland socket"
        ;;
    eglfs)
        wait_for -e /dev/dri "DRM device directory"
        # Qt's libinput backend needs a runtime dir for xkb; any writable path will do.
        export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/qt-runtime}"
        mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null || export XDG_RUNTIME_DIR=/tmp
        ;;
esac

exec /opt/booth-ui/bin/booth-ui "$@"
