"""Camera discovery check. Needs real V4L2 nodes to mean anything."""
import glob, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from booth.sources import _querycap, _sysfs_id_path, find_camera, open_source

nodes = sorted(glob.glob("/dev/video*"))
print(f"  nodes present: {nodes or 'none'}")
print(f"\n  {'device':16} {'capture':8} {'name':28} sysfs id")
for dev in nodes:
    is_cap, name = _querycap(dev)
    print(f"  {dev:16} {str(is_cap):8} {name[:28]:28} {_sysfs_id_path(dev)}")

dev, name = find_camera()
print(f"\n  find_camera() -> {dev} ({name!r})")

captures = [d for d in nodes if _querycap(d)[0]]
print(f"  capture nodes: {captures}")
print(f"  metadata-only nodes correctly skipped: "
      f"{[d for d in nodes if d not in captures]}")

if nodes and not captures:
    print("\n  WARNING: nodes exist but none report VIDEO_CAPTURE")
if dev and dev != captures[0]:
    print(f"\n  WARNING: picked {dev}, expected {captures[0]}")

src = open_source(stock_dir="booth/stock", wait_s=0)
frame = src.read()
print(f"\n  open_source() -> {src.label} (live={src.live})")
print(f"  frame: {None if frame is None else frame.shape}")
