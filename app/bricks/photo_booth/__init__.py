"""photo_booth Brick: Python access to the booth backend running in the Brick's container.

    booth = PhotoBooth()
    booth.on_update(lambda state: print(state["state"], state["smile"]))
    booth.trigger("pharaoh")          # take a photo now, skipping the smile
    App.run()
"""

import os
import time
from collections.abc import Callable
from typing import Any

import requests

from arduino.app_utils import Logger, brick

logger = Logger("PhotoBooth")


@brick
class PhotoBooth:
    def __init__(self, url: str | None = None, poll_s: float = 0.25):
        self.url = (url or os.getenv("BOOTH_URL", "http://booth:8080")).rstrip("/")
        self._poll_s = poll_s
        self._handlers: list[Callable[[dict[str, Any]], Any]] = []
        self.state: dict[str, Any] = {}
        self._connected = False

    def on_update(self, handler: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
        self._handlers.append(handler)
        return handler

    def trigger(self, effect: str | None = None, force: bool = False) -> dict[str, Any]:
        params = {}
        if effect:
            params["effect"] = effect
        if force:
            params["force"] = "1"
        return requests.post(f"{self.url}/api/trigger", params=params, timeout=30).json()

    def loop(self) -> None:
        try:
            state = requests.get(f"{self.url}/api/state", timeout=2).json()
        except Exception as err:  # noqa: BLE001
            if self._connected:
                logger.warning(f"booth unreachable at {self.url}: {err}")
            self._connected = False
            time.sleep(1.0)
            return
        if not self._connected:
            logger.info(f"booth at {self.url}: {state.get('source', {}).get('label')}, device {state.get('device')}")
            self._connected = True
        self.state = state
        for handler in self._handlers:
            try:
                handler(state)
            except Exception as err:  # noqa: BLE001
                logger.error(f"state handler failed: {err}")
        time.sleep(self._poll_s)
