"""Render the contribution calendar with a Pac-Man eating it.

Reads cache/calendar.json (written by tools/fetch_stats.py) and writes
pacman_dark.svg / pacman_light.svg next to the card SVGs.

The board keeps GitHub's calendar format (53 weeks by 7 days of rounded
squares, months across the top, Mon/Wed/Fri down the side, the Less/More
legend) so it still reads as your contribution graph. The retro part is
confined to what moves: pixel-art sprites, and a header that counts up like an
arcade score as Pac-Man eats each day.

Design rules:

- Colours come from theme.THEMES. The level ramp is a blend between the card's
  own background and foreground, so the calendar is a greyscale version of
  GitHub's drawn in the card's palette. Pac-Man is the card's accent colour and
  the ghosts take its coral. Change the palette and the board follows.
- Every sprite is one <path> on a single pixel grid, so neighbouring pixels
  never show anti-aliased seams.
- Every long animation shares one duration and begins at 0, so the whole board
  stays in lock-step forever with no scripting.

Usage:
    python tools/build_pacman.py
"""

from __future__ import annotations

import datetime as dt
import json

from theme import (ADVANCE, CANVAS_W, FONT_FACE, FONT_STACK, ROOT, THEMES,
                   bitmap, loop, mix, sprite_path, validate_smil)

CALENDAR_SRC = ROOT / "cache" / "calendar.json"

# --- Geometry (px) ----------------------------------------------------------
U = 2                      # one Pac-Man pixel
GHOST_PX = 1.5             # one ghost pixel
CELL = 14                  # a day's square
PITCH = 18                 # day-to-day spacing; the 14/18 ratio matches GitHub's
RADIUS = 3
MARGIN = 15
LABEL_COL = 38             # room for Mon/Wed/Fri left of the grid
HEADER_FONT = 14
LABEL_FONT = 12

# Share of the way from the card's background to its foreground, per level.
LEVEL_MIX = (0.10, 0.30, 0.50, 0.72, 1.0)

# --- Timing (s) -------------------------------------------------------------
STEP = 0.075               # time to cross one day
INTRO = 1.5                # full calendar, Pac-Man waiting, before he moves
OUTRO = 1.8                # empty calendar and the final total, before the reset
EAT_AHEAD = 5              # px: a day vanishes as the mouth reaches it
CHOMP = 0.24               # one open-half-shut-half mouth cycle

# Three ghosts trail Pac-Man by some days. Stride lengths differ on purpose:
# three identical loops started together would march in perfect lock-step.
CAST = (
    # (days behind, trait, seconds per stride)
    (5, "blink", 0.34),
    (8, "bob", 0.30),
    (11, "hop", 0.38),
)
TRAIL = tuple(lag for lag, _, _ in CAST)
BLINK_EVERY = 2.4          # eyes shut for a beat once per this many seconds

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}

# --- Sprites ----------------------------------------------------------------
PAC_OPEN = """
..#####..
.######..
######...
#####....
#####....
#####....
######...
.######..
..#####..
"""
PAC_HALF = """
..#####..
.#######.
#########
#######..
#####....
#######..
#########
.#######.
..#####..
"""
PAC_SHUT = """
..#####..
.#######.
#########
#########
#########
#########
#########
.#######.
..#####..
"""

# A ghost, split into layers so each animates on its own: the body with
# round eyes cut out, two skirt frames, and a pair of eyelids.
GHOST_BODY = """
...######...
..########..
.##########.
###..##..###
###..##..###
############
############
############
############
############
............
............
"""
GHOST_SKIRT_A = """
............
............
............
............
............
............
............
............
............
............
###.####.###
##...##...##
"""
GHOST_SKIRT_B = """
............
............
............
............
............
............
............
............
............
............
#.###..###.#
...##..##...
"""
GHOST_LIDS = """
............
............
............
............
###..##..###
............
............
............
............
............
............
............
"""


