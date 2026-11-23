# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Twilight sky wallpapers: horizon glow -> blue -> black, with height-tinted stars.

After Howard Look's SGI IRIX "twilight" and Brendan Caluneo's SDL2 port
(https://bcaluneo.com/projects/twilight/, https://github.com/bcaluneo/Twilight).

  uv run twilight.py                       # enhanced, classic colours, light + dark
  uv run twilight.py --classic --mode dark # faithful to the original (pixel stars)
  uv run twilight.py --palette rose --seed 3
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
    """Area (ox, oy, w, h) the composition is laid out in (see top-level README)."""
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


def rgb(*c):
    return np.array(c, F32) / 255


# horizon, mid, top colours.  "classic" are the original program's exact values.
PALETTES = {
    "classic": dict(dark=(rgb(255, 72, 0), rgb(0, 110, 189), rgb(0, 0, 0)),
                    light=(rgb(255, 170, 100), rgb(90, 165, 230), rgb(28, 70, 150))),
    "rose":    dict(dark=(rgb(255, 80, 120), rgb(90, 60, 170), rgb(4, 2, 14)),
                    light=(rgb(255, 178, 190), rgb(170, 150, 225), rgb(70, 60, 150))),
    "ember":   dict(dark=(rgb(255, 120, 30), rgb(150, 40, 70), rgb(8, 2, 8)),
                    light=(rgb(255, 196, 120), rgb(230, 130, 140), rgb(110, 60, 120))),
    "teal":    dict(dark=(rgb(255, 150, 60), rgb(0, 140, 150), rgb(0, 6, 14)),
                    light=(rgb(255, 205, 150), rgb(100, 200, 205), rgb(25, 95, 130))),
}


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * np.asarray(t, F32)[..., None]


# gradient shape, set from the command line (see main)
GRAD = dict(fade=1.0, curve=1.0)


def sky_color(p, cols, transition):
    """p = height above the horizon as a fraction of the design height (0 = horizon, 1 = top).

    0 .. transition      horizon colour -> mid colour   (the bottom band, --band)
    transition .. fade   mid colour -> top colour        (the main gradient, --fade / --curve)
    above fade           solid top colour
    """
    hor, mid, top = cols
    fade = max(GRAD["fade"], transition + 1e-3)
    lo = lerp(hor, mid, np.clip(p / transition, 0, 1))
    t = np.clip((p - transition) / (fade - transition), 0, 1) ** GRAD["curve"]
    hi = lerp(mid, top, t)
    return np.where((p < transition)[..., None], lo, hi)


def parse_colors(spec):
    cs = [c.strip().lstrip("#") for c in spec.split(",")]
    if len(cs) != 3:
        raise SystemExit("--colors needs exactly 3 hex colours: HORIZON,MID,TOP")
    return tuple(np.array([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)], F32) for c in cs)


def lighten(cols):
    """Derive a light-mode palette from a dark one (blend toward white, top the least)."""
    return tuple(c + (1 - c) * k for c, k in zip(cols, (0.45, 0.35, 0.2)))


