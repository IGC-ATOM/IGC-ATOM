#!/usr/bin/env python3
"""Render data/contributions.json as a self-animating contribution heatmap SVG.

The animation is pure SMIL/CSS inside the SVG (GitHub strips <script> and any
external stylesheet from README embeds). Cells fade and scale in along a
diagonal wavefront, then hold their final state forever -- one pass, no loop.

Usage:
    python render_heatmap_svg.py
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

# Dark base, then GitHub-inspired green ramp.
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

BG = "#0d1117"
BORDER = "#21262d"
TEXT = "#c9d1d9"
MUTED = "#7d8590"
ACCENT = "#39d353"

CELL = 12          # cell edge
GAP = 3            # gap between cells
RADIUS = 2.5
LEFT = 34          # room for weekday labels
TOP = 70           # room for title, scope line and month labels
BOTTOM = 46        # room for the legend row
RIGHT = 20

WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Animation budget (seconds).
WAVE = 1.9         # time for the wavefront to cross the whole grid
CELL_FADE = 0.55   # per-cell fade duration
CHROME_FADE = 0.5


def build_grid(days):
    """Bucket days into GitHub-style columns (weeks), rows 0=Sun..6=Sat."""
    weeks = []
    column = [None] * 7
    for entry in days:
        day = date.fromisoformat(entry["date"])
        row = (day.weekday() + 1) % 7  # Python Mon=0 -> GitHub Sun=0
        if column[row] is not None:
            weeks.append(column)
            column = [None] * 7
        column[row] = entry
    if any(slot is not None for slot in column):
        weeks.append(column)
    return weeks


def month_label_columns(weeks):
    """First column of each month, skipping labels that would collide."""
    labels = []
    seen = set()
    for col, week in enumerate(weeks):
        first = next((d for d in week if d), None)
        if not first:
            continue
        day = date.fromisoformat(first["date"])
        key = (day.year, day.month)
        if key in seen:
            continue
        seen.add(key)
        # Only label a month that owns most of its first column.
        if day.day > 21:
            continue
        if labels and col - labels[-1][0] < 3:
            continue
        labels.append((col, MONTHS[day.month - 1]))
    return labels


def human(iso):
    day = date.fromisoformat(iso)
    return "%s %d, %d" % (MONTHS[day.month - 1], day.day, day.year)


def plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")


def render(payload, scope_note="public repository activity only"):
    days = payload["days"]
    stats = payload["stats"]
    weeks = build_grid(days)
    cols = len(weeks)

    grid_w = cols * (CELL + GAP) - GAP
    grid_h = 7 * (CELL + GAP) - GAP
    width = LEFT + grid_w + RIGHT
    height = TOP + grid_h + BOTTOM

    total = stats["total"]
    is_empty = total == 0

    out = []
    add = out.append

    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" '
        'aria-label="GitHub contribution heatmap for Parth Rajput">'
        % (width, height, width, height))

    add('<title>Contribution activity &#8212; %s</title>' % plural(total, "contribution"))

    # ---- styles: one-shot animations, all frozen via forwards fill ----
    add('<style>')
    add('.bg{fill:%s}' % BG)
    add('.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace}')
    add('.t{fill:%s;font-size:12px}' % TEXT)
    add('.m{fill:%s;font-size:10px}' % MUTED)
    add('.a{fill:%s;font-size:12px}' % ACCENT)
    # Everything is visible by default; the animation only adds the entrance.
    # animation-fill-mode:both holds the `from` frame through the stagger delay,
    # so a sanitiser that drops @keyframes yields the finished graph rather than
    # an invisible one.
    add('.cell{transform-box:fill-box;transform-origin:center;'
        'animation:pop %.2fs ease-out both}' % CELL_FADE)
    add('.chrome{animation:fade %.2fs ease-out both}' % CHROME_FADE)
    add('@keyframes pop{from{opacity:0;transform:scale(.55)}'
        'to{opacity:1;transform:scale(1)}}')
    add('@keyframes fade{from{opacity:0}to{opacity:1}}')
    # Respect reduced-motion: show the finished state immediately.
    add('@media (prefers-reduced-motion:reduce){'
        '.cell,.chrome{animation-duration:.01s;animation-delay:0s!important}}')
    add('</style>')

    add('<rect class="bg" width="%d" height="%d" rx="8"/>' % (width, height))
    add('<rect x="0.5" y="0.5" width="%d" height="%d" rx="8" fill="none" stroke="%s"/>'
        % (width - 1, height - 1, BORDER))

    # ---- header ----
    add('<g class="mono chrome" style="animation-delay:0.05s">')
    add('<text x="%d" y="22" class="a">contributions</text>' % LEFT)
    add('<text x="%d" y="22" class="m" text-anchor="end">%s</text>'
        % (width - RIGHT, escape("%s · last 12 months"
                                 % plural(total, "public contribution"))))
    # Only the public calendar is readable without a token, so the graph states
    # its own scope. It must never imply this is all of Parth's activity.
    add('<text x="%d" y="38" class="m">%s</text>' % (LEFT, escape(scope_note)))
    add('</g>')

    # ---- month labels ----
    add('<g class="mono chrome" style="animation-delay:0.15s">')
    for col, name in month_label_columns(weeks):
        add('<text x="%d" y="%d" class="m">%s</text>'
            % (LEFT + col * (CELL + GAP), TOP - 8, name))
    add('</g>')

    # ---- weekday labels ----
    add('<g class="mono chrome" style="animation-delay:0.2s">')
    for row, name in WEEKDAYS.items():
        add('<text x="%d" y="%d" class="m" text-anchor="end">%s</text>'
            % (LEFT - 8, TOP + row * (CELL + GAP) + CELL - 2, name))
    add('</g>')

    # ---- the grid ----
    add('<g>')
    span = max(1, (cols - 1) + 6)
    for col, week in enumerate(weeks):
        for row, entry in enumerate(week):
            if entry is None:
                continue
            level = max(0, min(4, int(entry["level"])))
            # Diagonal wavefront: delay grows with col + row.
            delay = WAVE * ((col + row) / span)
            x = LEFT + col * (CELL + GAP)
            y = TOP + row * (CELL + GAP)
            count = entry["count"]
            label = "%s on %s" % (plural(count, "contribution"), human(entry["date"]))
            add('<rect class="cell" x="%d" y="%d" width="%d" height="%d" rx="%s" '
                'fill="%s" style="animation-delay:%.2fs">'
                % (x, y, CELL, CELL, RADIUS, PALETTE[level], delay))
            add('<title>%s</title></rect>' % escape(label))
    add('</g>')

    # ---- legend + stats ----
    legend_y = TOP + grid_h + 24
    after = WAVE + CELL_FADE + 0.1
    add('<g class="mono chrome" style="animation-delay:%.2fs">' % after)

    add('<text x="%d" y="%d" class="m">Less</text>' % (LEFT, legend_y + 10))
    lx = LEFT + 34
    for i, colour in enumerate(PALETTE):
        add('<rect x="%d" y="%d" width="%d" height="%d" rx="%s" fill="%s"/>'
            % (lx + i * (CELL + GAP), legend_y, CELL, CELL, RADIUS, colour))
    add('<text x="%d" y="%d" class="m">More</text>'
        % (lx + len(PALETTE) * (CELL + GAP) + 6, legend_y + 10))

    if is_empty:
        summary = "private repository activity is not included"
    else:
        parts = [
            "%s active" % plural(stats["active_days"], "day"),
            "%s longest streak" % plural(stats["longest_streak"], "day"),
        ]
        best = stats.get("best_day")
        if best:
            parts.append("best %d on %s" % (best["count"], human(best["date"])))
        summary = "  ·  ".join(parts)
    if summary:
        add('<text x="%d" y="%d" class="m" text-anchor="end">%s</text>'
            % (width - RIGHT, legend_y + 10, escape(summary)))
    add('</g>')

    add('</svg>')
    return "\n".join(out) + "\n"


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Render the contribution heatmap SVG.")
    parser.add_argument("--data", default=str(root / "data" / "contributions.json"))
    parser.add_argument("--out", default=str(root / "assets" / "contribution" / "contrib-heatmap.svg"))
    parser.add_argument("--scope-note",
                        default="public repository activity only · private contributions not included",
                        help="scope label shown beside the contribution total")
    args = parser.parse_args()

    payload = json.loads(Path(args.data).read_text(encoding="utf-8"))
    svg = render(payload, args.scope_note)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print("wrote %s (%d bytes, %d days)" % (out, len(svg.encode("utf-8")), len(payload["days"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
