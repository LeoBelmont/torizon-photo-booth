#!/bin/sh
# Three modes:
#   router        the msgpack RPC router, which bridges Python to the microcontroller
#   daemon        the App Lab daemon, which App Lab on a PC talks to
#   <any args>    one-off arduino-app-cli command, e.g. `app list`
#
# arduino-app-cli refuses to run as root, exactly as on Arduino's own image, so anything
# that needs it runs as APP_UID (1000 by default, which is `torizon` on Torizon OS and
# `arduino` on the Arduino image). This script starts as root only to prepare the
# directories, then drops.
set -eu

ROUTER_SOCKET="${ROUTER_SOCKET:-/run/arduino/arduino-router.sock}"
DATA_DIR="${ARDUINO_APP_CLI__DATA_DIR:-/var/lib/arduino-app-cli}"
APPS_DIR="${ARDUINO_APP_CLI__APPS_DIR:-/var/lib/arduino-apps/apps}"
RELEASES_DIR="${ARDUINO_APP_CLI__RELEASES_DIR:-/var/lib/arduino-apps/releases}"
APP_UID="${APP_UID:-1000}"
# The runtime keeps custom models under $HOME and hands that path to the App's containers
# to mount, so HOME has to be a directory that exists at the same path on the host. Give
# it one we already mount rather than depending on where the host user's home happens to be.
APP_HOME_DIR="${APP_HOME_DIR:-/var/lib/arduino-apps/home}"
export HOME="$APP_HOME_DIR"

prepare() {
    [ "$(id -u)" = "0" ] || return 0
    mkdir -p "$DATA_DIR" "$APPS_DIR" "$RELEASES_DIR" "$APP_HOME_DIR"
    # First start against empty host directories: lay down the brick index, the API docs
    # and the bundled examples that the package ships.
    if [ ! -d "$DATA_DIR/assets" ]; then
        echo "seeding $DATA_DIR from the packaged assets"
        cp -a /opt/arduino-app-cli-seed/. "$DATA_DIR/"
    fi
    chown -R "$APP_UID" "$DATA_DIR" "$APPS_DIR" "$RELEASES_DIR" "$APP_HOME_DIR" 2>/dev/null || true
}

# Run as APP_UID with the host's supplementary groups, so the process is in docker, video
# and the rest exactly as the same user is on the host.
as_app_user() {
    if [ "$(id -u)" != "0" ]; then
        exec "$@"
    fi
    if ! getent passwd "$APP_UID" >/dev/null; then
        echo "no uid $APP_UID on this host; set APP_UID to a real user" >&2
        exit 1
    fi
    # setpriv keeps the caller's HOME, so pass ours through explicitly.
    exec setpriv --reuid "$APP_UID" --regid "$(id -g "$APP_UID")" --init-groups \
         env HOME="$APP_HOME_DIR" "$@"
}

case "${1:-daemon}" in
router)
    # Put the microcontroller in a ready state, as the board's systemd drop-in does.
    # Skipped where MCU_READY_GPIO does not name this board's lines.
    if [ -n "${MCU_READY_GPIO:-}" ]; then
        gpioset ${MCU_READY_GPIO} 2>/dev/null || echo "MCU ready gpio not set, carrying on" >&2
    fi
    mkdir -p "$(dirname "$ROUTER_SOCKET")"
    set -- arduino-router --unix-port "$ROUTER_SOCKET"
    if [ -n "${SERIAL_PORT:-}" ]; then
        set -- "$@" --serial-port "$SERIAL_PORT" --serial-baudrate "${SERIAL_BAUDRATE:-115200}"
    fi
    echo "starting: $*"
    exec "$@"
    ;;
daemon)
    prepare
    as_app_user arduino-app-cli daemon --port "${DAEMON_PORT:-8800}" \
                                       --log-level "${LOG_LEVEL:-info}"
    ;;
*)
    prepare
    as_app_user arduino-app-cli "$@"
    ;;
esac
