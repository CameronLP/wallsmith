# aero

Abstract Frutiger Aero / mid-2000s wallpaper: translucent glass ribbons with glossy
edges and thin light streaks over a soft diagonal gradient.

- **Light:** sky blue to near-white, with white, aqua, mint and lime glass
- **Dark:** deep navy to teal, with cyan, emerald and blue glass

## Usage

```bash
uv run generate.py                                   # seed 7, 3840x2400, light + dark
uv run generate.py --seed 42                         # different light-streak layout
uv run generate.py --width 4096 --height 4096        # square, design centered automatically
uv run generate.py --mode dark --focus full
```

Output: `aero-<seed>-<width>x<height>-<light|dark>.png`

| Flag | Default | Meaning |
|---|---|---|
| `--seed N` | 7 | Changes the thin light streaks. The main ribbons are fixed |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--width / --height` | 3840×2400 | Output size |
| `--focus` / `--targets` | `auto` | Safe-area layout for square multi-screen images (see the top-level README) |
| `--out DIR` | script folder | Output folder |

## Tweaking

Everything is in `generate.py`:

- `PALETTES`: background gradient stops, glow, ribbon colors, ribbon opacity (`sheet_a`),
  edge shine (`edge`), streak color and strength, vignette.
- `layers` inside `render()`: one tuple per glass sheet, giving
  `(amplitude, frequency, phase, base height, wobble)` for the top edge and
  `(amplitude, frequency, phase, base)` for its thickness. Add or remove tuples to change the
  number of ribbons.
- `range(7)` in the streak loop: the number of thin light streaks.
- `REF`: the design height that the pixel-based edge widths were tuned for.
