#!/usr/bin/env python3
"""Convert the prepared portrait into a self-animating ASCII SVG.

Density ramp: " .`:-=+*cs#%@" -- sparse glyphs for low ink, dense glyphs for
high ink. The art is rendered as light-on-dark (a terminal), so by default
BRIGHT pixels get the dense glyphs and dark pixels collapse to spaces; that
keeps the background empty instead of filling it with a solid wall of '@'.
Pass --no-invert for the print-style mapping (dark pixels -> dense glyphs).

Animation is SMIL with fill="freeze": rows appear top to bottom, each wiping
left to right behind a moving cursor block. It runs exactly once and holds.

Usage:
    python make_ascii_svg.py --preview
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

RAMP = " .`:-=+*cs#%@"

BG = "#0d1117"
BORDER = "#21262d"
CURSOR = "#39d353"

# Green -> white ink ramp, indexed by glyph density. Monochrome by design.
INK = ["#1b5e35", "#238636", "#2ea043", "#39d353", "#57e08d", "#8bf0b4", "#d8fde8"]

# A monospace glyph is about 0.60 em wide; rows sit at 1.06 em.
ADVANCE_EM = 0.60
LINE_EM = 1.06

ROW_WIPE = 0.34     # seconds for one row to wipe across
ROW_STEP = 0.028    # delay added per row
START = 0.15


def to_rows(img, cols, invert):
    """Downsample to a character grid and map luminance onto the ramp."""
    w, h = img.size
    # Characters are taller than wide, so compensate to keep the aspect ratio.
    rows = max(1, int(round(cols * (h / float(w)) * (ADVANCE_EM / LINE_EM))))
    small = img.convert("L").resize((cols, rows), Image.LANCZOS)
    pixels = small.load()

    last = len(RAMP) - 1
    grid = []
    for y in range(rows):
        line = []
        for x in range(cols):
            value = pixels[x, y]
            level = int(round((value if invert else 255 - value) / 255.0 * last))
            line.append(RAMP[max(0, min(last, level))])
        grid.append("".join(line))
    return grid


def ink_for(ch):
    """Pick an ink shade from the glyph's position in the density ramp."""
    idx = RAMP.index(ch)
    if idx == 0:
        return None
    slot = int(round((idx - 1) / float(len(RAMP) - 2) * (len(INK) - 1)))
    return INK[max(0, min(len(INK) - 1, slot))]


def segments(line):
    """Group a row into runs sharing one ink shade, so the SVG stays small."""
    runs = []
    start = 0
    current = ink_for(line[0]) if line else None
    for i in range(1, len(line) + 1):
        shade = ink_for(line[i]) if i < len(line) else "<end>"
        if shade != current:
            if current is not None:
                runs.append((start, line[start:i], current))
            start, current = i, shade
    return runs


