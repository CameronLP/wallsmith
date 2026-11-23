# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""GNOME-style wallpapers: flat layered vector shapes with soft shadows, light + dark.

Uses the GNOME (Adwaita) colour palette. Shapes are signed-distance fields, so edges are
crisp and shadows are soft at any resolution. Light and dark share the same composition.

  uv run gnome.py                               # random motif + palette, light + dark
  uv run gnome.py --motif waves --palette blue --seed 3
  uv run gnome.py --fast --count 12             # quick previews of random designs
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


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# GNOME HIG palette, 5 shades each (light -> dark)
PALETTES = {
    "blue":   ["#99c1f1", "#62a0ea", "#3584e4", "#1c71d8", "#1a5fb4"],
    "green":  ["#8ff0a4", "#57e389", "#33d17a", "#2ec27e", "#26a269"],
    "yellow": ["#f9f06b", "#f8e45c", "#f6d32d", "#f5c211", "#e5a50a"],
    "orange": ["#ffbe6f", "#ffa348", "#ff7800", "#e66100", "#c64600"],
    "red":    ["#f66151", "#ed333b", "#e01b24", "#c01c28", "#a51d2d"],
    "purple": ["#dc8add", "#c061cb", "#9141ac", "#813d9c", "#613583"],
    "brown":  ["#cdab8f", "#b5835a", "#986a44", "#865e3c", "#63452c"],
    "slate":  ["#deddda", "#c0bfbc", "#9a9996", "#77767b", "#5e5c64"],
}
MOTIFS = ["waves", "blobs", "pills", "rings", "folds", "dots"]


def shade(pal, t):
    """Continuous position along a 5-shade ramp, t in [0, 1]."""
    cols = np.array([hexc(c) for c in pal])
    x = np.linspace(0, 1, len(cols))
    return np.array([np.interp(t, x, cols[:, c]) for c in range(3)], F32)


# ---------------------------------------------------------------- shapes (SDFs)
# each motif returns a list of sdf(X, Y) functions, back to front; negative = inside

def m_waves(rng, asp):
    n = int(rng.integers(4, 7))
    out = []
    for k in range(n):
        base = 0.22 + 0.68 * k / n + rng.uniform(-0.03, 0.03)
        A, f, p = rng.uniform(0.03, 0.09), rng.uniform(1.2, 3.2), rng.uniform(0, 6)
        A2, f2, p2 = A * rng.uniform(0.2, 0.5), f * rng.uniform(1.8, 2.6), rng.uniform(0, 6)
        tilt = rng.uniform(-0.12, 0.12)

        def sdf(X, Y, base=base, A=A, f=f, p=p, A2=A2, f2=f2, p2=p2, tilt=tilt):
            y = base + tilt * (X - asp / 2) + A * np.sin(f * X + p) + A2 * np.sin(f2 * X + p2)
            slope = A * f * np.cos(f * X + p) + A2 * f2 * np.cos(f2 * X + p2) + tilt
            return (y - Y) / np.sqrt(1 + slope ** 2)
        out.append(sdf)
    return out


def m_blobs(rng, asp):
    out = []
    for k in range(int(rng.integers(5, 9))):
        cx, cy = rng.uniform(-0.1, asp + 0.1), rng.uniform(-0.1, 1.1)
        R = rng.uniform(0.14, 0.42)
        a1, p1, a2, p2 = rng.uniform(0.05, 0.16), rng.uniform(0, 6), rng.uniform(0.03, 0.08), rng.uniform(0, 6)

        def sdf(X, Y, cx=cx, cy=cy, R=R, a1=a1, p1=p1, a2=a2, p2=p2):
            dx, dy = X - cx, Y - cy
            th = np.arctan2(dy, dx)
            r = R * (1 + a1 * np.sin(2 * th + p1) + a2 * np.sin(3 * th + p2))
            return np.hypot(dx, dy) - r
        out.append(sdf)
    return out


def m_pills(rng, asp):
    ang = rng.choice([np.pi / 4, -np.pi / 4, np.pi / 6, -np.pi / 6, np.pi / 3])
    d = np.array([np.cos(ang), np.sin(ang)])
    out = []
    for k in range(int(rng.integers(7, 13))):
        c = np.array([rng.uniform(-0.1, asp + 0.1), rng.uniform(-0.1, 1.1)])
        L, r = rng.uniform(0.15, 0.5), rng.uniform(0.035, 0.11)
        a, b = c - d * L / 2, c + d * L / 2

        def sdf(X, Y, a=a, b=b, r=r):
            ba = b - a
            t = np.clip(((X - a[0]) * ba[0] + (Y - a[1]) * ba[1]) / (ba @ ba), 0, 1)
            return np.hypot(X - a[0] - ba[0] * t, Y - a[1] - ba[1] * t) - r
        out.append(sdf)
    return out


