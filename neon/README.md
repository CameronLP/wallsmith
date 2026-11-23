# neon

Neon Nocturne wallpapers: blurred city lights reflected on wet pavement.

Bokeh orbs, vertical rain reflections on slick ground, distant neon haze, and fine
rain streaks. Evokes a rainy night in a neon-lit street viewed through a raindrop-covered
window—or the soft ambient glow of a sleeping city.

- **Light:** pale warm sky, soft reflections in muted pastels, gentle rain
- **Dark:** deep indigo/navy sky, vivid magenta/cyan/gold bokeh, bright wet reflections

## Usage

```bash
uv run neon.py                          # random palette + seed, light + dark
uv run neon.py --palette seoul --seed 3
uv run neon.py --fast --count 8         # quick previews
uv run neon.py --mode dark --size gnome --ss 1
```

Output: `neon-<palette>-<seed>-<width>x<height>-<light|dark>.png`

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--palette` | random | `tokyo`, `seoul`, `hongkong`, `kyoto` |
| `--seed N` | 8 | Reproducible random state |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--count N` | 1 | How many images |
| `--width / --height` | 1920×1200 | Output size |
| `--size PRESET` | | Size preset (`gnome`, `4k`, `ultrawide`, etc.) |
| `--ss N` | 2 | Supersampling factor |
| `--fast` | | 960×600 preview without supersampling; adds `-fast` suffix |
| `--focus` / `--targets` | `auto` | Safe-area layout (see top-level README) |
| `--out DIR` | script folder | Output folder |

### Palettes

- **tokyo** — magenta, hot cyan, amber on deep indigo (classic neon)
- **seoul** — cool blue, soft pink, mint on midnight navy
- **hongkong** — deep red, electric teal, gold on dark plum
- **kyoto** — warm amber, gold, rose on charcoal (softer, traditional warmth)

Browse seeds with `--fast --count 10`, then re-render favourites big.

## Tweaking

In `neon.py`:

- `PALETTES`: sky gradients (top/mid/horizon), ground, bokeh accent colours, haze pair.
- `n_orbs` (≈ 32): number of bokeh light spots per image.
- `n_rain` (≈ 270): number of rain streaks.
- `n_strips` (4–8): horizontal neon strips in the ground reflection zone.
- Horizon height is randomised around 0.34; ground tone, vignette strength and haze
  intensity all shift between light and dark modes.
