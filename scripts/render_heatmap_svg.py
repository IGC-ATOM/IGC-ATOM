#!/usr/bin/env python3
"""Render data/contributions.json as a self-animating activity heatmap SVG.

Cells reveal along a diagonal wavefront and then freeze -- one pass, no loop,
pure CSS inside the SVG (GitHub strips <script> and external stylesheets).

Nothing is drawn that is not in the data: every coloured cell is a real date
carrying a real count. Only the 0-5 colour level is derived, and that mapping
is computed upstream in fetch_contributions.py from the observed distribution.

Usage:
    python render_heatmap_svg.py
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

# Level 0 is "no activity"; 1..5 climb from the quietest real day to the busiest.
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#69f0a0"]

BG = "#0d1117"
BORDER = "#21262d"
MUTED = "#7d8590"
DIM = "#565f6a"
ACCENT = "#39d353"

CELL = 13
GAP = 3
RADIUS = 3
LEFT = 32          # room for weekday labels
TOP = 54           # room for the header row and month labels
BOTTOM = 42        # room for the legend row
RIGHT = 18

WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Animation budget (seconds). Brisk, like a dashboard panel populating.
WAVE = 1.25        # wavefront crossing time
CELL_FADE = 0.42
CHROME_FADE = 0.45


def build_grid(days):
    """Bucket days into calendar columns (weeks), rows 0=Sun..6=Sat."""
    weeks = []
    column = [None] * 7
    for entry in days:
        row = (date.fromisoformat(entry["date"]).weekday() + 1) % 7
        if column[row] is not None:
            weeks.append(column)
            column = [None] * 7
        column[row] = entry
    if any(slot is not None for slot in column):
        weeks.append(column)
    return weeks


def month_label_columns(weeks):
    """First column of each month, dropping labels that would crowd."""
    labels = []
    seen = set()
    for col, week in enumerate(weeks):
        first = next((d for d in week if d), None)
        if not first:
            continue
        day = date.fromisoformat(first["date"])
        key = (day.year, day.month)
        if key in seen or day.day > 21:
            continue
        seen.add(key)
        if labels and col - labels[-1][0] < 3:
            continue
        labels.append((col, MONTHS[day.month - 1]))
    return labels


def human(iso):
    day = date.fromisoformat(iso)
    return "%s %d, %d" % (MONTHS[day.month - 1], day.day, day.year)


def plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")


def render(payload, footer_note):
    days = payload["days"]
    stats = payload["stats"]
    weeks = build_grid(days)
    cols = len(weeks)

    grid_w = cols * (CELL + GAP) - GAP
    grid_h = 7 * (CELL + GAP) - GAP
    width = LEFT + grid_w + RIGHT
    height = TOP + grid_h + BOTTOM

    out = []
    add = out.append

    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" '
        'aria-label="Contribution activity heatmap for Parth Rajput">'
        % (width, height, width, height))
    add('<title>Contribution activity &#8212; %s over %s</title>'
        % (plural(stats["total"], "contribution"),
           plural(stats["active_days"], "active day")))

    add('<style>')
    add('.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace}')
    add('.m{fill:%s;font-size:10.5px}' % MUTED)
    add('.d{fill:%s;font-size:9.5px}' % DIM)
    add('.a{fill:%s;font-size:11.5px}' % ACCENT)
    # Visible by default; the animation only adds the entrance. fill-mode:both
    # holds the `from` frame through the stagger, so a sanitiser that drops
    # @keyframes yields the finished graph rather than an invisible one.
    add('.cell{transform-box:fill-box;transform-origin:center;'
        'animation:pop %.2fs ease-out both}' % CELL_FADE)
    add('.chrome{animation:fade %.2fs ease-out both}' % CHROME_FADE)
    add('@keyframes pop{from{opacity:0;transform:scale(.6)}'
        'to{opacity:1;transform:scale(1)}}')
    add('@keyframes fade{from{opacity:0}to{opacity:1}}')
    add('@media (prefers-reduced-motion:reduce){'
        '.cell,.chrome{animation-duration:.01s;animation-delay:0s!important}}')
    add('</style>')

    add('<rect width="%d" height="%d" rx="10" fill="%s"/>' % (width, height, BG))
    add('<rect x="0.5" y="0.5" width="%d" height="%d" rx="10" fill="none" stroke="%s"/>'
        % (width - 1, height - 1, BORDER))

    # ---- header: label left, window right; no total shouting from the top ----
    add('<g class="mono chrome" style="animation-delay:0.04s">')
    add('<text x="%d" y="26" class="a">contribution activity</text>' % LEFT)
    add('<text x="%d" y="26" class="d" text-anchor="end">last 12 months</text>'
        % (width - RIGHT))
    add('</g>')

    # ---- month labels ----
    add('<g class="mono chrome" style="animation-delay:0.12s">')
    for col, name in month_label_columns(weeks):
        add('<text x="%d" y="%d" class="d">%s</text>'
            % (LEFT + col * (CELL + GAP), TOP - 9, name))
    add('</g>')

    # ---- weekday labels ----
    add('<g class="mono chrome" style="animation-delay:0.16s">')
    for row, name in WEEKDAYS.items():
        add('<text x="%d" y="%d" class="d" text-anchor="end">%s</text>'
            % (LEFT - 7, TOP + row * (CELL + GAP) + CELL - 3, name))
    add('</g>')

    # ---- the grid ----
    add('<g>')
    span = max(1, (cols - 1) + 6)
    for col, week in enumerate(weeks):
        for row, entry in enumerate(week):
            if entry is None:
                continue
            level = max(0, min(len(PALETTE) - 1, int(entry["level"])))
            delay = WAVE * ((col + row) / span)
            x = LEFT + col * (CELL + GAP)
            y = TOP + row * (CELL + GAP)
            add('<rect class="cell" x="%d" y="%d" width="%d" height="%d" rx="%d" '
                'fill="%s" style="animation-delay:%.2fs">'
                % (x, y, CELL, CELL, RADIUS, PALETTE[level], delay))
            add('<title>%s on %s</title></rect>'
                % (escape(plural(entry["count"], "contribution")),
                   escape(human(entry["date"]))))
    add('</g>')

    # ---- legend + discreet footer ----
    legend_y = TOP + grid_h + 18
    after = WAVE + CELL_FADE + 0.05
    add('<g class="mono chrome" style="animation-delay:%.2fs">' % after)

    add('<text x="%d" y="%d" class="d">Less</text>' % (LEFT, legend_y + 10))
    lx = LEFT + 32
    for i, colour in enumerate(PALETTE):
        add('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="%s"/>'
            % (lx + i * (CELL + GAP), legend_y, CELL, CELL, RADIUS, colour))
    add('<text x="%d" y="%d" class="d">More</text>'
        % (lx + len(PALETTE) * (CELL + GAP) + 6, legend_y + 10))

    add('<text x="%d" y="%d" class="d" text-anchor="end">%s</text>'
        % (width - RIGHT, legend_y + 10, escape(footer_note)))
    add('</g>')

    add('</svg>')
    return "\n".join(out) + "\n"


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Render the activity heatmap SVG.")
    parser.add_argument("--data", default=str(root / "data" / "contributions.json"))
    parser.add_argument("--out",
                        default=str(root / "assets" / "contribution" / "contrib-heatmap.svg"))
    parser.add_argument("--footer", default=None,
                        help="footer text (default: derived from the data)")
    args = parser.parse_args()

    payload = json.loads(Path(args.data).read_text(encoding="utf-8"))
    stats = payload["stats"]
    footer = args.footer or ("verified activity · %s"
                             % plural(stats["active_days"], "active day"))
    svg = render(payload, footer)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print("wrote %s (%d bytes, %d days, %d active)"
          % (out, len(svg.encode("utf-8")), len(payload["days"]), stats["active_days"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
