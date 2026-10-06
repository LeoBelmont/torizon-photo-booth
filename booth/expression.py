
"""Is this face happy?"""

import logging
import os

import cv2
import numpy as np

log = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("FER_MODEL", "/app/models/emotion-ferplus-8.onnx")

EMOTIONS = ("neutral", "happiness", "surprise", "sadness",
            "anger", "disgust", "fear", "contempt")
HAPPINESS = EMOTIONS.index("happiness")

INPUT_SIZE = 64


def _softmax(x):
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


class ExpressionModel:
    """FER+ over ONNX Runtime. Raises if it cannot be loaded."""

    def __init__(self, path=MODEL_PATH):
        import onnxruntime as ort

        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(path, sess_options=opts,
                                          providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name
        log.info("expression model loaded from %s", path)

    def happiness(self, grey, face):
        """Probability that the given face box is smiling, 0..1."""
        x, y, w, h = face
        pad = int(0.08 * max(w, h))
        H, W = grey.shape[:2]
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        crop = grey[y0:y1, x0:x1]
        if crop.size == 0:
            return 0.0

        crop = cv2.resize(crop, (INPUT_SIZE, INPUT_SIZE),
                          interpolation=cv2.INTER_AREA)
        blob = crop.astype(np.float32).reshape(1, 1, INPUT_SIZE, INPUT_SIZE)
        scores = self._sess.run(None, {self._input: blob})[0].ravel()
        return float(_softmax(scores)[HAPPINESS])


def try_load(path=MODEL_PATH):
    """Load the model, or return None and say why."""
    try:
        return ExpressionModel(path)
    except Exception as exc:
        log.warning("expression model unavailable (%s: %s); "
                    "falling back to the Haar smile cascade",
                    type(exc).__name__, exc)
        return None
