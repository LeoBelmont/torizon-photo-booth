
"""The photo booth."""

import io
import json
import logging
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from . import effects as effects_mod
from .faceswap import FaceSwapper
from .framing import crop_for_generation
from .quality import QualityGate, level
from .smile import SmileDetector, SmileGate
from .sources import open_source

log = logging.getLogger("booth")

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")

PACK_PATH = os.environ.get("EFFECT_PACK", "/app/effects/pack.json")
STOCK_DIR = os.environ.get("STOCK_DIR", os.path.join(HERE, "stock"))
PORT = int(os.environ.get("PORT", "8080"))
GEN_SIZE = int(os.environ.get("GEN_SIZE", "512"))
GEN_ZOOM = float(os.environ.get("GEN_ZOOM", "2.0"))

DETECT_EVERY = 3
FACE_SMOOTHING = 0.25
REVEAL_S = 14.0
ERROR_S = 6.0
GALLERY_MAX = 12

IDLE, AIM, GENERATE, REVEAL, ERROR = (
    "idle", "aim", "generate", "reveal", "error")


def _blend_box(previous, box, alpha=FACE_SMOOTHING):
    """Exponentially smooth a face box, or let it go when the face does."""
    if box is None:
        return previous
    if previous is None:
        return tuple(float(v) for v in box)
    return tuple(previous[i] + alpha * (box[i] - previous[i]) for i in range(4))


