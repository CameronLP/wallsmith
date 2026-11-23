# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Retro 90s raytraced landscape generator in the spirit of Bryce 3D.

Fractal terrain, mirror water, chrome spheres, cloud layers, ringed planets.

  uv run bryce.py                      # random seed + random preset
  uv run bryce.py --seed 12 --preset alien
  uv run bryce.py --count 6            # batch of random ones
  uv run bryce.py --fast               # quick low-res preview
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

L = 256.0     # terrain tiling period (world units)
NRES = 1024   # heightmap resolution
FAR = 650.0


# ---------------------------------------------------------------- helpers
def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], F32)


def nrm(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def mix(a, b, t):
    return a + (b - a) * np.asarray(t, F32)[..., None]


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def periodic_noise(n, cells, rng):
    g = rng.random((cells, cells)).astype(F32)
    x = np.arange(n, dtype=F32) * cells / n
    i0 = np.floor(x).astype(int)
    f = x - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells
    fx, fy = f[None, :], f[:, None]
    a, b = g[i0][:, i0], g[i0][:, i1]
    c, d = g[i1][:, i0], g[i1][:, i1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(n, cells, octaves, rng, ridged=False, gain=0.5):
    tot = np.zeros((n, n), F32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        c = cells * 2 ** o
        if c > n:
            break
        x = periodic_noise(n, c, rng)
        if ridged:
            x = (1 - np.abs(x * 2 - 1)) ** 2
        tot += x * amp
        norm += amp
        amp *= gain
    tot /= norm
    return (tot - tot.min()) / (tot.max() - tot.min())


class Grid:
    """Bilinear lookup into a periodic 2D grid covering `period` world units."""

    def __init__(self, g, period):
        self.g, self.n, self.s = g.astype(F32), g.shape[0], g.shape[0] / period

    def __call__(self, x, z):
        gx, gz = x * self.s, z * self.s
        x0, z0 = np.floor(gx), np.floor(gz)
        fx, fz = (gx - x0).astype(F32), (gz - z0).astype(F32)
        n, g = self.n, self.g
        x0, z0 = x0.astype(np.int64) % n, z0.astype(np.int64) % n
        x1, z1 = (x0 + 1) % n, (z0 + 1) % n
        return ((g[z0, x0] * (1 - fx) + g[z0, x1] * fx) * (1 - fz)
                + (g[z1, x0] * (1 - fx) + g[z1, x1] * fx) * fz)


# ---------------------------------------------------------------- presets
PRESETS = {
    "classic": dict(
        zenith="#1a4ca8", horizon="#b4d2ee", sun="#fff2d8", elev=(0.35, 0.7), off=(1.0, 2.2),
        amb="#6a88b8", amb_k=0.5, cloud_lit="#ffffff", cloud_dark="#8a9ab8", cover=0.5, cloud_op=0.95,
        water="#0a2a48", shallow="#2a8a9a", sand="#cdbb8a", grass="#4c7034", rock="#7c6e62",
        rock2="#8e8a86", snow="#f2f4f8", snow_frac=0.62, fog=0.0035, hmax=30, terrace=False, strata=False,
        planet=0.35, p1="#e4e8f0", p2="#9aa4b8", rings=0.2, spheres=(1, 2), chrome="#e8eef8"),
    "alien": dict(
        zenith="#2b1050", horizon="#ff9860", sun="#ffd2a0", elev=(0.05, 0.16), off=(-0.45, 0.45),
        amb="#8a4a8a", amb_k=0.45, cloud_lit="#ffd0b0", cloud_dark="#6a3a6a", cover=0.55, cloud_op=0.9,
        water="#1a0a2a", shallow="#7a3a5a", sand="#e0a070", grass="#b0603a", rock="#a84a2c",
        rock2="#c86e4a", snow="#ffe2c8", snow_frac=0.85, fog=0.0045, hmax=32, terrace=True, strata=True,
        planet=0.9, p1="#f0c890", p2="#a05a3a", rings=0.65, spheres=(1, 3), chrome="#ffe8d8"),
    "dusk": dict(
        zenith="#0a1238", horizon="#e870a0", sun="#ffb47a", elev=(0.02, 0.09), off=(-0.4, 0.4),
        amb="#5a4a9a", amb_k=0.5, cloud_lit="#ffb0c8", cloud_dark="#3a2a6a", cover=0.55, cloud_op=0.9,
        water="#060a28", shallow="#3a3a7a", sand="#b89aa8", grass="#5a5a7a", rock="#4a4060",
        rock2="#6a6080", snow="#e8e0ff", snow_frac=0.45, fog=0.0055, hmax=34, terrace=False, strata=False,
        planet=0.85, p1="#c8d8ff", p2="#6a7ab0", rings=0.45, spheres=(1, 2), chrome="#e0d8ff"),
    "toxic": dict(
        zenith="#062a2a", horizon="#b8f0b0", sun="#f8ffd0", elev=(0.2, 0.45), off=(-1.3, 1.3),
        amb="#3a7a6a", amb_k=0.5, cloud_lit="#f0fff0", cloud_dark="#5a8a7a", cover=0.52, cloud_op=0.9,
        water="#02261e", shallow="#1aa080", sand="#c8d890", grass="#2a8a4a", rock="#3a5a50",
        rock2="#5a7a70", snow="#e8fff0", snow_frac=0.75, fog=0.0045, hmax=28, terrace=False, strata=True,
        planet=0.7, p1="#f0e0a0", p2="#c07040", rings=0.5, spheres=(0, 2), chrome="#e8fff0"),
}
COLOR_KEYS = {"zenith", "horizon", "sun", "amb", "cloud_lit", "cloud_dark", "water", "shallow",
              "sand", "grass", "rock", "rock2", "snow", "p1", "p2", "chrome"}


MOON = hexc("#f2f0e6")


def night(P):
    """Turn a day preset into its moonlit night version."""
    P = dict(P)
    k = lambda a, b, t: a + (hexc(b) - a) * t
    P["zenith"] = k(P["zenith"], "#01030c", 0.88)
    P["horizon"] = k(P["horizon"], "#0b1636", 0.78)
    P["sun"] = hexc("#9db4e8") * 0.62
    P["amb"] = k(P["amb"], "#1c2c60", 0.6)
    P["amb_k"] = P["amb_k"] * 0.45
    P["cloud_lit"] = k(P["cloud_lit"], "#5a6a90", 0.75)
    P["cloud_dark"] = k(P["cloud_dark"], "#070b18", 0.85)
    P["cloud_op"] = P["cloud_op"] * 0.75
    P["water"] = P["water"] * 0.5
    P["shallow"] = P["shallow"] * 0.35
    P["p1"], P["p2"] = P["p1"] * 1.1, P["p2"] * 1.1
    P["fog"] = P["fog"] * 0.8
    return P


# ---------------------------------------------------------------- scene
class Scene:
    def __init__(self, preset, seed, mode="light"):
        rng = np.random.default_rng(seed)  # same seed -> same world in both modes
        self.rng = rng
        self.night = mode == "dark"
        P = {k: (hexc(v) if k in COLOR_KEYS else v) for k, v in PRESETS[preset].items()}
        if self.night:
            P = night(P)
        self.P = P
        self.hmax = P["hmax"]
        self._build_terrain(rng)
        self.clouds = Grid(fbm(512, 4, 6, rng), 900.0)
        rip = fbm(512, 24, 3, rng)
        d = 40.0 / 512
        self.rx = Grid((np.roll(rip, -1, 1) - np.roll(rip, 1, 1)) / (2 * d), 40.0)
        self.rz = Grid((np.roll(rip, -1, 0) - np.roll(rip, 1, 0)) / (2 * d), 40.0)
        self._camera(rng)
        self._sky_objects(rng)
        self._spheres(rng)

    def _build_terrain(self, rng):
        P, hm = self.P, self.hmax
        cont = fbm(NRES, 3, 4, rng)
        ridge = fbm(NRES, 6, 7, rng, ridged=True, gain=0.55)
        det = fbm(NRES, 48, 4, rng)
        land = smooth(0.4, 0.72, cont)
        h = land * (0.12 + ridge ** 1.7) * hm + det * 0.5 - 2.5 * (1 - land) - 0.6
        if P["terrace"]:
            s = hm / 12
            q = h / s
            stepped = (np.floor(q) + smooth(0.7, 1.0, q % 1.0)) * s
            h = np.where(h > 0.5, stepped * 0.85 + h * 0.15, h)
        self.hgrid = h
        self.H = Grid(h, L)
        dd = L / NRES
        self.NX = Grid(-(np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * dd), L)
        self.NZ = Grid(-(np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * dd), L)
        self.D = Grid(fbm(512, 16, 5, rng), 24.0)

    def _camera(self, rng):
        best, best_s = None, -1e9
        for _ in range(400):
            x, z = rng.uniform(0, L, 2)
            if self.H(np.array([x]), np.array([z]))[0] > -0.8:
                continue
            yaw = rng.uniform(0, 2 * np.pi)
            fx, fz = np.sin(yaw), np.cos(yaw)
            dn = np.linspace(3, 22, 10)
            df = np.linspace(40, 200, 24)
            near = self.H(x + fx * dn, z + fz * dn).max()
            far = self.H(x + fx * df, z + fz * df)
            if near > 0.5:
                continue
            if ((far - 4.0) / df).max() > 0.16:  # wall filling the frame
                continue
            s = far.max() + 0.3 * far.mean() + rng.uniform(0, 4)
            if s > best_s:
                best_s, best = s, (x, z, yaw)
        x, z, yaw = best
        self.cam = np.array([x, rng.uniform(2.2, 5.5), z], F32)
        self.yaw = yaw
        pitch = rng.uniform(-0.06, 0.03)
        self.fwd = np.array([np.sin(yaw) * np.cos(pitch), np.sin(pitch), np.cos(yaw) * np.cos(pitch)], F32)
        self.right = np.array([np.cos(yaw), 0, -np.sin(yaw)], F32)
        self.up = np.cross(self.fwd, self.right).astype(F32)
        P = self.P
        az = yaw + rng.uniform(*P["off"]) * rng.choice([-1, 1])
        el = rng.uniform(*P["elev"])
        self.sun = np.array([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)], F32)

    def _sky_objects(self, rng):
        P = self.P
        self.planet = None
        if rng.random() < P["planet"]:
            az = self.yaw + rng.uniform(-0.45, 0.45)
            el = rng.uniform(0.14, 0.34)
            pd = np.array([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)], F32)
            ang = rng.uniform(0.05, 0.13)
            dist = 5000.0
            v = nrm(np.array([rng.uniform(-0.5, 0.5), 1.0, rng.uniform(-0.5, 0.5)], F32))
            rn = nrm(v - (v @ pd) * pd + pd * rng.uniform(0.15, 0.4) * rng.choice([-1, 1]))
            self.planet = dict(c=pd * dist, R=dist * np.sin(ang), rings=rng.random() < P["rings"],
                               rn=rn, band_ph=rng.uniform(0, 6), band_f=rng.uniform(10, 22))

    def _spheres(self, rng):
        lo, hi = self.P["spheres"]
        k = int(rng.integers(lo, hi + 1))
        cs, rs = [], []
        ff = np.array([np.sin(self.yaw), 0, np.cos(self.yaw)], F32)
        for _ in range(k):
            d = rng.uniform(9, 32)
            pos = self.cam + ff * d + self.right * rng.uniform(-0.38, 0.38) * d
            r = rng.uniform(0.8, 2.6)
            ground = max(self.H(pos[[0]], pos[[2]])[0], 0.0)
            pos[1] = ground + r * (1.0 if rng.random() < 0.35 else rng.uniform(1.6, 4.0))
            cs.append(pos)
            rs.append(r)
        self.sc = np.array(cs, F32).reshape(-1, 3)
        self.sr = np.array(rs, F32)

    # ------------------------------------------------------------ intersection
    def hit_spheres(self, ro, rd):
        t = np.full(len(ro), np.inf, F32)
        sid = np.full(len(ro), -1)
        for i, (c, r) in enumerate(zip(self.sc, self.sr)):
            oc = ro - c
            b = np.einsum("ij,ij->i", oc, rd)
            cc = np.einsum("ij,ij->i", oc, oc) - r * r
            disc = b * b - cc
            ok = disc > 0
            ti = np.where(ok, -b - np.sqrt(np.maximum(disc, 0)), np.inf)
            ti = np.where(ti > 1e-3, ti, np.inf)
            better = ti < t
            t[better], sid[better] = ti[better], i
        return t, sid

    def march(self, ro, rd, tmax):
        n = len(ro)
        t = np.full(n, 0.02, F32)
        tprev = t.copy()
        res = np.full(n, np.inf, F32)
        act = np.arange(n)
        for _ in range(450):
            if act.size == 0:
                break
            ta = t[act]
            p = ro[act] + rd[act] * ta[:, None]
            dy = p[:, 1] - self.H(p[:, 0], p[:, 2])
            hit = dy < 0
            if hit.any():
                hi = act[hit]
                res[hi] = self._refine(ro[hi], rd[hi], tprev[hi], t[hi])
            tn = ta + np.maximum(dy * 0.4, 0.002 * ta + 0.004)
            out = (tn > tmax[act]) | ((p[:, 1] > self.hmax + 1) & (rd[act, 1] >= 0))
            keep = ~hit & ~out
            act, ta, tn = act[keep], ta[keep], tn[keep]
            tprev[act], t[act] = ta, tn
        return res

    def _refine(self, ro, rd, a, b):
        for _ in range(8):
            m = (a + b) * 0.5
            p = ro + rd * m[:, None]
            below = p[:, 1] < self.H(p[:, 0], p[:, 2])
            b, a = np.where(below, m, b), np.where(below, a, m)
        return b

    def normal(self, p):
        return nrm(np.stack([self.NX(p[:, 0], p[:, 2]), np.ones(len(p), F32),
                             self.NZ(p[:, 0], p[:, 2])], -1))

    def shadow(self, p):
        n = len(p)
        res = np.ones(n, F32)
        t = np.full(n, 0.25, F32)
        act = np.arange(n)
        s = self.sun
        for _ in range(90):
            if act.size == 0:
                break
            q = p[act] + s * t[act, None]
            dy = q[:, 1] - self.H(q[:, 0], q[:, 2])
            res[act] = np.minimum(res[act], 10 * dy / t[act])
            t[act] += np.clip(dy * 0.5, 0.12, 6.0)
            keep = (res[act] > 0) & (t[act] < 160) & (q[:, 1] < self.hmax)
            act = act[keep]
        res = smooth(0, 1, res)
        if len(self.sr):
            ts, _ = self.hit_spheres(p, np.broadcast_to(s, p.shape))
            res = np.where(np.isfinite(ts), res * 0.12, res)
        return res

    # ------------------------------------------------------------ shading
    def sky(self, ro, rd):
        P = self.P
        y = rd[:, 1]
        col = mix(P["horizon"], P["zenith"], np.clip(y, 0, 1) ** 0.45)
        col = np.where((y < 0)[:, None], P["horizon"] * 0.85, col)
        cs = np.clip(rd @ self.sun, 0, 1)
        if self.night:
            col = col + self.stars(rd)
            moon = smooth(0.99985, 0.9999, cs)
            col = col + P["sun"] * (cs ** 3000 * 0.6 + cs ** 80 * 0.25 + cs ** 8 * 0.1)[:, None]
            col = mix(col, MOON, moon)
        else:
            col = col + P["sun"] * (cs ** 900 * 2.5 + cs ** 60 * 0.35 + cs ** 6 * 0.18)[:, None]

        if self.planet is not None:
            col = self._planet(rd, col)

        m = y > 0.008
        if m.any():
            tc = (220.0 - ro[m, 1]) / y[m]
            cx, cz = ro[m, 0] + rd[m, 0] * tc, ro[m, 2] + rd[m, 2] * tc
            d = self.clouds(cx, cz)
            ds = self.clouds(cx + self.sun[0] * 25, cz + self.sun[2] * 25)
            dens = smooth(P["cover"], P["cover"] + 0.3, d) * np.exp(-tc / 4500) * smooth(0.008, 0.1, y[m])
            lit = np.clip(0.55 + (d - ds) * 4, 0, 1)
            cc = mix(P["cloud_dark"], P["cloud_lit"], lit)
            cc = cc + P["sun"] * (cs[m] ** 8 * 0.5 * (1 - dens))[:, None]
            # distant clouds dissolve into horizon haze
            cc = mix(cc, P["horizon"], 1 - np.exp(-tc / 2500))
            col[m] = mix(col[m], cc, dens * P["cloud_op"])
        return col

    def stars(self, rd):
        """Hash-based starfield on an (azimuth, elevation) grid."""
        cell = 0.0035
        az = np.arctan2(rd[:, 0], rd[:, 2])
        el = np.arcsin(np.clip(rd[:, 1], -1, 1))
        gx, gy = np.floor(az / cell), np.floor(el / cell)
        h = np.sin(gx * 127.1 + gy * 311.7) * 43758.5453
        h = h - np.floor(h)
        h2 = np.sin(gx * 269.5 + gy * 183.3) * 43758.5453
        h2 = h2 - np.floor(h2)
        jx = (gx + 0.2 + 0.6 * h2) * cell
        jy = (gy + 0.2 + 0.6 * h) * cell
        d = np.hypot((az - jx) * np.cos(el), el - jy) / cell
        on = h > 0.93
        bright = ((h - 0.93) / 0.07) ** 2
        st = on * np.clip(1 - d / 0.18, 0, 1) * (0.25 + 1.2 * bright) * smooth(0.0, 0.25, rd[:, 1])
        tint = mix(np.array([0.75, 0.85, 1.0], F32), np.array([1.0, 0.9, 0.8], F32), h2)
        return tint * st[:, None]

    def _planet(self, rd, col):
        pl, P = self.planet, self.P
        C, R = pl["c"], pl["R"]
        b = -(rd @ C)
        cc = C @ C - R * R
        disc = b * b - cc
        hitp = disc > 0
        tp = np.where(hitp, -b - np.sqrt(np.maximum(disc, 0)), np.inf)
        alpha = np.clip(disc / (R * R) * 60, 0, 1) * hitp
        if hitp.any():
            q = rd[hitp] * tp[hitp, None]
            nn = (q - C) / R
            lam = np.clip(nn @ self.sun, 0, 1)
            tex = self.clouds(nn[:, 0] * 400 + 50, nn[:, 2] * 400)
            band = 0.5 + 0.5 * np.sin(nn[:, 1] * pl["band_f"] + tex * 5 + pl["band_ph"])
            pc = mix(P["p2"], P["p1"], band)
            pc = pc * (0.28 + 0.9 * lam)[:, None]
            rim = (1 - np.clip(-(nn * rd[hitp]).sum(1), 0, 1)) ** 3
            pc = pc + P["horizon"] * (rim * 0.35)[:, None]
            col[hitp] = mix(col[hitp], pc, alpha[hitp] * 0.94)
        if pl["rings"]:
            rn = pl["rn"]
            den = rd @ rn
            tr = (C @ rn) / np.where(np.abs(den) < 1e-6, 1e-6, den)
            q = rd * tr[:, None]
            r = np.linalg.norm(q - C, axis=1) / R
            ring = (r > 1.35) & (r < 2.3) & (tr > 0)
            vis = ring & (~hitp | (tr < tp))
            if vis.any():
                rr = r[vis]
                a = (0.45 + 0.35 * np.sin(rr * 37) * np.sin(rr * 11)) * smooth(1.35, 1.45, rr) * smooth(2.3, 2.15, rr)
                lam = 0.35 + 0.65 * abs(float(rn @ self.sun))
                col[vis] = mix(col[vis], mix(P["p1"], P["horizon"], 0.3) * lam, a * 0.8)
        return col

    def fogged(self, col, t, rd):
        P = self.P
        cs = np.clip(rd @ self.sun, 0, 1)
        fc = P["horizon"] + P["sun"] * (cs ** 6 * 0.25)[:, None]
        f = 1 - np.exp(-t * P["fog"])
        return mix(col, fc, f)

    def ambient(self, ny):
        return self.P["amb"] * self.P["amb_k"] * (0.4 + 0.6 * (0.5 + 0.5 * ny))[:, None]

    def shade_terrain(self, p):
        P = self.P
        nn = self.normal(p)
        h, sl = p[:, 1], nn[:, 1]
        det = self.D(p[:, 0], p[:, 2])
        c = mix(P["sand"], P["grass"], smooth(0.4, 1.3, h + det * 0.5))
        c = mix(c, P["rock"] * (0.8 + 0.4 * det)[:, None], 1 - smooth(0.6, 0.82, sl + (det - 0.5) * 0.25))
        c = mix(c, P["rock2"], smooth(self.hmax * 0.35, self.hmax * 0.6, h) * 0.6)
        if P["strata"]:
            c = c * (0.82 + 0.18 * np.sin(h * 2.6 + det * 2))[:, None]
        sn = smooth(self.hmax * P["snow_frac"], self.hmax * P["snow_frac"] + 2, h + det * 4)
        c = mix(c, P["snow"], sn * smooth(0.5, 0.72, sl))
        c = c * (0.85 + 0.3 * det)[:, None]
        sh = self.shadow(p + nn * 0.05)
        dif = np.clip(nn @ self.sun, 0, 1) * sh
        return c * (P["sun"] * (dif * 1.15)[:, None] + self.ambient(sl))

    def shade_water(self, p, rd, depth):
        P = self.P
        s = 0.02
        nn = nrm(np.stack([-self.rx(p[:, 0], p[:, 2]) * s, np.ones(len(p), F32),
                           -self.rz(p[:, 0], p[:, 2]) * s], -1))
        cosi = np.clip(-(rd * nn).sum(1), 0, 1)
        F = np.maximum(0.04 + 0.96 * (1 - cosi) ** 5, 0.3)
        r = rd - 2 * (rd * nn).sum(1, keepdims=True) * nn
        r[:, 1] = np.abs(r[:, 1]) + 1e-3
        r = nrm(r)
        ro = p.copy()
        ro[:, 1] = 1e-3
        rc = self.trace(ro, r, depth - 1) if depth > 0 else self.sky(ro, r)
        hb = self.H(p[:, 0], p[:, 2])
        shallow = np.exp(np.minimum(hb, 0) * 1.3)
        sh = self.shadow(ro)
        wc = mix(P["water"], P["shallow"], shallow) * (self.ambient(np.ones(len(p), F32)) * 1.2 + P["sun"] * (0.25 * sh)[:, None])
        col = mix(wc, rc, F)
        spec = np.clip(r @ self.sun, 0, 1) ** 500 * 4 * sh
        return col + P["sun"] * spec[:, None]

    def shade_sphere(self, p, rd, sid, depth):
        c, r = self.sc[sid], self.sr[sid]
        nn = (p - c) / r[:, None]
        rr = nrm(rd - 2 * (rd * nn).sum(1, keepdims=True) * nn)
        o = p + nn * 1e-3
        rc = self.trace(o, rr, depth - 1) if depth > 0 else self.sky(o, rr)
        spec = np.clip(rr @ self.sun, 0, 1) ** 300 * 3
        return rc * self.P["chrome"] * 0.92 + self.P["sun"] * spec[:, None]

    def trace(self, ro, rd, depth):
        n = len(ro)
        col = np.zeros((n, 3), F32)
        tw = np.where(rd[:, 1] < -1e-5, -ro[:, 1] / np.where(rd[:, 1] < -1e-5, rd[:, 1], -1), np.inf).astype(F32)
        ts, sid = self.hit_spheres(ro, rd)
        tt = self.march(ro, rd, np.minimum(np.minimum(tw, ts), FAR))
        T = np.stack([tt, tw, ts], 1)
        cls = np.argmin(T, 1)
        tmin = T[np.arange(n), cls]
        sky = ~np.isfinite(tmin) | (tmin > FAR)
        if sky.any():
            col[sky] = self.sky(ro[sky], rd[sky])
        for k in range(3):
            m = (cls == k) & ~sky
            if not m.any():
                continue
            p = ro[m] + rd[m] * tmin[m, None]
            if k == 0:
                c = self.shade_terrain(p)
            elif k == 1:
                c = self.shade_water(p, rd[m], depth)
            else:
                c = self.shade_sphere(p, rd[m], sid[m], depth)
            col[m] = self.fogged(c, tmin[m], rd[m])
        return col

    # ------------------------------------------------------------ render
    def render(self, W, H, fov_deg=58, rows=96, rect=None):
        ox, oy, dw, dh = rect or (0, 0, W, H)   # framing is designed for this area
        tan = np.tan(np.radians(fov_deg) / 2)
        img = np.zeros((H, W, 3), F32)
        xs = ((np.arange(W, dtype=F32) + 0.5 - ox) / dw * 2 - 1) * tan
        t0 = time.time()
        for y0 in range(0, H, rows):
            y1 = min(y0 + rows, H)
            ys = (1 - (np.arange(y0, y1, dtype=F32) + 0.5 - oy) / dh * 2) * tan * dh / dw
            px, py = np.meshgrid(xs, ys)
            rd = nrm(self.fwd + px[..., None] * self.right + py[..., None] * self.up).reshape(-1, 3).astype(F32)
            ro = np.broadcast_to(self.cam, rd.shape).copy()
            img[y0:y1] = self.trace(ro, rd, 2).reshape(y1 - y0, W, 3)
            print(f"\r  {y1 * 100 // H:3d}%  {time.time() - t0:5.0f}s", end="", flush=True)
        print()
        return img


def finish(img, rng):
    img = np.clip(img, 0, None)
    img = img / (1 + img * 0.15) * 1.15  # gentle highlight rolloff
    img = img ** 0.95
    img += rng.normal(0, 0.8 / 255, img.shape).astype(F32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--preset", choices=list(PRESETS))
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both",
                    help="light = daytime, dark = same scene at night")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--ss", type=int, default=2, help="supersampling factor (antialiasing)")
    ap.add_argument("--fast", action="store_true", help="960x600, no supersampling")
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
    meta = np.random.default_rng()
    for i in range(a.count):
        seed = a.seed + i if a.seed is not None else int(meta.integers(0, 100000))
        preset = a.preset or list(PRESETS)[np.random.default_rng(seed).integers(len(PRESETS))]
        print(f"[{i + 1}/{a.count}] preset={preset} seed={seed}")
        for m in (["light", "dark"] if a.mode == "both" else [a.mode]):
            sc = Scene(preset, seed, m)
            img = sc.render(a.width * a.ss, a.height * a.ss,
                             rect=focus_rect(a.width * a.ss, a.height * a.ss, a.focus, a.targets))
            im = Image.fromarray(finish(img, sc.rng), "RGB")
            if a.ss > 1:
                im = im.resize((a.width, a.height), Image.LANCZOS)
            path = os.path.join(a.out, f"bryce-{preset}-{seed}-{m}{tag}.png")
            im.save(path, optimize=True)
            print("  ->", path)


if __name__ == "__main__":
    main()
