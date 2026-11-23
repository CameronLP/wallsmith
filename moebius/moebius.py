# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Möbius strip wallpapers: a twisting single-sided ribbon in 3D space.

Ray-marched using a signed-distance field for crisp geometry at any resolution.
Color bands wrap continuously around the strip, passing through the half-twist
to reveal the single-sided surface.  Clean, graphic shading with warm sun-bleached
palettes.

  uv run moebius.py                     # random seed, light + dark
  uv run moebius.py --seed 7 --palette desert --mode dark
  uv run moebius.py --fast --count 8    # quick previews
"""
import argparse
import sys
import os

import numpy as np
from PIL import Image

F32 = np.float32
DEFAULT_TARGETS = "16:9,9:16,21:9"

SIZES = {
    "gnome": (4096, 4096),
    "gnome-5k": (5120, 5120),
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
    asp = W / H
    if focus == "full":
        return 0, 0, W, H
    if targets is None:
        if focus == "auto" and not (0.8 < asp < 1.25):
            return 0, 0, W, H
    sw, sh = float(W), float(H)
    for a in parse_targets(targets or DEFAULT_TARGETS):
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


# ---------------------------------------------------------------- palettes
PALETTES = {
    "desert": dict(
        dark_bg=("#0a0608", "#1a1210"), light_bg=("#f5ebe0", "#e8ddd0"),
        bands=["#c4762a", "#d98a3a", "#b8601a", "#e8a860", "#f5d0a0"],
        accent="#6a8aaa", spec=0.5,
    ),
    "alien": dict(
        dark_bg=("#060a10", "#0e1828"), light_bg=("#e8f0f5", "#d8e4ee"),
        bands=["#5a9a8a", "#7ab8a8", "#4a7a7a", "#9ad8c8", "#b8f0e0"],
        accent="#b87090", spec=0.45,
    ),
    "dune": dict(
        dark_bg=("#0c0806", "#1e1410"), light_bg=("#f2e8d8", "#e8dcc8"),
        bands=["#c85030", "#e07040", "#b04020", "#d89060", "#f0c0a0"],
        accent="#5070a0", spec=0.4,
    ),
    "space": dict(
        dark_bg=("#050208", "#0e0a18"), light_bg=("#e8e2f0", "#dbd4e8"),
        bands=["#a080c0", "#c0a0e0", "#9070b0", "#d0b0f0", "#e8d8f8"],
        accent="#7090b0", spec=0.6,
    ),
    "ochre": dict(
        dark_bg=("#0c0a04", "#1e1a0a"), light_bg=("#f5f0e0", "#ebe5d4"),
        bands=["#c4a020", "#d8b840", "#b08810", "#e8cc70", "#f8e8b0"],
        accent="#608888", spec=0.45,
    ),
}


# ---------------------------------------------------------------- SDF
def moebius_sdf(p, R, w):
    """
    Approximate SDF for a Möbius strip parameterised by
      ρ = R + v·cos(u/2) ,  z = v·sin(u/2) ,  u∈[0,2π] , v∈[-w,w]
    Returns the exact distance to the 1-D strip profile at the angular
    slice u = atan2(y,x).  For thin strips (w ≪ R) this is an excellent
    bound; we step conservatively to stay safe everywhere.
    """
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    r = np.sqrt(x * x + y * y)
    a = np.arctan2(y, x)
    a2 = a * 0.5
    ca2, sa2 = np.cos(a2), np.sin(a2)
    dr = r - R
    v0 = ca2 * dr + sa2 * z          # unconstrained closest v
    vc = np.clip(v0, -w, w)
    dx = dr - ca2 * vc
    dz = z - sa2 * vc
    return np.sqrt(dx * dx + dz * dz)


def scene_sdf(p, R, w):
    return moebius_sdf(p, R, w)


def surface_uvn(p_hit, R, w):
    """For hit points, return (u_norm, v_norm, normal_vector) all as (N,...) arrays."""
    x, y, z = p_hit[..., 0], p_hit[..., 1], p_hit[..., 2]
    r = np.sqrt(x * x + y * y)
    a = np.arctan2(y, x)
    a2 = a * 0.5
    ca2, sa2 = np.cos(a2), np.sin(a2)
    dr = r - R
    v0 = ca2 * dr + sa2 * z
    vc = np.clip(v0, -w, w)
    u = np.mod(a, 2 * np.pi) / (2 * np.pi)
    v = vc / w

    # Normal via finite differences of the SDF
    eps = 0.001
    n = np.empty_like(p_hit)
    for axis in range(3):
        dp = np.zeros(3, F32)
        dp[axis] = eps
        plus = p_hit + dp
        minus = p_hit - dp
        n[..., axis] = scene_sdf(plus, R, w) - scene_sdf(minus, R, w)
    nlen = np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
    n = n / nlen
    return u, v, n


def make_band_lut(bands, n=512):
    cols = np.array([hexc(c) for c in bands], F32)
    t = np.linspace(0, 1, n, endpoint=False)
    idx = np.floor(t * len(cols)).astype(int) % len(cols)
    idx2 = (idx + 1) % len(cols)
    frac = (t * len(cols)) % 1.0
    return cols[idx] * (1 - frac[:, None]) + cols[idx2] * frac[:, None]


# ---------------------------------------------------------------- rendering
def render(mode, W, H, seed, pal_name="desert"):
    rng = np.random.default_rng(seed)
    pal = PALETTES[pal_name]
    lut = make_band_lut(pal["bands"])

    # Strip geometry
    R = 1.35 + rng.uniform(-0.15, 0.15)
    w = 0.28 + rng.uniform(-0.04, 0.06)

    # Camera: orbit, looking toward origin
    cd = 3.8 + rng.uniform(-0.4, 0.4)
    theta = rng.uniform(0, 2 * np.pi)
    phi = rng.uniform(0.22, 0.78)       # avoid looking straight down the axis
    cam = np.array([
        cd * np.cos(theta) * np.sin(phi),
        cd * np.sin(theta) * np.sin(phi),
        cd * np.cos(phi),
    ], F32)

    # Ray directions (camera at cam, looking toward origin, +z is up in screen)
    aspect = W / H
    fov = 0.85
    Y, X = np.mgrid[0:H, 0:W].astype(F32)
    sx = ((X + 0.5) / W * 2 - 1) * aspect * np.tan(fov / 2)
    sy = (1 - (Y + 0.5) / H * 2) * np.tan(fov / 2)

    fwd = -cam / (np.linalg.norm(cam) + 1e-8)
    right = np.cross(fwd, np.array([0, 0, 1], F32))
    right = right / (np.linalg.norm(right) + 1e-8)
    up = np.cross(right, fwd)

    rd = fwd + sx[..., None] * right + sy[..., None] * up
    rd = rd / np.linalg.norm(rd, axis=-1, keepdims=True)

    ro = np.broadcast_to(cam, (H, W, 3)).copy()

    # Bounding sphere for early start
    bound_r = R + w + 0.05
    oc = -cam
    b = np.dot(oc, fwd)
    c = np.dot(oc, oc) - bound_r * bound_r
    disc = b * b - c
    t0 = np.where(disc > 0, np.maximum(0, b - np.sqrt(np.maximum(disc, 0))), 0.0)

    # Raymarch
    t = np.full((H, W), t0, F32)
    alive = np.ones((H, W), dtype=bool)
    hit = np.zeros((H, W), dtype=bool)

    for _ in range(100):
        if not alive.any():
            break
        p = ro + rd * t[..., None]
        d = np.empty((H, W), F32)
        d[alive] = scene_sdf(p[alive], R, w)
        hit[alive] |= d[alive] < 0.002
        alive &= ~hit
        t[alive] += d[alive] * 0.5          # conservative step factor
        alive &= t < 15.0

    # Background
    if mode == "dark":
        top, bot = hexc(pal["dark_bg"][0]), hexc(pal["dark_bg"][1])
    else:
        top, bot = hexc(pal["light_bg"][0]), hexc(pal["light_bg"][1])

    sky_t = np.clip(rd[..., 1] * 0.5 + 0.4, 0, 1)
    bg = bot + (top - bot) * sky_t[..., None]

    # Subtle distant ground plane shadow (projected on background)
    ground_z = -1.8
    t_g = (ground_z - cam[2]) / (rd[..., 2] + 1e-8)
    gx = cam[0] + rd[..., 0] * t_g
    gy = cam[1] + rd[..., 1] * t_g
    g_r = np.sqrt(gx * gx + gy * gy)
    shadow = np.exp(-((g_r - R) ** 2) / 0.8) * np.clip(np.heaviside(t_g, 0), 0, 1)

    col = bg.copy()
    if mode == "dark":
        col -= shadow[..., None] * 0.25
    else:
        col -= shadow[..., None] * 0.12

    # Shade surface hits
    if hit.any():
        p_hit = ro + rd * t[..., None]
        # Refine
        for _ in range(2):
            dh = scene_sdf(p_hit[hit], R, w)
            p_hit[hit] -= rd[hit] * dh[..., None]

        u, v, n = surface_uvn(p_hit[hit], R, w)

        n_bands = 2 + int(rng.integers(0, 3))   # 2–4 bands around the strip
        band_t = np.mod(u * n_bands, 1.0)
        base = lut[(band_t * 511).astype(int)]

        # Slight side-tint so the half-twist is visible
        side = np.cos(v * np.pi)[..., None] * 0.06
        base = np.clip(base + side, 0, 1)

        # Lighting
        l0 = np.array([0.55, 0.75, 0.35], F32)
        l0 = l0 / np.linalg.norm(l0)
        diff = np.maximum(0.0, np.sum(n * l0, axis=-1))

        l1 = np.array([-0.35, 0.2, -0.55], F32)
        l1 = l1 / np.linalg.norm(l1)
        fill = np.maximum(0.0, np.sum(n * l1, axis=-1))

        view = -rd[hit]
        rim = np.maximum(0.0, 1 - np.sum(n * view, axis=-1)) ** 2.5

        refl = 2 * np.sum(n * l0, axis=-1)[..., None] * n - l0
        spec = np.maximum(0.0, np.sum(refl * view, axis=-1)) ** 18

        if mode == "dark":
            amb = 0.10
            c = base * (amb + diff[..., None] * 0.72 + fill[..., None] * 0.30)
            c += hexc("#ffffff") * spec[..., None] * pal["spec"] * diff[..., None]
            c += hexc(pal["accent"]) * rim[..., None] * 0.14
            # Thin highlight down the centre
            c *= 0.94 + 0.06 * (1 - np.abs(v))[..., None]
        else:
            amb = 0.52
            c = base * (amb + diff[..., None] * 0.48 + fill[..., None] * 0.25)
            c += hexc("#ffffff") * spec[..., None] * pal["spec"] * 0.35 * diff[..., None]
            c += hexc(pal["accent"]) * rim[..., None] * 0.07
            c = c * 0.96 + 0.04

        # Edge ink (ligne claire)
        edge = smooth(0.85, 1.0, np.abs(v))
        if mode == "light":
            ink = hexc("#3a3028") * 0.22
            c = c * (1 - edge[..., None] * 0.15) + ink * edge[..., None]
        else:
            c = c * (1 - edge[..., None] * 0.10)

        col[hit] = np.clip(c, 0, 1)

    # Film grain
    col += rng.normal(0, 0.5 / 255, col.shape).astype(F32)
    return (np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--palette", choices=list(PALETTES), help="default: random")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096")
    ap.add_argument("--ss", type=int, default=1, help="supersampling factor")
    ap.add_argument("--fast", action="store_true", help="960x600 quick preview")
    ap.add_argument("--focus", choices=["auto", "center", "full"], default="auto",
                    help="where to lay out the composition")
    ap.add_argument("--targets", help=f"screen aspect ratios, e.g. '{DEFAULT_TARGETS}' "
                                      "or '3840x2160,2160x3840,3440x1440'")
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
    for i in range(a.count):
        seed = a.seed + i if a.seed is not None else int(np.random.default_rng().integers(0, 100000))
        r = np.random.default_rng(seed + 7919)
        pal = a.palette or list(PALETTES)[r.integers(len(PALETTES))]
        print(f"[{i + 1}/{a.count}] palette={pal} seed={seed}")
        for m in (["light", "dark"] if a.mode == "both" else [a.mode]):
            arr = render(m, a.width * a.ss, a.height * a.ss, seed, pal_name=pal)
            im = Image.fromarray(arr)
            if a.ss > 1:
                im = im.resize((a.width, a.height), Image.LANCZOS)
            p = os.path.join(a.out, f"moebius-{pal}-{seed}-{m}{tag}.png")
            im.save(p, optimize=True)
            print("  ->", p)


if __name__ == "__main__":
    main()
