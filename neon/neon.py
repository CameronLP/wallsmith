# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Neon Nocturne wallpapers: blurred city lights reflected on wet pavement.

Bokeh orbs, vertical rain reflections, and hazy neon haze. Evokes a rainy night
in a neon-lit street, or the soft glow through a rainy window.

  uv run neon.py                       # random seed, light + dark
  uv run neon.py --seed 8 --mode dark  # single dark variant
  uv run neon.py --fast --count 6      # quick low-res previews
"""
import argparse
import sys
import os

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


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- palettes
# Each palette: sky gradient (top -> mid -> horizon), ground color, bokeh accent colors,
# haze tint, overall warmth/tone.
PALETTES = {
    "tokyo": dict(
        dark_sky=("#030210", "#080620", "#151044"),      # top, mid, horizon
        dark_ground="#060416",
        light_sky=("#f0e8e0", "#e0d2c8", "#c8b8b0"),
        light_ground="#c0b0a8",
        bokeh=["#ff3385", "#00e5ff", "#ffb800", "#ff6b35", "#c8a8ff", "#ff80ab"],
        haze=("#ff3385", "#00e5ff"),
    ),
    "seoul": dict(
        dark_sky=("#020814", "#0a1430", "#101c48"),
        dark_ground="#060c20",
        light_sky=("#c8d8e8", "#a0b8d8", "#809cc0"),
        light_ground="#90a4b8",
        bokeh=["#00f0ff", "#ff5090", "#ffb820", "#60e0a0", "#ff9e50", "#a8c8ff"],
        haze=("#00f0ff", "#ff5090"),
    ),
    "hongkong": dict(
        dark_sky=("#0c0408", "#200a18", "#361230"),
        dark_ground="#0a0408",
        light_sky=("#f0e0d8", "#dcc8c0", "#c0a4a0"),
        light_ground="#b4a098",
        bokeh=["#ff1a6b", "#00ffc8", "#ffcc00", "#ff6b35", "#c8a0ff", "#ff4080"],
        haze=("#ff1a6b", "#00ffc8"),
    ),
    "kyoto": dict(
        dark_sky=("#060a10", "#0c1828", "#142438"),
        dark_ground="#04080c",
        light_sky=("#e8e4d8", "#d0c8b8", "#b4a898"),
        light_ground="#c0b8a8",
        bokeh=["#ffa000", "#ffd700", "#ff4080", "#20c0ff", "#80c8ff", "#ffc044"],
        haze=("#ffa000", "#20c0ff"),
    ),
}


# ---------------------------------------------------------------- blur helpers
def gaussian_kernel(size, sigma):
    x = np.arange(size, dtype=F32) - (size - 1) / 2.0
    k = np.exp(-x * x / (2 * sigma * sigma))
    return k / k.sum()


def blur(img, sigma):
    """Fast separable Gaussian blur on a (H,W,3) float image."""
    if sigma < 0.4:
        return img
    size = max(int(sigma * 3.5) * 2 + 1, 3)
    k = gaussian_kernel(size, sigma)
    pad = size // 2
    out = np.empty_like(img)
    # horizontal
    padded = np.pad(img, ((0, 0), (pad, pad), (0, 0)), mode="reflect")
    for i in range(3):
        out[:, :, i] = np.apply_along_axis(lambda row: np.convolve(row, k, mode="valid"),
                                           axis=1, arr=padded[:, :, i])
    # vertical
    padded = np.pad(out, ((pad, pad), (0, 0), (0, 0)), mode="reflect")
    for i in range(3):
        img[:, :, i] = np.apply_along_axis(lambda col: np.convolve(col, k, mode="valid"),
                                           axis=0, arr=padded[:, :, i])
    return img


# ---------------------------------------------------------------- rendering
def screen(base, col, a=1.0):
    return base + (1 - base) * col * a


def add_glow(base, col, intensity, sigma):
    """Add a soft blurred glow layer using additive blend."""
    layer = col[None, None, :] * intensity[:, :, None]
    layer = blur(layer, sigma)
    return np.clip(base + layer, 0, None)


def render(mode, W, H, seed, palette="tokyo"):
    rng = np.random.default_rng(seed)
    pal = PALETTES[palette]

    xx, yy = np.mgrid[0:H, 0:W].astype(F32)
    u = xx / max(W - 1, 1)
    v = yy / max(H - 1, 1)

    # --- background gradient ---
    if mode == "dark":
        t_top, t_mid, t_hor = hexc(pal["dark_sky"][0]), hexc(pal["dark_sky"][1]), hexc(pal["dark_sky"][2])
        gnd = hexc(pal["dark_ground"])
        vign_strength = 0.55
    else:
        t_top, t_mid, t_hor = hexc(pal["light_sky"][0]), hexc(pal["light_sky"][1]), hexc(pal["light_sky"][2])
        gnd = hexc(pal["light_ground"])
        vign_strength = 0.30

    horizon = 0.34 + rng.uniform(-0.04, 0.05)

    # Sky gradient
    sky_t = np.clip(v / horizon, 0, 1)
    sky = lerp(t_hor, t_mid, smooth(0.0, 0.55, sky_t))
    sky = lerp(sky, t_top, smooth(0.45, 1.0, sky_t))

    # Ground: smooth transition below horizon
    below = v >= horizon
    ground_t = np.clip((v - horizon) / max(1 - horizon, 1e-3), 0, 1)
    ground = lerp(t_hor, gnd, smooth(0.0, 1.0, ground_t))
    col = np.where(below[:, :, None], ground, sky)

    # --- horizon haze / glow ---
    haze_t = np.exp(-((v - horizon) ** 2) * 90.0)
    haze_l, haze_r = hexc(pal["haze"][0]), hexc(pal["haze"][1])
    haze_phase = rng.uniform(0, 4)
    # Left-to-right blend of the two haze colours, sinusoidal
    haze = lerp(haze_l, haze_r, 0.5 + 0.5 * np.sin(u * np.pi * 2.1 + haze_phase))
    if mode == "light":
        col += haze * haze_t[:, :, None] * 0.12
    else:
        col += haze * haze_t[:, :, None] * 0.28

    # --- bokeh orbs (soft blurred spots of light) ---
    n_orbs = 18 + rng.integers(14)
    # Store orb data for reflections
    orb_data = []
    for _ in range(n_orbs):
        ox = rng.uniform(-0.15, 1.15)
        oy = rng.uniform(0.04, horizon + 0.16)
        radius = rng.uniform(0.018, 0.065) * min(W, H)
        blur_sig = radius * rng.uniform(0.7, 1.8)
        color = hexc(rng.choice(pal["bokeh"])) * rng.uniform(0.6, 1.3)
        if mode == "light":
            color *= rng.uniform(0.7, 1.1)
        orb_data.append((ox, oy, radius, blur_sig, color))

    for ox, oy, radius, blur_sig, color in orb_data:
        dx = (u - ox) * W
        dy = (v - oy) * H
        dist2 = (dx ** 2 + dy ** 2) / (radius * radius + 1e-6)
        core = np.exp(-dist2 * 0.9)
        halo = np.exp(-dist2 * 0.12) * 0.35
        intensity = core + halo
        col = add_glow(col, color, intensity, blur_sig)

    # --- vertical wet reflections ---
    # For each orb, reflect its position below the horizon and draw a long blurred vertical streak
    for ox, oy, radius, _, color in orb_data:
        # Reflection position: mirrored below horizon
        ry_top = horizon + (horizon - oy) * rng.uniform(0.8, 1.2)
        if ry_top > 0.95:
            continue
        ry_bot = rng.uniform(0.82, 1.0)
        cx = ox + rng.uniform(-0.04, 0.04)
        width = rng.uniform(2.0, 6.0) * (1 + (ry_bot - ry_top) * 0.5)
        brightness = rng.uniform(0.25, 0.7)
        if mode == "light":
            brightness *= 0.4

        y0, y1 = ry_top * H, ry_bot * H
        # Vertical mask: strong near top, fading to bottom
        y_mask = np.exp(-((v * H - y0) / max(y1 - y0, 10)) * 1.5)
        y_mask *= smooth(y0, y0 + 25, v * H)
        y_mask *= smooth(y1, y1 - 60, v * H)

        dx = (u - cx) * W
        spread = 1.0 + (v - ry_top) * 3.0
        streak = np.exp(-(dx / (width * spread + 1e-3)) ** 2)
        streak *= y_mask

        col = add_glow(col, color, streak * brightness, max(3.0, width * 0.6))

    # --- horizontal neon strips (distant street lights / building edges) ---
    n_strips = rng.integers(4, 9)
    for _ in range(n_strips):
        sy = rng.uniform(horizon + 0.04, 0.92)
        height = rng.uniform(2.0, 6.0)
        color = hexc(rng.choice(pal["bokeh"])) * rng.uniform(0.5, 1.2)
        brightness = rng.uniform(0.3, 0.9)
        if mode == "light":
            brightness *= 0.5

        y_px = v * H
        band = np.exp(-((y_px - sy * H) / height) ** 2)
        # Occasional occlusion/gap for realism
        if rng.random() < 0.35:
            gap = rng.uniform(0.25, 0.75)
            band *= np.where((u > gap) & (u < gap + rng.uniform(0.04, 0.12)), 0.15, 1.0)

        col = add_glow(col, color, band * brightness, height * 1.2)

    # --- rain streaks ---
    n_rain = 150 + rng.integers(120)
    for _ in range(n_rain):
        rx = rng.uniform(-0.05, 1.05)
        ry_top = rng.uniform(-0.1, 0.7)
        length = rng.uniform(0.06, 0.30) * H
        angle = rng.uniform(-0.03, 0.03)  # slight slant
        width_r = rng.uniform(0.25, 0.9)
        brightness = rng.uniform(0.03, 0.18)

        # Rotate coordinates to align with the rain streak
        dy = (v - ry_top) * H
        dx = (u - rx) * W
        # Distance along the streak direction
        # Direction vector: (sin(angle), cos(angle)) -- mostly vertical
        proj = dy * np.cos(angle) + dx * np.sin(angle)
        perp = dy * np.sin(angle) - dx * np.cos(angle)

        in_len = (proj >= 0) & (proj <= length)
        streak = np.exp(-(perp / (width_r + 1e-3)) ** 2)
        streak *= np.exp(-(proj / (length * 0.6 + 1e-3)) ** 2)
        streak *= in_len.astype(F32)

        if mode == "dark":
            col += 1.0 * streak[:, :, None] * brightness
        else:
            col -= streak[:, :, None] * brightness * 0.25

    # --- very subtle warm/cool colour overlay to unify the image ---
    warm = hexc("#ffaa44") * 0.04
    cool = hexc("#4488ff") * 0.03
    tone = warm * (1 - v[:, :, None]) + cool * v[:, :, None]
    if mode == "light":
        tone *= 0.5
    col += tone

    # --- vignette ---
    vig_u = np.linspace(0, 1, W, dtype=F32)[None, :]
    vig_v = np.linspace(0, 1, H, dtype=F32)[:, None]
    vig = (vig_u - 0.5) ** 2 + (vig_v - 0.5) ** 2
    if mode == "dark":
        col *= (1 - vig[:, :, None] * vign_strength)
    else:
        col *= (1 - vig[:, :, None] * vign_strength * 0.5)

    # --- film grain ---
    noise = rng.normal(0, 1.2 / 255, col.shape).astype(F32)
    if mode == "light":
        noise *= 0.6
    col += noise

    return Image.fromarray((np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=8, help="reproducible random state")
    ap.add_argument("--palette", choices=list(PALETTES), default="tokyo",
                    help="city colour mood")
    ap.add_argument("--count", type=int, default=1, help="generate N images (seeds seed..seed+count-1)")
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--ss", type=int, default=2, help="supersampling antialiasing factor")
    ap.add_argument("--fast", action="store_true", help="960x600 preview without supersampling")
    ap.add_argument("--focus", choices=["auto", "center", "full"], default="auto",
                    help="where to lay out the composition (see README)")
    ap.add_argument("--targets", help=f"screen aspect ratios the image must work on, e.g. '{DEFAULT_TARGETS}'")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()

    if a.size:
        a.width, a.height = SIZES[a.size]
        if "--ss" not in sys.argv and a.width * a.height > 9_000_000:
            a.ss = 1
    tag = "-fast" if a.fast else ""
    if a.fast:
        k = 960 / max(a.width, a.height) if a.size else 0
        a.width, a.height, a.ss = (round(a.width * k), round(a.height * k), 1) if k else (960, 600, 1)

    meta = np.random.default_rng()
    for i in range(a.count):
        seed = a.seed + i if a.seed is not None else int(meta.integers(0, 100000))
        palette = a.palette
        print(f"[{i + 1}/{a.count}] palette={palette} seed={seed}")
        for m in (["light", "dark"] if a.mode == "both" else [a.mode]):
            out = os.path.join(a.out, f"neon-{palette}-{seed}-{a.width}x{a.height}-{m}{tag}.png")
            img = render(m, a.width * a.ss, a.height * a.ss, seed, palette)
            if a.ss > 1:
                img = img.resize((a.width, a.height), Image.LANCZOS)
            img.save(out, optimize=True)
            print("  ->", out)


if __name__ == "__main__":
    main()
