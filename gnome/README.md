# gnome

GNOME-style wallpapers: flat, layered vector shapes with soft drop shadows, in the
GNOME (Adwaita) color palette.

Shapes are signed-distance fields, so edges stay crisp and shadows stay soft at any
resolution. Light and dark modes share exactly the same composition:

- **Light:** a pale tint of the palette as background, with light-to-mid shades
- **Dark:** a near-black (#1e1e1e) background tinted by the palette, with deep shades and
  stronger shadows

## Usage

```bash
uv run gnome.py                                  # random motif + palette, light + dark
uv run gnome.py --motif waves --palette blue --seed 3
uv run gnome.py --fast --count 12                # browse random designs quickly
```

Output: `gnome-<motif>-<palette>-<seed>-<light|dark>.png`

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--motif` | random | `waves`, `blobs`, `pills`, `rings`, `folds`, `dots` (see below) |
| `--palette` | random | `blue`, `green`, `yellow`, `orange`, `red`, `purple`, `brown`, `slate` |
| `--seed N` | random | Same seed gives the same layout |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--count N` | 1 | Number of designs |
| `--width / --height` | 1920×1200 | Output size |
| `--ss N` | 2 | Supersampling factor |
| `--fast` | | 960×600 preview; adds a `-fast` suffix |
| `--focus` / `--targets` | `auto` | Safe-area layout for square multi-screen images (see the top-level README) |
| `--out DIR` | script folder | Output folder |

### Motifs

- **waves:** stacked wavy layers, like paper cut-outs
- **blobs:** overlapping organic rounded shapes
- **pills:** diagonal rounded capsules
- **rings:** concentric discs growing out of a corner
- **folds:** angled paper sheets layered across the screen
- **dots:** a loose diagonal cluster of circles

## Tweaking

In `gnome.py`:

- `PALETTES`: five shades per color (light to dark). Add your own lists here.
- `m_<motif>()`: each motif is a small function that returns a list of SDF shapes
  (back to front). Add a new motif by writing one and registering it in `MOTIF_FN`/`MOTIFS`.
- `render()`: background mix, which shade range each mode uses, shadow softness
  (`soft`), shadow offset (`off`) and opacity (`sh_a`).
