
"""Running models on the GPU through TensorRT."""

import json
import logging
import os
import struct
import subprocess
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

RUNNER = os.environ.get("TRT_INFER", "/usr/local/bin/trt_infer")
TRTEXEC = os.environ.get("TRTEXEC", "/usr/bin/trtexec")
ENGINE_DIR = os.environ.get("TRT_ENGINE_DIR", "/engines")

BUILD_TIMEOUT_S = float(os.environ.get("TRT_BUILD_TIMEOUT_S", "600"))
RUN_TIMEOUT_S = float(os.environ.get("TRT_RUN_TIMEOUT_S", "60"))
READY_MAX_LINES = 40


def available():
    """Is there a GPU path at all in this container?"""
    return os.path.isfile(RUNNER) and os.access(RUNNER, os.X_OK)


def _meta_path(engine_path):
    return engine_path + ".json"


def build_engine(onnx_path, engine_path, size, nchw, input_name=None,
                 dynamic=False, fp16=True, shapes=None):
    """Compile an ONNX model into a TensorRT engine with trtexec."""
    if not os.path.isfile(TRTEXEC):
        log.warning("trtexec not found at %s; no GPU engines will be built",
                    TRTEXEC)
        return False

    os.makedirs(os.path.dirname(engine_path) or ".", exist_ok=True)
    tmp_engine = engine_path + ".partial"
    cmd = [TRTEXEC, f"--onnx={onnx_path}", f"--saveEngine={tmp_engine}"]
    if fp16:
        cmd.append("--fp16")
    if shapes:
        cmd.append(f"--shapes={shapes}")
    elif dynamic and input_name:
        dims = (f"1x3x{size}x{size}" if nchw else f"1x{size}x{size}x3")
        # trtexec splits name from dims on the last colon; ONNX names end ":0".
        cmd.append(f"--shapes={input_name}:{dims}")
    # trtexec benchmarks after saving, which has OOM-killed it mid-write.
    cmd.append("--skipInference")

    started = time.time()
    log.info("building TensorRT engine for %s (this takes a minute or two)",
             os.path.basename(onnx_path))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=BUILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        log.error("engine build for %s timed out", onnx_path)
        return False
    if proc.returncode != 0 or not os.path.isfile(tmp_engine):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        log.error("engine build for %s failed: %s", onnx_path, " | ".join(tail))
        return False

    os.replace(tmp_engine, engine_path)
    with open(_meta_path(engine_path), "w", encoding="utf-8") as fh:
        json.dump({"size": size, "nchw": bool(nchw)}, fh)
    log.info("engine ready: %s (%.0fs)", os.path.basename(engine_path),
             time.time() - started)
    return True


class TRTRunner:
    """A resident trt_infer process: float32 tensor in, float32 tensor out."""

    def __init__(self, engine_path):
        if not os.path.isfile(engine_path):
            raise FileNotFoundError(engine_path)
        self.engine_path = engine_path
        self._proc = None
        self._lock = threading.Lock()

    def _ensure_process(self):
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if self._proc is not None:
            log.warning("trt_infer for %s exited (%s); restarting",
                        os.path.basename(self.engine_path),
                        self._proc.returncode)
        self._proc = subprocess.Popen(
            [RUNNER, "--serve", self.engine_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0)
        line = ""
        for _ in range(READY_MAX_LINES):
            raw = self._proc.stderr.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("ready"):
                log.info("trt_infer resident for %s (%s)",
                         os.path.basename(self.engine_path), line)
                return self._proc
            if line:
                log.debug("trt_infer: %s", line)
        out = (self._proc.stderr.read(400).decode("utf-8", "replace")
               if self._proc.poll() is not None else "")
        raise RuntimeError(
            f"trt_infer did not report ready; last line: {line} {out}".strip())

    def infer(self, tensor):
        """Run one or more float32 arrays through the engine."""
        if isinstance(tensor, (list, tuple)):
            payload = b"".join(
                np.ascontiguousarray(t, dtype=np.float32).tobytes()
                for t in tensor)
        else:
            payload = np.ascontiguousarray(tensor, dtype=np.float32).tobytes()
        with self._lock:
            proc = self._ensure_process()
            try:
                proc.stdin.write(struct.pack("<I", len(payload)))
                proc.stdin.write(payload)
                proc.stdin.flush()
                header = proc.stdout.read(4)
                if len(header) != 4:
                    raise RuntimeError("trt_infer closed the stream")
                (count,) = struct.unpack("<I", header)
                if count == 0:
                    raise RuntimeError("trt_infer reported an inference failure")
                buf = b""
                while len(buf) < count:
                    chunk = proc.stdout.read(count - len(buf))
                    if not chunk:
                        raise RuntimeError("trt_infer truncated its response")
                    buf += chunk
            except Exception:
                self._proc = None
                proc.kill()
                raise
        return np.frombuffer(buf, dtype=np.float32)

    def close(self):
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._proc.stdin.close()
                    self._proc.wait(timeout=5)
                except Exception:
                    self._proc.kill()
            self._proc = None


def load_meta(engine_path):
    """The input layout recorded beside an engine when it was built."""
    meta_path = _meta_path(engine_path)
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(meta_path)
    with open(meta_path, "r", encoding="utf-8") as fh:
        return json.load(fh)
