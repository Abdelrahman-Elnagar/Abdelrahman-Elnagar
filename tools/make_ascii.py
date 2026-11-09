"""Turn a picture into the ASCII art on the left of the profile card.

    python tools/make_ascii.py            # a monogram badge (the default)
    python tools/make_ascii.py photo.jpg  # your own photo, centre-cropped to a portrait

Writes assets/ascii-art.txt (for the dark card) and assets/ascii-art-light.txt
(for the light card). A photo needs opposite ramps on the two backgrounds:
light pixels are the dense glyphs on dark, dark pixels are the dense glyphs on
white. The monogram is drawn as ink on blank, so both files come out the same.

Needs Pillow:  pip install pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from theme import ROOT

COLS = 60
CELL_ASPECT = 0.54          # a character cell is this much as wide as it is tall
PORTRAIT = 1.38             # height / width of the art
RAMP = " .:-=+*#%@"         # blank to dense

FONT_CANDIDATES = (
    "C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/System/Library/Fonts/Menlo.ttc",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def monogram(w: int, h: int) -> Image.Image:
    """White ink on black: a rounded badge around the initials."""
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    pad = int(w * 0.07)
    d.rounded_rectangle((pad, pad, w - pad, h - pad), radius=int(w * 0.16), outline=170, width=int(w * 0.022))

    letters = "AE"
    f = font(int(w * 0.70))
    box = d.textbbox((0, 0), letters, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = (w - tw) / 2 - box[0], h * 0.50 - th / 2 - box[1]
    # fade the ink from bright at the top to softer at the bottom, so the ramp has range
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((x, y), letters, fill=255, font=f)
    fade = Image.linear_gradient("L").resize((w, h)).transpose(Image.FLIP_TOP_BOTTOM)
    fade = fade.point(lambda v: 150 + v * 105 // 255)
    img = ImageChops.lighter(img, ImageChops.multiply(mask, fade))

    return img.filter(ImageFilter.GaussianBlur(radius=w * 0.003))


def photo(path: str, w: int, h: int) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path)).convert("L")
    img = ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=(0.5, 0.35))
    return ImageOps.autocontrast(img, cutoff=2)


def to_ascii(img: Image.Image, rows: int, invert: bool) -> str:
    small = img.resize((COLS, rows), Image.LANCZOS)
    out = []
    for y in range(rows):
        line = ""
        for x in range(COLS):
            v = small.getpixel((x, y)) / 255
            if invert:
                v = 1 - v
            line += RAMP[min(len(RAMP) - 1, int(v * len(RAMP)))]
        out.append(line.rstrip())
    return "\n".join(out) + "\n"


def main() -> None:
    rows = round(COLS * CELL_ASPECT * PORTRAIT)
    w, h = 1200, round(1200 * PORTRAIT)
    src = sys.argv[1] if len(sys.argv) > 1 else None
    img = photo(src, w, h) if src else monogram(w, h)

    dark = to_ascii(img, rows, invert=False)
    light = to_ascii(img, rows, invert=bool(src))
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "ascii-art.txt").write_text(dark, encoding="utf-8")
    (ROOT / "assets" / "ascii-art-light.txt").write_text(light, encoding="utf-8")
    print(f"wrote assets/ascii-art*.txt ({COLS} cols x {rows} rows, {'photo' if src else 'monogram'})")


if __name__ == "__main__":
    main()
