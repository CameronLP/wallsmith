# wallsmith

Procedural wallpaper generators. Each one is a standalone Python script that renders
matching **light and dark** variants of the same design.

wallsmith only *generates* images. It never touches your desktop settings.

| Folder | Style | Render time (full quality, 1920×1200) |
|---|---|---|
| [`aero/`](aero/README.md) | Frutiger Aero glass ribbons and light streaks | ~10 s |
| [`veils/`](veils/README.md) | Silky flame-fractal veils, including Vista and macOS-style swoops | ~2 min |
| [`aurora/`](aurora/README.md) | Photographic volumetric aurora (horizon, treeline or overhead) | ~20 s per mode |
| [`bryce/`](bryce/README.md) | 90s Bryce 3D raytraced landscapes (day/night) | ~45 s per mode |
| [`gnome/`](gnome/README.md) | GNOME/Adwaita-style flat layered shapes | ~5 s per mode |
| [`twilight/`](twilight/README.md) | Twilight sky with original or realistic stars (after SGI's classic Twilight) | ~9 s per mode |

Planned generators and features are listed in [TODO.md](TODO.md).

## Requirements

[`uv`](https://docs.astral.sh/uv/) is the only requirement. Each script declares its own
dependencies (`numpy`, `pillow`) inline, so `uv run script.py` installs them automatically
into a cached environment.

## Common options

All generators share these flags (`aero` has all except `--count`, `--ss` and `--fast`):

| Flag | Meaning |
|---|---|
| `--seed N` | Reproducible result: the same seed gives the same image |
| `--count N` | Make N images (seeds `seed`, `seed+1`, …, or random) |
| `--mode light\|dark\|both` | Which variants to render (default `both`) |
| `--width / --height` | Output size (default 1920×1200) |
| `--size PRESET` | Size preset (overrides width/height): `gnome` (4096×4096, the size of GNOME's own default wallpapers), `gnome-5k` (5120×5120), `1080p`, `1200p`, `1440p`, `4k`, `5k`, `ultrawide` (3440×1440), `superwide` (5120×2160), `vertical-4k` (2160×3840). Large presets use `--ss 1` unless you set it; `--fast` previews keep the preset's shape |
| `--ss N` | Supersampling (antialiasing) factor, default 2 |
| `--fast` | Quick 960×600 preview without supersampling; files get a `-fast` suffix |
| `--focus auto\|center\|full` | Where the composition is laid out (see [Focus](#focus-one-image-for-many-screens)) |
| `--targets LIST` | Screens the image must work on, e.g. `16:9,9:16,21:9` or `3840x2160,2160x3840,3440x1440` |
| `--out DIR` | Output folder (default: the script's folder) |

A good workflow: generate a batch with `--fast --count 10`, pick the seeds you like, then
re-render those at full quality with `--seed N`.

## Choosing a wallpaper size

Desktops like GNOME show **one image on all monitors**, scaling it to *cover* each screen
and cropping whatever sticks out. So the image has to be big enough for your most
demanding screen in **both** directions.

### Recommendation: one square 4096×4096 image

This is also exactly what GNOME ships: its default wallpapers are 4096×4096 light/dark
pairs. Use `--size gnome` as the shortcut (or `--size gnome-5k` for 5120×5120).

A square image covers every orientation and aspect ratio:

| Screen | Resolution | Part of a 4096² image shown | Sharp? |
|---|---|---|---|
| Laptop | 1920×1080 | full width, middle 56% of height | ✔ downscaled |
| 4K landscape | 3840×2160 | full width, middle 56% of height | ✔ |
| 4K vertical | 2160×3840 | middle 56% of width, full height | ✔ |
| Ultrawide | 3440×1440 | full width, middle 42% of height | ✔ |
| Super-ultrawide | 5120×2160 | full width, middle 42% of height | ~ slight upscale (1.25×) |

```bash
uv run veils/veils.py       --size gnome
uv run gnome/gnome.py       --size gnome
uv run aurora/aurora.py     --size gnome
uv run bryce/bryce.py       --size gnome
uv run twilight/twilight.py --size gnome
uv run aero/generate.py     --size gnome
```

- **Use `--ss 1` at this size.** 4096² already has plenty of pixels. Supersampling
  would mean rendering 8192², which is slow and uses a lot of RAM (veils needs several GB).
  `--quality 2` is a cheaper way to reduce grain in veils.
- **Render time** scales with pixel count: 4096² is about 7× more pixels than 1920×1200.
  Browse with `--fast` first, then render only your favorite seeds big.
- For a super-ultrawide that must be pixel-perfect, use 5120×5120.

### Focus: one image for many screens

On a square image, each screen only sees part of it: wide screens see a horizontal band
through the middle, and vertical screens see a vertical band. Only the **center area that
all of them share** is guaranteed to be visible. `--focus` controls where the design goes:

| `--focus` | Behaviour |
|---|---|
| `auto` (default) | **Best guess.** Near-square canvases (aspect 0.8–1.25) or an explicit `--targets` use `center`; anything else uses `full` |
| `center` | The composition is laid out inside the shared safe area, so the interesting features (horizon, swoop bends, focal shapes) land where every screen sees them. The rest of the canvas is a natural continuation (bleed) |
| `full` | The composition uses the whole canvas (the classic behavior) |

The safe area is the intersection of what each target screen shows after cropping. The
default targets are `16:9,9:16,21:9` (landscape, portrait and ultrawide). For a 4096² image
that's a centered 2304×1755 area. Set your exact screens for a precise result:

```bash
uv run veils/veils.py --width 4096 --height 4096 --ss 1 \
    --targets 3840x2160,2160x3840,3440x1440,1920x1080
```

The script prints the design area it chose. Vertical gradients (twilight) get special handling: the horizon stays in the
safe area, but the sky extends to the top of the canvas and the area below the horizon gets
a ground silhouette, so a vertical monitor sees a complete scene too. In the scene generators (`aurora`, `bryce`),
`center` keeps the original camera framing inside the safe area and widens the field of
view to fill the rest, so the horizon stays in view on every screen.

### One image per screen

To match each screen exactly instead, render each resolution with the same seed. You get
the same design adapted to each aspect ratio:

```bash
S=42
uv run veils/veils.py --seed $S --width 2160 --height 3840   # vertical 4K
uv run veils/veils.py --seed $S --width 3440 --height 1440   # ultrawide
uv run veils/veils.py --seed $S --width 3840 --height 2160   # 4K
uv run veils/veils.py --seed $S --width 1920 --height 1080   # laptop
```
