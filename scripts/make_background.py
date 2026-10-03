"""Turn a logo into a dark, softened full-screen background for the Room EQ page.

Usage: python scripts/make_background.py <logo.png> <out.jpg> [--brightness 0.35] [--blur 6]
The logo is centred on a 1920x1080 dark canvas, darkened and blurred so the
panels stay readable on top of it.
"""
import argparse

from PIL import Image, ImageEnhance, ImageFilter

W, H = 1920, 1080


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logo")
    ap.add_argument("out")
    ap.add_argument("--brightness", type=float, default=0.35)
    ap.add_argument("--blur", type=float, default=6)
    ap.add_argument("--scale", type=float, default=0.95, help="logo height as a fraction of the canvas height")
    a = ap.parse_args()

    logo = Image.open(a.logo).convert("RGBA")
    h = int(H * a.scale)
    logo = logo.resize((int(logo.width * h / logo.height), h), Image.LANCZOS)
    logo = ImageEnhance.Brightness(logo).enhance(a.brightness)
    # Fill with the logo's own corner colour so its square edge disappears.
    canvas = Image.new("RGBA", (W, H), logo.getpixel((2, 2))[:3] + (255,))
    canvas.alpha_composite(logo, ((W - logo.width) // 2, (H - logo.height) // 2))
    canvas = canvas.convert("RGB").filter(ImageFilter.GaussianBlur(a.blur))
    canvas.save(a.out, quality=88)
    print(f"wrote {a.out} ({W}x{H})")


if __name__ == "__main__":
    main()
