# twilight

A twilight sky: a glowing horizon band fading through blue into the night, with stars.

Based on **Twilight**, the classic SGI IRIX wallpaper program by Howard Look, and
Brendan Caluneo's SDL2 port
([project page](https://bcaluneo.com/projects/twilight/),
[source](https://github.com/bcaluneo/Twilight)). The `--classic` mode reproduces the
original: the same colors and gradient, 2500 pixel stars and 200 chunky "big stars"
(2×2 dots and rounded 4×4 blobs, centered so none come out L-shaped),
with stars tinted by the sky near the horizon and turning white higher up.

- **Dark:** the original night-falling sky
- **Light:** an earlier, brighter dusk (peach horizon, sky blue, deep blue top) with a few
  crisp first stars near the top (`--light-stars` controls how many)

## Usage

```bash
uv run twilight.py                                    # realistic stars, classic colors, light + dark
uv run twilight.py --classic --mode dark              # exactly like the original program
uv run twilight.py --star-style original              # original-style stars, enhanced sky
uv run twilight.py --milkyway --palette rose
uv run twilight.py --band 0.1 --fade 0.6              # thin horizon, dark sky from 60% up
uv run twilight.py --colors '#ff3060,#3a2a90,#020010' # your own palette
```

Output: `twilight-<star style>[-milkyway]-<palette|custom>-<seed>-<light|dark>[-fast].png`

## Options

### Stars

| Flag | Default | Meaning |
|---|---|---|
| `--star-style` | `realistic` | `realistic`: photographic stars, with power-law brightness (many faint, few bright), sub-pixel antialiasing, blue-white to orange color temperatures, soft halos on bright stars, and dimmer, redder stars near the horizon. `original`: the classic look from the original's screenshots, with single-pixel stars plus chunky 2×2 dots and rounded 4×4 blobs. At high resolutions they're upscaled in whole pixels so they stay crisp and blocky, and star density scales with resolution |
| `--milkyway` | off | Adds a Milky Way band with dust lanes and extra stars (realistic style) |
| `--stars X` | 1 | Star density multiplier |
| `--light-stars X` | 1 | Stars in light mode. `0` = none (clean dusk); `1` = a few clearly visible "first stars of the evening", concentrated high up where the sky is darkest; `3` = noticeably starry; `~10` = every dark-mode star (the maximum). Light-mode stars are a subset of the dark-mode ones, in the same positions, so a light/dark pair (same seed) matches |
| `--light-level X` | 1 | Brightness of light mode's sky: `0` = as dark as dark mode, `0.5` = deep moody dusk, `1` = normal, `1.3` = paler daytime look, `2` = near white. Stars and composition are unchanged |
| `--evening-star` | off | Adds one brilliant planet (like Venus) low over the horizon, with a soft glow, in the same place in both modes |
| `--classic` | off | Faithful original: hard gradient, exact star counts and shapes, no glow/dither. Above 1200 px tall, the star layout is made on the original 1200 px grid and scaled up in whole pixels, so e.g. `--width 5120 --height 3200` is the same picture as 1920×1200, just sharper |

### Gradient and colors

```
 top colour  ─────────────  ← above --fade: solid top colour
             ╲  main gradient (mid → top), shaped by --curve
 mid colour  ─────────────  ← --band
             ╲  horizon band (horizon → mid)
 horizon     ─────────────  ← --horizon (0 = bottom edge)
```

| Flag | Default | Meaning |
|---|---|---|
| `--band X` | 0.2 | Height of the bottom horizon gradient, as a fraction of the sky (the original's `TRANSITION`). `--transition` is an alias |
| `--fade X` | 1.0 | Height where the sky reaches the top color. `1` = the top edge; `0.6` = solid night sky above 60% |
| `--curve X` | 1.0 | Shape of the main gradient: `<1` darkens quickly above the band; `>1` keeps the mid color longer |
| `--horizon X` | 0 | Raises the horizon above the bottom edge (e.g. `0.15`). Below it, the glow continues and darkens |
| `--sky-span` | `auto` | Vertical layout for square / multi-screen images. `safe`: the whole gradient fits inside the focus (safe) area. `full`: the horizon stays in the safe area (every screen sees it), but the sky runs to the top of the canvas, so a vertical monitor gets the complete gradient. `auto` = `full` whenever the focus area is smaller than the canvas |
| `--ground` | `auto` | What fills the canvas below the horizon (seen on vertical monitors): `hills` (low dark silhouette), `dark` (flat), `none` (the glow continues). `auto` = `hills` when there's space below the horizon |
| `--glow X` | 1 | Strength of the soft horizon glow (not used with `--classic`) |
| `--palette` | `classic` | `classic` (original orange/blue/black), `rose`, `ember`, `teal` |
| `--colors H,M,T` | | Custom palette: horizon, mid and top colors as hex, e.g. `'#ff4800,#006ebd,#000000'`. Sets dark mode; light mode is derived automatically |
| `--colors-light H,M,T` | | Custom light-mode palette (overrides the derived one) |

### Vertical monitors

A gradient sky only changes vertically, so it needs its own handling on a single square image
shared by landscape and portrait screens. Landscape screens see a horizontal band through the
middle; a vertical monitor sees the full height. With `--size gnome`, the defaults
(`--sky-span full --ground hills`) give:

- **landscape / ultrawide:** horizon at the bottom of the screen, orange → blue → darkening sky
- **vertical:** the complete gradient up to black, the horizon about 70% down, and dark hills below

For a vertical monitor on its own, render its exact size instead: `--size vertical-4k`.

### Common

| Flag | Default | Meaning |
|---|---|---|
| `--seed N` | random | Same seed gives the same star field |
| `--mode` | `both` | `light`, `dark` or `both` |
| `--count N` | 1 | Number of images |
| `--width / --height` | 1920×1200 | Output size |
| `--size PRESET` | | Size preset, e.g. `gnome` (4096×4096) or `5k` (see the top-level README) |
| `--ss N` | 1 | Supersampling. 1 keeps the original-style stars pixel-crisp |
| `--fast` | | 960×600 preview; adds a `-fast` suffix |
| `--focus` / `--targets` | `auto` | Safe-area layout for square multi-screen images (see the top-level README). With `center`, the horizon sits at the bottom of the shared safe area, so every screen sees it |
| `--out DIR` | script folder | Output folder |

## Tweaking

In `twilight.py`:

- `PALETTES`: (horizon, mid, top) colors per mode.
- `original_stars()`: the classic star counts (2500 / 200), big-star blob sizes and the
  `getStarColor` height tinting.
- `realistic_stars()`: star density (`W * H / 260`), brightness distribution, color
  temperatures, halo size and the Milky Way band.
