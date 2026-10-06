#!/bin/sh
# Take a photo from the terminal, skipping the smile trigger.
#
#   ./snap.sh                  next effect in rotation, needs a face in frame
#   ./snap.sh ancient          a named effect
#   ./snap.sh ancient --force  skip the face check too
#   ./snap.sh --list           show the effect ids
#   ./snap.sh --watch          follow what the booth is doing
#
# Saves the result beside itself as snap-<effect>-{before,after}.png, so a photo
# can be inspected without looking at the display.
set -eu

BOOTH="${BOOTH:-http://127.0.0.1:8080}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
EFFECT=""
FORCE=0

state() { curl -s --max-time 5 "$BOOTH/api/state" > "$TMP"; }

for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=1 ;;
    --list|-l)
      state
      python3 - "$TMP" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    for e in json.load(fh)["pack"]["effects"]:
        print(f"  {e['id']:14} {e['label']}")
PY
      exit 0 ;;
    --watch|-w)
      while true; do
        state
        python3 - "$TMP" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    s = json.load(fh)
print(f"  {s['state']:9} face={str(s['has_face']):5} "
      f"happy={s.get('happy', 0):4.2f} "
      f"advice={s.get('advice') or '-':14} "
      f"effect={s.get('effect') or '-'}")
PY
        sleep 1
      done ;;
    --help|-h) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) EFFECT="$arg" ;;
  esac
done

URL="$BOOTH/api/trigger"
SEP="?"
if [ "$FORCE" = "1" ]; then URL="$URL${SEP}force=1"; SEP="&"; fi
if [ -n "$EFFECT" ]; then URL="$URL${SEP}effect=$EFFECT"; fi

REPLY="$(curl -s --max-time 30 -X POST "$URL")"
echo "  $REPLY"
echo "$REPLY" | grep -q '"ok": true' || exit 1

i=0
while [ "$i" -lt 60 ]; do
  state
  if grep -q '"state": "reveal"' "$TMP"; then break; fi
  if grep -q '"state": "error"' "$TMP"; then head -c 300 "$TMP"; echo; exit 1; fi
  i=$((i + 1))
  sleep 1
done

python3 - "$TMP" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    s = json.load(fh)
print(f"  {s.get('effect')}  on {s.get('device')}  "
      f"{s['stats']['last_seconds']}s")
PY

NAME="${EFFECT:-latest}"
curl -s --max-time 15 "$BOOTH/api/photo/0/before.png" -o "snap-$NAME-before.png"
curl -s --max-time 15 "$BOOTH/api/photo/0/after.png"  -o "snap-$NAME-after.png"
echo "  wrote snap-$NAME-before.png and snap-$NAME-after.png"
