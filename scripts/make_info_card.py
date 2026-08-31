#!/usr/bin/env python3
"""Build the neofetch-style information card SVG.

Terminal window chrome plus a key/value block, a stack tree and a status line.
Every row fades and slides in on a stagger, runs once, then freezes -- CSS
keyframes with `forwards`, no script, no external stylesheet, so it survives
GitHub's README sanitiser.

Usage:
    python make_info_card.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

BG = "#0d1117"
CHROME = "#161b22"
BORDER = "#21262d"
RULE = "#21262d"
LABEL = "#7d8590"
COLON = "#484f58"
VALUE = "#c9d1d9"
GREEN = "#39d353"
CYAN = "#56d4dd"
TREE = "#3d444d"

FONT = 11.5
LINE = 15.2
PAD_X = 20
TITLEBAR = 34
PAD_TOP = 14
PAD_BOTTOM = 16
WIDTH = 468

LABEL_W = 92  # x-offset of the value column

# Row kinds: kv, cont (value-only continuation of the row above), head, tree, rule
ROWS = [
    ("kv", "USER", "Parth Rajput", VALUE),
    ("kv", "HANDLE", "IGC-ATOM", CYAN),
    ("kv", "ROLE", "Full-Stack Developer", VALUE),
    ("cont", None, "Flutter Developer", VALUE),
    ("cont", None, "AI/ML Enthusiast", VALUE),
    ("kv", "EDUCATION", "MCA", VALUE),
    ("kv", "LOCATION", "Gujarat, India", VALUE),
    ("rule", None, None, None),
    ("head", "STACK", None, None),
    ("tree", "├─", "React / Next.js", VALUE),
    ("tree", "├─", "Node.js / Express", VALUE),
    ("tree", "├─", "Flutter / Dart", VALUE),
    ("tree", "├─", "Python", VALUE),
    ("tree", "├─", "PostgreSQL / MongoDB / SQLite", VALUE),
    ("tree", "├─", "Prisma", VALUE),
    ("tree", "└─", "AI APIs", VALUE),
    ("rule", None, None, None),
    ("head", "BUILDING", None, None),
    ("tree", "├─", "SaaS Applications", VALUE),
    ("tree", "├─", "AI Applications", VALUE),
    ("tree", "└─", "Business Software", VALUE),
    ("rule", None, None, None),
    ("kv", "STATUS", "Building", GREEN),
]

STAGGER = 0.045
ROW_DUR = 0.42
START = 0.2


def render():
    body_h = len(ROWS) * LINE
    height = int(round(TITLEBAR + PAD_TOP + body_h + PAD_BOTTOM))

    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" '
        'aria-label="Profile summary card for Parth Rajput">'
        % (WIDTH, height, WIDTH, height))
    add('<title>parth@github &#8212; profile</title>')

    add('<style>')
    add('.m{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace;font-size:%.1fpx}' % FONT)
    # The rows are visible by default and the animation only adds the entrance.
    # animation-fill-mode:both holds the `from` frame through the delay, so the
    # stagger still works -- but if a sanitiser strips @keyframes (GitHub does
    # this in its blob preview) the content simply renders finished instead of
    # staying stuck at opacity 0.
    add('.r{animation:in %.2fs cubic-bezier(.22,.61,.36,1) both}' % ROW_DUR)
    add('@keyframes in{from{opacity:0;transform:translateX(-7px)}'
        'to{opacity:1;transform:translateX(0)}}')
    add('@media (prefers-reduced-motion:reduce){'
        '.r{animation-duration:.01s;animation-delay:0s!important}}')
    add('</style>')

    # Window
    add('<rect width="%d" height="%d" rx="8" fill="%s"/>' % (WIDTH, height, BG))
    add('<path d="M0 8a8 8 0 0 1 8-8h%d a8 8 0 0 1 8 8v%d H0Z" fill="%s"/>'
        % (WIDTH - 16, TITLEBAR - 8, CHROME))
    add('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="%s"/>'
        % (TITLEBAR, WIDTH, TITLEBAR, BORDER))

    for i, colour in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        add('<circle cx="%d" cy="%d" r="4.5" fill="%s" opacity="0.85"/>'
            % (PAD_X + i * 16, TITLEBAR / 2, colour))

    add('<text class="m" x="%d" y="%.1f" fill="%s">parth@github</text>'
        % (PAD_X + 56, TITLEBAR / 2 + 4, LABEL))
    add('<text class="m" x="%d" y="%.1f" fill="%s" text-anchor="end">neofetch</text>'
        % (WIDTH - PAD_X, TITLEBAR / 2 + 4, COLON))

    # Rows
    y = TITLEBAR + PAD_TOP
    for idx, (kind, a, b, colour) in enumerate(ROWS):
        delay = START + idx * STAGGER
        baseline = y + LINE * 0.72
        style = ' style="animation-delay:%.3fs"' % delay

        if kind == "rule":
            add('<line class="r" x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"%s/>'
                % (PAD_X, y + LINE / 2, WIDTH - PAD_X, y + LINE / 2, RULE, style))
        elif kind == "head":
            add('<text class="m r" x="%d" y="%.1f" fill="%s" '
                'font-weight="600" letter-spacing="1.1"%s>%s</text>'
                % (PAD_X, baseline, GREEN, style, escape(a)))
        elif kind == "cont":
            # Continuation of the key above: value column only, no label.
            add('<text class="m r" x="%d" y="%.1f" fill="%s"%s>%s</text>'
                % (PAD_X + LABEL_W, baseline, colour, style, escape(b)))
        elif kind == "tree":
            add('<g class="r"%s>' % style)
            add('<text class="m" x="%d" y="%.1f" fill="%s">%s</text>'
                % (PAD_X + 8, baseline, TREE, escape(a)))
            add('<text class="m" x="%d" y="%.1f" fill="%s">%s</text>'
                % (PAD_X + 30, baseline, colour, escape(b)))
            add('</g>')
        else:  # kv
            add('<g class="r"%s>' % style)
            add('<text class="m" x="%d" y="%.1f" fill="%s">%s</text>'
                % (PAD_X, baseline, LABEL, escape(a)))
            add('<text class="m" x="%d" y="%.1f" fill="%s">:</text>'
                % (PAD_X + LABEL_W - 10, baseline, COLON))
            add('<text class="m" x="%d" y="%.1f" fill="%s">%s</text>'
                % (PAD_X + LABEL_W, baseline, colour, escape(b)))
            if a == "STATUS":
                add('<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>'
                    % (PAD_X + LABEL_W + len(b) * FONT * 0.6 + 9, baseline - 4, GREEN))
            add('</g>')
        y += LINE

    add('</svg>')
    return "\n".join(out) + "\n", height


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Build the neofetch info card SVG.")
    parser.add_argument("--out", default=str(root / "assets" / "profile" / "info-card.svg"))
    args = parser.parse_args()

    svg, height = render()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print("wrote %s (%dx%d, %d rows, %d bytes)"
          % (out, WIDTH, height, len(ROWS), len(svg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
