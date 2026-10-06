
"""Where frames come from."""

import fcntl
import fnmatch
import glob
import logging
import os
import re
import struct
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

FRAME_W = 640
FRAME_H = 480

_VIDIOC_QUERYCAP = 0x80685600
_V4L2_CAP_VIDEO_CAPTURE = 0x00000001
_V4L2_CAP_DEVICE_CAPS = 0x80000000

_QUERYCAP_SIZE = 104
_OFF_CARD = 16
_OFF_CAPABILITIES = 84
_OFF_DEVICE_CAPS = 88


def _querycap(device):
    """Return (is_capture_device, human_readable_name) for a V4L2 node."""
    try:
        with open(device, "rb") as fh:
            buf = bytearray(_QUERYCAP_SIZE)
            fcntl.ioctl(fh, _VIDIOC_QUERYCAP, buf)
        caps = struct.unpack_from("<I", buf, _OFF_CAPABILITIES)[0]
        device_caps = struct.unpack_from("<I", buf, _OFF_DEVICE_CAPS)[0]
        effective = device_caps if (caps & _V4L2_CAP_DEVICE_CAPS) else caps
        card = bytes(buf[_OFF_CARD:_OFF_CARD + 32]).split(b"\0")[0].decode(
            "utf-8", "replace")
        return bool(effective & _V4L2_CAP_VIDEO_CAPTURE), card
    except Exception as exc:
        log.debug("QUERYCAP failed on %s: %s", device, exc)
        return False, ""


def _sysfs_id_path(device):
    """A stable "which USB port is this on" string, for pinning one camera."""
    name = os.path.basename(device)
    try:
        real = os.path.realpath(f"/sys/class/video4linux/{name}")
        m = re.search(
            r"/([^/]+)/usb(\d+)/(?:[^/]+/)*(\d+(?:-[\d.]+)+):(\d+\.\d+)/video4linux",
            real)
        if not m:
            return ""
        bus_num = int(m.group(2)) - 1
        port_path = re.sub(r"^\d+-", "", m.group(3))
        return f"platform-{m.group(1)}-usb-{bus_num}:{port_path}:{m.group(4)}"
    except Exception:
        return ""


class FrameSource:
    """A thing that yields BGR frames."""

    live = False
    label = "none"

    def read(self):
        raise NotImplementedError

    def close(self):
        pass


class V4L2Camera(FrameSource):
    """A USB webcam."""

    live = True

    def __init__(self, device, name=""):
        self.device = device
        self.name = name
        self.label = f"{name} ({device})" if name else f"camera {device}"
        self._cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open {device}")
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
        self._cap.set(cv2.CAP_PROP_FPS, 30)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self):
        ok, frame = self._cap.read()
        if not ok:
            return None
        return cv2.flip(frame, 1)

    def close(self):
        self._cap.release()


class StockPortraits(FrameSource):
    """Cycles through bundled portraits when there is no camera."""

    live = False

    HEAD_SCALE = 0.7

    def __init__(self, directory, dwell_s=6.0):
        paths = sorted(glob.glob(os.path.join(directory, "*.png")))
        self._frames = []
        for p in paths:
            img = cv2.imread(p, cv2.IMREAD_COLOR)
            if img is not None:
                self._frames.append(self._compose(img))
        if not self._frames:
            self._frames = [np.full((FRAME_H, FRAME_W, 3), 90, np.uint8)]
            log.warning("no stock portraits in %s", directory)
        self._dwell = dwell_s
        self.label = f"stock portraits ({len(self._frames)})"

    @classmethod
    def _compose(cls, img):
        """Place the portrait in a webcam-sized frame at a plausible distance."""
        side = int(FRAME_H * cls.HEAD_SCALE)
        small = cv2.resize(img, (side, side), interpolation=cv2.INTER_AREA)
        canvas = np.full((FRAME_H, FRAME_W, 3), 70, np.uint8)
        x0, y0 = (FRAME_W - side) // 2, (FRAME_H - side) // 2
        canvas[y0:y0 + side, x0:x0 + side] = small
        return canvas

    def read(self):
        idx = int(time.time() / self._dwell) % len(self._frames)
        frame = self._frames[idx].copy()
        wobble = 1.0 + 0.04 * np.sin(time.time() * 2.0)
        return np.clip(frame.astype(np.float32) * wobble, 0, 255).astype(np.uint8)


def find_camera(device_glob="/dev/video*", hub_pattern=""):
    """Return (device, name) for the first real capture device, or (None, "")."""
    for device in sorted(glob.glob(device_glob)):
        is_capture, name = _querycap(device)
        if not is_capture:
            log.info("skipping %s: not a capture device", device)
            continue
        if hub_pattern and not fnmatch.fnmatch(_sysfs_id_path(device), hub_pattern):
            log.info("skipping %s: not on %s", device, hub_pattern)
            continue
        return device, name
    return None, ""


def open_source(device_glob="/dev/video*", stock_dir="/app/booth/stock",
                hub_pattern=None, wait_s=None):
    """Pick a source at start-up: a real camera if one is present, else stock."""
    if hub_pattern is None:
        hub_pattern = os.environ.get("CAMERA_HUB_PATTERN", "")
    if wait_s is None:
        wait_s = float(os.environ.get("CAMERA_WAIT_S", "6"))

    forced = os.environ.get("CAMERA_DEVICE", "")
    deadline = time.time() + wait_s
    attempt = 0
    while True:
        attempt += 1
        if forced:
            device, name = forced, _querycap(forced)[1]
        else:
            device, name = find_camera(device_glob, hub_pattern)

        if device:
            try:
                cam = V4L2Camera(device, name)
            except Exception as exc:
                log.warning("%s present but unusable: %s", device, exc)
            else:
                if cam.read() is not None:
                    log.info("using %s", cam.label)
                    return cam
                log.warning("%s opened but returned no frame", device)
                cam.close()

        if time.time() >= deadline:
            break
        if attempt == 1:
            log.info("no camera yet; waiting up to %.0fs", wait_s)
        time.sleep(0.5)

    log.info("no usable camera; falling back to stock portraits")
    return StockPortraits(stock_dir)
