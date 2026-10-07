#!/usr/bin/env bash
# Run the photo booth as an Arduino App, on either the Arduino Ubuntu image or Torizon OS.
#
# It is the same App and the same arduino-app-cli commands on both. The only difference is
# where the runtime comes from: Arduino's image has it installed, and on Torizon OS it runs
# from a container (see runtime/). This script hides that difference.
#
#   scripts/photo-booth.sh install    put the App in place (and start the runtime if needed)
#   scripts/photo-booth.sh start
#   scripts/photo-booth.sh stop
#   scripts/photo-booth.sh logs
#   scripts/photo-booth.sh status
#
# APPS_ROOT moves the App directory; FREE_DISPLAY=1 lets it stop a running desktop.
# RUNTIME=container forces the containerized runtime even where one is installed on the
# host; RUNTIME=host requires the installed one. The default picks whichever fits.
#   scripts/photo-booth.sh cli <args> any other arduino-app-cli command
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME=photo-booth

# Which runtime to use. The default is to use a host arduino-app-cli if there is one,
# which is the Arduino image, and the containerized runtime otherwise, which is Torizon,
# where nothing Arduino is installed in the rootfs by design. RUNTIME=container|host
# forces it, so a stray host install cannot quietly change what is being demonstrated.
case "${RUNTIME:-auto}" in
    auto|host|container) ;;
    *) echo "RUNTIME must be auto, host or container (got '${RUNTIME}')" >&2; exit 2 ;;
esac
if [ "${RUNTIME:-auto}" = host ] || { [ "${RUNTIME:-auto}" = auto ] && command -v arduino-app-cli >/dev/null 2>&1; }; then
    command -v arduino-app-cli >/dev/null 2>&1 || { echo "RUNTIME=host but arduino-app-cli is not installed" >&2; exit 2; }
    MODE="the runtime installed on this image"
    APPS_DIR="${APPS_DIR:-$HOME/ArduinoApps}"
    cli() { arduino-app-cli "$@"; }
    put_app() { mkdir -p "$APPS_DIR"; rm -rf "${APPS_DIR:?}/$APP_NAME"; cp -a "$REPO/app" "$APPS_DIR/$APP_NAME"; }
else
    MODE="the runtime in a container"
    APPS_DIR="${APPS_DIR:-/var/lib/arduino-apps/apps}"
    COMPOSE=(docker compose -f "$REPO/runtime/compose.yml")
    cli() { "${COMPOSE[@]}" exec -T arduino-app-cli arduino-app-cli "$@"; }
    put_app() {
        # /var/lib is root owned on a fresh board, so fall back to sudo when it has to be.
        local as=""
        mkdir -p "$APPS_DIR" 2>/dev/null || as=sudo
        [ -w "$APPS_DIR" ] || as=sudo
        $as mkdir -p "$APPS_DIR"
        $as rm -rf "${APPS_DIR:?}/$APP_NAME"
        $as cp -a "$REPO/app" "$APPS_DIR/$APP_NAME"
        $as chown -R "${APP_UID:-1000}" "$APPS_DIR/$APP_NAME"
    }
fi
APP_PATH="$APPS_DIR/$APP_NAME"

runtime_up() {
    [ -n "${COMPOSE+x}" ] || return 0
    if [ -z "$("${COMPOSE[@]}" ps -q arduino-app-cli 2>/dev/null)" ]; then
        echo "==> starting the App Lab runtime"
        "${COMPOSE[@]}" up -d
        # The daemon seeds its data directory on first start.
        sleep 3
    fi
}

check_the_display() {
    # The panel draws straight to KMS, so nothing else may hold the display. On Torizon
    # there is usually nothing to do; on the Arduino image the desktop has it. Stopping
    # someone's desktop without asking is rude, so say it rather than do it.
    systemctl is-active --quiet display-manager 2>/dev/null || return 0
    if [ "${FREE_DISPLAY:-0}" = "1" ]; then
        echo "==> stopping the desktop, which is holding the display"
        sudo systemctl stop display-manager
    else
        echo "!!  A desktop is running and holds the display, so the panel will show"
        echo "!!  nothing. Either stop it:"
        echo "!!      sudo systemctl stop display-manager"
        echo "!!  or re-run this with FREE_DISPLAY=1, or set the qt_ui Brick's"
        echo "!!  QT_QPA_PLATFORM to wayland to open the panel as a window instead."
    fi
}

case "${1:-}" in
install)
    echo "==> using $MODE"
    runtime_up
    put_app
    echo "==> App in place at $APP_PATH"
    cli app list
    ;;
start)
    runtime_up
    check_the_display
    cli app start "$APP_PATH"
    ;;
stop)    runtime_up; cli app stop "$APP_PATH" ;;
logs)    runtime_up; shift; cli app logs "$APP_PATH" "${@:---tail 40}" ;;
status)  runtime_up; cli app ps 2>/dev/null || cli app list ;;
cli)     runtime_up; shift; cli "$@" ;;
*)
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
