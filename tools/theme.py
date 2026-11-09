"""Shared palette, type metrics and SVG helpers for every generator in tools/.

One palette, one pixel grid, one font: the profile card, the link buttons and
the Pac-Man board all import from here, so a colour changed in THEMES reaches
every SVG on the next build.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Identity ---------------------------------------------------------------
LOGIN = "Abdelrahman-Elnagar"

# --- Palette ----------------------------------------------------------------
THEMES = {
    "dark": {
        "bg": "#161b22", "fg": "#c9d1d9", "art": "#c9d1d9",
        "key": "#F76E0A", "value": "#a5d6ff",
        "add": "#3fb950", "del": "#f85149", "dots": "#616e7f",
        "coral": "#D97757",
    },
    "light": {
        "bg": "#ffffff", "fg": "#24292f", "art": "#24292f",
        "key": "#bc4c00", "value": "#0550ae",
        "add": "#1a7f37", "del": "#cf222e", "dots": "#8c959f",
        "coral": "#C15F3C",
    },
}

# --- Type metrics -----------------------------------------------------------
# Consolas advances 0.55em per glyph, the generic monospace fallback 0.60em.
# The @font-face in every SVG re-declares Consolas at size-adjust:109%, which
# lands it on 0.55 * 1.09 = 0.5995, so both measure the same and the layout
# holds whether or not the viewer has Consolas installed.
ADVANCE = 0.5995
LINE_MID = 0.35            # a text line's visual middle sits this far (em) above its baseline
CANVAS_W = 1018            # every SVG on the profile is this wide, so they stack as one unit

FONT_STACK = "ConsolasFallback,Consolas,Menlo,monospace"
FONT_FACE = """@font-face {
  src: local('Consolas'), local('Consolas Bold');
  font-family: 'ConsolasFallback';
  font-display: swap;
  size-adjust: 109%;
}"""


# --- Colour -----------------------------------------------------------------
def mix(a: str, b: str, t: float) -> str:
    """Blend two #rrggbb colours: t=0 is a, t=1 is b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


# --- Pixel sprites ----------------------------------------------------------
def bitmap(art: str) -> list[str]:
    return [r for r in art.strip("\n").split("\n") if r]


def sprite_path(rows: list[str], pw: float = 2, ph: float = 2) -> str:
    """Merge a bitmap into one <path> of horizontal runs, centred on 0,0.

    One path per sprite means neighbouring pixels never show anti-aliased seams.
    """
    h, w = len(rows), max(len(r) for r in rows)
    x0, y0 = -w * pw / 2, -h * ph / 2
    d = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            if row[x] != "#":
                x += 1
                continue
            run = x
            while run < len(row) and row[run] == "#":
                run += 1
            d.append(f"M{x0 + x * pw:g} {y0 + y * ph:g}h{(run - x) * pw:g}v{ph:g}h{-(run - x) * pw:g}z")
            x = run
    return "".join(d)


def loop(attr: str, values: list[str], dur: float) -> str:
    """A short free-running discrete cycle, independent of any master clock."""
    n = len(values)
    keys = ";".join(f"{i / n:.4f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{";".join(values)}" '
            f'keyTimes="{keys}" dur="{dur}s" calcMode="discrete" repeatCount="indefinite"/>')


# --- Validation -------------------------------------------------------------
def validate_smil(svg: str) -> int:
    """Reject any animation a browser would silently drop.

    SMIL does not error on a malformed animation, it just ignores it, so a bad
    keyTimes list ships as a sprite that never moves. Check the rules that
    bite: keyTimes start at 0, never decrease, stay within 1, match the number
    of values, and (for non-discrete modes) end exactly at 1.
    """
    root = ET.fromstring(svg.split("?>", 1)[1])
    count = 0
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("animate", "animateTransform") or "keyTimes" not in el.attrib:
            continue
        count += 1
        keys = [float(k) for k in el.get("keyTimes").split(";")]
        values = el.get("values").split(";")
        where = f"{tag} {el.get('attributeName')} ({len(values)} values)"
        if len(keys) != len(values):
            raise SystemExit(f"{where}: {len(keys)} keyTimes for {len(values)} values")
        if keys[0] != 0:
            raise SystemExit(f"{where}: first keyTime is {keys[0]}, must be 0")
        if any(b < a for a, b in zip(keys, keys[1:])):
            raise SystemExit(f"{where}: keyTimes decrease")
        if keys[-1] > 1:
            raise SystemExit(f"{where}: keyTime {keys[-1]} past 1")
        if el.get("calcMode", "linear") != "discrete" and keys[-1] != 1:
            raise SystemExit(f"{where}: interpolated animation must end at keyTime 1")
        if re.search(r"nan|inf", el.get("values"), re.I):
            raise SystemExit(f"{where}: non-finite value")
    return count