class Booth:
    def __init__(self):
        self.pack = effects_mod.load(PACK_PATH)
        self.source = open_source(stock_dir=STOCK_DIR)
        self.detector = SmileDetector()
        self.gate = SmileGate()
        self.quality = QualityGate()
        self.swapper = FaceSwapper()

        self._lock = threading.Lock()
        self._state = IDLE
        self._state_since = time.time()
        self._preview_jpeg = None
        self._smile_progress = 0.0
        self._happy = 0.0
        self._has_face = False
        self._advice = ""
        self._effect_index = 0
        self._current = None
        self._before = None
        self._after = None
        self._error = None
        self._gallery = []
        self._next_id = 1
        self._stats = {"photos": 0, "last_seconds": None, "mean_seconds": None}
        self._gen_started = 0.0
        self._seconds_total = 0.0
        self._capture_eyes = None
        self._smooth_face = None
        self._device = "cpu"

        self._stop = threading.Event()


    def snapshot(self):
        """State for the panel. Kept small: the panel polls this several"""
        with self._lock:
            elapsed = time.time() - self._state_since
            expected = self._stats["mean_seconds"] or 4.5
            return {
                "state": self._state,
                "elapsed": round(elapsed, 2),
                "has_face": self._has_face,
                "smile": round(self._smile_progress, 3),
                "happy": round(self._happy, 3),
                "model": self.detector.using_model,
                "advice": self._advice,
                "progress": min(0.99, elapsed / expected)
                            if self._state == GENERATE else None,
                "effect": self._current.label if self._current else None,
                "device": self._device,
                "pack": {
                    "name": self.pack.name,
                    "version": self.pack.version,
                    "count": len(self.pack),
                    "error": self.pack.error,
                    "effects": [{"id": e.id, "label": e.label}
                                for e in self.pack.effects],
                },
                "source": {
                    "label": self.source.label,
                    "live": self.source.live,
                    "name": getattr(self.source, "name", "") or None,
                },
                "stats": dict(self._stats),
                "gallery": [{"id": i, "label": lbl} for i, _, lbl in self._gallery],
                "error": self._error,
                "has_photo": self._after is not None,
            }

    def preview_jpeg(self):
        with self._lock:
            return self._preview_jpeg

    def photo(self, photo_id, which):
        with self._lock:
            if which == "after":
                for i, jpg, _ in self._gallery:
                    if i == photo_id:
                        return jpg
            if photo_id == 0:
                return self._before if which == "before" else self._after
        return None

    def _set_state(self, state):
        self._state = state
        self._state_since = time.time()


    def run(self):
        self.swapper.warm_engines()

        frame_no = 0
        detection_smile = False

        while not self._stop.is_set():
            frame = self.source.read()
            if frame is None:
                time.sleep(0.05)
                continue

            frame_no += 1
            now = time.time()

            with self._lock:
                state = self._state
                since = now - self._state_since

            if state in (IDLE, AIM) and frame_no % DETECT_EVERY == 0:
                det = self.detector.detect(frame)
                detection_smile = det.smiling

                if not self.swapper.ready:
                    advice, usable, eyes = "Warming up…", False, None
                elif det.has_face:
                    q = self.quality.assess(frame, det.face)
                    advice, usable, eyes = q.advice, q.ok, q.eyes
                else:
                    advice, usable, eyes = "", False, None

                fired = self.gate.update(det.smiling and usable, now)
                with self._lock:
                    self._smooth_face = _blend_box(self._smooth_face, det.face)
                    self._has_face = det.has_face
                    self._happy = det.confidence
                    self._advice = advice
                    self._smile_progress = self.gate.progress
                    self._capture_eyes = eyes
                    if det.has_face and self._state == IDLE:
                        self._set_state(AIM)
                    elif not det.has_face and self._state == AIM:
                        self._set_state(IDLE)
                if fired:
                    with self._lock:
                        box = self._smooth_face or det.face
                    self._capture(frame, box, eyes)

            elif state == REVEAL and since >= REVEAL_S:
                with self._lock:
                    self._set_state(IDLE)
                    self._current = None
                self.gate.reset(time.time())

            elif state == ERROR and since >= ERROR_S:
                with self._lock:
                    self._error = None
                    self._set_state(IDLE)
                self.gate.reset(time.time())

            self._publish_preview(frame, detection_smile)

        self.source.close()

    def _publish_preview(self, frame, smiling):
        """Crop, annotate lightly, and encode for the MJPEG stream."""
        with self._lock:
            state = self._state
            progress = self._smile_progress
            box = self._smooth_face

        # The same square a capture takes, so the photo fades in over it.
        shown = crop_for_generation(frame, box, GEN_SIZE, GEN_ZOOM)
        if state == AIM and progress > 0:
            colour = (60, 220, 60) if smiling else (200, 200, 200)
            h, w = shown.shape[:2]
            bar = int(w * min(1.0, progress))
            cv2.rectangle(shown, (0, h - 10), (bar, h), colour, -1)

        ok, buf = cv2.imencode(".jpg", shown, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
        if ok:
            with self._lock:
                self._preview_jpeg = buf.tobytes()

    def _capture(self, frame, face, eyes):
        """Take the photo now, from the frame that completed the smile."""
        upright = level(frame, None, eyes)
        if upright is not frame:
            found = self.detector.detect(upright)
            if found.has_face:
                log.info("smile detected; capturing (levelled)")
                self._begin_generation(upright, found.face)
                return
        log.info("smile detected; capturing")
        self._begin_generation(frame, face)

    def _pick_effect(self, effect_id=None):
        """The effect to apply: a named one, or the next in rotation."""
        if effect_id:
            for candidate in self.pack.effects:
                if candidate.id == effect_id:
                    return candidate
            raise RuntimeError(
                f"no effect {effect_id!r}; have "
                f"{[e.id for e in self.pack.effects]}")
        effect = self.pack.by_index(self._effect_index)
        self._effect_index += 1
        return effect

    def _begin_generation(self, frame, face=None, effect_id=None):
        square = crop_for_generation(frame, face, GEN_SIZE, GEN_ZOOM)

        ok, png = cv2.imencode(".png", square)
        if not ok:
            with self._lock:
                self._error = "could not encode the captured frame"
                self._set_state(ERROR)
            return

        with self._lock:
            effect = self._pick_effect(effect_id)
            self._current = effect
            self._before = png.tobytes()
            self._after = None
            self._gen_started = time.time()
            self._set_state(GENERATE)

        threading.Thread(target=self._generate, args=(png.tobytes(), effect),
                         daemon=True).start()

    def _generate(self, png, effect):
        try:
            bgr = cv2.imdecode(np.frombuffer(png, dtype=np.uint8),
                               cv2.IMREAD_COLOR)
            out, seconds = self.swapper.run(bgr, effect.template)
            ok, buf = cv2.imencode(".png", out)
            if not ok:
                raise RuntimeError("could not encode the swapped image")
            out_png = buf.tobytes()
        except Exception as exc:
            log.error("generation failed: %s", exc)
            with self._lock:
                self._error = str(exc)
                self._set_state(ERROR)
            return

        img = cv2.imdecode(np.frombuffer(out_png, dtype=np.uint8),
                           cv2.IMREAD_COLOR)
        ok, jpg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])

        with self._lock:
            self._after = out_png
            self._device = self.swapper.device
            self._stats["photos"] += 1
            self._stats["last_seconds"] = round(seconds, 2)
            self._seconds_total += seconds
            self._stats["mean_seconds"] = round(
                self._seconds_total / self._stats["photos"], 2)
            if ok:
                self._gallery.insert(0, (self._next_id, jpg.tobytes(),
                                         effect.label))
                self._next_id += 1
                del self._gallery[GALLERY_MAX:]
            self._set_state(REVEAL)
        log.info("%s in %.2fs", effect.label, seconds)

    def trigger(self, require_face=True, effect_id=None):
        """Fire the booth without waiting for a smile. A debugging aid."""
        frame = self.source.read()
        if frame is None:
            return False, "no frame from the source"
        with self._lock:
            if self._state == GENERATE:
                return False, f"busy ({self._state})"
        if not self.swapper.ready:
            return False, "still compiling the GPU engines"
        detection = self.detector.detect(frame)
        if require_face and not detection.has_face:
            return False, "no face in frame"
        try:
            self._begin_generation(frame, detection.face, effect_id)
        except RuntimeError as exc:
            return False, str(exc)
        return True, "started"

    def stop(self):
        self._stop.set()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    booth = None

    def log_message(self, fmt, *args):
        pass

    def _send(self, body, ctype, code=200, cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not cache:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path, _, query = self.path.partition("?")
        if path == "/api/trigger":
            params = urllib.parse.parse_qs(query)
            force = params.get("force", ["0"])[0] in ("1", "true", "yes")
            effect_id = params.get("effect", [None])[0]
            ok, detail = self.booth.trigger(require_face=not force,
                                            effect_id=effect_id)
            self._send(json.dumps({"ok": ok, "detail": detail}).encode(),
                       "application/json")
        else:
            self._send(b"not found", "text/plain", 404)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/api/state":
            body = json.dumps(self.booth.snapshot()).encode()
            return self._send(body, "application/json")
        if path == "/preview.mjpg":
            return self._serve_mjpeg()
        if path.startswith("/api/photo/"):
            return self._serve_photo(path)
        self._send(b"not found", "text/plain", 404)

    def _serve_photo(self, path):
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            return self._send(b"bad path", "text/plain", 400)
        try:
            photo_id = int(parts[2])
        except ValueError:
            return self._send(b"bad id", "text/plain", 400)
        which = parts[3].rsplit(".", 1)[0]
        data = self.booth.photo(photo_id, which)
        if data is None:
            return self._send(b"no photo", "text/plain", 404)
        ctype = "image/png" if photo_id == 0 else "image/jpeg"
        self._send(data, ctype, cache=photo_id != 0)

    def _serve_static(self, name):
        if ".." in name or name.startswith("/"):
            return self._send(b"no", "text/plain", 403)
        full = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(full):
            return self._send(b"not found", "text/plain", 404)
        ctype = {"html": "text/html", "js": "application/javascript",
                 "css": "text/css", "png": "image/png"}.get(
                     name.rsplit(".", 1)[-1], "application/octet-stream")
        with open(full, "rb") as fh:
            self._send(fh.read(), ctype + "; charset=utf-8"
                       if ctype.startswith("text") or "javascript" in ctype
                       else ctype)

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                jpeg = self.booth.preview_jpeg()
                if jpeg:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(
                        f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                time.sleep(1 / 15)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    booth = Booth()
    Handler.booth = booth

    thread = threading.Thread(target=booth.run, daemon=True)
    thread.start()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    log.info("panel on http://0.0.0.0:%d  (source: %s, pack: %s)",
             PORT, booth.source.label, booth.pack.describe())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        booth.stop()


if __name__ == "__main__":
    main()
