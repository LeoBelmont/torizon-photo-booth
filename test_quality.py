"""The gate should reject the frame that produced the bad results."""
import glob, os, sys
import cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from booth.quality import QualityGate, level
from booth.smile import SmileDetector
from booth.sources import StockPortraits

det, gate = SmileDetector(), QualityGate()

print(f"  {'image':22} {'face':6} {'sharp':>7} {'frac':>6} {'eyes':>5} "
      f"{'roll':>6} {'ok':>5}  advice")
rows = []

# The real webcam frame that produced a stranger's face.
if os.path.isfile("_subject.jpg"):
    rows.append(("REAL webcam frame", cv2.imread("_subject.jpg")))

src = StockPortraits("booth/stock")
for p, f in zip(sorted(glob.glob("booth/stock/*.png")), src._frames):
    rows.append((os.path.basename(p), f))

for name, frame in rows:
    d = det.detect(frame)
    if not d.has_face:
        print(f"  {name:22} {'no':6}")
        continue
    q = gate.assess(frame, d.face)
    print(f"  {name:22} {'yes':6} {q.sharpness:7.0f} {q.face_fraction:6.2f} "
          f"{len(q.eyes or []):5} {q.roll_deg:6.1f} {str(q.ok):>5}  {q.advice}")
    lev = level(frame, d.face, q.eyes)
    if lev is not frame:
        print(f"  {'':22} levelled by {q.roll_deg:.1f} deg")