def m_rings(rng, asp):
    corner = rng.integers(4)
    cx = [-0.1, asp + 0.1][corner % 2] + rng.uniform(-0.15, 0.15)
    cy = [-0.1, 1.1][corner // 2] + rng.uniform(-0.15, 0.15)
    n = int(rng.integers(5, 9))
    radii = np.sort(rng.uniform(0.15, 1.0, n))[::-1] * np.linspace(1.6, 1.0, n)
    out = []
    for r in np.sort(radii)[::-1]:        # biggest first (back)
        out.append(lambda X, Y, r=r: np.hypot(X - cx, Y - cy) - r)
    return out


def m_folds(rng, asp):
    base = rng.uniform(0, 2 * np.pi)
    n = int(rng.integers(4, 7))
    out = []
    for k in range(n):
        a = base + rng.uniform(-0.25, 0.25)
        nx, ny = np.cos(a), np.sin(a)
        # project the screen centre and spread the fold lines across the screen
        c0 = nx * asp / 2 + ny * 0.5
        off = c0 + (k - n / 2 + 0.5) * rng.uniform(0.12, 0.22)
        out.append(lambda X, Y, nx=nx, ny=ny, off=off: off - (X * nx + Y * ny))
    return out


def m_dots(rng, asp):
    out = []
    # a loose diagonal cluster of circles of varying size
    a = rng.uniform(0, np.pi)
    for k in range(int(rng.integers(10, 18))):
        t = rng.uniform(-0.7, 0.7)
        cx = asp / 2 + t * np.cos(a) * asp + rng.normal(0, 0.12)
        cy = 0.5 + t * np.sin(a) + rng.normal(0, 0.12)
        r = rng.uniform(0.03, 0.17) * (1.2 - abs(t))
        out.append(lambda X, Y, cx=cx, cy=cy, r=r: np.hypot(X - cx, Y - cy) - r)
    rng.shuffle(out)
    return out


MOTIF_FN = dict(waves=m_waves, blobs=m_blobs, pills=m_pills, rings=m_rings, folds=m_folds, dots=m_dots)


# ---------------------------------------------------------------- render
def render(mode, motif, pal_name, W, H, seed, rect=None):
    rng = np.random.default_rng(seed)
    ox, oy, dw, dh = rect or (0, 0, W, H)   # design area inside the canvas
    asp = dw / dh
    pal = PALETTES[pal_name]
    shapes = MOTIF_FN[motif](rng, asp)
    px = 1.0 / dh
    Y, X = np.mgrid[0:H, 0:W].astype(F32)
    X, Y = (X - ox + 0.5) * px, (Y - oy + 0.5) * px

    n = len(shapes)
    if mode == "light":
        bg = 0.55 * hexc("#ffffff") + 0.45 * shade(pal, 0.0)
        ts = np.linspace(0.0, 0.85, n)
        cols = [shade(pal, t) for t in ts]
        sh_col, sh_a = shade(pal, 1.0) * 0.35, 0.28
    else:
        bg = 0.6 * hexc("#1e1e1e") + 0.4 * shade(pal, 1.0) * 0.6
        ts = np.linspace(1.0, 0.35, n)
        dims = np.linspace(0.45, 0.85, n)
        cols = [shade(pal, t) * d + hexc("#1e1e1e") * (1 - d) * 0.5 for t, d in zip(ts, dims)]
        sh_col, sh_a = np.zeros(3, F32), 0.45
    if motif in ("pills", "dots", "blobs"):
        order = rng.permutation(n)       # scattered shapes: mix shades rather than a ramp
        cols = [cols[i] for i in order]

    img = np.broadcast_to(bg, (H, W, 3)).astype(F32).copy()
    # subtle background light from top-left
    img *= (1.04 - 0.08 * ((X / asp) * 0.5 + Y * 0.5))[..., None]

    soft = 0.035                          # shadow softness (screen-height units)
    off = np.array([0.006, 0.012], F32)   # light from above
    for sdf, col in zip(shapes, cols):
        d_sh = sdf(X - off[0], Y - off[1])
        a = (1 - smooth(-soft * 0.3, soft, d_sh)) * sh_a
        img = img * (1 - a[..., None]) + sh_col * a[..., None]
        d = sdf(X, Y)
        fill = np.clip(0.5 - d / px, 0, 1)
        # gentle in-shape gradient so flat colours don't look dead
        g = (1.03 - 0.06 * Y)[..., None]
        img = img * (1 - fill[..., None]) + (col * g) * fill[..., None]
    img += rng.normal(0, 0.7 / 255, img.shape).astype(F32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--motif", choices=MOTIFS, help="default: random")
    ap.add_argument("--palette", choices=list(PALETTES), help="default: random")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--ss", type=int, default=2, help="supersampling factor")
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
    tag = "-fast" if a.fast else ""
    if a.fast:
        k = 960 / max(a.width, a.height) if a.size else 0   # previews keep the preset's shape
        a.width, a.height, a.ss = (round(a.width * k), round(a.height * k), 1) if k else (960, 600, 1)
    for i in range(a.count):
        seed = a.seed + i if a.seed is not None else int(np.random.default_rng().integers(0, 100000))
        r = np.random.default_rng(seed + 7919)
        motif = a.motif or MOTIFS[r.integers(len(MOTIFS))]
        pal = a.palette or list(PALETTES)[r.integers(len(PALETTES))]
        print(f"[{i + 1}/{a.count}] motif={motif} palette={pal} seed={seed}")
        for m in (["light", "dark"] if a.mode == "both" else [a.mode]):
            im = Image.fromarray(render(m, motif, pal, a.width * a.ss, a.height * a.ss, seed,
                                         focus_rect(a.width * a.ss, a.height * a.ss, a.focus, a.targets)), "RGB")
            if a.ss > 1:
                im = im.resize((a.width, a.height), Image.LANCZOS)
            p = os.path.join(a.out, f"gnome-{motif}-{pal}-{seed}-{m}{tag}.png")
            im.save(p, optimize=True)
            print("  ->", p)


if __name__ == "__main__":
    main()
