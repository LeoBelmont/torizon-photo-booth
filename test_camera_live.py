"""Live smoke test: real webcam frames through the real detector."""
import sys, time
sys.path.insert(0, "/w")
from booth.smile import SmileDetector
from booth.sources import open_source

src = open_source(stock_dir="/w/booth/stock", wait_s=2)
det = SmileDetector()
print(f"  source: {src.label} (live={src.live}), model={det.using_model}")

n, faces, t0, worst = 0, 0, time.time(), 0.0
while time.time() - t0 < 6.0:
    frame = src.read()
    if frame is None:
        continue
    n += 1
    t = time.time()
    d = det.detect(frame)
    worst = max(worst, (time.time() - t) * 1000)
    if d.has_face:
        faces += 1
elapsed = time.time() - t0
print(f"  {n} frames in {elapsed:.1f}s = {n/elapsed:.1f} fps with detection "
      f"every frame")
print(f"  frames with a face: {faces}")
print(f"  slowest detection: {worst:.1f} ms")
src.close()
