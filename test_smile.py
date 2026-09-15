"""Trigger check: the real source through the real detector.

Goes via StockPortraits rather than loading PNGs directly, because the framing
that source applies is part of what makes face detection work at all.
"""
import glob, os, sys, time
import cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from booth.smile import SmileDetector, SmileGate
from booth.sources import StockPortraits

det = SmileDetector()
print(f"  expression model in use: {det.using_model}")
src = StockPortraits("booth/stock")
paths = sorted(glob.glob("booth/stock/*.png"))

ok = True
print(f"\n  {'file':22} {'face':6} {'happy':>7} {'smiling':8} {'want':6} {'ms':>6}")
scores = {}
for i, path in enumerate(paths):
    frame = src._frames[i]
    t0 = time.time()
    d = det.detect(frame)
    ms = (time.time() - t0) * 1000
    name = os.path.basename(path)
    want = "smile" in name
    scores[name] = d.confidence
    verdict = "ok" if (d.has_face and d.smiling == want) else "FAIL"
    if verdict == "FAIL":
        ok = False
    print(f"  {name:22} {str(d.has_face):6} {d.confidence:7.3f} "
          f"{str(d.smiling):8} {str(want):6} {ms:6.1f}  {verdict}")

smiling = [v for k, v in scores.items() if "smile" in k]
neutral = [v for k, v in scores.items() if "neutral" in k]
if smiling and neutral:
    print(f"\n  separation: neutral max {max(neutral):.3f} | "
          f"smiling min {min(smiling):.3f}")
    if min(smiling) > max(neutral):
        print(f"  a threshold anywhere in "
              f"({max(neutral):.3f}, {min(smiling):.3f}) separates them")
    else:
        print("  scores OVERLAP -- no threshold separates these")
        ok = False

gate = SmileGate(need_frames=4, cooldown_s=3.0)
fires = sum(gate.update(True, 1000.0 + i * 0.1) for i in range(12))
print(f"\n  gate fires over 12 held smiling frames: {fires} (want 1)")
if fires != 1:
    ok = False

gate2 = SmileGate(need_frames=6, cooldown_s=3.0)
seq = [False, True, False, True, True, False, True]
stray = sum(gate2.update(v, 2000.0 + i * 0.1) for i, v in enumerate(seq))
print(f"  gate fires on a flickering false positive: {stray} (want 0)")
if stray != 0:
    ok = False

print("\n  RESULT:", "PASS" if ok else "PROBLEMS ABOVE")
sys.exit(0 if ok else 1)
