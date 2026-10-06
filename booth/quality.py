
"""Deciding whether a frame is worth generating from, and levelling it if so."""

import logging

import cv2
import numpy as np

from .smile import cascade_path

log = logging.getLogger(__name__)

MIN_SHARPNESS = 150.0
MIN_FACE_FRACTION = 0.30
MAX_ROLL_DEG = 25.0


class Quality:
    __slots__ = ("ok", "advice", "sharpness", "face_fraction", "roll_deg",
                 "eyes")

    def __init__(self, ok, advice="", sharpness=0.0, face_fraction=0.0,
                 roll_deg=0.0, eyes=None):
        self.ok = ok
        self.advice = advice
        self.sharpness = sharpness
        self.face_fraction = face_fraction
        self.roll_deg = roll_deg
        self.eyes = eyes

    def __repr__(self):
        return (f"Quality(ok={self.ok}, advice={self.advice!r}, "
                f"sharp={self.sharpness:.0f}, frac={self.face_fraction:.2f}, "
                f"roll={self.roll_deg:.0f})")


class QualityGate:
    def __init__(self, min_sharpness=MIN_SHARPNESS,
                 min_face_fraction=MIN_FACE_FRACTION):
        self._eyes = cv2.CascadeClassifier(cascade_path("haarcascade_eye.xml"))
        if self._eyes.empty():
            raise RuntimeError("eye cascade file found but failed to load")
        self._min_sharpness = min_sharpness
        self._min_face_fraction = min_face_fraction

    def find_eyes(self, grey, face):
        """Eye centres inside a face box, upper half only, left-to-right."""
        x, y, w, h = face
        roi = grey[y:y + int(h * 0.55), x:x + w]
        if roi.size == 0:
            return []
        found = self._eyes.detectMultiScale(
            roi, scaleFactor=1.1, minNeighbors=6,
            minSize=(int(w * 0.10), int(w * 0.10)))
        centres = [(x + ex + ew / 2.0, y + ey + eh / 2.0)
                   for ex, ey, ew, eh in found]
        centres.sort(key=lambda p: p[0])
        return centres

    def assess(self, frame, face):
        h, w = frame.shape[:2]
        fx, fy, fw, fh = face
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        face_fraction = fh / float(h)
        region = grey[fy:fy + fh, fx:fx + fw]
        sharpness = (float(cv2.Laplacian(region, cv2.CV_64F).var())
                     if region.size else 0.0)

        eyes = self.find_eyes(grey, face)
        roll = 0.0
        if len(eyes) >= 2:
            left, right = eyes[0], eyes[-1]
            roll = float(np.degrees(np.arctan2(right[1] - left[1],
                                               right[0] - left[0])))

        if face_fraction < self._min_face_fraction:
            advice = "Come closer"
        elif sharpness < self._min_sharpness:
            advice = "Hold still"
        else:
            advice = ""

        return Quality(ok=not advice, advice=advice, sharpness=sharpness,
                       face_fraction=face_fraction, roll_deg=roll, eyes=eyes)


def level(frame, face, eyes):
    """Rotate so the eyes are horizontal, about the midpoint between them."""
    if not eyes or len(eyes) < 2:
        return frame
    left, right = eyes[0], eyes[-1]
    angle = float(np.degrees(np.arctan2(right[1] - left[1], right[0] - left[0])))
    if abs(angle) < 1.5:
        return frame
    centre = ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    m = cv2.getRotationMatrix2D(centre, angle, 1.0)
    h, w = frame.shape[:2]
    return cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)