def original_stars(img, rng, W, H, oy, dh, cols, transition, mode, stars, classic, light_stars=1.0):
    """The original's stars: 2500 single pixels + 200 plus-shaped crosses, tinted by height."""
    ref_area = 1280 * 1024                          # roughly the screens the original targeted
    scale = 1 if classic else max(1.0, H / 1080)
    # more pixels -> more stars (linear in scale, so big canvases aren't sparse)
    area_k = 1 if classic else (W * H) / ref_area / scale
    # both modes lay out the same (dark-mode) star field from the same random draws, so a
    # light/dark pair has its stars in the same places. Light mode then shows only a subset:
    # the first stars of the evening -- few, but clearly visible (see --light-stars)
    n_small = int(2500 * area_k * stars)
    n_big = int(200 * area_k * stars)
    light = mode == "light"
    frac = min(1.0, 0.1 * light_stars)              # share of the dark-mode stars shown in light mode
    # the light-mode selection uses its own child streams, so the main stream (and with it the
    # dark-mode picture, the hills and the dither) is identical in both modes
    sel_small, sel_big = rng.spawn(2)

    def light_weight(sp):
        """Light mode: concentrate stars toward the darker top of the sky."""
        return frac * np.clip((sp - 0.3) / 0.45, 0, 1) ** 1.5

    def star_color(sp):
        """The original's getStarColor: sky-tinted near the horizon, white above half height."""
        c = sky_color(sp, cols, transition)
        a = np.clip(sp / 0.5, 0, 1)[:, None]
        c = c * (1 - a) + a
        if mode == "light":
            c = np.ones_like(c) * np.array([1.0, 0.98, 0.94], F32)   # crisp white on the brighter sky
        return c

    # classic at high resolution: lay stars out on the original 1200-px-tall grid and scale that up
    # in whole pixels, so e.g. 5120x3200 is the same picture as 1920x1200, just sharper
    H0 = 1200 if (classic and H > 1200) else H
    W0 = int(round(W * H0 / H))
    kc = H / H0                                    # classic upscale factor (1 at native size)
    uc = max(1, int(round(kc)))                    # whole-pixel star size
    ys = (rng.integers(0, H0, n_small) * kc).astype(int)
    xs = (rng.integers(0, W0, n_small) * kc).astype(int)
    sp = (oy + dh - (ys + 0.5)) / dh
    keep = sp > 0.02 if not classic else np.ones_like(sp, bool)
    if not classic:                                # brightness (drawn in both modes)
        br = (0.45 + 0.55 * rng.random(keep.sum()) ** 3).astype(F32)
    if light:
        shown = sel_small.random(len(sp)) < light_weight(sp)
        if not classic:
            br = br[shown[keep]]
        keep &= shown
    sc = star_color(sp[keep])
    if classic:
        for dy in range(uc):
            for dx in range(uc):
                img[np.minimum(ys[keep] + dy, H - 1), np.minimum(xs[keep] + dx, W - 1)] = sc
    else:
        # round antialiased dots (radius grows gently with resolution) instead of square blocks
        rad = 0.5 + 0.3 * (scale - 1)
        k = int(np.ceil(rad + 1))
        ky, kx = np.mgrid[-k:k + 1, -k:k + 1]
        ker = np.clip(rad + 0.5 - np.hypot(kx, ky), 0, 1).astype(F32)
        yk, xk = ys[keep], xs[keep]
        for dy, dx, w in zip(ky.ravel(), kx.ravel(), ker.ravel()):
            if w <= 0:
                continue
            yy, xx = np.clip(yk + dy, 0, H - 1), np.clip(xk + dx, 0, W - 1)
            a = (br * w)[:, None]
            img[yy, xx] = img[yy, xx] * (1 - a) + sc * a

    # big stars: chunky pixel blobs like the original's screenshots. The original drew two
    # overlapping 2 px bars of length 1-4; centred, that gives 2x2 dots and rounded 4x4 "+" blobs.
    # At high resolutions they're upscaled in whole pixels (u) so they stay crisp and blocky.
    u = uc if classic else max(1, int(round(scale ** 0.6)))
    for _ in range(n_big):
        if classic:
            x, y = int(rng.integers(0, W0) * kc), int(rng.integers(0, H0) * kc)
        else:
            x, y = int(rng.integers(0, W)), int(rng.integers(0, H))
        size = int(rng.integers(1, 5))
        spy = (oy + dh - (y + 0.5)) / dh
        if light and not sel_big.random() < light_weight(spy):
            continue
        if not classic and spy < 0.03:
            continue
        c = star_color(np.array([spy], F32))[0]
        t, L = 2 * u, (2 if size <= 2 else 4) * u
        img[max(y - L // 2, 0):min(y - L // 2 + L, H), max(x - t // 2, 0):min(x - t // 2 + t, W)] = c
        img[max(y - t // 2, 0):min(y - t // 2 + t, H), max(x - L // 2, 0):min(x - L // 2 + L, W)] = c

    return img


def gauss_blur(a, sig):
    """Separable gaussian blur (small sigma), edge-clamped."""
    if sig < 0.6:
        return a
    r = int(np.ceil(sig * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2).astype(F32)
    k /= k.sum()
    out = a
    for axis in (0, 1):
        pad = [(r, r) if i == axis else (0, 0) for i in range(a.ndim)]
        src = np.pad(out, pad, mode="edge")
        n = out.shape[axis]
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            acc += w * np.take(src, np.arange(i, i + n), axis=axis)
        out = acc
    return out


def soft_noise(rng, W, H, cells):
    """Smooth value noise in [0,1] via an upscaled random grid."""
    g = rng.random((cells, max(2, int(cells * W / H)))).astype(F32)
    im = Image.fromarray(g, "F").resize((W, H), Image.BICUBIC)
    return np.clip(np.asarray(im), 0, 1)


def realistic_stars(img, rng, W, H, ox, oy, dw, dh, mode, stars, milkyway, light_stars=1.0):
    """Photographic-ish stars: power-law brightness, sub-pixel AA, colour temperature,
    soft halos on bright stars, atmospheric extinction near the horizon, optional Milky Way."""
    scale = max(1.0, H / 1080)
    acc = np.zeros((H, W, 3), F32)
    light = mode == "light"

    band = None
    if milkyway:
        # a diagonal band of diffuse glow + extra stars, broken up by "dust" noise
        ang = rng.uniform(0.35, 1.2) * rng.choice([-1, 1])
        cx, cy = ox + dw * rng.uniform(0.35, 0.65), oy + dh * rng.uniform(0.25, 0.5)
        yy, xx = np.mgrid[0:H, 0:W].astype(F32)
        dist = ((xx - cx) * np.sin(ang) - (yy - cy) * np.cos(ang)) / dh
        n1, n2 = soft_noise(rng, W, H, 6), soft_noise(rng, W, H, 22)
        band = np.exp(-(dist / 0.13) ** 2) * (0.35 + 0.65 * n1) * (0.6 + 0.4 * n2)
        dust = np.clip((soft_noise(rng, W, H, 14) - 0.45) * 2.5, 0, 1) * np.exp(-(dist / 0.05) ** 2)
        band = np.clip(band - dust * 0.6, 0, 1)
        p = (oy + dh - yy) / dh
        fade = np.clip(p / 0.3, 0, 1) ** 1.5
        glow_col = np.array([0.75, 0.78, 0.9], F32)
        acc += (band * fade * (0.05 if light else 0.16))[..., None] * glow_col

    # both modes draw the same (dark-mode) star field, so a light/dark pair has its stars in the
    # same places; light mode then shows only the brightest of them (see --light-stars)
    n = int(W * H / 260 / scale * stars)
    frac = min(1.0, 0.12 * light_stars)        # share of the dark-mode stars shown in light mode
    x = rng.random(n) * W
    y = rng.random(n) * H
    if band is not None:  # extra stars inside the Milky Way
        m = int(n * 0.8)
        cand_x, cand_y = rng.random(m * 4) * W, rng.random(m * 4) * H
        w = band[cand_y.astype(int).clip(0, H - 1), cand_x.astype(int).clip(0, W - 1)]
        pick = rng.random(m * 4) < w
        x, y = np.concatenate([x, cand_x[pick][:m]]), np.concatenate([y, cand_y[pick][:m]])
        n = len(x)
    p = (oy + dh - y) / dh
    # power-law magnitudes: most stars are faint, a handful are bright
    r = rng.random(n)
    b = np.clip(0.035 / r ** 0.85, 0, 6).astype(F32)
    # atmospheric extinction: dimmer near the horizon
    b *= (np.clip(p / 0.35, 0, 1) ** 1.6).astype(F32)
    # colour temperature: blue-white .. white .. yellow .. orange; redder near the horizon
    temps = np.array([[0.78, 0.86, 1.0], [1.0, 1.0, 1.0], [1.0, 0.92, 0.78], [1.0, 0.78, 0.6]], F32)
    tsel = np.clip(rng.normal(1.2, 0.8, n) + (1 - np.clip(p / 0.3, 0, 1)) * 1.2, 0, 3)
    if light:
        # the first stars of the evening are the brightest ones (smallest r). Rescaling r by frac
        # gives the shown stars the full brightness spread again, so they look like before
        shown = r < frac
        x, y, p, tsel = x[shown], y[shown], p[shown], tsel[shown]
        b = b[shown] * F32(frac ** 0.85)
        # few but clearly visible stars, mostly high up where the dusk sky is darkest
        b = np.clip(b * 4, 0, 4) * smooth(0.3, 0.8, p).astype(F32)
        n = len(x)
    i0 = np.floor(tsel).astype(int).clip(0, 2)
    f = (tsel - i0)[:, None]
    col = temps[i0] * (1 - f) + temps[i0 + 1] * f

    faint = b < 0.7
    # faint stars: bilinear splat (sub-pixel antialiasing)
    xf, yf, bf, cf = x[faint], y[faint], b[faint], col[faint]
    # splat point flux, then blur with a small gaussian so faint stars are round at any resolution
    psf = scale ** 0.55                       # star size grows slower than resolution: stays sharp
    sig_f = 0.45 * psf
    gain = 2 * np.pi * sig_f ** 2 if sig_f >= 0.6 else 1.0   # keep the peak brightness ~constant
    pts = np.zeros_like(acc)
    x0, y0 = np.floor(xf - 0.5).astype(int), np.floor(yf - 0.5).astype(int)
    fx, fy = (xf - 0.5 - x0).astype(F32), (yf - 0.5 - y0).astype(F32)
    for dx, dy, wgt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = (x0 + dx).clip(0, W - 1), (y0 + dy).clip(0, H - 1)
        np.add.at(pts, (yi, xi), cf * (bf * wgt * gain)[:, None])
    acc += gauss_blur(pts, sig_f)
    # bright stars: gaussian core + wide soft halo
    for xb, yb, bb, cb in zip(x[~faint], y[~faint], b[~faint], col[~faint]):
        sig = (0.5 + 0.3 * np.sqrt(bb)) * psf
        r = int(np.ceil(sig * 7))
        xa, xb2 = max(int(xb) - r, 0), min(int(xb) + r + 1, W)
        ya, yb2 = max(int(yb) - r, 0), min(int(yb) + r + 1, H)
        if xa >= xb2 or ya >= yb2:
            continue
        gy, gx = np.mgrid[ya:yb2, xa:xb2].astype(F32)
        d2 = (gx + 0.5 - xb) ** 2 + (gy + 0.5 - yb) ** 2
        prof = np.exp(-d2 / (2 * sig ** 2)) + 0.06 * np.exp(-np.sqrt(d2) / (sig * 2.2))
        acc[ya:yb2, xa:xb2] += prof[..., None] * cb * min(bb, 3.0)
    return 1 - (1 - img) * np.exp(-acc)       # additive light with gentle roll-off


def render(mode, pal, W, H, seed, rect, classic=False, transition=0.2, stars=1.0, glow=1.0,
           star_style="realistic", milkyway=False, horizon=0.0, custom=None, sky_span="auto", ground="auto",
           light_stars=1.0, evening_star=False, light_level=1.0):
    rng = np.random.default_rng(seed)
    ox, oy, dw, dh = rect
    shrunk = dh < H * 0.98
    if sky_span == "full" or (sky_span == "auto" and shrunk):
        # keep the horizon at the bottom of the safe area (every screen sees it) but let the
        # sky run all the way to the top of the canvas, so tall/portrait crops get the whole
        # gradient instead of a flat black block
        dh, oy = oy + dh, 0
    if ground == "auto":
        ground = "hills" if (oy + dh - horizon * dh) < H * 0.97 else "none"
    cols = custom[mode] if custom else PALETTES[pal][mode]
    if mode == "light" and light_level != 1.0:
        # --light-level: 0 = dark-mode sky, 1 = normal light mode, 2 = near white
        dark = custom["dark"] if custom else PALETTES[pal]["dark"]
        L = float(np.clip(light_level, 0, 2))
        if L < 1:
            cols = tuple(d + (c - d) * L for d, c in zip(dark, cols))
        else:
            cols = tuple(c + (1 - c) * (L - 1) * 0.85 for c in cols)
    oy = oy - horizon * dh                        # raise the horizon above the bottom edge
    rows = np.arange(H, dtype=F32)
    p = (oy + dh - (rows + 0.5)) / dh            # height above the design area's bottom edge
    line = sky_color(p, cols, transition)        # (H, 3)
    img = np.broadcast_to(line[:, None, :], (H, W, 3)).copy()

    if not classic:
        # soft glow hugging the horizon, plus dithering to avoid banding in 8-bit output
        hor = cols[0]
        g = np.exp(-np.maximum(p, 0) / (transition * 0.45)) * 0.35 * glow
        cx = (np.arange(W, dtype=F32) + 0.5 - ox) / dw
        bump = 0.75 + 0.25 * np.exp(-((cx - rng.uniform(0.3, 0.7)) / 0.45) ** 2)
        img += (g[:, None] * bump[None, :])[..., None] * hor
        # below the horizon (only seen on tall/portrait crops): the glow continues, dimming gently
        below = np.clip(-p, 0, None)[:, None, None]
        img *= 1 - np.clip(below * 0.6, 0, 0.18)

    if classic or star_style == "original":
        img = original_stars(img, rng, W, H, oy, dh, cols, transition, mode, stars, classic, light_stars)
    else:
        img = realistic_stars(img, rng, W, H, ox, oy, dw, dh, mode, stars, milkyway, light_stars)
    if evening_star:
        img = draw_evening_star(img, np.random.default_rng(seed + 1), W, H, ox, oy, dw, dh)

    if ground != "none":
        img = draw_ground(img, rng, W, H, ox, oy - horizon * dh, dw, dh, cols, mode, ground)
    if not classic:
        img += rng.normal(0, 0.6 / 255, img.shape).astype(F32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def draw_evening_star(img, rng, W, H, ox, oy, dw, dh):
    """One brilliant planet low over the horizon, same position in light and dark mode."""
    scale = max(1.0, H / 1080) ** 0.7
    x = ox + dw * rng.uniform(0.15, 0.85)
    y = oy + dh * (1 - rng.uniform(0.14, 0.3))
    r = int(110 * scale)
    y0, y1 = int(max(y - r, 0)), int(min(y + r + 1, H))
    x0, x1 = int(max(x - r, 0)), int(min(x + r + 1, W))
    gy, gx = np.mgrid[y0:y1, x0:x1].astype(F32)
    d = np.hypot(gx + 0.5 - x, gy + 0.5 - y)
    prof = (4.0 * np.exp(-0.5 * (d / (2.2 * scale)) ** 2)      # bright core
            + 0.45 * np.exp(-d / (7 * scale))                 # glow
            + 0.08 * np.exp(-d / (22 * scale)))               # wide haze
    col = np.array([1.0, 0.97, 0.9], F32)
    img[y0:y1, x0:x1] = 1 - (1 - img[y0:y1, x0:x1]) * np.exp(-prof[..., None] * col)
    return img


def draw_ground(img, rng, W, H, ox, oy, dw, dh, cols, mode, kind):
    """Dark land below the horizon: a flat silhouette ('dark') or low rolling hills ('hills')."""
    hor_row = oy + dh                                   # horizon line in pixels
    x = (np.arange(W, dtype=F32) + 0.5 - ox) / dh
    if kind == "hills":
        ridge = np.zeros(W, F32)
        for k in range(4):                                # a few octaves of smooth bumps
            f = rng.uniform(1.5, 3.0) * 2 ** k
            ridge += np.sin(x * f + rng.uniform(0, 6)) / 2 ** k
        ridge = (ridge - ridge.min()) / (ridge.max() - ridge.min() + 1e-6)
        ridge_row = hor_row - (0.006 + 0.03 * ridge ** 1.5) * dh
    else:
        ridge_row = np.full(W, hor_row, F32)
    rows = np.arange(H, dtype=F32)[:, None] + 0.5
    m = np.clip(rows - ridge_row[None, :] + 0.5, 0, 1)      # 1 px antialiased edge
    base = cols[2] * 0.55 + cols[0] * 0.04 if mode == "dark" else cols[2] * 0.6 + cols[1] * 0.1
    depth = np.clip((rows - hor_row) / (dh * 0.3), 0, 1)
    gcol = base[None, None, :] * (1.15 - 0.4 * depth)[..., None]   # a hint of sky light near the horizon
    return img * (1 - m[..., None]) + gcol * m[..., None]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--palette", choices=list(PALETTES), default="classic")
    ap.add_argument("--classic", action="store_true",
                    help="faithful to the original: hard gradient, 2500 pixel stars + 200 crosses, no glow")
    ap.add_argument("--colors", help="custom palette HORIZON,MID,TOP, e.g. '#ff4800,#006ebd,#000000' "
                                     "(dark mode; light mode is derived unless --colors-light is given)")
    ap.add_argument("--colors-light", help="custom light-mode palette HORIZON,MID,TOP")
    ap.add_argument("--sky-span", choices=["auto", "safe", "full"], default="auto",
                    help="vertical layout: 'safe' squeezes the whole gradient into the focus area; 'full' keeps "
                         "the horizon in the focus area but runs the sky to the top of the canvas "
                         "(auto = full when the focus area is smaller than the canvas, e.g. --size gnome)")
    ap.add_argument("--ground", choices=["auto", "none", "dark", "hills"], default="auto",
                    help="what fills the canvas below the horizon (seen on portrait crops); "
                         "auto = hills when there is space below the horizon")
    ap.add_argument("--horizon", type=float, default=0.0,
                    help="raise the horizon above the bottom edge (fraction of height, e.g. 0.1)")
    ap.add_argument("--fade", type=float, default=1.0,
                    help="height where the sky reaches its top colour (1 = top edge; 0.6 = dark sky from 60%% up)")
    ap.add_argument("--curve", type=float, default=1.0,
                    help="shape of the main gradient: <1 darkens quickly, >1 keeps the mid colour longer")
    ap.add_argument("--band", "--transition", dest="transition", type=float, default=0.2,
                    help="height of the horizon colour band as a fraction of the sky (original: 0.2)")
    ap.add_argument("--star-style", choices=["realistic", "original"], default="realistic",
                    help="realistic = photographic stars; original = the classic pixel + cross stars")
    ap.add_argument("--milkyway", action="store_true", help="add a Milky Way band (realistic stars)")
    ap.add_argument("--stars", type=float, default=1.0, help="star density multiplier")
    ap.add_argument("--light-stars", type=float, default=1.0,
                    help="stars in light mode: 0 = none, 1 = a few bright 'first stars' near the top (default), "
                         "~10 = every dark-mode star (the most it goes). Light-mode stars are always a "
                         "subset of the dark-mode ones, in the same positions")
    ap.add_argument("--light-level", type=float, default=1.0,
                    help="brightness of light mode: 0 = as dark as dark mode, 1 = normal (default), "
                         "1.3 = paler daytime look, 2 = near white")
    ap.add_argument("--evening-star", action="store_true",
                    help="add one brilliant 'evening star' (a planet like Venus) low in the sky")
    ap.add_argument("--glow", type=float, default=1.0, help="horizon glow strength (enhanced mode)")
    ap.add_argument("--mode", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--size", choices=list(SIZES),
                    help="size preset (overrides --width/--height); 'gnome' = 4096x4096 like GNOME's defaults")
    ap.add_argument("--ss", type=int, default=1, help="supersampling (1 keeps stars crisp)")
    ap.add_argument("--fast", action="store_true", help="960x600 quick preview")
    ap.add_argument("--focus", choices=["auto", "center", "full"], default="auto",
                    help="where to lay out the composition (see top-level README)")
    ap.add_argument("--targets", help=f"screen aspect ratios the image must work on, e.g. '{DEFAULT_TARGETS}'")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    if a.size:
        a.width, a.height = SIZES[a.size]
        if hasattr(a, "ss") and "--ss" not in sys.argv and a.width * a.height > 9_000_000:
            a.ss = 1                     # big presets: supersampling would be slow and memory-hungry
    GRAD.update(fade=a.fade, curve=a.curve)
    custom = None
    if a.colors or a.colors_light:
        dark = parse_colors(a.colors) if a.colors else PALETTES[a.palette]["dark"]
        light = parse_colors(a.colors_light) if a.colors_light else (lighten(dark) if a.colors else PALETTES[a.palette]["light"])
        custom = dict(dark=dark, light=light)
    tag = "-fast" if a.fast else ""
    if a.fast:
        k = 960 / max(a.width, a.height) if a.size else 0   # previews keep the preset's shape
        a.width, a.height, a.ss = (round(a.width * k), round(a.height * k), 1) if k else (960, 600, 1)
    W, H = a.width * a.ss, a.height * a.ss
    rect = focus_rect(W, H, a.focus, a.targets)
    for i in range(a.count):
        seed = a.seed + i if a.seed is not None else int(np.random.default_rng().integers(0, 100000))
        print(f"[{i + 1}/{a.count}] palette={a.palette} seed={seed}{' classic' if a.classic else ''}")
        for m in (["light", "dark"] if a.mode == "both" else [a.mode]):
            px = render(m, a.palette, W, H, seed, rect, a.classic, a.transition, a.stars, a.glow,
                        a.star_style, a.milkyway, a.horizon, custom, a.sky_span, a.ground,
                        a.light_stars, a.evening_star, a.light_level)
            im = Image.fromarray(px, "RGB")
            if a.ss > 1:
                im = im.resize((a.width, a.height), Image.LANCZOS)
            style = "classic" if a.classic else a.star_style + ("-milkyway" if a.milkyway else "")
            name = f"twilight-{style}-{'custom' if custom else a.palette}-{seed}-{m}{tag}.png"
            p = os.path.join(a.out, name)
            im.save(p, optimize=True)
            print("  ->", p)


if __name__ == "__main__":
    main()
