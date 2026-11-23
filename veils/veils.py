# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Silky translucent 'veil' wallpapers (flame-fractal style), light + dark.

Each veil is a twisting ribbon swept by thousands of faint lines; where it folds
the lines bunch up into bright creases. Densities are accumulated and log
tone-mapped like a flame fractal renderer.

  uv run veils.py                       # random seed, blue, light + dark
  uv run veils.py --seed 5 --palette violet
  uv run veils.py --count 4 --mode dark
"""
import argparse
import sys
import os
import time

import numpy as np
from PIL import Image

F32 = np.float32
DEFAULT_TARGETS = "16:9,9:16,21:9"

# --size presets.  GNOME's own default wallpapers are 4096x4096 squares (light/dark pairs).
SIZES = {
    "gnome": (4096, 4096),       # same as GNOME's default wallpapers; one image for every screen
    "gnome-5k": (5120, 5120),    # square, sharp even on 5K / super-ultrawide (5120x2160)
    "1080p": (1920, 1080), "1200p": (1920, 1200), "1440p": (2560, 1440),
    "4k": (3840, 2160), "5k": (5120, 2880),
    "ultrawide": (3440, 1440), "superwide": (5120, 2160), "vertical-4k": (2160, 3840),
}


# ---------------------------------------------------------------- focus / safe area
def parse_targets(spec):
    out = []
    for t in spec.split(","):
        a, b = t.strip().lower().replace("x", ":").split(":")
        out.append(float(a) / float(b))
    return out


def focus_rect(W, H, focus="auto", targets=None):
    """Area (ox, oy, w, h) the composition is laid out in.

    full   - the whole canvas
    center - the region that stays visible when the image is zoom-cropped to every target
             aspect ratio (e.g. landscape, portrait and ultrawide screens)
    auto   - 'center' for near-square canvases or when --targets is given, else 'full'
    """
    asp = W / H
    if focus == "full":
        return 0, 0, W, H
    if targets is None:
        if focus == "auto" and not (0.8 < asp < 1.25):
            return 0, 0, W, H
        targets = DEFAULT_TARGETS
    sw, sh = float(W), float(H)
    for a in parse_targets(targets):
        vw, vh = (H * a, H) if asp > a else (W, W / a)
        sw, sh = min(sw, vw), min(sh, vh)
    sw, sh = int(round(sw)), int(round(sh))
    return (W - sw) // 2, (H - sh) // 2, sw, sh



def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], F32)


# per palette: veil hues (picked per veil), dark bg (top, bottom), light bg, light-mode ink
PALETTES = {
    "blue":   dict(veils=["#3d7bff", "#5a8cff", "#6f9dff", "#8a7dff", "#4fa0ff"],
                   dark_bg=("#061033", "#0b2a8a"), light_bg=("#f3f7ff", "#cfdcff"), ink="#1d4fd8"),
    "violet": dict(veils=["#8a5bff", "#a77bff", "#6f6dff", "#c07bff", "#7f9bff"],
                   dark_bg=("#0e0626", "#2a0f6a"), light_bg=("#f8f4ff", "#e0d4ff"), ink="#5a2fd0"),
    "teal":   dict(veils=["#1fc8c8", "#3fd8b0", "#2fa8e8", "#5fe0d8", "#3f8fe0"],
                   dark_bg=("#021a22", "#04485a"), light_bg=("#f0fcfc", "#c8f0ee"), ink="#0a8a96"),
    "ember":  dict(veils=["#ff7a3d", "#ff9a4a", "#ff5a5a", "#ffb35a", "#e8607a"],
                   dark_bg=("#1a0604", "#4a1206"), light_bg=("#fff8f2", "#ffe0cc"), ink="#c8461a"),
    "rose":   dict(veils=["#ff6fb0", "#e07bff", "#ff8fa0", "#c86fe0", "#ff7fd0"],
                   dark_bg=("#1a0618", "#4a0f48"), light_bg=("#fff4fa", "#ffd8ec"), ink="#c02a7a"),
    "aurora": dict(veils=["#3cffa8", "#2fd8ff", "#4f9bff", "#8affd8", "#2fffd0"],
                   dark_bg=("#020a1a", "#06304a"), light_bg=("#eefcff", "#c8f0f4"), ink="#0a8a7a"),
    "cosmic": dict(veils=["#b46bff", "#ff7ad9", "#7a8bff", "#e0b0ff", "#ff9ad0"],
                   dark_bg=("#05020f", "#24083e"), light_bg=("#f8f2ff", "#e6d6ff"), ink="#6a2fc0"),
}

ANCHORS = {"center": (0.5, 0.5), "top": (0.5, 0.2), "bottom": (0.5, 0.8), "left": (0.2, 0.5),
           "right": (0.8, 0.5), "top-left": (0.2, 0.2), "top-right": (0.8, 0.2),
           "bottom-left": (0.2, 0.8), "bottom-right": (0.8, 0.8)}

# style presets: defaults for options you don't set explicitly
STYLES = {
    "vista": dict(palette="aurora", swoop=1.4, align=0.85, direction=10, veils=22,
                  anchor="0.68,0.58", spread=0.4, denoise=1, glow=1.3, thickness=0.3, exposure=0.55),
    "macos": dict(palette="cosmic", swoop=2.0, align=0.55, direction=-8, veils=28,
                  anchor="0.45,0.5", spread=0.55, denoise=1, glow=1.2, thickness=0.45, exposure=0.6),
}
BASE = dict(palette="blue", swoop=0.0, align=0.0, direction=None, veils=44, anchor=None,
            spread=0.5, denoise=0, glow=1.0, thickness=1.0, exposure=1.0)


def parse_anchor(spec):
    if spec is None:
        return None
    if spec in ANCHORS:
        return ANCHORS[spec]
    x, y = (float(t) for t in spec.split(","))
    return x, y


def smooth_fn(rng, n_terms=3, amp=1.0, base_freq=1.0):
    """Random smooth 1D function of s in [0,1] (sum of sinusoids), returned as a callable."""
    ks = [(amp / (k + 1) * rng.uniform(0.4, 1.0), base_freq * rng.uniform(0.5, 1.6) * (k + 1),
           rng.uniform(0, 2 * np.pi)) for k in range(n_terms)]
    return lambda s: sum(a * np.sin(2 * np.pi * f * s + p) for a, f, p in ks)


def render_density(W, H, seed, n_veils, points, pal, align=0.0, direction=None, denoise=0, rect=None, swoop=0.0,
                   anchor=None, spread=0.5, thickness=1.0):
    ox, oy, dw, dh = rect or (0, 0, W, H)   # design area inside the canvas
    rng = np.random.default_rng(seed)
    dens = np.zeros(W * H, np.float64)
    rgb = np.zeros((3, W * H), np.float64)
    veil_cols = [hexc(c) for c in pal["veils"]]
    flow = rng.uniform(-0.5, -0.15)  # dominant up-right diagonal for the whole image
    if direction is not None:        # degrees, 0 = left->right, 90 = upward (screen y points down)
        flow = -np.radians(direction)
    fx, fy = np.cos(flow), np.sin(flow)
    loose = 1.0 - align              # align=1 -> veils follow the flow closely, with fewer twists
    batch = 4_000_000
    t0 = time.time()
    for v in range(n_veils):
        col = veil_cols[rng.integers(len(veil_cols))] * rng.uniform(0.85, 1.15)
        ang = flow + rng.uniform(-0.3, 0.3) * loose
        length = rng.uniform(2.6, 3.4)
        cx0, cy0 = rng.uniform(0.25, 0.75), rng.uniform(-0.1, 0.75)
        if direction is not None:
            # spread ribbons across the screen perpendicular to the chosen flow
            perp = (cy0 - 0.325) / 0.425 * 0.6
            along_off = (cx0 - 0.5) * 0.4
            cx0 = 0.5 - fy * perp + fx * along_off
            cy0 = 0.5 + fx * perp + fy * along_off
        ao = 0.0
        if anchor is not None:
            # every ribbon passes close to the anchor point and fans out from there
            apx, apy = anchor[0], 0.5 + (anchor[1] - 0.5) * dh / dw
            tx, ty = np.cos(ang), np.sin(ang)
            perp = rng.normal(0, 1) * spread * 0.25
            ao = rng.uniform(-0.2, 0.2) * (0.3 + spread)   # anchor's position along this ribbon
            cx0 = apx - ty * perp - tx * ao
            cy0 = apy + tx * perp - ty * ao
        wob_x, wob_y = smooth_fn(rng, 3, 0.14 * (1 - 0.5 * align)), smooth_fn(rng, 3, 0.24 * (1 - 0.5 * align))
        tw = smooth_fn(rng, 3, rng.uniform(0.5, 1.5) * (1 - 0.45 * align), rng.uniform(0.4, 1.0))
        hw0 = rng.uniform(0.08, 0.5) * (1 - 0.45 * align) * thickness
        hwf = smooth_fn(rng, 2, 0.5)
        bendf = smooth_fn(rng, 2, rng.uniform(0.03, 0.15))
        env_p = rng.uniform(1.5, 2.5)
        w = rng.uniform(0.5, 1.0)
        if swoop > 0:
            # Vista-style swoop: flat, then curving away exponentially near one end
            sw_k = rng.uniform(3.0, 7.0)          # how sharply it bends (per screen width)
            sw_d0 = rng.uniform(-0.05, 0.4)       # where the bend happens (0 = screen centre)
            sw_a = swoop * rng.uniform(0.08, 0.16)
            nx, ny = np.sin(ang), -np.cos(ang)   # 'up' relative to the ribbon's direction
            if anchor is not None:                # bend right at the anchor
                sw_d0 = ao + (sw_d0 - 0.175) * 0.4
        n_pts = int(points * rng.uniform(0.6, 1.4) * (0.4 + hw0 * 1.6) * 26 / n_veils)
        for b0 in range(0, n_pts, batch):
            n = min(batch, n_pts - b0)
            s = rng.random(n, dtype=F32)
            u = rng.random(n, dtype=F32) * 2 - 1
            sx = cx0 + (s - 0.5) * length * np.cos(ang) + wob_x(s)
            sy = cy0 + (s - 0.5) * length * np.sin(ang) + wob_y(s)
            twist = ang + np.pi / 2 + tw(s)
            if swoop > 0:
                dd = (s - 0.5) * length
                off = sw_a * np.exp(np.minimum(sw_k * (dd - sw_d0), 12.0))
                sx, sy = sx + nx * off, sy + ny * off
                twist = twist - np.arctan(sw_k * off)   # keep cross-lines perpendicular to the bend
            half = hw0 * (1 + hwf(s))
            dx, dy = np.cos(twist), np.sin(twist)
            arc = (1 - u * u) * bendf(s)
            px = sx + u * half * dx - arc * dy
            py = sy + u * half * dy + arc * dx
            wt = np.sin(np.pi * s) ** env_p * (1 - u * u) ** 0.6 * w
            if anchor is not None:                # brightest near the anchor, fading away from it
                wt = wt * np.exp(-(((s - 0.5) * length - ao) / (0.35 + spread * 1.2)) ** 2)
            ix = (px * dw + ox).astype(np.int64)
            iy = (py * dw + (dh - dw) / 2 + oy).astype(np.int64)
            ok = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
            d = np.bincount((iy * W + ix)[ok], weights=wt[ok], minlength=W * H)
            dens += d
            for c in range(3):
                rgb[c] += d * col[c]
        print(f"\r  veil {v + 1}/{n_veils}  {time.time() - t0:4.0f}s", end="", flush=True)
    print()
    dens = dens.reshape(H, W)
    rgb = rgb.reshape(3, H, W).transpose(1, 2, 0)
    if denoise > 0:                  # smooth Monte Carlo grain before tone mapping
        dens = blur(dens, denoise).astype(np.float64)
        rgb = blur(rgb, denoise).astype(np.float64)
    return dens, rgb / np.maximum(dens, 1e-9)[..., None]


def blur(img, r):
    """Cheap box-ish blur via repeated 1D cumulative sums (for glow)."""
    out = img.astype(F32)
    for axis in (0, 1):
        for _ in range(2):
            c = np.cumsum(np.pad(out, [(r + 1, r) if a == axis else (0, 0) for a in range(out.ndim)], mode="edge"),
                          axis=axis, dtype=np.float64)
            n = out.shape[axis]
            out = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis) - np.take(c, np.arange(0, n), axis)) / (2 * r + 1)
    return out.astype(F32)


def compose(dens, col, mode, pal, rng, glow_k=1.0, exposure=1.0):
    H, W = dens.shape
    # flame-style log tone map; normalise on a high percentile, not the max
    ref = np.percentile(dens[dens > 0], 99.7)
    b = np.log1p(dens / ref * 6 * exposure) / np.log1p(6)
    b = np.clip(b, 0, 1.6).astype(F32)
    glow = blur(b, max(2, W // 400))
    v = np.linspace(0, 1, H, dtype=F32)[:, None]
    u = np.linspace(0, 1, W, dtype=F32)[None, :]
    t = np.clip(0.6 * v + 0.4 * u, 0, 1)[..., None]

    if mode == "dark":
        top, bot = hexc(pal["dark_bg"][0]), hexc(pal["dark_bg"][1])
        bg = top + (bot - top) * t
        light = col * (b ** 1.1)[..., None] * 1.05 + col * glow[..., None] * 0.35 * glow_k
        img = bg + (1 - bg) * np.clip(light, 0, None)  # screen-ish
        # whitish highlights on the brightest creases
        img = img + (np.clip(b - 0.85, 0, None) ** 1.5)[..., None] * 0.6
        vig = (u - 0.5) ** 2 + (v - 0.5) ** 2
        img *= (1 - vig * 0.5)[..., None]
    else:
        top, bot = hexc(pal["light_bg"][0]), hexc(pal["light_bg"][1])
        bg = top + (bot - top) * t
        ink = hexc(pal["ink"])
        tint = (col * 0.5 + ink * 0.5)
        a = np.clip(b * 0.75 + glow * 0.25 * glow_k, 0, 1)[..., None] ** 1.05
        img = bg * (1 - a) + tint * a
        # bright creases become white sheen rather than dark ink
        img = img + (np.clip(b - 0.9, 0, None) ** 1.5)[..., None] * 0.9
    img += rng.normal(0, 1.0 / 255, img.shape).astype(F32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--style", choices=list(STYLES), help="preset: vista or macos (explicit flags still override)")
    ap.add_argument("--palette", choices=list(PALETTES))
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--ss", type=int, default=2, help="supersampling factor")
    ap.add_argument("--veils", type=int, help="number of veils drawn")
    ap.add_argument("--quality", type=float, default=1.0,
                    help="sample multiplier: 2 = twice the points, less grain, ~2x slower")
    ap.add_argument("--denoise", type=int,
                    help="smoothing radius in output pixels (1-3 removes grain, softens fine creases)")
    ap.add_argument("--align", type=float,
                    help="0..1: how strongly veils follow one common direction (1 = calm, parallel swoops)")
    ap.add_argument("--swoop", type=float,
                    help="Vista-style exponential swoops: 0 = off, 0.5 = gentle, 1 = strong, 2 = dramatic")
    ap.add_argument("--direction", type=float,
                    help="rough flow direction in degrees: 0 = left->right, 30 = rising to the right, "
                         "-30 = falling, 90 = vertical (default: random rising diagonal)")
    ap.add_argument("--anchor", help="concentrate the veils around a point: center, top, bottom, left, right, "
                                     "top-left, top-right, bottom-left, bottom-right, or 'x,y' (0..1)")
    ap.add_argument("--spread", type=float, help="with --anchor: 0 = tight bundle, 1 = loose (default 0.5)")
    ap.add_argument("--glow", type=float, help="glow strength multiplier (default 1)")
    ap.add_argument("--thickness", type=float, help="ribbon width multiplier: <1 = thin crisp bands (default 1)")
    ap.add_argument("--exposure", type=float, help="brightness of the veils: <1 = darker, more contrast (default 1)")
    ap.add_argument("--fast", action="store_true", help="960x600 quick preview")
    ap.add_argument("--focus", choices=["auto", "center", "full"], default="auto",
                    help="where to lay out the composition: full canvas, or centred in the area visible "
                         "on all --targets screens (auto = center for near-square canvases)")
    ap.add_argument("--targets", help=f"screen aspect ratios the image must work on, e.g. '{DEFAULT_TARGETS}' "
                                      "or '3840x2160,2160x3840,3440x1440'")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    if a.size:
        a.width, a.height = SIZES[a.size]
        if hasattr(a, "ss") and "--ss" not in sys.argv and a.width * a.height > 9_000_000:
            a.ss = 1                     # big presets: supersampling would be slow and memory-hungry
    preset = STYLES.get(a.style, {})
    for k, base in BASE.items():
        if getattr(a, k) is None:
            setattr(a, k, preset.get(k, base))
    tag = "-fast" if a.fast else ""
    if a.fast:
        k = 960 / max(a.width, a.height) if a.size else 0   # previews keep the preset's shape
        a.width, a.height, a.ss = (round(a.width * k), round(a.height * k), 1) if k else (960, 600, 1)
    modes = ["light", "dark"] if a.mode == "both" else [a.mode]
    pal = PALETTES[a.palette]
    W, H = a.width * a.ss, a.height * a.ss
    for i in range(a.count):
        seed = a.seed + i if a.seed is not None else int(np.random.default_rng().integers(0, 100000))
        print(f"[{i + 1}/{a.count}] palette={a.palette} seed={seed}")
        dens, col = render_density(W, H, seed, a.veils, points=int(W * H * 5 * a.quality), pal=pal,
                                   align=float(np.clip(a.align, 0, 1)), direction=a.direction, swoop=max(a.swoop, 0.0),
                                   anchor=parse_anchor(a.anchor), spread=a.spread, thickness=a.thickness,
                                   denoise=a.denoise * a.ss,
                                   rect=focus_rect(W, H, a.focus, a.targets))
        for m in modes:
            im = Image.fromarray(compose(dens, col, m, pal, np.random.default_rng(seed), a.glow, a.exposure), "RGB")
            if a.ss > 1:
                im = im.resize((a.width, a.height), Image.LANCZOS)
            p = os.path.join(a.out, f"veils-{a.style + '-' if a.style else ''}{a.palette}-{seed}-{m}{tag}.png")
            im.save(p, optimize=True)
            print("  ->", p)


if __name__ == "__main__":
    main()
