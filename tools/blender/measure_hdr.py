"""Печатает распределение яркости в HDR-карте — чтобы сверять её числами, а не на глаз.

Запуск:
  "C:\\Program Files\\Blender Foundation\\Blender 5.3\\blender.exe" -b --factory-startup -P tools/blender/measure_hdr.py
"""

import os
import bpy
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PATH = os.path.join(ROOT, "public", "hdr", "studio.hdr")

img = bpy.data.images.load(PATH)
w, h = img.size
a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
lum = 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]

print("HDR_SIZE %dx%d" % (w, h))
print("HDR_MEAN %.4f" % lum.mean())
print("HDR_P50 %.4f P90 %.4f P99 %.4f P999 %.4f MAX %.2f" % (
    np.percentile(lum, 50), np.percentile(lum, 90),
    np.percentile(lum, 99), np.percentile(lum, 99.9), lum.max()))
for t in (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0):
    print("HDR_OVER %.2f %.2f%%" % (t, (lum > t).mean() * 100.0))
print("MEASURE_OK")
