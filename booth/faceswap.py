
"""Putting the visitor's face into a character portrait."""

import glob
import logging
import os
import threading
import time

import cv2
import numpy as np

from . import trt

log = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("ONNX_MODEL_DIR", "/app/models")
TEMPLATE_DIR = os.environ.get("TEMPLATE_DIR", "/app/templates")

DET_MODEL = "det_10g.onnx"
REC_MODEL = "w600k_r50.onnx"
SWAP_MODEL = "inswapper_128.onnx"
EMAP_FILE = "inswapper_emap.npy"

# inswapper must be fp32: with fp16 it returns a smeared face, not an error.
# w600k declares a dynamic batch, so its shape has to be pinned.
# Detection is absent because its input is dynamically shaped; it stays on CPU.
ENGINE_SPECS = {
    "w600k_r50": {"size": 112, "nchw": True, "fp16": True,
                  "shapes": "input.1:1x3x112x112"},
    "inswapper_128": {"size": 128, "nchw": True, "fp16": False, "shapes": None},
}

ARCFACE_DST = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)

DET_SIZE = int(os.environ.get("SWAP_DET_SIZE", "320"))
DET_THRESHOLD = 0.5


def norm_crop(img, kps, size):
    """Align a face to the canonical five-point layout at a given size."""
    if size % 112 == 0:
        dst = ARCFACE_DST * (size / 112.0)
    else:
        # 128 is not a multiple of 112: keep the 112 scale and shift x instead.
        dst = ARCFACE_DST * (size / 128.0)
        dst[:, 0] += 8.0 * (size / 128.0)
    matrix, _ = cv2.estimateAffinePartial2D(kps.reshape(5, 2), dst,
                                            method=cv2.LMEDS)
    if matrix is None:
        raise RuntimeError("could not align the face")
    return cv2.warpAffine(img, matrix, (size, size), borderValue=0.0), matrix


