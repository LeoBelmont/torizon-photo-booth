
"""Deciding which square of the frame the model actually sees."""

import cv2

DEFAULT_ZOOM = 1.4

UPWARD_BIAS = 0.10


def centre_square(frame):
    """Largest centred square. Used when no face was found."""
    h, w = frame.shape[:2]
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    return frame[y0:y0 + side, x0:x0 + side]


def face_square(frame, face, zoom=DEFAULT_ZOOM):
    """Square crop around a detected face box, clamped to the frame."""
    x, y, w, h = (float(v) for v in face)
    cx = x + w / 2.0
    cy = y + h / 2.0 - UPWARD_BIAS * h
    ih, iw = frame.shape[:2]

    side = min(max(w, h) * zoom, ih, iw)
    x0 = int(round(min(max(0.0, cx - side / 2.0), iw - side)))
    y0 = int(round(min(max(0.0, cy - side / 2.0), ih - side)))
    s = int(round(side))
    return frame[y0:y0 + s, x0:x0 + s]


def crop_for_generation(frame, face, size, zoom=DEFAULT_ZOOM):
    """The square the model sees, at the model's resolution."""
    crop = face_square(frame, face, zoom) if face else centre_square(frame)
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
