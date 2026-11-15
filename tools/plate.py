"""Фоновая плита сайта из ref/hero.png.

Машина вырезается: её область забивается куском стены справа (без растения),
края патча сводятся мягкой маской, затем всё слегка размывается — под затемнением
швы не читаются, а свет и материал остаются от исходного кадра.

usage: python tools/plate.py [--blur=6]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ref" / "hero.png"
OUT = ROOT / "public" / "img" / "bg.webp"

# Область машины в исходнике 1710×1112 (bbox кропа machine.webp + запас).
BOX = (505, 45, 1180, 1020)
# Донор: правая часть кадра — стена и дерево, без растения и без машины.
DONOR = (1190, 0, 1710, 1112)
FEATHER = 90


def main() -> None:
    blur = 6.0
    for arg in sys.argv[1:]:
        if arg.startswith("--blur="):
            blur = float(arg.split("=", 1)[1])

    img = Image.open(SRC).convert("RGB")
    w, h = img.size

    x0, y0, x1, y1 = BOX
    bw, bh = x1 - x0, y1 - y0

    donor = img.crop(DONOR).transpose(Image.FLIP_LEFT_RIGHT).resize((bw, bh), Image.LANCZOS)

    # Маска с плавными краями: внутри — 255, к границе — 0.
    yy, xx = np.mgrid[0:bh, 0:bw]
    edge = np.minimum.reduce([xx, yy, bw - 1 - xx, bh - 1 - yy]).astype(np.float32)
    mask = np.clip(edge / FEATHER, 0.0, 1.0)
    mask = (mask * mask * (3 - 2 * mask) * 255).astype(np.uint8)

    patch = img.copy()
    patch.paste(donor, (x0, y0), Image.fromarray(mask))

    # Мягкое размытие только вокруг патча, чтобы не терять текстуру дерева целиком.
    soft = patch.filter(ImageFilter.GaussianBlur(blur))
    assert soft.size == (w, h)
    plate = Image.blend(patch, soft, 0.55)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    plate.save(OUT, "WEBP", quality=80, method=6)
    print(f"{OUT} {OUT.stat().st_size} B {plate.size[0]}x{plate.size[1]}")


if __name__ == "__main__":
    main()
