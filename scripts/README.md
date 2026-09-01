# Profile art pipeline

Two independent pipelines. Only the first one runs in CI.

## 1. Contribution graph — automated (daily)

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_contributions.py --users IGC-ATOM,parthrajpurt16
python scripts/render_heatmap_svg.py
```

`fetch_contributions.py` collects **verified** activity from up to three real
sources and writes `data/contributions.json`:

| source | needs a token | what it counts |
| :--- | :--- | :--- |
| `public` | no | GitHub's own published contribution calendar |
| `commits` | yes (`repo`) | commits authored by the logins, deduped by SHA across every branch of owned repos |
| `pulls` | yes (`repo`) | pull requests opened by the logins |

`commits` and `pulls` are disjoint event types and are summed; `public` counts
the same underlying activity, so it is compared against that sum rather than
added to it. Each source is stored separately under `sources`, and a run only
refreshes the sources it was asked for — so the tokenless daily workflow can
never erase commit data gathered locally with a token.

To refresh everything (needs `gh auth login` or `GITHUB_TOKEN`):

```bash
python scripts/fetch_contributions.py --users IGC-ATOM,parthrajpurt16 --sources public,commits,pulls
python scripts/render_heatmap_svg.py
```

Intensity levels are derived, never the counts: the distinct non-zero daily
totals are ranked and spread across levels 1-5, so the quietest real day still
reads above empty and the busiest reaches the top. Dates and counts are stored
exactly as observed.

> Only **public** activity reaches the `public` source. Turning on GitHub →
> Settings → Profile → **Include private contributions on my profile** makes
> the published calendar match what the `commits` source already sees.

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
