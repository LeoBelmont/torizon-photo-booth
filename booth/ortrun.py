
"""Running models with ONNX Runtime: on the Hexagon NPU through the QNN provider where
the board has one, on the CPU otherwise. Same contract as trt.TRTRunner."""

import logging
import os
import time

import numpy as np
import onnxruntime as ort

log = logging.getLogger(__name__)

THREADS = int(os.environ.get("ORT_THREADS", "4"))
CACHE_DIR = os.environ.get("QNN_CACHE_DIR", "/cache")
ACCEL = os.environ.get("BOOTH_ACCEL", "auto")  # auto | npu | cpu

# fp16 on the HTP: measured against the fp32 CPU result on a VENTUNO Q, the swapped
# face is visually identical (PSNR 34 dB), unlike TensorRT fp16 on Jetson.
QNN_OPTIONS = {
    "backend_type": "htp",
    "htp_performance_mode": "burst",
    "enable_htp_fp16_precision": "1",
    "htp_graph_finalization_optimization_mode": "3",
}

_devices = None


def npu_devices():
    """The NPU as ONNX Runtime sees it, or [] when the plugin or the device is absent."""
    global _devices
    if _devices is None:
        _devices = []
        if ACCEL != "cpu":
            try:
                import onnxruntime_qnn as oq

                ort.register_execution_provider_library(oq.EP_NAME, oq.get_library_path())
                _devices = [d for d in ort.get_ep_devices() if d.ep_name == oq.EP_NAME]
                log.info("QNN provider %s: %d NPU device(s)", oq.__version__, len(_devices))
            except Exception as exc:
                log.warning("QNN provider unavailable (%s); models run on the CPU", exc)
        if ACCEL == "npu" and not _devices:
            raise RuntimeError("BOOTH_ACCEL=npu but no QNN NPU device is available")
    return _devices


class OrtRunner:
    """float32 tensor(s) in, flat float32 out. Compiles for the NPU once and keeps the
    compiled context under CACHE_DIR, so later starts load in a second."""

    def __init__(self, path, threads=THREADS, allow_npu=True):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        self.path = path
        name = os.path.splitext(os.path.basename(path))[0]
        devices = npu_devices() if allow_npu else []
        self.device = "npu" if devices else "cpu"

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.log_severity_level = 3
        started = time.time()
        if devices:
            opts.add_provider_for_devices(devices, QNN_OPTIONS)
            ctx = os.path.join(CACHE_DIR, f"{name}_ctx.onnx")
            if os.path.isfile(ctx):
                self._sess = ort.InferenceSession(ctx, opts)
                log.info("%s on the NPU from the cached context (%.1fs)", name,
                         time.time() - started)
            else:
                caching = True
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    opts.add_session_config_entry("ep.context_enable", "1")
                    opts.add_session_config_entry("ep.context_file_path", ctx)
                except OSError as exc:
                    caching = False
                    log.warning("cannot cache the NPU context in %s: %s", CACHE_DIR, exc)
                self._sess = ort.InferenceSession(path, opts)
                # ONNX Runtime falls back to the CPU silently when the HTP backend
                # cannot be set up (a missing device node, say). The context file only
                # appears when a graph really was compiled for the NPU.
                if caching and not os.path.isfile(ctx):
                    self.device = "cpu"
                    log.error("%s did NOT reach the NPU (no QNN context written); "
                              "running on the CPU. Check the fastrpc/dma_heap devices "
                              "and the QNN errors above.", name)
                else:
                    log.info("%s compiled for the NPU (%.1fs)", name, time.time() - started)
        else:
            self._sess = ort.InferenceSession(path, opts)
            log.info("%s on the CPU (%.1fs)", name, time.time() - started)
        self._inputs = self._sess.get_inputs()

    def infer(self, tensor):
        tensors = list(tensor) if isinstance(tensor, (list, tuple)) else [tensor]
        feed = {}
        if len(tensors) == 1:
            feed[self._inputs[0].name] = np.ascontiguousarray(tensors[0], np.float32)
        else:
            # Inputs are matched by rank: inswapper takes the 1x3x128x128 face and
            # the 1x512 identity, whichever order the graph declares them.
            remaining = list(tensors)
            for inp in self._inputs:
                rank = len(inp.shape)
                idx = next((i for i, t in enumerate(remaining)
                            if np.ndim(t) == rank), 0)
                feed[inp.name] = np.ascontiguousarray(remaining.pop(idx), np.float32)
        out = self._sess.run(None, feed)[0]
        return np.asarray(out, dtype=np.float32).reshape(-1)

    def close(self):
        self._sess = None
