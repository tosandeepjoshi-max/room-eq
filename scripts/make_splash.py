"""Make the Pi boot splash: the logo centred on black at the touchscreen's native size.

Usage: python scripts/make_splash.py [logo.png] [out.png] [--size 800x480] [--fill 0.8]
The logo's black margin is cropped, then the logo is scaled to --fill of the
screen height (keeping its aspect ratio) and centred. At the native size the
Plymouth script shows it unscaled, so it cannot be stretched.
"""
import argparse

from PIL import Image, ImageChops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logo", nargs="?", default="assets/logos/joshs_eq.png")
    ap.add_argument("out", nargs="?", default="pi/plymouth/joshs-eq/splash.png")
    ap.add_argument("--size", default="800x480")
    ap.add_argument("--fill", type=float, default=0.8, help="logo height as a share of the screen height")
    ap.add_argument("--threshold", type=int, default=18, help="brightness (0-255) treated as background")
    a = ap.parse_args()

    sw, sh = (int(v) for v in a.size.lower().split("x"))
    im = Image.open(a.logo).convert("RGB")
    r, g, b = im.split()
    bright = ImageChops.lighter(ImageChops.lighter(r, g), b)  # max channel per pixel
    box = bright.point(lambda v: 255 if v > a.threshold else 0).getbbox()
    logo = im.crop(box)
    scale = min(sh * a.fill / logo.height, sw * 0.9 / logo.width)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
    out = Image.new("RGB", (sw, sh), (0, 0, 0))
    out.paste(logo, ((sw - logo.width) // 2, (sh - logo.height) // 2))
    out.save(a.out, optimize=True)
    print(f"wrote {a.out} ({sw}x{sh}), logo {logo.width}x{logo.height}, cropped to {box}")


if __name__ == "__main__":
    main()
