# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Realistic aurora wallpapers (volumetric), light + dark.

The aurora is a 3D volume: curtains are defined as a pattern on the ground plane and
extruded upward through stacked atmosphere layers. Each pixel's view ray is intersected
with every layer, which gives proper perspective, rays converging overhead, a sharp
bright lower edge and colour changing with altitude.

  uv run aurora.py                          # random seed, horizon view, light + dark
  uv run aurora.py --view overhead --palette violet --seed 3
  uv run aurora.py --view treeline
  uv run aurora.py --fast --count 8         # quick previews
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


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# colour by altitude inside the aurora: 0 = lower edge, 1 = top
PALETTES = {
    "classic": [(0, "#d8ffe6"), (0.05, "#5dff9a"), (0.3, "#1fd98a"), (0.55, "#17a98a"),
                (0.78, "#6a3fc8"), (1, "#c0306a")],
    "violet":  [(0, "#ffe0f4"), (0.05, "#ff7ad0"), (0.35, "#c04aff"), (0.7, "#6a3aff"), (1, "#2a1a9a")],
    "teal":    [(0, "#e0fffb"), (0.05, "#5ff8e8"), (0.35, "#22c8e0"), (0.7, "#2a6aff"), (1, "#3a2aa0")],
    "fire":    [(0, "#fff2c8"), (0.05, "#ffb04a"), (0.35, "#ff5a3a"), (0.7, "#c02a6a"), (1, "#5a1a6a")],
}

SKY = {
    "dark": dict(zenith="#010208", horizon="#0a1824", land="#010204", water="#01040a"),
    # "light" = blue hour: clearly brighter than night, but not washed out
    "light": dict(zenith="#1e3266", horizon="#d49aa8", land="#141a2c", water="#0e1830"),
}


class Noise1D:
    def __init__(self, rng, size=1 << 16):
        self.t = rng.random(size).astype(F32)
        self.n = size
        self.off = rng.uniform(0, size)

    def __call__(self, x):
        x = x + self.off
        i = np.floor(x)
        f = (x - i).astype(F32)
        f = f * f * (3 - 2 * f)
        i = i.astype(np.int64) % self.n
        return self.t[i] * (1 - f) + self.t[(i + 1) % self.n] * f

    def fbm(self, x, freq, octaves, gain=0.5):
        tot, amp, norm = 0.0, 1.0, 0.0
        for o in range(octaves):
            tot = tot + self(x * freq * 2 ** o + 911.0 * o) * amp
            norm += amp
            amp *= gain
        return tot / norm


class Grid:
    """Bilinear lookup into a periodic grid covering [x0, x0+size] x [z0, z0+size]."""

    def __init__(self, g, size, x0, z0):
        self.g, self.n = g.astype(F32), g.shape[0]
        self.s, self.x0, self.z0 = g.shape[0] / size, x0, z0

    def __call__(self, x, z):
        gx, gz = (x - self.x0) * self.s, (z - self.z0) * self.s
        ix, iz = np.floor(gx), np.floor(gz)
        fx, fz = (gx - ix).astype(F32), (gz - iz).astype(F32)
        n, g = self.n, self.g
        ix, iz = ix.astype(np.int64) % n, iz.astype(np.int64) % n
        jx, jz = (ix + 1) % n, (iz + 1) % n
        return ((g[iz, ix] * (1 - fx) + g[iz, jx] * fx) * (1 - fz)
                + (g[jz, ix] * (1 - fx) + g[jz, jx] * fx) * fz)


def box_blur(a, r):
    out = a.astype(np.float64)
    for axis in (0, 1):
        for _ in range(3):
            pad = [(r + 1, r) if k == axis else (0, 0) for k in range(out.ndim)]
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
            n = out.shape[axis]
            out = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis) - np.take(c, np.arange(n), axis)) / (2 * r + 1)
    return out.astype(F32)


def bloom(img, k=4, r=12):
    H, W, _ = img.shape
    h, w = H // k, W // k
    small = box_blur(img[:h * k, :w * k].reshape(h, k, w, k, 3).mean((1, 3)), r)
    out = np.zeros_like(img)
    for c in range(3):
        out[..., c] = np.asarray(Image.fromarray(small[..., c], "F").resize((W, H), Image.BILINEAR))
    return out


