# moebius

Möbius strip wallpapers: a twisting single-sided ribbon in 3D space.

Ray-marched using a signed-distance field for crisp geometry at any resolution.
Colour bands wrap continuously around the strip, passing through the half-twist
to reveal the single-sided surface. Clean, graphic shading with warm sun-bleached
palettes.

- **Light:** warm cream background, sunlit bands, subtle ink edges
- **Dark:** deep muted background, glowing bands, rim-lit contours

## Usage

```bash
uv run moebius.py                       # random seed, light + dark
uv run moebius.py --seed 7 --palette desert --mode dark
uv run moebius.py --fast --count 8      # quick previews
```

Output: `moebius-<palette>-<seed>-<width>x<height>-<light|dark>.png`

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--palette` | random | `desert`, `alien`, `dune`, `space`, `ochre` |
| `--seed N` | random | Same seed → same strip geometry and camera |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--count N` | 1 | How many images |
| `--width / --height` | 1920×1200 | Output size |
| `--size PRESET` | | Size preset (`gnome`, `4k`, `ultrawide`, etc.) |
| `--ss N` | 2 | Supersampling factor |
| `--fast` | | 960×600 preview; adds `-fast` suffix |
| `--focus` / `--targets` | `auto` | Safe-area layout (see top-level README) |
| `--out DIR` | script folder | Output folder |

### Palettes

- **desert** — burnt orange, sandy gold, denim accent
- **alien** — seafoam, teal, rose accent
- **dune** — rust, terracotta, slate accent
- **space** — lilac, violet, steel accent
- **ochre** — mustard, gold, sage accent

## Tweaking

In `moebius.py`:

- `PALETTES`: background colours, band colours, accent, specular strength.
- `R` and `w` in `render()`: major radius and half-width of the strip.
- Camera orbit (`cd`, `theta`, `phi`) and field of view.
- Lighting directions `l0` and `l1`, and the rim/specular exponents.
- The ink edge is `smooth(0.85, 1.0, abs(v))` applied to the strip boundary.
