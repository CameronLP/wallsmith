# aurora

Photographic-style aurora wallpapers, rendered volumetrically.

The aurora is a real 3D volume: curtain shapes are laid out on the ground plane and
extruded upward through about 56 stacked atmosphere layers. Every pixel's view ray passes
through each layer and collects light. This gives you, for free:

- proper perspective: curtains sweep toward you and recede into the distance
- vertical rays that converge overhead (a corona when you look straight up)
- a bright lower edge with color changing by altitude (green, then teal, then violet/red)
- soft bloom, a starfield and photo-like grain

**Light vs dark**

- **dark:** a night sky with full stars and a filmic exposure
- **light:** *blue hour*, a mid-tone dusk sky with a warm horizon, faint stars and the same
  aurora. It's lighter than dark mode but not washed out.

The same seed gives the same aurora in both modes.

## Usage

```bash
uv run aurora.py                                  # random seed, horizon view, light + dark
uv run aurora.py --view overhead --seed 7         # looking straight up
uv run aurora.py --view treeline --palette violet
uv run aurora.py --fast --count 8                 # quick previews (~3 s each)
```

Output: `aurora-<palette>-<view>-<seed>-<light|dark>.png`

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--view` | `horizon` | `horizon`: low view over a mirror lake with a distant treeline. `treeline`: tilted up at the sky with a strip of land at the bottom. `overhead`: lying on your back looking straight up, with curtains directly above you |
| `--palette` | `classic` | `classic` (green into violet/red), `violet`, `teal`, `fire` |
| `--seed N` | random | Same seed gives the same aurora |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--count N` | 1 | Number of images |
| `--width / --height` | 1920×1200 | Output size |
| `--ss N` | 1 | Supersampling. The aurora is soft, so 1 is usually enough; 2 gives crisper stars |
| `--fast` | | 960×600 preview; adds a `-fast` suffix |
| `--focus` / `--targets` | `auto` | Safe-area layout for square multi-screen images (see the top-level README) |
| `--out DIR` | script folder | Output folder |

## Tweaking

In `aurora.py`:

- `PALETTES`: color by altitude inside the curtain (0 = lower edge, 1 = top).
- `SKY`: zenith/horizon sky colors, land and water for each mode.
- `Aurora._build()`: the number of curtains, their distance (`zc0`), how much they swing
  (`amp`, `f`), thickness (`w`) and angle (`th`). Overhead uses separate, tighter values.
- `Aurora.trace()`: `layers`, `y0`/`y1` (curtain bottom/top height), `ray_f` (ray
  fineness), `drift` (ray lean) and the brightness factor.
- `render()`: camera `pitch` per view, field of view, star brightness and exposure.