def render(grid, font_size, pad, weight):
    cols = max(len(r) for r in grid)
    advance = font_size * ADVANCE_EM
    line_h = font_size * LINE_EM

    art_w = cols * advance
    art_h = len(grid) * line_h
    width = int(round(art_w + pad * 2))
    height = int(round(art_h + pad * 2))

    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" '
        'aria-label="ASCII rendering of Parth Rajput\'s GitHub avatar">'
        % (width, height, width, height))
    add('<title>whoami &#8212; ASCII portrait</title>')

    add('<style>')
    # A heavier weight matters at this glyph size: '@' is mostly hole at 8px,
    # so a normal weight makes dense regions read as grey haze instead of mass.
    add('.a{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace;font-size:%.2fpx;font-weight:%s;'
        'white-space:pre;letter-spacing:0}' % (font_size, weight))
    add('</style>')

    add('<rect width="%d" height="%d" rx="8" fill="%s"/>' % (width, height, BG))
    add('<rect x="0.5" y="0.5" width="%d" height="%d" rx="8" fill="none" stroke="%s"/>'
        % (width - 1, height - 1, BORDER))

    # One clip rect per row, animated from zero width to full: the wipe.
    # The rect's own width attribute is already the full width, and SMIL's
    # `from` overrides it while the animation runs. If a sanitiser strips the
    # <animate>, the art renders complete instead of clipped away to nothing.
    add('<defs>')
    for r in range(len(grid)):
        begin = START + r * ROW_STEP
        y = pad + r * line_h
        add('<clipPath id="w%d" clipPathUnits="userSpaceOnUse">' % r)
        add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f">'
            % (pad, y - font_size, art_w, line_h + font_size * 0.3))
        add('<animate attributeName="width" from="0" to="%.2f" begin="%.3fs" '
            'dur="%.2fs" fill="freeze" calcMode="spline" keyTimes="0;1" '
            'keySplines="0.25 0.1 0.25 1"/>' % (art_w, begin, ROW_WIPE))
        add('</rect></clipPath>')
    add('</defs>')

    add('<g class="a">')
    for r, line in enumerate(grid):
        runs = segments(line)
        if not runs:
            continue
        baseline = pad + r * line_h + font_size * 0.82
        add('<g clip-path="url(#w%d)">' % r)
        for col, text, shade in runs:
            add('<text x="%.2f" y="%.2f" fill="%s" xml:space="preserve">%s</text>'
                % (pad + col * advance, baseline, shade, escape(text)))
        add('</g>')
    add('</g>')

    # Cursor block riding the wipe, fading out when the last row lands.
    last_begin = START + (len(grid) - 1) * ROW_STEP
    end = last_begin + ROW_WIPE
    add('<rect width="%.2f" height="%.2f" fill="%s" opacity="0">'
        % (advance * 1.1, line_h * 0.92, CURSOR))
    add('<animate attributeName="opacity" values="0;0.85;0.85;0" '
        'keyTimes="0;0.04;0.9;1" begin="%.3fs" dur="%.2fs" fill="freeze"/>'
        % (START, end - START + 0.25))
    add('<animate attributeName="x" values="%.2f;%.2f" begin="%.3fs" dur="%.2fs" '
        'fill="freeze"/>' % (pad, pad + art_w, START, end - START))
    add('<animate attributeName="y" values="%.2f;%.2f" begin="%.3fs" dur="%.2fs" '
        'fill="freeze"/>'
        % (pad - font_size * 0.1, pad + art_h - line_h, START, end - START))
    add('</rect>')

    add('</svg>')
    return "\n".join(out) + "\n"


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Build the animated ASCII portrait SVG.")
    parser.add_argument("--source", default=str(root / "assets" / "profile" / "portrait-source.png"))
    parser.add_argument("--out", default=str(root / "assets" / "profile" / "parth-ascii.svg"))
    # 72 columns at 7.92px renders ~366px wide, which is 1:1 with the width the
    # README asks for. More columns look finer in a text editor but collapse to
    # 4px glyphs on GitHub, where the art stops reading as anything.
    parser.add_argument("--cols", type=int, default=72, help="character columns")
    parser.add_argument("--font-size", type=float, default=7.92)
    parser.add_argument("--pad", type=float, default=12)
    parser.add_argument("--weight", default="700", help="font-weight for the art")
    parser.add_argument("--no-invert", dest="invert", action="store_false",
                        help="print-style mapping: dark pixels get dense glyphs")
    parser.add_argument("--preview", action="store_true", help="print the ASCII to stdout")
    parser.set_defaults(invert=True)
    args = parser.parse_args()

    img = Image.open(args.source)
    grid = to_rows(img, args.cols, args.invert)

    if args.preview:
        for line in grid:
            print(line)

    svg = render(grid, args.font_size, args.pad, args.weight)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")

    ink = sum(1 for row in grid for ch in row if ch != " ")
    total = sum(len(row) for row in grid)
    print("wrote %s (%d cols x %d rows, %.0f%% ink, %d bytes)"
          % (out, args.cols, len(grid), ink * 100.0 / total, len(svg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
