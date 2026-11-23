# veils

Silky, translucent "veil" wallpapers in the style of classic flame-fractal backgrounds.

Each veil is a long twisting ribbon made of millions of randomly sampled points. Where the
ribbon folds, the points bunch up into bright creases. Point density is accumulated per
pixel and log tone-mapped, the same way flame fractal renderers do it.

- **Dark:** veils glow on a deep background, and the brightest creases turn whitish
- **Light:** veils are drawn like colored ink on a pale background

Both modes come from the same density render, so the pair always matches.

## Usage

```bash
uv run veils.py                              # random seed, blue, light + dark
uv run veils.py --seed 7 --palette violet
uv run veils.py --veils 20                   # sparser, calmer
uv run veils.py --veils 80                   # denser, busier
uv run veils.py --align 0.8 --direction 15   # calm, mostly horizontal swoops
uv run veils.py --quality 2 --denoise 1      # smoothest, least grain
uv run veils.py --fast --count 8             # quick previews to browse
uv run veils.py --style vista                # Windows Vista-style swoops
uv run veils.py --style macos                # macOS (Leopard-era) style swirls
uv run veils.py --swoop 1.5 --anchor bottom-right --spread 0.3
```

Output: `veils-[<style>-]<palette>-<seed>-<light|dark>[-fast].png`

## Styles

`--style` bundles a look into one flag. Any option you pass explicitly overrides the preset.

| Style | Look | Preset values |
|---|---|---|
| `vista` | Thin glowing green/blue bands that run flat and sweep up exponentially on the right | palette `aurora`, swoop 1.4, align 0.85, direction 10°, 22 veils, anchor `0.68,0.58`, spread 0.4, thickness 0.3, exposure 0.55, glow 1.3, denoise 1 |
| `macos` | Purple/pink cosmic swirls curving dramatically through the center | palette `cosmic`, swoop 2.0, align 0.55, direction −8°, 28 veils, anchor `0.45,0.5`, spread 0.55, thickness 0.45, exposure 0.6, glow 1.2, denoise 1 |

```bash
uv run veils.py --style vista --palette violet       # Vista shapes, violet colors
uv run veils.py --style vista --anchor left          # bend on the left instead
```

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--veils N` | 44 | **Number of veils drawn.** Fewer = cleaner and more open; more = denser silk |
| `--align X` | 0 | 0–1: how strongly the veils follow one common direction. `0.6`–`0.9` gives calm, parallel swoops with fewer twists |
| `--direction DEG` | random rising diagonal | Rough flow direction: `0` = left→right, `30` = rising to the right, `-30` = falling, `90` = vertical |
| `--quality X` | 1.0 | Sample multiplier. `2` = twice the points, less grain, about 2× slower |
| `--denoise R` | 0 | Smoothing radius in output pixels. `1`–`2` removes grain; higher values soften the fine creases |
| `--style` | | `vista` or `macos` preset (see above) |
| `--swoop X` | 0 | Vista-style exponential swoops: ribbons run flat, then curve away sharply. `0.5` = gentle, `1` = strong, `2` = dramatic |
| `--anchor POS` | | Concentrate the veils around a point, where they cross and bend: `center`, `top`, `bottom`, `left`, `right`, `top-left`, `top-right`, `bottom-left`, `bottom-right`, or `x,y` (0–1 in the design area) |
| `--spread X` | 0.5 | With `--anchor`: `0` = tight bundle, `1` = loose |
| `--thickness X` | 1 | Ribbon width multiplier. `<1` gives thin, crisp bands (Vista look) |
| `--exposure X` | 1 | Veil brightness. `<1` is darker with more contrast; use this when dense/anchored designs blow out |
| `--glow X` | 1 | Glow strength multiplier |
| `--palette` | `blue` | `blue`, `violet`, `teal`, `ember`, `rose`, `aurora` (Vista greens/blues), `cosmic` (purple/pink) |
| `--focus` / `--targets` | `auto` | Safe-area layout for square multi-screen images (see the top-level README) |
| `--seed N` | random | Same seed gives the same image |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--count N` | 1 | Number of images |
| `--width / --height` | 1920×1200 | Output size |
| `--ss N` | 2 | Supersampling; higher values are smoother but slower and use more RAM |
| `--fast` | | 960×600 at ss=1 for quick previews (grainier); adds a `-fast` suffix |
| `--out DIR` | script folder | Output folder |

Render time grows with the number of pixels (roughly `width × height × ss²`), not with
`--veils`. The total point budget is shared across all veils.

## Tweaking

In `veils.py`:

- `PALETTES`: veil hues (one is picked at random per veil), dark background gradient,
  light background gradient, and light-mode `ink` color.
- `render_density()`: ribbon shape. `flow` sets the dominant diagonal direction,
  `length`, `hw0` (ribbon width), `tw` (twist amount, which creates more folds/creases) and
  `wob_x/wob_y` (how much the spine meanders).
- `points=W * H * 5` in `main()`: sample density. Raise it to reduce grain.
