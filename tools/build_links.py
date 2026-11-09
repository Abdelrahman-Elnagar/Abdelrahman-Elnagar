"""Render the pixel-art link buttons that sit between the card and the board.

Writes link_<name>_<theme>.svg for portfolio, LinkedIn and email, in both themes.

GitHub shows README SVGs through <img>, so nothing inside one is clickable and
nothing reacts to hover. Each button is therefore its own image inside its own
link. To still read as one row, every image is exactly a third of the card's
width and the README sizes each at a third of the column; the gaps are drawn
inside the images, so the outer edges line up with the card and the board.

Usage:
    python tools/build_links.py
"""

from __future__ import annotations

from theme import (ADVANCE, CANVAS_W, FONT_FACE, FONT_STACK, LINE_MID, ROOT, THEMES,
                   bitmap, loop, mix, sprite_path, validate_smil)

PX = 3                         # one sprite pixel
GAP = 14                       # space between two buttons
SLOT_W = CANVAS_W / 3          # each image: a third of the row
BUTTON_W = (CANVAS_W - 2 * GAP) / 3
HEIGHT = 20 * PX
LABEL_FONT = 18
ICON_GAP = 12                  # between the icon and its label
OUTLINE_MIX = 0.18             # outline: this far from the background toward the text

assert BUTTON_W % PX == 0, "the button must be a whole number of pixels wide"

# --- Sprites (10 x 9..10 pixels) ---------------------------------------------
MONITOR = """
##########
#........#
#.#......#
#..#.....#
#.#......#
#........#
##########
....##....
..######..
"""

MONITOR_CURSOR = """
..........
..........
..........
..........
....###...
..........
..........
..........
..........
"""

LINKEDIN = """
.########.
##########
##.#######
##########
##.#...###
##.#.##.##
##.#.##.##
##.#.##.##
##########
.########.
"""

ENVELOPE = """
##########
##......##
#.#....#.#
#..#..#..#
#...##...#
#........#
#........#
##########
"""

# Each icon has its own idle move: the monitor's cursor blinks, LinkedIn hops,
# the envelope rattles like a notification.
CURSOR_BLINK = 1.06
HOP_EVERY = 2.0
RATTLE_EVERY = 2.4


def path(art: str) -> str:
    return sprite_path(bitmap(art), PX, PX)


def twitch(offsets: list[tuple[int, int]], times: list[float], dur: float) -> str:
    """Whole-pixel jumps at the given fractions of a dur-second cycle."""
    values = ";".join(f"{dx * PX},{dy * PX}" for dx, dy in offsets)
    return (f'<animateTransform attributeName="transform" type="translate" '
            f'values="{values}" keyTimes="{";".join(f"{t:g}" for t in times)}" dur="{dur}s" '
            f'calcMode="discrete" repeatCount="indefinite"/>')


def monitor() -> str:
    return (f'<path d="{path(MONITOR)}"/>'
            f'<path d="{path(MONITOR_CURSOR)}">{loop("opacity", ["1", "0"], CURSOR_BLINK)}</path>')


def linkedin() -> str:
    hop = twitch([(0, 0), (0, -1), (0, 0)], [0, 0.8, 0.9], HOP_EVERY)
    return f'<g>{hop}<path d="{path(LINKEDIN)}"/></g>'


def envelope() -> str:
    rattle = twitch([(0, 0), (-1, 0), (1, 0), (-1, 0), (1, 0), (0, 0)],
                    [0, 0.7, 0.74, 0.78, 0.82, 0.86], RATTLE_EVERY)
    return f'<g>{rattle}<path d="{path(ENVELOPE)}"/></g>'


# (file name, label, accent colour key, icon)
LINKS = (
    ("portfolio", "PORTFOLIO", "key", monitor),
    ("linkedin", "LINKEDIN", "value", linkedin),
    ("email", "EMAIL", "coral", envelope),
)


def stepped(x: float, y: float, w: float, h: float) -> str:
    """A rectangle whose corners are cut by one pixel step."""
    return (f"M{x + PX:g} {y:g}h{w - 2 * PX:g}v{PX}h{PX}v{h - 2 * PX:g}h{-PX}v{PX}"
            f"h{-(w - 2 * PX):g}v{-PX}h{-PX}v{-(h - 2 * PX):g}h{PX}z")


def build(theme: str, slot: int) -> str:
    c = THEMES[theme]
    _, label, accent_key, icon = LINKS[slot]
    accent = c[accent_key]

    x = slot * GAP / 3         # button i starts at i * (BUTTON_W + GAP) on the row, its image at i * SLOT_W
    icon_w = 10 * PX
    label_w = len(label) * LABEL_FONT * ADVANCE
    left = x + (BUTTON_W - icon_w - ICON_GAP - label_w) / 2
    mid = (PX + HEIGHT - 2 * PX) / 2   # centre on the area above the accent bar

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{SLOT_W:.3f}px" height="{HEIGHT}px"
     viewBox="0 0 {SLOT_W:.3f} {HEIGHT}" font-family="{FONT_STACK}">
<style>
{FONT_FACE}
text {{white-space: pre;}}
.px {{shape-rendering: crispEdges;}}
</style>
<g class="px">
<path d="{stepped(x, 0, BUTTON_W, HEIGHT)}" fill="{mix(c['bg'], c['fg'], OUTLINE_MIX)}"/>
<path d="{stepped(x + PX, PX, BUTTON_W - 2 * PX, HEIGHT - 2 * PX)}" fill="{c['bg']}"/>
<rect x="{x + 2 * PX:g}" y="{HEIGHT - 2 * PX}" width="{BUTTON_W - 4 * PX:g}" height="{PX}" fill="{accent}"/>
<g fill="{accent}" transform="translate({left + icon_w / 2:.2f},{mid:g})">{icon()}</g>
</g>
<text x="{left + icon_w + ICON_GAP:.2f}" y="{mid + LINE_MID * LABEL_FONT:.2f}" font-size="{LABEL_FONT}px" fill="{c['fg']}">{label}</text>
</svg>
"""


def main() -> None:
    print(f"row      : {CANVAS_W}px = 3 x {BUTTON_W:g}px buttons + 2 x {GAP}px gaps")
    for theme in THEMES:
        for slot, (name, *_) in enumerate(LINKS):
            svg = build(theme, slot)
            checked = validate_smil(svg)
            out = ROOT / f"link_{name}_{theme}.svg"
            out.write_text(svg, encoding="utf-8")
            print(f"wrote {out.name} ({out.stat().st_size:,} bytes, {checked} animations validated)")


if __name__ == "__main__":
    main()
