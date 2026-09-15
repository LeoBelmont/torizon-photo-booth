
"""Finding a face, and deciding whether it is smiling."""

import logging
import os

import cv2

from . import expression

log = logging.getLogger(__name__)

MOUTH_TOP = 0.55
MOUTH_BOTTOM = 1.0

_CASCADE_DIRS = (
    "/usr/share/opencv4/haarcascades/",
    "/usr/share/opencv/haarcascades/",
    "/usr/share/OpenCV/haarcascades/",
)


def cascade_path(name):
    """Absolute path to a named Haar cascade XML, wherever OpenCV put it."""
    bundled = getattr(getattr(cv2, "data", None), "haarcascades", None)
    for directory in ([bundled] if bundled else []) + list(_CASCADE_DIRS):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError(
        f"cannot find {name}; looked in {[bundled] + list(_CASCADE_DIRS)}")


class Detection:
    """One frame's worth of findings."""

    __slots__ = ("face", "smiling", "confidence")

    def __init__(self, face=None, smiling=False, confidence=0.0):
        self.face = face
        self.smiling = smiling
        self.confidence = confidence

    @property
    def has_face(self):
        return self.face is not None


class SmileDetector:
    def __init__(self, min_face=90, smile_neighbors=24, happy_threshold=0.5,
                 model=None):
        self._face = cv2.CascadeClassifier(
            cascade_path("haarcascade_frontalface_default.xml"))
        self._smile = cv2.CascadeClassifier(
            cascade_path("haarcascade_smile.xml"))
        if self._face.empty() or self._smile.empty():
            raise RuntimeError("Haar cascade files found but failed to load")
        self._min_face = min_face
        self._smile_neighbors = smile_neighbors
        self._threshold = happy_threshold
        self._model = model if model is not None else expression.try_load()

    @property
    def using_model(self):
        return self._model is not None

    def detect(self, frame):
        grey_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        grey_eq = cv2.equalizeHist(grey_raw)

        faces = self._face.detectMultiScale(
            grey_eq, scaleFactor=1.2, minNeighbors=5,
            minSize=(self._min_face, self._min_face))
        if len(faces) == 0:
            return Detection()

        face = max(faces, key=lambda f: f[2] * f[3])

        if self._model is not None:
            score = self._model.happiness(grey_raw, face)
            return Detection(face=tuple(face), smiling=score >= self._threshold,
                             confidence=score)
        return self._cascade_smile(grey_eq, face)

    def _cascade_smile(self, grey, face):
        x, y, w, h = face
        mouth = grey[int(y + h * MOUTH_TOP):int(y + h * MOUTH_BOTTOM), x:x + w]
        if mouth.size == 0:
            return Detection(face=tuple(face))
        smiles = self._smile.detectMultiScale(
            mouth, scaleFactor=1.7, minNeighbors=self._smile_neighbors,
            minSize=(int(w * 0.25), int(h * 0.10)))
        return Detection(face=tuple(face), smiling=len(smiles) > 0,
                         confidence=min(1.0, len(smiles) / 2.0))


class SmileGate:
    """Turns a noisy per-frame boolean into one trigger."""

    def __init__(self, need_frames=6, cooldown_s=3.0):
        self._need = need_frames
        self._cooldown = cooldown_s
        self._run = 0
        self._armed = True
        self._last_fire = 0.0

    @property
    def progress(self):
        """0..1, for the on-screen smile meter."""
        if not self._armed:
            return 0.0
        return min(1.0, self._run / self._need)

    def update(self, smiling, now):
        if not smiling:
            self._run = 0
            if now - self._last_fire >= self._cooldown:
                self._armed = True
            return False

        self._run += 1
        if self._armed and self._run >= self._need:
            self._armed = False
            self._run = 0
            self._last_fire = now
            return True
        return False

    def reset(self, now):
        self._run = 0
        self._armed = False
        self._last_fire = now
