"""Make a header logo from a logo on a black background.

Usage: python scripts/make_logo.py <logo.png> <out.png> [--height 240] [--threshold 18]
Black turns transparent (brightness becomes opacity, so glows fade out
smoothly), the empty margin is cropped, and the result is scaled to --height
pixels tall (about 4x the on-screen header height, so it stays sharp).
"""
import argparse

from PIL import Image, ImageChops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logo")
    ap.add_argument("out")
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--threshold", type=int, default=18, help="brightness (0-255) treated as background")
    a = ap.parse_args()

    im = Image.open(a.logo).convert("RGB")
    r, g, b = im.split()
    bright = ImageChops.lighter(ImageChops.lighter(r, g), b)  # max channel per pixel
    t = a.threshold
    alpha = bright.point(lambda v: 0 if v <= t else min(255, (v - t) * 255 // max(1, 110 - t)))
    rgba = Image.merge("RGBA", (r, g, b, alpha))
    box = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
    rgba = rgba.crop(box)
    w = round(rgba.width * a.height / rgba.height)
    rgba.resize((w, a.height), Image.LANCZOS).save(a.out, optimize=True)
    print(f"wrote {a.out} ({w}x{a.height}), cropped to {box}")


if __name__ == "__main__":
    main()