class FaceDetector:
    """SCRFD: one box and five keypoints for the most prominent face."""

    def __init__(self, path, size=DET_SIZE, threshold=DET_THRESHOLD):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(path, sess_options=opts,
                                          providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name
        self._size = size
        self._threshold = threshold
        self._centers = {}

    def _anchor_centers(self, grid, stride, anchors=2):
        key = (grid, stride)
        if key not in self._centers:
            ys, xs = np.mgrid[:grid, :grid]
            pts = np.stack([xs, ys], -1).astype(np.float32) * stride
            self._centers[key] = np.broadcast_to(
                pts[:, :, None, :], (grid, grid, anchors, 2)).reshape(-1, 2)
        return self._centers[key]

    def detect(self, bgr):
        """Return (box, keypoints) for the largest confident face, or None."""
        h0, w0 = bgr.shape[:2]
        scale = min(self._size / h0, self._size / w0)
        resized = cv2.resize(bgr, (int(round(w0 * scale)),
                                   int(round(h0 * scale))))
        canvas = np.zeros((self._size, self._size, 3), np.uint8)
        canvas[:resized.shape[0], :resized.shape[1]] = resized

        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128,
                                     (self._size, self._size),
                                     (127.5, 127.5, 127.5), swapRB=True)
        # Outputs are grouped by stride: scores, then boxes, then keypoints.
        outs = self._sess.run(None, {self._input: blob})

        boxes, kpss, scores = [], [], []
        for i, stride in enumerate((8, 16, 32)):
            score = outs[i].reshape(-1)
            keep = score >= self._threshold
            if not keep.any():
                continue
            centers = self._anchor_centers(self._size // stride, stride)[keep]
            box = outs[i + 3].reshape(-1, 4)[keep] * stride
            kps = outs[i + 6].reshape(-1, 10)[keep] * stride
            boxes.append(np.stack([centers[:, 0] - box[:, 0],
                                   centers[:, 1] - box[:, 1],
                                   centers[:, 0] + box[:, 2],
                                   centers[:, 1] + box[:, 3]], axis=1))
            kpss.append((centers[:, None, :] + kps.reshape(-1, 5, 2)))
            scores.append(score[keep])
        if not boxes:
            return None, None

        boxes = np.concatenate(boxes) / scale
        kpss = np.concatenate(kpss) / scale
        scores = np.concatenate(scores)
        area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        best = int(np.argmax(area * scores))
        return boxes[best], kpss[best]


class FaceSwapper:
    def __init__(self, model_dir=MODEL_DIR, template_dir=TEMPLATE_DIR):
        det_path = os.path.join(model_dir, DET_MODEL)
        rec_path = os.path.join(model_dir, REC_MODEL)
        swap_path = os.path.join(model_dir, SWAP_MODEL)
        for path in (det_path, rec_path, swap_path):
            if not os.path.isfile(path):
                raise FileNotFoundError(path)

        self._model_dir = model_dir
        self.detector = FaceDetector(det_path)

        # The identity vector is projected through this or the face is nobody's.
        self._emap = self._load_emap(model_dir, swap_path)

        engine_dir = trt.ENGINE_DIR
        self._rec_trt = self._maybe_engine(engine_dir, "w600k_r50")
        self._swap_trt = self._maybe_engine(engine_dir, "inswapper_128")

        self._templates = {}
        self._load_templates(template_dir)
        log.info("face swap ready: %d templates, emap %s",
                 len(self._templates), self._emap.shape)

    @staticmethod
    def _maybe_engine(engine_dir, name):
        path = os.path.join(engine_dir, f"{name}.engine")
        if not (trt.available() and os.path.isfile(path)):
            return None
        try:
            runner = trt.TRTRunner(path)
            log.info("%s on the GPU", name)
            return runner
        except Exception as exc:
            log.warning("engine %s unusable (%s); using the CPU", path, exc)
            return None

    def warm_engines(self):
        """Compile any missing engines, in the background."""
        if not trt.available():
            log.error("no trt_infer in this image; the booth cannot take photos")
            return None

        def work():
            for name, spec in ENGINE_SPECS.items():
                engine = os.path.join(trt.ENGINE_DIR, f"{name}.engine")
                onnx_path = os.path.join(self._model_dir, f"{name}.onnx")
                if (os.path.isfile(engine)
                        and os.path.isfile(engine + ".json")):
                    log.info("engine already cached: %s", f"{name}.engine")
                    continue
                if not os.path.isfile(onnx_path):
                    log.warning("no %s to build an engine from", onnx_path)
                    continue
                trt.build_engine(onnx_path, engine, spec["size"], spec["nchw"],
                                 fp16=spec["fp16"], shapes=spec["shapes"])
            if self.refresh() == "gpu":
                log.info("face swap moved to the GPU")

        thread = threading.Thread(target=work, name="swap-warm", daemon=True)
        thread.start()
        return thread

    def refresh(self):
        """Re-check for engines after a background build."""
        if self.ready:
            return self.device
        engine_dir = trt.ENGINE_DIR
        self._rec_trt = self._rec_trt or self._maybe_engine(engine_dir, "w600k_r50")
        self._swap_trt = (self._swap_trt
                          or self._maybe_engine(engine_dir, "inswapper_128"))
        return self.device

    def close(self):
        for runner in (self._rec_trt, self._swap_trt):
            if runner is not None:
                runner.close()

    @staticmethod
    def _load_emap(model_dir, swap_path):
        cached = os.path.join(model_dir, EMAP_FILE)
        if os.path.isfile(cached):
            return np.load(cached)
        log.info("extracting emap from %s (no %s present)",
                 os.path.basename(swap_path), EMAP_FILE)
        import onnx
        from onnx import numpy_helper

        return numpy_helper.to_array(
            onnx.load(swap_path).graph.initializer[-1])

    def _load_templates(self, directory):
        """Detect each template's face once, at start-up."""
        for path in sorted(glob.glob(os.path.join(directory, "*.png"))
                           + glob.glob(os.path.join(directory, "*.jpg"))):
            name = os.path.splitext(os.path.basename(path))[0]
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                log.warning("template %s could not be read", path)
                continue
            box, kps = self.detector.detect(img)
            if box is None:
                log.warning("template %s has no detectable face; skipped", name)
                continue
            self._templates[name] = (img, kps)
            log.info("template %r ready (%dx%d)", name, img.shape[1], img.shape[0])

    @property
    def templates(self):
        return sorted(self._templates)

    @property
    def ready(self):
        """Are both GPU engines in place? Nothing works until they are."""
        return self._rec_trt is not None and self._swap_trt is not None

    @property
    def device(self):
        return "gpu" if self.ready else "warming"

    def _identity(self, bgr, kps):
        """The 512-d vector describing who this is, projected for the swapper."""
        aligned, _ = norm_crop(bgr, kps, 112)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (112, 112),
                                     (127.5, 127.5, 127.5), swapRB=True)
        embedding = self._rec_trt.infer(blob).flatten()
        embedding = embedding / np.linalg.norm(embedding)
        latent = np.dot(embedding.reshape(1, -1), self._emap)
        return (latent / np.linalg.norm(latent)).astype(np.float32)

    def run(self, bgr, template):
        """Put the face in `bgr` into the named template."""
        if not self.ready:
            raise RuntimeError("still compiling the GPU engines")
        entry = self._templates.get(template)
        if entry is None:
            raise RuntimeError(f"no template named {template!r}; have "
                               f"{self.templates}")
        target_img, target_kps = entry

        started = time.time()
        box, kps = self.detector.detect(bgr)
        if box is None:
            raise RuntimeError("no face found to swap")
        latent = self._identity(bgr, kps)

        aligned, matrix = norm_crop(target_img, target_kps, 128)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 255.0, (128, 128),
                                     (0.0, 0.0, 0.0), swapRB=True)
        out = self._swap_trt.infer([blob, latent]).reshape(3, 128, 128)
        face = np.clip(np.transpose(out, (1, 2, 0))[:, :, ::-1] * 255.0, 0, 255)

        result = self._paste(target_img, face.astype(np.uint8), matrix)
        return result, time.time() - started

    @staticmethod
    def _paste(target_img, face, matrix):
        inverse = cv2.invertAffineTransform(matrix)
        h, w = target_img.shape[:2]
        warped = cv2.warpAffine(face, inverse, (w, h), borderValue=0)

        mask = np.zeros((128, 128), np.float32)
        cv2.ellipse(mask, (64, 78), (46, 56), 0, 0, 360, 1.0, -1)
        mask = cv2.warpAffine(mask, inverse, (w, h), borderValue=0)
        face_px = max(1.0, float(np.count_nonzero(mask > 0.5)) ** 0.5)
        kernel = int(max(9, (face_px * 0.12) // 2 * 2 + 1))
        mask = cv2.GaussianBlur(mask, (kernel, kernel), 0)[..., None]
        return (warped * mask + target_img * (1.0 - mask)).astype(np.uint8)
