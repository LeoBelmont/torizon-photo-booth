"""Torizon Photo Booth: the App's Python glue.

The booth backend and the Qt panel are containers of the two Bricks and talk to each
other directly. This script follows the booth state and mirrors it on the microcontroller
(LED patterns) over the Bridge, so the Arduino side takes part in the demo too.
"""

import sys
from pathlib import Path

_BRICKS_DIR = Path(__file__).resolve().parents[1] / "bricks"
if str(_BRICKS_DIR) not in sys.path:
    sys.path.insert(0, str(_BRICKS_DIR))

from arduino.app_utils import App, Bridge, Logger  # noqa: E402
from photo_booth import PhotoBooth  # noqa: E402

logger = Logger("Main")

STATE_CODES = {"idle": 0, "aim": 1, "generate": 2, "reveal": 3, "error": 4}

booth = PhotoBooth()
mcu_available = True
_last = None


def on_update(state: dict) -> None:
    """Forward the booth state to the sketch whenever it changes."""
    global _last, mcu_available
    code = STATE_CODES.get(state.get("state"), 0)
    smile = int(round(100 * float(state.get("smile") or 0)))
    key = (code, smile // 10)
    if key == _last or not mcu_available:
        return
    _last = key
    try:
        Bridge.notify("booth_state", code, smile)
    except Exception as err:  # noqa: BLE001 - no router on this board: carry on without the LED
        mcu_available = False
        logger.warning(f"Microcontroller bridge unavailable, LED mirroring off. {err}")


booth.on_update(on_update)

App.run()
