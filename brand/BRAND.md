# Brand

A small, fixed set of assets. Everything here is SVG except the social card,
which GitHub needs as a raster.

| File | What it is | Where it goes |
|---|---|---|
| [`mark.svg`](mark.svg) | The mark alone, 100 x 100 | favicon, avatar, anywhere under 200px |
| [`lockup.svg`](lockup.svg) | Mark plus wordmark, horizontal | README header, slides, docs |
| [`social.svg`](social.svg) | 1280 x 640 source | edit this, then re-export |
| [`social.png`](social.png) | 1280 x 640 export | GitHub → Settings → Social preview |

## The mark

Two chevrons approaching a single rule from opposite sides. One question,
asked from both directions, meeting at the same line.

The gap matters. Closed up, the two chevrons would read as an X, which
means rejection — the wrong story for a primitive whose job is to ask
twice, not to refuse.

Built on a 100 x 100 grid. Stroke weight 7.5, round caps, corner radius 18.

- **Clear space:** half the mark height on every side.
- **Smallest size:** 16px alone, 24px locked to the wordmark. Verified at 16px —
  the two chevrons and the centre rule stay separable.
- **Never:** a second hue, a gradient, an outline version, a drop shadow, or the
  mark rotated. The geometry carries the meaning; rotating it breaks the meaning.

## Palette

| Token | Hex | Use |
|---|---|---|
| ink | `#0C0D10` | the mark's field, and any dark surface |
| chalk | `#E8E6E1` | the wordmark and primary text. Never pure white |
| accent | `#8B7CF6` | the mark, one primary action, one live state |
| muted | `#9AA0A8` | secondary text |
| rule | `#232830` | hairlines and dividers |

One accent, used sparingly. On the social card it appears exactly three times:
the top bar, the mark, and the footer line.

## Type

**Inter**, weights 400 and 700, tracking tightened to -1.4 on the wordmark and
-2.6 at display size. Monospace for the footer strapline and anything that is a
value rather than a sentence: `ui-monospace, SFMono-Regular, Menlo, monospace`.

The wordmark is always lowercase.

## Re-exporting the social card

Edit `social.svg`, then:

```bash
pip install cairosvg
python -c "import cairosvg; cairosvg.svg2png(url='brand/social.svg', \
    write_to='brand/social.png', output_width=1280, output_height=640)"
```

Upload the result under **Settings → General → Social preview**. GitHub uses it
whenever a link to this repository is shared.

## Licence

The assets in this folder are MIT along with the rest of the repository. The
name and mark identify this specific primitive, so if you fork it and change
what it does, change the name too.