class Aurora:
    SIZE = 200.0

    def __init__(self, rng, pal, view="horizon"):
        self.view = view
        # looking straight up passes through far less aurora than looking at the horizon
        self.gain = 4.0 if view == "overhead" else 1.0
        stops = PALETTES[pal]
        self.xs = [s[0] for s in stops]
        self.cols = np.array([hexc(s[1]) for s in stops])
        self.nz = Noise1D(rng)
        self.rays = Noise1D(rng)
        self.ray_f = 14.0 if view == "overhead" else 3.0   # finer rays when right underneath
        self._build(rng, 2048 if view == "overhead" else 1400)
        self.layers = 56
        self.y0, self.y1 = 1.0, 4.2
        self.drift = rng.uniform(-0.012, 0.012)  # rays lean slightly as they rise

    def _build(self, rng, n=1400):
        ov = self.view == "overhead"
        S = 40.0 if ov else self.SIZE      # overhead needs a finer, local pattern
        x = np.linspace(-S / 2, S / 2, n, endpoint=False, dtype=F32)[None, :]
        z = np.linspace(-S / 2, S / 2, n, endpoint=False, dtype=F32)[:, None]
        P = np.zeros((n, n), F32)
        nz = self.nz
        for k in range(int(rng.integers(4, 7) if ov else rng.integers(3, 6))):
            # overhead: curtains pass right above the viewer; otherwise they sit out in front
            zc0 = rng.uniform(-1.2, 1.2) if ov else rng.uniform(2.0, 14.0)
            amp = rng.uniform(0.3, 0.9) if ov else rng.uniform(1.5, 4.0) * (0.5 + zc0 / 10)
            f = rng.uniform(0.15, 0.35) if ov else rng.uniform(0.04, 0.09)
            # each curtain runs at its own angle, so it recedes into the distance in perspective
            th = rng.uniform(-0.7, 0.7)
            cu, su = np.cos(th), np.sin(th)
            u = x * cu + z * su          # along the curtain
            wv = -x * su + z * cu        # across the curtain
            zc = zc0 * cu + amp * (nz.fbm(u + 1000 * k, f, 4) * 2 - 1)
            # small tight folds on top of the big swings
            zc = zc + rng.uniform(0.3, 1.2) * np.sin(u * rng.uniform(0.25, 0.6) + rng.uniform(0, 6))
            w = rng.uniform(0.04, 0.1) if ov else rng.uniform(0.15, 0.45)
            d = wv - zc
            prof = np.exp(-(d / w) ** 2) + 0.2 * np.exp(-(d / (w * 4)) ** 2)  # core + diffuse halo
            along = smooth(0.25, 0.7, nz.fbm(u + 3000 * k, rng.uniform(0.01, 0.03), 3))
            P += prof * along * rng.uniform(0.5, 1.0)
        self.P = Grid(P, S, -S / 2, -S / 2)

    def ramp(self, t):
        return np.array([np.interp(t, self.xs, self.cols[:, c]) for c in range(3)], F32)

    def trace(self, rd):
        """Accumulated aurora light along view rays (only rays pointing up)."""
        acc = np.zeros((len(rd), 3), F32)
        upm = rd[:, 1] > 0.004
        if not upm.any():
            return acc
        r = rd[upm]
        ry = r[:, 1]
        a = np.zeros((len(r), 3), F32)
        L = self.layers
        hs = self.y0 + (self.y1 - self.y0) * (np.arange(L + 1, dtype=F32) / L) ** 1.35
        for i in range(L):
            y, dy = hs[i], hs[i + 1] - hs[i]
            t = y / ry
            px, pz = r[:, 0] * t, r[:, 2] * t
            dens = self.P(px, pz)
            ray = self.rays.fbm(px + 0.35 * pz + i * self.drift * 40, self.ray_f, 3, 0.6)
            detail = np.exp(-t / 14.0)          # fade fine rays with distance (no moire)
            ray = 0.5 + (ray - 0.5) * detail
            dens = dens * (0.25 + 0.75 * smooth(0.2, 0.85, ray) ** 1.6)
            h = i / (L - 1)
            wgt = (1.6 if i < 2 else 1.0) * np.exp(-h * 2.0)   # bright lower boundary
            path = np.minimum(dy / ry, 0.9)                     # optical path through slab
            fade = np.exp(-t / 40.0)                            # distance haze
            a += self.ramp(h)[None, :] * (dens * wgt * path * fade * 0.95 * self.gain)[:, None]
        acc[upm] = a
        return acc


def stars(W, H, rng, horizon_row):
    s = np.zeros((H, W), F32)
    n = W * H // 1600
    xs = rng.integers(1, W - 1, n)
    ys = rng.integers(1, max(horizon_row - 1, 2), n)
    br = (rng.random(n) ** 7 * 1.6 + 0.08).astype(F32)
    br *= smooth(0.0, 0.3, 1 - ys / max(horizon_row, 1)).astype(F32)
    np.add.at(s, (ys, xs), br)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        np.add.at(s, (ys + dy, xs + dx), br * 0.25)
    return s


