# TODO

## New generators (ideas)

- [ ] **Topographic contours:** thin contour lines of a fractal landscape. Minimal, and works well in light and dark.
- [ ] **Mesh gradients:** smooth, soft blobs of color in the style of modern macOS/iOS wallpapers.
- [ ] **Glass refraction:** frosted or ribbed glass distorting a colorful background.
- [ ] **Low-poly crystals:** triangulated shards with subtle lighting.
- [ ] **Flow fields:** thousands of fine particle trails following a noise field (hair or wind look).
- [ ] **Retro synthwave:** neon grid floor, striped sun, chrome mountains.
- [ ] **Moiré / op-art:** overlapping line patterns with interference effects.
- [ ] **Paper cut-out landscapes:** layered hills in the GNOME flat style, but as scenery.
- [x] **Moebius-style artwork:** clean ink linework (ligne claire) with flat, sun-bleached pastel
      fills and fine hatching. Think vast desert or alien landscapes: mesas, rock spires, huge
      skies, maybe a tiny distant figure or structure for scale.

## Features / improvements

- [ ] aurora: option for ray direction and other ray variations, e.g. rays that explode or
      radiate from a point (corona-style bursts), fanning or twisted rays, instead of only
      parallel vertical streaks.
- [~] One wallpaper for all monitor types (laptop, 4K, vertical, ultrawide). Mostly covered by
      `--size gnome` (4096×4096 + `--ss 1`, with `--focus auto` centering the design). Still open:
      per-generator tuning, e.g. a lower veils point budget and vertical-monitor handling like
      twilight's `--sky-span`/`--ground` for aurora and bryce.
- [ ] Bring twilight-style settings to the other generators:
      - custom palettes from the command line (`--colors` / `--colors-light`) for veils, aero, gnome, aurora, bryce
      - gradient controls (`--band`, `--fade`, `--curve`, `--horizon`) for the sky/background gradients
        in aurora, bryce and aero
      - vertical-monitor handling (`--sky-span`, `--ground`) for aurora and bryce, so square images
        work on portrait screens too
      - `--star-style original|realistic` and `--milkyway` for the night skies in aurora and bryce
      - resolution-independent output like twilight's `--classic` scaling (same picture at any size)
      - light-mode controls like twilight's `--light-level` (how bright light mode is) and
        `--light-stars` for the generators with night skies (aurora, bryce)
- [ ] veils: more style presets (e.g. Vista "aurora" variants, Leopard-style nebula swirl with stars).
- [ ] veils: optional starfield / sparkles for the `macos` style.
- [ ] Shared module for the common code (`focus_rect`, noise, blur, CLI flags). It's currently
      duplicated in each script to keep them standalone.
- [ ] `aero`: random ribbon layouts per seed (currently only the light streaks change).
- [ ] A single `wallsmith` entry point (`uv run wallsmith.py veils --style vista …`).
- [ ] Batch contact sheet: render `--fast` previews into one grid image for picking seeds.
- [ ] Mobile wallpaper sizes: `--size` presets for phones and tablets (e.g. common iPhone/Android
      portrait resolutions, ~9:19.5 / 9:20, plus tablets around 3:4 / 10:16). Consider the extra
      width phone launchers use for parallax/scrolling, and a safe area that avoids the clock and
      dock regions on lock and home screens. Also check that each generator's composition works in
      tall portrait (like twilight's `--sky-span`/`--ground`).

## Done

- [x] veils: `--quality` / `--denoise` for less grain
- [x] veils: `--align` and `--direction` for the swoops
- [x] veils: `--swoop` (Vista-style exponential swoops), `--anchor` / `--spread` positioning,
      `--thickness`, `--exposure`, `--glow`, and `--style vista|macos` presets
- [x] `-fast` filename suffix for previews
- [x] `--focus` / `--targets` safe-area layout for single square images
- [x] `--size` presets for every generator (`gnome` = 4096², like GNOME's defaults)
- [x] twilight: generator after SGI/bcaluneo Twilight, with `--classic`, realistic stars, Milky Way,
      and `--band`/`--fade`/`--curve`/`--horizon`/`--colors` controls
- [x] twilight: `--sky-span` / `--ground` so square images work on vertical monitors
- [x] twilight: `--classic` scales to any resolution (same picture, e.g. 5120×3200)
- [x] twilight: original-style stars fixed (no L-shapes; chunky blobs like the original's screenshot);
      realistic stars stay round, sharp and dense at 4K/5K
- [x] twilight: `--light-stars`, `--evening-star`, `--light-level`
- [x] aurora: volumetric rewrite with `--view horizon|treeline|overhead` and a blue-hour light mode
