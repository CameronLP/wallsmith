# bryce

Retro raytraced landscapes in the spirit of 90s **Bryce 3D**: fractal mountains,
mirror-like water, floating chrome spheres, cloud layers and ringed alien planets.

This is a small numpy raytracer. Terrain is a heightfield traced with ray marching and soft
shadows, and the water and spheres have two bounces of reflection. Every seed is a
different world, and the camera picks a view over water facing the mountains.

- **Light:** the daytime scene
- **Dark:** the *same world* at night: moonlight, a starfield, darker clouds and
  dimly lit planets

## Usage

```bash
uv run bryce.py                              # random preset + seed, light + dark
uv run bryce.py --preset alien --seed 42
uv run bryce.py --mode dark --count 4
uv run bryce.py --fast --count 10            # quick previews (~3 s each)
```

Output: `bryce-<preset>-<seed>-<light|dark>.png`

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--preset` | random | `classic`, `alien`, `dusk`, `toxic` |
| `--seed N` | random | Same seed gives the same world |
| `--mode` | `both` | `light` (day), `dark` (night) or `both` |
| `--count N` | 1 | Number of worlds |
| `--width / --height` | 1920×1200 | Output size |
| `--ss N` | 2 | Supersampling (antialiasing) |
| `--fast` | | 960×600 preview without supersampling; adds a `-fast` suffix |
| `--focus` / `--targets` | `auto` | Safe-area layout for square multi-screen images (see the top-level README) |
| `--out DIR` | script folder | Output folder |

### Presets

- **classic**: blue sky, white clouds, grey peaks with green slopes and snow, deep blue water
- **alien**: orange/purple sunset, stepped red-rock mesas with strata, big ringed planet
- **dusk**: pink/violet twilight, purple mountains, pale moon or planet
- **toxic**: green sky, teal water, bright sun with glare on the water

Some seeds are better than others. Browse with `--fast --count 10` and re-render your
favorites at full quality.

## Tweaking

In `bryce.py`:

- `PRESETS`: all colors, sun elevation and angle relative to the camera (`elev`, `off`),
  cloud cover, fog density, mountain height (`hmax`), terraced terrain (`terrace`),
  rock strata (`strata`), planet/ring probability and the number of spheres.
- `night()`: how a day preset becomes its night version (sky darkening, moonlight color
  and strength, cloud and water darkening).
- `Scene.stars()`: star density (`h > 0.93`) and size.
- `Scene._camera()`: view selection (camera height, pitch, how open the foreground must be).