# --- Timeline ---------------------------------------------------------------
class Timeline:
    """Pac-Man's route: a zigzag across the seven weekday rows, as timed waypoints."""

    def __init__(self, weeks: int, left: float, top: float) -> None:
        self.left, self.top = left, top
        self.speed = PITCH / STEP

        pts = []
        for r in range(7):
            cols = (0, weeks - 1) if r % 2 == 0 else (weeks - 1, 0)
            pts += [(self.cx(cols[0]), self.cy(r)), (self.cx(cols[1]), self.cy(r))]
        # run off the right edge far enough that the last ghost clears it too
        pts.append((CANVAS_W + (max(TRAIL) + 2) * PITCH, self.cy(6)))
        self.points = pts

        self.dist = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.dist.append(self.dist[-1] + abs(b[0] - a[0]) + abs(b[1] - a[1]))

        self.done = INTRO + (self.dist[-1] + max(TRAIL) * PITCH) / self.speed
        self.total = self.done + OUTRO

    def cx(self, col: int) -> float:
        return self.left + col * PITCH + CELL / 2

    def cy(self, row: int) -> float:
        return self.top + row * PITCH + CELL / 2

    def k(self, t: float) -> str:
        """A keyTime: seconds on the master clock as a 0..1 fraction."""
        return f"{min(max(t / self.total, 0.0), 1.0):.5f}"

    def eat_time(self, col: int, row: int) -> float:
        seg = row * 2
        s = self.dist[seg] + abs(self.cx(col) - self.points[seg][0])
        return INTRO + max(0.0, s - EAT_AHEAD) / self.speed

    def motion(self, lag_cells: int = 0):
        """Keyframes and headings for a sprite trailing Pac-Man by lag_cells.

        Returns (keys, heads): keys is [(t, (x, y))] for the translate, heads is
        [(t, degrees)] for the facing. Both start at t=0, because a discrete SMIL
        animation whose first keyTime is not 0 is silently discarded.
        """
        lag = lag_cells * PITCH
        start = (self.points[0][0] - lag, self.points[0][1])
        route = [start] + self.points
        dist = [0.0] + [d + lag for d in self.dist]

        keys = [(0.0, start)]
        for d, p in zip(dist, route):
            t = INTRO + d / self.speed
            if (t, p) != keys[-1]:
                keys.append((t, p))

        heads = []
        for (t, a), (_, b) in zip(keys, keys[1:]):
            if a != b:
                heads.append((t, 0 if b[0] > a[0] else 180 if b[0] < a[0] else 90))
        heads[0] = (0.0, heads[0][1])  # face the first move before making it
        return keys, heads


def anim_translate(tl: Timeline, keys) -> str:
    """Linear motion through keys, holding the last point until the loop ends."""
    last = keys[-1][1]
    values = ";".join(f"{x:g},{y:g}" for _, (x, y) in keys) + f";{last[0]:g},{last[1]:g}"
    times = ";".join(tl.k(t) for t, _ in keys) + ";1"
    return (f'<animateTransform attributeName="transform" type="translate" '
            f'values="{values}" keyTimes="{times}" dur="{tl.total:.3f}s" repeatCount="indefinite"/>')


def anim_discrete(tl: Timeline, attr: str, values: list[str], times: list[float]) -> str:
    """A step function on the master clock: values[i] holds from times[i]."""
    return (f'<animate attributeName="{attr}" values="{";".join(values)}" '
            f'keyTimes="{";".join(tl.k(t) for t in times)}" dur="{tl.total:.3f}s" '
            f'calcMode="discrete" repeatCount="indefinite"/>')


# --- Data -------------------------------------------------------------------
def load_calendar() -> dict:
    if not CALENDAR_SRC.exists():
        raise SystemExit(f"{CALENDAR_SRC} missing: run tools/fetch_stats.py first")
    return json.loads(CALENDAR_SRC.read_text(encoding="utf-8"))


def month_labels(weeks: list[list]) -> list[tuple[int, str]]:
    labels, last = [], None
    for i, week in enumerate(weeks):
        day = next((d for d in week if d), None)
        if not day:
            continue
        m = dt.date.fromisoformat(day["date"]).month
        if m != last:
            labels.append((i, MONTHS[m - 1]))
            last = m
    # GitHub drops a label squeezed against the next one; so do we
    return [lab for j, lab in enumerate(labels)
            if j + 1 == len(labels) or labels[j + 1][0] - lab[0] >= 3]