def render(mode, pal, view, W, H, seed, rows=64, rect=None):
    ox, oy, dw, dh = rect or (0, 0, W, H)   # framing is designed for this area
    rng = np.random.default_rng(seed)       # same seed -> same aurora in both modes
    au = Aurora(rng, pal, view)
    sk = {k: hexc(v) for k, v in SKY[mode].items()}
    land_nz = Noise1D(rng)
    ripple = Noise1D(rng)
    yaw = rng.uniform(-0.3, 0.3)
    pitch = {"horizon": 0.22, "treeline": 0.36, "overhead": 1.42}[view]
    tan = np.tan(np.radians(72) / 2)
    fwd = np.array([np.sin(yaw) * np.cos(pitch), np.sin(pitch), np.cos(yaw) * np.cos(pitch)], F32)
    right = np.array([np.cos(yaw), 0, -np.sin(yaw)], F32)
    up = np.cross(fwd, right).astype(F32)

    aur = np.zeros((H, W, 3), F32)
    sky = np.zeros((H, W, 3), F32)
    below = np.zeros((H, W), bool)
    xs = ((np.arange(W, dtype=F32) + 0.5 - ox) / dw * 2 - 1) * tan
    t0 = time.time()
    for y0 in range(0, H, rows):
        y1 = min(y0 + rows, H)
        ys = (1 - (np.arange(y0, y1, dtype=F32) + 0.5 - oy) / dh * 2) * tan * dh / dw
        px, py = np.meshgrid(xs, ys)
        rd = fwd + px[..., None] * right + py[..., None] * up
        rd = (rd / np.linalg.norm(rd, axis=-1, keepdims=True)).reshape(-1, 3).astype(F32)
        bl = rd[:, 1] < 0
        if bl.any():  # water: mirror the ray, with gentle horizontal ripples
            rr = rd[bl].copy()
            rr[:, 1] = -rr[:, 1]
            row = np.repeat(np.arange(y0, y1), W)[bl].astype(F32)
            closeness = np.clip(rr[:, 1] * 10, 0, 1)
            rr[:, 0] += (ripple.fbm(row * 0.7, 1.0, 3) - 0.5) * 0.02 * (0.2 + closeness)
            rr[:, 1] = np.abs(rr[:, 1] + (ripple.fbm(row * 0.31 + 50, 1.0, 2) - 0.5) * 0.004 * closeness)
            rd[bl] = rr / np.linalg.norm(rr, axis=-1, keepdims=True)
        a = au.trace(rd)
        yy = np.clip(rd[:, 1], 0, 1)
        s = sk["horizon"] + (sk["zenith"] - sk["horizon"]) * (yy ** 0.5)[:, None]
        # distant low treeline / hills on the horizon
        az = np.arctan2(rd[:, 0], rd[:, 2])
        land_h = 0.006 + 0.022 * land_nz.fbm(az, 9.0, 5, 0.55) ** 1.5
        land = smooth(land_h + 0.0015, land_h - 0.0015, rd[:, 1])
        s = s * (1 - land[:, None]) + sk["land"] * land[:, None]
        a = a * (1 - land[:, None])
        aur[y0:y1] = a.reshape(y1 - y0, W, 3)
        sky[y0:y1] = s.reshape(y1 - y0, W, 3)
        below[y0:y1] = bl.reshape(y1 - y0, W)
        print(f"\r  {mode}: {y1 * 100 // H:3d}%  {time.time() - t0:4.0f}s", end="", flush=True)
    print()

    horizon_row = int(np.argmax(below.any(1))) if below.any() else H
    bl3 = below[..., None]
    star_k = 1.0 if mode == "dark" else 0.25
    sky = sky + stars(W, H, rng, horizon_row)[..., None] * np.array([0.85, 0.92, 1.0], F32) * star_k
    light = aur + bloom(aur, 4, max(4, W // 160)) * 0.55
    if mode == "dark":
        img = 1 - np.exp(-(sky + light) * 1.25)      # filmic roll-off keeps highlights soft
    else:
        # sky is already in display range; add aurora as light with a softer roll-off
        img = 1 - (1 - sky) * np.exp(-light * 1.1)
    img = np.where(bl3, img * 0.6 + sk["water"], img)
    img = img + rng.normal(0, 1.4 / 255, img.shape).astype(F32)   # photo-like grain
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--palette", choices=list(PALETTES), default="classic")
    ap.add_argument("--view", choices=["horizon", "treeline", "overhead"], default="horizon",
                    help="horizon = lake with reflection, treeline = looking up over a strip of land, "
                         "overhead = looking straight up")
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--ss", type=int, default=1, help="supersampling (aurora is soft; 1 is usually fine)")
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
        print(f"[{i + 1}/{a.count}] palette={a.palette} view={a.view} seed={seed}")
        for m in (["light", "dark"] if a.mode == "both" else [a.mode]):
            px = render(m, a.palette, a.view, a.width * a.ss, a.height * a.ss, seed,
                        rect=focus_rect(a.width * a.ss, a.height * a.ss, a.focus, a.targets))
            im = Image.fromarray(px, "RGB")
            if a.ss > 1:
                im = im.resize((a.width, a.height), Image.LANCZOS)
            p = os.path.join(a.out, f"aurora-{a.palette}-{a.view}-{seed}-{m}{tag}.png")
            im.save(p, optimize=True)
            print("  ->", p)


if __name__ == "__main__":
    main()
