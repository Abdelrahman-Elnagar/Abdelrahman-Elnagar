"""Build the neofetch-style profile card (dark_mode.svg / light_mode.svg).

Everything is regenerated from scratch on every run: the ASCII art comes from
assets/ascii-art*.txt and the numbers from cache/stats.json (written by
tools/fetch_stats.py). Nothing patches an SVG after the fact, so the column
arithmetic lives in exactly one place, `line()` below. Its elastic fills
stretch each row to exactly PANEL_COLS characters and the render asserts it,
so an arithmetic slip is a crash, not a row that quietly drifts out of line.

Usage:
    python tools/build_card.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from theme import ADVANCE, FONT_FACE, FONT_STACK, LINE_MID, ROOT, THEMES

STATS_SRC = ROOT / "cache" / "stats.json"
ART_SRC = {"dark": ROOT / "assets" / "ascii-art.txt", "light": ROOT / "assets" / "ascii-art-light.txt"}

# --- Content ----------------------------------------------------------------
TITLE = "abdelrahman@elnagar"
SINCE = dt.date(2025, 6, 1)        # AI Engineer at BSA, from the CV

INFO = [
    ("OS", "Windows"),
    ("Uptime.BSA", None),          # filled from SINCE
    ("Host", "Cairo, Egypt"),
    ("Kernel", "AI Engineer @ BSA"),
    ("Education", "B.Sc. CS (Data Science), GIU"),
    None,
    ("Languages.Programming", "Python, Java, C++, Julia"),
    ("Languages.Computer", "SQL, GraphQL"),
    ("Languages.Real", "Arabic, English, German (A2)"),
    None,
    ("Focus.AI", "RAG, Agentic Workflows, VLMs"),
    ("Focus.Vision", "DINOv2, YOLOv8, Computer Vision"),
    ("Focus.Backend", "FastAPI, Django, Docker, AWS"),
    ("Awards", "Kaggle 1st x2, DAAD Scholar"),
    ("Certs", "AWS AI + Cloud Practitioner"),
]

CONTACT = [
    ("Email", "abdelrahmanelnagar123@gmail.com"),
    ("LinkedIn", "abdelrahman-elnagar"),
    ("Portfolio", "abdelrahman-elnagar.my.canva.site"),
]

# --- Geometry ---------------------------------------------------------------
ART_COL_WIDTH = 414.0      # the art column is a fixed pixel width; its font size follows from the grid
ART_CELL_ASPECT = 0.54     # a character cell is this much as wide as it is tall
PANEL_FONT = 16.0
PANEL_LINE = 20.0
PANEL_COLS = 58
MARGIN = 15
GUTTER = 18
LINE_PAD = 0.65            # a block of lines reaches this far (em) past its outer baselines


def art_metrics(cols: int) -> tuple[float, float]:
    """(font_size, line_height) that fit `cols` into ART_COL_WIDTH without stretching the portrait."""
    font = ART_COL_WIDTH / (cols * ADVANCE)
    return font, font * ADVANCE / ART_CELL_ASPECT


def esc(text: str) -> str:
    return html.escape(text, quote=False)


# --- Rows -------------------------------------------------------------------
# A row is a list of segments: (class, text), or ("fill", char, class) for a
# run that stretches to take up the slack.
def line(segs: list[tuple], x: int, y: float) -> str:
    fixed = sum(len(s[1]) for s in segs if s[0] != "fill")
    fills = [i for i, s in enumerate(segs) if s[0] == "fill"]
    slack = PANEL_COLS - fixed
    if slack < len(fills):
        raise SystemExit(f"row does not fit in {PANEL_COLS} cols: {segs!r}")
    base, extra = divmod(slack, len(fills))
    widths = {idx: base + (1 if n < extra else 0) for n, idx in enumerate(fills)}

    out, total = [], 0
    for i, s in enumerate(segs):
        if s[0] == "fill":
            body, cls = s[1] * widths[i], s[2]
        else:
            cls, body = s
        total += len(body)
        out.append(f'<tspan class="{cls}">{esc(body)}</tspan>' if cls else esc(body))
    assert total == PANEL_COLS, f"row rendered {total} cols, expected {PANEL_COLS}"
    return f'<tspan x="{x}" y="{y:g}">{"".join(out)}</tspan>'


def key_segs(key: str) -> list[tuple]:
    """A key split on dots, so `Languages.Programming` colours both halves."""
    segs = []
    for i, part in enumerate(key.split(".")):
        if i:
            segs.append((None, "."))
        segs.append(("key", part))
    return segs


def info_row(key: str, value: str) -> list[tuple]:
    return ([("cc", ". ")] + key_segs(key)
            + [(None, ":"), ("cc", " "), ("fill", ".", "cc"), ("cc", " "), ("value", value)])


def rule_row(label: str, bold: bool = False) -> list[tuple]:
    return [("title" if bold else None, label), (None, " -"), ("fill", "—", None), (None, "-")]


# --- Data -------------------------------------------------------------------
def span(since: dt.date, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    years = today.year - since.year
    months = today.month - since.month
    days = today.day - since.day
    if days < 0:
        months -= 1
        days += (today.replace(day=1) - dt.timedelta(days=1)).day
    if months < 0:
        years -= 1
        months += 12

    def plural(n: int, word: str) -> str:
        return f"{n} {word}" + ("" if n == 1 else "s")

    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


def load_stats() -> dict:
    blank = {k: "--" for k in ("repos", "contrib", "stars", "commits", "followers", "loc", "added", "deleted")}
    if not STATS_SRC.exists():
        return blank
    raw = json.loads(STATS_SRC.read_text(encoding="utf-8"))
    return {k: f"{raw[k]:,}" if isinstance(raw.get(k), int) else blank[k] for k in blank}


def load_art(src: Path) -> list[str]:
    lines = src.read_text(encoding="utf-8").split("\n")
    filled = [i for i, text in enumerate(lines) if text.strip()]
    if not filled:
        raise SystemExit(f"{src} has no content")
    body = [text.rstrip() for text in lines[filled[0]: filled[-1] + 1]]
    indent = min(len(t) - len(t.lstrip()) for t in body if t.strip())
    return [t[indent:] for t in body]


# --- Panel ------------------------------------------------------------------
def panel_rows() -> list[list[tuple] | None]:
    st = load_stats()
    rows: list[list[tuple] | None] = [rule_row(TITLE, bold=True)]
    for item in INFO:
        if item is None:
            rows.append(None)
            continue
        key, val = item
        rows.append(info_row(key, span(SINCE) if val is None else val))

    rows += [None, rule_row("- Contact")]
    rows += [info_row(k, v) for k, v in CONTACT]

    rows += [None, rule_row("- GitHub Stats")]
    rows.append(
        [("cc", ". "), ("key", "Repos"), (None, ":"), ("cc", " "), ("fill", ".", "cc"), ("cc", " "),
         ("value", st["repos"]), (None, " {"), ("key", "Contributed"), (None, ": "), ("value", st["contrib"]),
         (None, "} | "), ("key", "Stars"), (None, ":"), ("cc", " "), ("fill", ".", "cc"), ("cc", " "),
         ("value", st["stars"])]
    )
    rows.append(
        [("cc", ". "), ("key", "Commits"), (None, ":"), ("cc", " "), ("fill", ".", "cc"), ("cc", " "),
         ("value", st["commits"]), (None, " | "), ("key", "Followers"), (None, ":"), ("cc", " "),
         ("fill", ".", "cc"), ("cc", " "), ("value", st["followers"])]
    )
    rows.append(
        [("cc", ". "), ("key", "Lines of Code"), (None, ":"), ("cc", " "), ("fill", ".", "cc"), ("cc", " "),
         ("value", st["loc"]), (None, " ( "), ("addColor", st["added"]), ("addColor", "++"), (None, ", "),
         ("delColor", st["deleted"]), ("delColor", "--"), (None, " )")]
    )
    return rows


def build_panel(x: int, y0: float) -> tuple[list[str], int]:
    """Render the panel with its first baseline at y0; returns (lines, row count)."""
    rows = panel_rows()
    out = []
    for i, row in enumerate(rows):
        y = y0 + i * PANEL_LINE
        out.append(f'<tspan x="{x}" y="{y:g}" class="cc">.</tspan>' if row is None else line(row, x, y))

    # A terminal waiting for the next command; discrete steps make the cursor
    # snap on and off like a real one instead of fading.
    y = y0 + (len(rows) + 1) * PANEL_LINE
    out.append(
        f'<tspan x="{x}" y="{y:g}"><tspan class="key">&gt; </tspan><tspan class="value">█'
        f'<animate attributeName="opacity" values="1;0" dur="1.06s" calcMode="discrete" '
        f'repeatCount="indefinite"/></tspan></tspan>'
    )
    return out, len(rows) + 2


# --- Card -------------------------------------------------------------------
def build(theme: str) -> str:
    c = THEMES[theme]
    art = load_art(ART_SRC[theme])
    art_font, art_line = art_metrics(max(len(t) for t in art))

    panel_x = int(MARGIN + ART_COL_WIDTH + GUTTER)
    _, panel_count = build_panel(panel_x, 0.0)  # dry run: the layout needs the row count

    # Art and panel centre on one horizontal axis, and the card is sized so
    # that axis is its exact middle.
    panel_span = (panel_count - 1) * PANEL_LINE
    art_span = (len(art) - 1) * art_line
    half = max(panel_span / 2 + LINE_PAD * PANEL_FONT, art_span / 2 + LINE_PAD * art_font)
    axis = MARGIN + half

    panel_lines, _ = build_panel(panel_x, axis - panel_span / 2 + LINE_MID * PANEL_FONT)
    art_y0 = axis - art_span / 2 + LINE_MID * art_font

    width = int(panel_x + PANEL_COLS * PANEL_FONT * ADVANCE + MARGIN)
    height = round(2 * axis)
    art_tspans = "\n".join(
        f'<tspan x="{MARGIN}" y="{art_y0 + i * art_line:.2f}">{esc(t)}</tspan>' for i, t in enumerate(art)
    )

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px"
     font-family="{FONT_STACK}">
<style>
{FONT_FACE}
.key {{fill: {c['key']};}}
.value {{fill: {c['value']};}}
.title {{fill: {c['key']}; font-weight: bold;}}
.addColor {{fill: {c['add']};}}
.delColor {{fill: {c['del']};}}
.cc {{fill: {c['dots']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{width}px" height="{height}px" fill="{c['bg']}" rx="15"/>
<text fill="{c['art']}" font-size="{art_font:.2f}px" class="ascii">
{art_tspans}
</text>
<text fill="{c['fg']}" font-size="{PANEL_FONT:g}px">
{chr(10).join(panel_lines)}
</text>
</svg>
"""


def main() -> None:
    print(f"uptime   : {span(SINCE)}")
    print(f"stats    : {'cache/stats.json' if STATS_SRC.exists() else 'not fetched yet (placeholders)'}")
    for name in THEMES:
        out = ROOT / f"{name}_mode.svg"
        out.write_text(build(name), encoding="utf-8")
        print(f"wrote {out.name} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