# --- Render -----------------------------------------------------------------
def ghost(theme: str, tl: Timeline, lag: int, trait: str, stride: float) -> str:
    layer = {name: sprite_path(bitmap(art), GHOST_PX, GHOST_PX) for name, art in (
        ("body", GHOST_BODY), ("a", GHOST_SKIRT_A), ("b", GHOST_SKIRT_B), ("lids", GHOST_LIDS))}

    keys, _ = tl.motion(lag)
    skirt_stride = stride if trait != "bob" else stride * 0.8
    parts = [
        f'<path d="{layer["body"]}"/>',
        f'<path d="{layer["a"]}">{loop("opacity", ["1", "0"], skirt_stride)}</path>',
        f'<path d="{layer["b"]}" opacity="0">{loop("opacity", ["0", "1"], skirt_stride)}</path>',
    ]
    if trait == "blink":
        # the eyelids fill the eye holes back in for a beat
        parts.append(
            f'<path d="{layer["lids"]}" opacity="0"><animate attributeName="opacity" '
            f'values="0;1;0" keyTimes="0;0.93;0.98" dur="{BLINK_EVERY}s" '
            f'calcMode="discrete" repeatCount="indefinite"/></path>'
        )
    body = "".join(parts)
    if trait == "hop":
        # one pixel row up on every other half-stride, in step with the skirt
        body = (f'<g><animateTransform attributeName="transform" type="translate" '
                f'values="0,0;0,{-GHOST_PX:g}" keyTimes="0;0.5" dur="{stride}s" '
                f'calcMode="discrete" repeatCount="indefinite"/>{body}</g>')
    return f'<g>{anim_translate(tl, keys)}<g fill="{THEMES[theme]["coral"]}">{body}</g></g>'


def pacman(theme: str, tl: Timeline) -> str:
    keys, heads = tl.motion(0)
    rot = (f'<animateTransform attributeName="transform" type="rotate" '
           f'values="{";".join(str(h) for _, h in heads)}" '
           f'keyTimes="{";".join(tl.k(t) for t, _ in heads)}" dur="{tl.total:.3f}s" '
           f'calcMode="discrete" repeatCount="indefinite"/>')
    idle = anim_discrete(tl, "visibility", ["visible", "hidden"], [0.0, INTRO])
    moving = anim_discrete(tl, "visibility", ["hidden", "visible"], [0.0, INTRO])
    frames = "".join(
        f'<path d="{sprite_path(bitmap(art))}">{loop("opacity", [str(v) for v in vis], CHOMP)}</path>'
        for art, vis in ((PAC_OPEN, (1, 0, 0, 0)), (PAC_HALF, (0, 1, 0, 1)), (PAC_SHUT, (0, 0, 1, 0)))
    )
    return (f'<g>{anim_translate(tl, keys)}<g fill="{THEMES[theme]["key"]}">{rot}'
            f'<g>{idle}<path d="{sprite_path(bitmap(PAC_OPEN))}"/></g>'
            f'<g visibility="hidden">{moving}{frames}</g></g></g>')


