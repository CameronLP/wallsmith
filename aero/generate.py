# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Abstract Frutiger Aero-style wallpaper: glass ribbons + light streaks. Light & dark.

  uv run generate.py                         # seed 7, 3840x2400, light + dark
  uv run generate.py --seed 42
  uv run generate.py --width 4096 --height 4096 --focus center
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


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], F32)


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def screen(base, col, a):
    return base + (1 - base) * col * a[..., None]


def over(base, col, a):
    return base * (1 - a[..., None]) + col * a[..., None]


def wave(x, amp, freq, phase, base, wob=0.0):
    return base + amp * np.sin(x * freq + phase) + wob * np.sin(x * freq * 2.7 + phase * 1.3)


REF = 2400.0  # pixel widths below were tuned for a 2400 px tall design


class Canvas:
    def __init__(self, W, H, rect):
        ox, oy, dw, dh = rect
        yy, xx = np.mgrid[0:H, 0:W].astype(F32)
        self.W, self.H, self.dh = W, H, dh
        self.u = (xx - ox) / dw      # 0..1 across the design area (extends beyond it)
        self.v = (yy - oy) / dh
        self.asp = dw / dh


def sheet(cv, img, top, bot, col, alpha, edge_glow):
    """Translucent glass sheet between two curves, with glossy edges."""
    v = cv.v
    thick = np.maximum(bot - top, 1e-3)
    t = np.maximum((v - top) / thick, 0)   # clamp: avoids exp overflow far outside the design area
    inside = np.clip(np.minimum(v - top, bot - v) * cv.dh / 2.0, 0, 1)
    body = inside * (0.35 + 0.65 * np.exp(-t * 2.5)) * alpha
    img = over(img, col, body)
    sheen = np.exp(-(((v - top) * REF) / 22) ** 2) + 0.5 * np.exp(-(((v - top) * REF - 60) / 50) ** 2)
    img = screen(img, np.ones(3, F32), sheen * edge_glow)
    low = np.exp(-(((v - bot) * REF) / 6) ** 2)
    img = screen(img, np.ones(3, F32), low * edge_glow * 0.45)
    return img


def streak(cv, img, curve, width_px, col, a):
    d = (cv.v - curve) * REF / width_px
    core = np.exp(-d ** 2)
    halo = np.exp(-(d / 8) ** 2) * 0.25
    taper = np.clip(np.sin(np.pi * np.clip(cv.u * 1.05, 0, 1)) * 1.4, 0, 1)
    return screen(img, col, (core + halo) * a * taper)


PALETTES = {
    "light": dict(
        bg=["#0a6fd1", "#3fb4ef", "#bdeeff", "#f2fdff"],
        glow="#ffffff", glow_a=0.75,
        sheets=["#ffffff", "#6fe6d0", "#9fe0ff", "#c9ff9e"],
        sheet_a=0.32, edge=0.55, streak="#ffffff", streak_a=0.8, vig=0.10,
    ),
    "dark": dict(
        bg=["#010613", "#03214a", "#055c7f", "#0a8f8a"],
        glow="#5fd6ff", glow_a=0.45,
        sheets=["#3fd2ff", "#1fd6a0", "#2f6bff", "#7cf2c8"],
        sheet_a=0.26, edge=0.40, streak="#bff4ff", streak_a=0.65, vig=0.35,
    ),
}


def render(mode, cv, seed):
    p = PALETTES[mode]
    rng = np.random.default_rng(seed)
    u, v = cv.u, cv.v
    c = [hex2rgb(h) for h in p["bg"]]

    # diagonal multi-stop gradient
    t = np.clip(v * 0.8 + u * 0.25 - 0.05, 0, 1)
    stops = [0.0, 0.4, 0.75, 1.0]
    img = np.zeros((cv.H, cv.W, 3), F32)
    for i in range(3):
        a, b = stops[i], stops[i + 1]
        m = (t >= a) & (t <= b)
        img[m] = lerp(c[i], c[i + 1], (t[m] - a) / (b - a))

    # soft radial glow where ribbons converge
    gd = np.sqrt(((u - 0.68) * cv.asp) ** 2 + ((v - 0.48) * 1.6) ** 2)
    img = screen(img, hex2rgb(p["glow"]), np.exp(-gd ** 2 * 3.5) * p["glow_a"])

    # glass sheets, back to front
    cols = [hex2rgb(h) for h in p["sheets"]]
    layers = [
        # (top amp,freq,phase,base,wob) , thickness amp/base
        ((0.20, 2.2, 0.4, 0.42, 0.03), (0.10, 1.7, 1.9, 0.30)),
        ((0.24, 2.5, -0.2, 0.52, 0.02), (0.06, 2.9, 0.4, 0.18)),
        ((0.18, 1.9, 0.9, 0.60, 0.04), (0.05, 2.2, 2.6, 0.12)),
        ((0.22, 2.7, 0.1, 0.66, 0.02), (0.04, 3.4, 1.1, 0.07)),
    ]
    for (top_p, thick_p), col in zip(layers, cols):
        ta, tf, tp, tb, tw = top_p
        ka, kf, kp, kb = thick_p
        top = wave(u, -ta, tf, tp, tb, tw)
        bot = top + np.maximum(wave(u, ka, kf, kp, kb), 0.02)
        img = sheet(cv, img, top, bot, col, p["sheet_a"], p["edge"])

    # fine light streaks weaving through
    sc = hex2rgb(p["streak"])
    for _ in range(7):
        amp = rng.uniform(0.15, 0.27)
        freq = rng.uniform(1.8, 2.9)
        ph = rng.uniform(-0.4, 1.0)
        base = rng.uniform(0.45, 0.72)
        img = streak(cv, img, wave(u, -amp, freq, ph, base, 0.02), rng.uniform(2.0, 5.0), sc,
                     p["streak_a"] * rng.uniform(0.4, 1.0))

    # vignette (over the full canvas) + dither
    uu = np.linspace(0, 1, cv.W, dtype=F32)[None, :]
    vv = np.linspace(0, 1, cv.H, dtype=F32)[:, None]
    vig = (uu - 0.5) ** 2 + (vv - 0.5) ** 2
    img *= (1 - vig * p["vig"])[..., None]
    img += rng.normal(0, 1.2 / 255, img.shape).astype(F32)
    return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7, help="changes the thin light streaks")
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--width", type=int, default=3840)
    ap.add_argument("--height", type=int, default=2400)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--focus", choices=["auto", "center", "full"], default="auto",
                    help="where to lay out the composition (see README)")
    ap.add_argument("--targets", help=f"screen aspect ratios the image must work on, e.g. '{DEFAULT_TARGETS}' "
                                      "or '3840x2160,2160x3840,3440x1440'")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    if a.size:
        a.width, a.height = SIZES[a.size]
        if hasattr(a, "ss") and "--ss" not in sys.argv and a.width * a.height > 9_000_000:
            a.ss = 1                     # big presets: supersampling would be slow and memory-hungry
    rect = focus_rect(a.width, a.height, a.focus, a.targets)
    if rect[2:] != (a.width, a.height):
        print(f"design area: {rect[2]}x{rect[3]} centred in {a.width}x{a.height}")
    cv = Canvas(a.width, a.height, rect)
    for mode in (["light", "dark"] if a.mode == "both" else [a.mode]):
        out = os.path.join(a.out, f"aero-{a.seed}-{a.width}x{a.height}-{mode}.png")
        render(mode, cv, a.seed).save(out, optimize=True)
        print("  ->", out)


if __name__ == "__main__":
    main()
