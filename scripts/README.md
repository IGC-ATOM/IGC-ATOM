# Profile art pipeline

Two independent pipelines. Only the first one runs in CI.

## 1. Contribution graph — automated (daily)

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_contributions.py --users IGC-ATOM,parthrajpurt16
python scripts/render_heatmap_svg.py
```

* `fetch_contributions.py` reads the public, token-free calendar endpoint
  (`https://github.com/users/<login>/contributions`) and normalises it into
  `data/contributions.json` with totals, streaks, best day and monthly sums.
  Multiple logins are summed and intensity levels recomputed from quartiles.
* `render_heatmap_svg.py` turns that JSON into
  `assets/contribution/contrib-heatmap.svg`, animated with a one-shot diagonal
  reveal.

Run by `.github/workflows/update-profile-art.yml` every day at 02:40 UTC.

> Only **public** contributions appear here. To include private-repo activity,
> turn on GitHub → Settings → Profile → **Include private contributions on my
> profile**. No code is exposed by that setting — only daily counts.

## 2. Portrait and card — manual

Needs Pillow, so it is deliberately kept out of the daily workflow. Re-run it
only when the avatar or the card content changes.

```bash
pip install -r scripts/requirements-art.txt
python scripts/prep_photo.py                 # avatar -> cropped grayscale PNG
python scripts/make_ascii_svg.py --preview   # PNG -> animated ASCII SVG
python scripts/make_info_card.py             # -> animated neofetch card SVG
```

`prep_photo.py` fetches `https://github.com/IGC-ATOM.png`, crops to the
subject, flattens the background, stretches contrast and sharpens edges.
`make_ascii_svg.py` maps luminance onto the ramp `" .\`:-=+*cs#%@"`. Because the
art is light-on-dark, bright pixels get the dense glyphs by default; pass
`--no-invert` for the print-style mapping.

## Animation notes

All animation lives inside the SVGs (SMIL for the ASCII wipe, CSS keyframes for
the card and heatmap). No JavaScript and no external stylesheets, because GitHub
strips both. Every animation runs once and freezes, and collapses to the final
frame under `prefers-reduced-motion`.