def build(theme: str, cal: dict) -> str:
    c = THEMES[theme]
    weeks = cal["weeks"]
    ramp = [mix(c["bg"], c["fg"], t) for t in LEVEL_MIX]

    left = MARGIN + LABEL_COL
    header_y = MARGIN + HEADER_FONT
    months_y = header_y + 26
    top = months_y + 8
    grid_bottom = top + 6 * PITCH + CELL
    legend_y = grid_bottom + 24
    height = legend_y + MARGIN

    tl = Timeline(len(weeks), left, top)
    cells: list[str] = []

    # The empty grid: every day that exists, drawn at level 0.
    base = []
    for col, week in enumerate(weeks):
        for row, day in enumerate(week):
            if day:
                base.append(f'<use href="#d" x="{left + col * PITCH:g}" y="{top + row * PITCH:g}"/>')
    cells.append(f'<g fill="{ramp[0]}">{"".join(base)}</g>')

    # Days with contributions sit on top and vanish as Pac-Man eats them.
    eaten: list[tuple[float, int]] = []
    for col, week in enumerate(weeks):
        for row, day in enumerate(week):
            if not day or not day["level"]:
                continue
            t = tl.eat_time(col, row)
            eaten.append((t, day["count"]))
            cells.append(
                f'<use href="#d" x="{left + col * PITCH:g}" y="{top + row * PITCH:g}" '
                f'fill="{ramp[day["level"]]}">'
                f'{anim_discrete(tl, "visibility", ["visible", "hidden"], [0.0, t])}</use>'
            )

    sprites = [ghost(theme, tl, lag, trait, stride) for lag, trait, stride in CAST]
    sprites.append(pacman(theme, tl))

    # Header: GitHub's own sentence, with the number counting up as an arcade
    # score. Every value is padded to the final width, so in a monospace font
    # the words after it never shift.
    eaten.sort()
    steps, score = [(0.0, 0)], 0
    for t, count in eaten:
        if count:
            score += count
            steps.append((t, score))
    width = len(f"{cal['total']:,}")
    number = []
    for i, (t, value) in enumerate(steps):
        nxt = steps[i + 1][0] if i + 1 < len(steps) else None
        if i == 0 and nxt is None:
            vals, times = ["visible"], [0.0]
        elif i == 0:
            vals, times = ["visible", "hidden"], [0.0, nxt]
        elif nxt is None:
            vals, times = ["hidden", "visible"], [0.0, t]
        else:
            vals, times = ["hidden", "visible", "hidden"], [0.0, t, nxt]
        anim = anim_discrete(tl, "visibility", vals, times) if len(vals) > 1 else ""
        number.append(
            f'<tspan x="{MARGIN:g}" visibility="{"visible" if i == 0 else "hidden"}">'
            f'{anim}{value:>{width},}</tspan>'
        )
    words_x = MARGIN + width * HEADER_FONT * ADVANCE

    months = "".join(f'<text x="{left + col * PITCH:g}" y="{months_y:g}">{name}</text>'
                     for col, name in month_labels(weeks))
    days = "".join(f'<text x="{MARGIN:g}" y="{tl.cy(row) + LABEL_FONT * 0.35:g}">{name}</text>'
                   for row, name in WEEKDAYS.items())

    # Legend, right-aligned under the grid like GitHub's.
    grid_right = left + (len(weeks) - 1) * PITCH + CELL
    more_w = 4 * LABEL_FONT * ADVANCE
    swatch_x = grid_right - more_w - 6 - (5 * PITCH - (PITCH - CELL))
    swatches = "".join(f'<rect x="{swatch_x + i * PITCH:g}" y="{legend_y - CELL + 3:g}" '
                       f'width="{CELL}" height="{CELL}" rx="{RADIUS}" fill="{ramp[i]}"/>'
                       for i in range(5))

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}px" height="{height:g}px"
     font-family="{FONT_STACK}">
<style>
{FONT_FACE}
text, tspan {{white-space: pre;}}
.px {{shape-rendering: crispEdges;}}
</style>
<defs><rect id="d" width="{CELL}" height="{CELL}" rx="{RADIUS}"/></defs>
<rect width="{CANVAS_W}px" height="{height:g}px" fill="{c['bg']}" rx="15"/>
<text y="{header_y:g}" font-size="{HEADER_FONT}px" fill="{c['fg']}">{"".join(number)}</text>
<text x="{words_x:g}" y="{header_y:g}" font-size="{HEADER_FONT}px" fill="{c['fg']}"> contributions in the last year</text>
<g font-size="{LABEL_FONT}px" fill="{c['dots']}">{months}{days}
<text x="{swatch_x - 6:g}" y="{legend_y:g}" text-anchor="end">Less</text>
<text x="{grid_right - more_w:g}" y="{legend_y:g}">More</text>
</g>
{swatches}
{"".join(cells)}
<g class="px">{"".join(sprites)}</g>
</svg>
"""


def main() -> None:
    cal = load_calendar()
    days = sum(1 for w in cal["weeks"] for d in w if d)
    print(f"calendar : {len(cal['weeks'])} weeks, {days} days, {cal['total']} contributions")
    for name in THEMES:
        svg = build(name, cal)
        checked = validate_smil(svg)
        out = ROOT / f"pacman_{name}.svg"
        out.write_text(svg, encoding="utf-8")
        print(f"wrote {out.name} ({out.stat().st_size:,} bytes, {checked} animations validated)")


if __name__ == "__main__":
    main()
