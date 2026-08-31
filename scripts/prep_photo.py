#!/usr/bin/env python3
"""Prepare the GitHub avatar for ASCII conversion.

Pipeline: fetch -> square crop -> grayscale -> background flatten ->
contrast stretch -> midtone lift -> edge sharpen -> save.

The avatar already sits on a near-black background, so this deliberately
avoids a heavyweight matting dependency (rembg/onnxruntime); a black-point
cut does the same job for this source in a fraction of the time.

Run this only when the avatar changes -- the daily workflow does not need it.

Usage:
    python prep_photo.py
    python prep_photo.py --source path/to/photo.jpg
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

AVATAR_URL = "https://github.com/IGC-ATOM.png"
USER_AGENT = "IGC-ATOM-profile-art/1.0 (+https://github.com/IGC-ATOM/IGC-ATOM)"


def load(source):
    if source:
        return Image.open(source)
    resp = requests.get(AVATAR_URL, headers={"User-Agent": USER_AGENT},
                        timeout=30, allow_redirects=True)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))


def square(img):
    w, h = img.size
    if w == h:
        return img
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def autocrop(img, threshold, margin):
    """Crop away the dead black border so the subject fills the frame.

    The avatar is a small emblem floating in a large black field; without this
    the ASCII grid spends most of its columns on empty space.
    """
    mask = img.point(lambda v: 255 if v > threshold else 0)
    box = mask.getbbox()
    if not box:
        return img
    left, top, right, bottom = box
    pad_x = int((right - left) * margin)
    pad_y = int((bottom - top) * margin)
    left = max(0, left - pad_x)
    top = max(0, top - pad_y)
    right = min(img.width, right + pad_x)
    bottom = min(img.height, bottom + pad_y)
    return img.crop((left, top, right, bottom))


def flatten_background(img, black_point):
    """Crush everything below *black_point* to pure black.

    Keeps the ASCII background clean instead of speckled with stray glyphs.
    """
    if black_point <= 0:
        return img
    lut = [0 if i < black_point else int((i - black_point) * 255 / (255 - black_point))
           for i in range(256)]
    return img.point(lut)


def lift_midtones(img, gamma):
    """gamma < 1 brightens midtones, pulling detail out of dark subjects."""
    if gamma == 1.0:
        return img
    inv = 1.0 / gamma
    lut = [min(255, int(((i / 255.0) ** inv) * 255 + 0.5)) for i in range(256)]
    return img.point(lut)


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Prepare avatar for ASCII conversion.")
    parser.add_argument("--source", default=None, help="local image (default: GitHub avatar)")
    parser.add_argument("--out", default=str(root / "assets" / "profile" / "portrait-source.png"))
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--black-point", type=int, default=30)
    parser.add_argument("--gamma", type=float, default=0.86)
    parser.add_argument("--contrast", type=float, default=1.32)
    parser.add_argument("--cutoff", type=float, default=0.6,
                        help="autocontrast histogram cutoff percentage")
    parser.add_argument("--crop-threshold", type=int, default=10,
                        help="luminance above which a pixel counts as subject")
    parser.add_argument("--crop-margin", type=float, default=0.04,
                        help="breathing room kept around the subject, as a fraction")
    parser.add_argument("--no-autocrop", dest="autocrop", action="store_false")
    parser.set_defaults(autocrop=True)
    args = parser.parse_args()

    img = load(args.source)
    if img.mode in ("RGBA", "LA", "P"):
        # Composite onto black so transparency reads as background.
        img = img.convert("RGBA")
        canvas = Image.new("RGBA", img.size, (0, 0, 0, 255))
        img = Image.alpha_composite(canvas, img)

    img = img.convert("L")
    if args.autocrop:
        img = autocrop(img, args.crop_threshold, args.crop_margin)
    img = square(img)
    img = img.resize((args.size, args.size), Image.LANCZOS)

    img = flatten_background(img, args.black_point)
    img = ImageOps.autocontrast(img, cutoff=args.cutoff)
    img = lift_midtones(img, args.gamma)
    img = ImageEnhance.Contrast(img).enhance(args.contrast)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=115, threshold=3))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)

    hist = img.histogram()
    dark = sum(hist[:32]) / float(args.size * args.size)
    print("wrote %s (%dx%d, %.0f%% background)" % (out, args.size, args.size, dark * 100))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
