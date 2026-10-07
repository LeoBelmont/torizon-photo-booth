#!/usr/bin/env bash
# Check that a board can run the photo booth. Run it on the board, on Torizon OS or on
# the Arduino image; it changes nothing and only reports.
#
#   ./check-board.sh
#
# Each check says what breaks if it fails, so a partial result is still useful: the demo
# runs without the microcontroller or without the NPU, just reduced.
set -u

pass=0; warn=0; fail=0
ok()   { printf '  \033[32m ok \033[0m %s\n' "$1"; pass=$((pass+1)); }
no()   { printf '  \033[31mFAIL\033[0m %s\n       %s\n' "$1" "$2"; fail=$((fail+1)); }
hmm()  { printf '  \033[33mwarn\033[0m %s\n       %s\n' "$1" "$2"; warn=$((warn+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

printf '\033[1mPhoto booth board check\033[0m\n'
printf '  %s\n' "$( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || echo 'unknown OS')"
printf '  kernel %s   %s\n' "$(uname -r)" "$(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null || echo '')"

head_ "Containers"
if command -v docker >/dev/null 2>&1; then
    v=$(docker version --format '{{.Server.APIVersion}}' 2>/dev/null)
    if [ -n "$v" ]; then
        maj=${v%%.*}; min=${v##*.}
        if [ "$maj" -gt 1 ] || { [ "$maj" -eq 1 ] && [ "$min" -ge 44 ]; }; then
            ok "Docker, API $v"
        else
            no "Docker API $v is too old" "arduino-app-cli needs 1.44 or newer (Docker 25+)."
        fi
    else
        no "Docker is installed but not answering" "Is the service running, and is this user allowed to use it?"
    fi
    docker compose version >/dev/null 2>&1 && ok "docker compose" \
        || no "docker compose is missing" "Both the runtime and the plain compose path need it."
else
    no "no docker" "Everything here runs in containers."
fi

head_ "The user the App runs as"
if getent passwd 1000 >/dev/null 2>&1; then
    u=$(getent passwd 1000 | cut -d: -f1)
    ok "uid 1000 is $u"
    id -nG "$u" 2>/dev/null | tr ' ' '\n' | grep -qx docker \
        && ok "$u is in the docker group" \
        || hmm "$u is not in the docker group" "The containerized runtime needs it to reach the Docker socket."
    for g in video render; do
        getent group "$g" >/dev/null 2>&1 && ok "group $g exists" \
            || hmm "no $g group" "The App's containers are given this group to reach the GPU and the camera."
    done
else
    no "no uid 1000" "arduino-app-cli refuses to run as root and expects uid 1000."
fi

head_ "Board identity (how arduino-app-cli knows which board this is)"
compat=$(tr '\0' ' ' < /sys/firmware/devicetree/base/compatible 2>/dev/null)
case "$compat" in
    *arduino,monza*) ok "device tree says arduino,monza, so the board is ventunoq" ;;
    *arduino,imola*) ok "device tree says arduino,imola, so the board is unoq" ;;
    "")              hmm "no device tree compatible string" "Drop a platform.json naming the board into the runtime's data directory." ;;
    *)               hmm "device tree says:$compat" "No arduino,* entry, so the runtime will not recognise the board. A platform.json in its data directory overrides this." ;;
esac

head_ "Hexagon NPU (the face swap)"
npu=1
for d in /dev/fastrpc-cdsp /dev/fastrpc-cdsp-secure /dev/dma_heap/system; do
    [ -e "$d" ] && ok "$d" || { no "$d is missing" "Without it the swap silently falls back to the CPU: about 4 s a photo instead of 0.7 s."; npu=0; }
done
if [ -d /usr/share/qcom ] || [ -d /usr/share/hexagon-dsp ]; then
    ok "DSP firmware directory present"
else
    no "no /usr/share/qcom or /usr/share/hexagon-dsp" "The NPU runtime loads the Hexagon firmware from there."; npu=0
fi
[ "$npu" = 1 ] && ok "NPU prerequisites complete" || hmm "NPU incomplete" "The demo still runs, on the CPU."

head_ "GPU (the Qt panel)"
if [ -e /dev/dri/card0 ]; then
    ok "/dev/dri/card0"
    drv=$(basename "$(readlink -f /sys/class/drm/card0/device/driver 2>/dev/null)" 2>/dev/null)
    [ -n "$drv" ] && ok "display driver: $drv" || hmm "no driver bound to card0" "The panel needs KMS."
    ls /dev/dri/renderD* >/dev/null 2>&1 && ok "render node present" \
        || hmm "no render node" "The panel falls back to software rendering."
    if [ -d /sys/bus/platform/drivers/adreno ]; then
        gpu=$(for d in /sys/bus/platform/devices/*gpu*; do [ -e "$d/of_node/compatible" ] && tr -d '\0' < "$d/of_node/compatible"; done 2>/dev/null)
        case "$gpu" in *adreno*) ok "Adreno GPU bound: $gpu" ;; *) hmm "the adreno driver is loaded but no GPU is bound" "The panel will render in software." ;; esac
    else
        hmm "no adreno driver" "Expected on a non-Qualcomm board. The panel renders in software."
    fi
else
    no "no /dev/dri/card0" "The panel has nothing to draw on."
fi
holder=""
systemctl is-active --quiet display-manager 2>/dev/null && holder="a desktop (display-manager)"
docker ps --format '{{.Names}}' 2>/dev/null | grep -qi weston && holder="${holder:+$holder and }a weston container"
[ -z "$holder" ] && ok "nothing else is holding the display" \
    || hmm "$holder is holding the display" "The panel draws straight to KMS and will show nothing until that stops."

head_ "Peripherals"
cam=""
for v in /dev/video*; do
    [ -e "$v" ] || continue
    n=$(basename "$v")
    case "$(cat "/sys/class/video4linux/$n/name" 2>/dev/null)" in
        *[Dd]ecoder*|*[Ee]ncoder*) ;;
        *) cam="${cam:+$cam }$v" ;;
    esac
done
[ -n "$cam" ] && ok "camera candidates:$cam" \
    || hmm "no USB camera found" "The booth falls back to the bundled portraits and runs by itself."
[ -e "${SERIAL_PORT:-/dev/ttySTM0}" ] && ok "microcontroller on ${SERIAL_PORT:-/dev/ttySTM0}" \
    || hmm "no ${SERIAL_PORT:-/dev/ttySTM0}" "The sketch and the LED will not work. The rest of the demo does."

head_ "Network"
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 8 -o /dev/null https://registry-1.docker.io/v2/ 2>/dev/null; then
    ok "Docker Hub is reachable"
else
    hmm "cannot reach Docker Hub" "The images must then be side-loaded with docker save | docker load."
fi

printf '\n\033[1mSummary:\033[0m %d ok, %d warnings, %d blocking\n' "$pass" "$warn" "$fail"
if [ "$fail" -gt 0 ]; then
    printf 'The blocking items have to be fixed before the demo will run.\n'; exit 1
fi
printf 'Good to go: scripts/photo-booth.sh install && scripts/photo-booth.sh start\n'
