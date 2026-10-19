#!/usr/bin/env python3
"""Writes the Sheet music backdrop for the desktop and for the phone.

    RPM.Desktop/Assets/background-sheet-music.jpg                          3840 x 2351
    RPM.iOS/Modules/RPMUI/Sources/RPMUI/Resources/background-sheet-music.jpg  1320 x 2868

The picture is Pexels 104084 (Richard Revel, "Musical notes"), a grey close-up of a printed
score, named in scripts/backdrop-photos.json. This script colours and lights it to match a warm
sepia reference photograph, then makes the paper more yellow (YELLOW_*) so that the app's white text
can be read over it. The reference is not in the repository. Three sets of numbers were measured
from it and are used below:

  * TONE: the reference's mean colour at each luminance. It is applied as a gradient map, so the
    photograph keeps its own light and shade and takes the reference's colour at each level.
  * LIGHT: the reference's paper brightness, as the 85th percentile luminance of each cell of a
    10 x 7 grid. It is brightest towards the upper left and falls to about 40% at the lower right
    corner, with a shadow near the top right. The grid is used turned 180 degrees, so the light
    comes from the lower right. The app's white wordmark and tagline are in the top left, and they
    cannot be read over the brightest paper. The light here is adjusted until this picture
    measures the same as the turned grid.
  * FOCUS: the reference is sharp along one band and blurred away from it. Here the band is
    along the top of the frame, not across the middle as in the reference: the main window's
    content pane covers the middle, and the backdrop is directly visible only in the strip above
    it, in the side rails and in the margin under the transport bar. The blur increases slowly
    downwards, so that those margins do not look like a low resolution picture.

The photograph's own unevenness is divided out first, so the light here is the only light on it.

THE PHONE'S CUT IS MADE HERE, not by make_phone_backdrops.py. That script cuts a centre column out
of the desktop picture, which for this one would be 1082 pixels wide, stretched to 1320. So the
picture is rendered once at the phone's height (RENDER), the desktop's file is scaled down from it,
and the phone's file is a column of it at its own size. The column is the left one (PHONE_LEFT):
the phone writes each page's title in white at the top left, and the light puts the paper in the
top left in shade.

Needs the network once: the original is cached as scripts/.photocache/<id>-original.jpg, in the
cache that gen_playlist_photos.py uses. The suffix keeps it apart from the smaller renditions that
gen_playlist_photos.py caches by id alone.

Usage: python3 scripts/make_sheet_music.py
"""
import colorsys
import json
import workspace
import os
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = workspace.path("scripts", ".photocache")
ASSETS = workspace.path("RPM.Desktop", "Assets")
SWIFT = workspace.path("RPM.iOS", "Modules", "RPMUI", "Sources", "RPMUI", "Resources")
PHOTOS = workspace.path("scripts", "backdrop-photos.json")
FILE = "background-sheet-music.jpg"

# The Pexels server answers 403 to Python's default User-Agent (see gen_playlist_photos.py).
AGENT = "rpm-sheet-music/1.0"

# The other desktop backdrops are 3840 x 2351, and the phone's are 1320 x 2868
# (make_phone_backdrops.py). The JPEG qualities are the ones those files use.
SIZE = (3840, 2351)
QUALITY = 88
PHONE = (1320, 2868)
PHONE_QUALITY = 82
PHONE_LEFT = 0.0

# The desktop's shape at the phone's height. Every pixel size below (the blur sigmas) is given at
# the desktop's size and scaled by RENDER[0] / SIZE[0].
RENDER = (round(PHONE[1] * SIZE[0] / SIZE[1]), PHONE[1])

# Luminance (0-255) to colour, sampled from the reference every 16 to 32 levels. The value for 255
# is extrapolated.
TONE = [
    (0, (10, 5, 4)),
    (16, (26, 19, 15)),
    (32, (47, 34, 26)),
    (64, (91, 64, 49)),
    (96, (127, 95, 70)),
    (128, (159, 128, 93)),
    (160, (186, 162, 120)),
    (192, (211, 196, 154)),
    (224, (234, 228, 203)),
    (240, (247, 244, 235)),
    (255, (253, 251, 248)),
]

# The measured ramp's paper is nearly neutral cream (saturation 0.05 at the top), and the app's
# white text does not stand out against it. Each stop is pulled towards YELLOW_HUE (degrees) by
# YELLOW_PULL * v^2 and given YELLOW_SATURATION * v^2 more saturation, where v is the stop's
# brightness. The paper turns gold and the ink stays brown. HIGHLIGHTS * v^2 makes the brightest
# stops darker: the 95th percentile luminance goes from 241 to 199.
YELLOW_HUE = 46.0
YELLOW_PULL = 0.8
YELLOW_SATURATION = 0.32
HIGHLIGHTS = 0.12

# The reference's 85th percentile luminance per cell, 10 across and 7 down, measured with its
# watermarks masked out.
LIGHT = [
    [245, 251, 246, 212, 203, 234, 233, 209, 213, 172],
    [248, 249, 249, 239, 225, 185, 150, 177, 178, 172],
    [236, 246, 246, 235, 215, 212, 208, 195, 173, 184],
    [230, 209, 238, 241, 242, 227, 218, 199, 173, 152],
    [223, 223, 212, 234, 233, 229, 221, 194, 164, 128],
    [204, 228, 226, 215, 199, 204, 194, 177, 161, 102],
    [141, 188, 216, 208, 179, 157, 128, 111, 126, 100],
]
LIGHT_PASSES = 3

# The reference has more ink on the page than this photograph, so matching its brightest paper
# still leaves this picture lighter on average. A power on the lit value darkens the mid-tones
# until the mean colour matches (reference 181, 164, 135), without changing paper white or ink.
MIDTONES = 1.25

# Ink in the reference never reaches black: its darkest 1% is at luminance 25.
INK = 0.09

# The sharp band: a line through FOCUS_AT with FOCUS_SLOPE (pixels down per pixel right, so
# negative rises to the right), sharp for FOCUS_HALF of the frame height either side. Blur grows
# by BLUR_BELOW or BLUR_ABOVE pixels of Gaussian sigma per FOCUS_RAMP of the frame height beyond
# that, up to BLUR_MAX. Sigmas are at the output size.
FOCUS_AT = (0.5, 0.06)
FOCUS_SLOPE = -0.08
FOCUS_HALF = 0.08
FOCUS_RAMP = 0.25
BLUR_BELOW = 6.0
BLUR_ABOVE = 12.0
BLUR_MAX = 16.0
BLUR_LEVELS = [0.0, 2.0, 4.0, 7.0, 11.0, 16.0, 24.0]


def photo():
    with open(PHOTOS, encoding="utf-8") as f:
        return next(p for p in json.load(f)["photos"] if p["file"] == FILE)


def fetch(entry):
    path = os.path.join(CACHE, f"{entry['id']}-original.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(CACHE, exist_ok=True)
    request = urllib.request.Request(entry["source"], headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=120) as reply:
        blob = reply.read()
    with open(path, "wb") as f:
        f.write(blob)
    return path


# The word "Legato" above the first stave would be right behind the app's tagline, so it is painted
# out of the original (6000 x 4000) before anything else. Two dust specks above it, next to the
# wordmark, are removed too. Inside LEGATO_BOX, every pixel darker than LEGATO_INK_BELOW is ink. The
# mask is that ink grown by LEGATO_GROW pixels and cut off LEGATO_STAFF_CLEAR pixels above the
# stave's top line, which runs from LEGATO_STAFF_LINE[0] to LEGATO_STAFF_LINE[1]. Masked pixels
# take the level of the surrounding paper, plus the fine grain of the paper at LEGATO_GRAIN_SHIFT
# away. The shift follows the slope of the stave, so the grain comes from the same distance above
# the same line, which is clean.
LEGATO_BOX = (150, 380, 600, 700)
LEGATO_INK_BELOW = 110
LEGATO_GROW = 7
LEGATO_STAFF_LINE = ((175, 707), (560, 638))
LEGATO_STAFF_CLEAR = 14
LEGATO_GRAIN_SHIFT = (450, -81)


def without_legato(im):
    a = np.asarray(im).astype(np.float32)
    x0, y0, x1, y1 = LEGATO_BOX
    region = a[y0:y1, x0:x1].mean(axis=2)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    (lx0, ly0), (lx1, ly1) = LEGATO_STAFF_LINE
    line = ly0 + (xs - lx0) * (ly1 - ly0) / (lx1 - lx0)
    above = ys < line - LEGATO_STAFF_CLEAR

    ink = Image.fromarray(((region < LEGATO_INK_BELOW) & above).astype(np.uint8) * 255, "L")
    grown = ink.filter(ImageFilter.MaxFilter(2 * LEGATO_GROW + 1))
    mask = (np.asarray(grown) > 0) & above
    soft = gaussian(mask.astype(np.float32), 1.5) * mask.astype(np.float32)
    soft = np.maximum(soft, gaussian(mask.astype(np.float32), 1.5))

    keep = (~mask).astype(np.float32)
    dx, dy = LEGATO_GRAIN_SHIFT
    for ch in range(3):
        plane = a[y0:y1, x0:x1, ch]
        paper = gaussian(plane * keep, 20) / np.maximum(gaussian(keep, 20), 1e-3)
        donor = a[y0 + dy:y1 + dy, x0 + dx:x1 + dx, ch]
        grain = donor - gaussian(donor, 4)
        a[y0:y1, x0:x1, ch] = plane * (1 - soft) + (paper + grain) * soft
    return Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8), "RGB")


def cropped(im):
    """Cuts the 3:2 photograph to the backdrop's aspect, centred, and scales it to RENDER."""
    w, h = im.size
    target = RENDER[0] / RENDER[1]
    ch = round(w / target)
    top = (h - ch) // 2
    return im.crop((0, top, w, top + ch)).resize(RENDER, Image.LANCZOS)


def gaussian(a, sigma):
    """Returns a Gaussian blur of a float array, computed with the FFT. The edges are reflected so
    that nothing wraps around."""
    if sigma <= 0:
        return a
    pad = int(3 * sigma) + 1
    p = np.pad(a, pad, mode="reflect")
    fy = np.fft.fftfreq(p.shape[0])[:, None]
    fx = np.fft.rfftfreq(p.shape[1])[None, :]
    kernel = np.exp(-2 * (np.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    out = np.fft.irfft2(np.fft.rfft2(p) * kernel, s=p.shape)
    return out[pad:-pad, pad:-pad]


def grid85(a, cells):
    """Returns the 85th percentile of each cell of a grid. `cells` is (across, down)."""
    h, w = a.shape
    gx, gy = cells
    grid = np.empty((gy, gx), np.float32)
    for j in range(gy):
        for i in range(gx):
            grid[j, i] = np.percentile(a[j * h // gy:(j + 1) * h // gy, i * w // gx:(i + 1) * w // gx], 85)
    return grid


def spread(grid, h, w, smooth):
    """Returns a grid of values stretched to the frame and smoothed, so that cell edges do not show."""
    return gaussian(np.asarray(Image.fromarray(grid, "F").resize((w, h), Image.BICUBIC)), smooth)


def paper_field(lum):
    """Returns the photograph's own paper brightness, which is divided out."""
    h, w = lum.shape
    return spread(grid85(lum, (24, 15)), h, w, h / 30)


def light(flat):
    """Returns a light field such that flat * field measures LIGHT in LIGHT's grid."""
    h, w = flat.shape
    target = np.rot90(np.array(LIGHT, np.float32), 2) / 255
    cells = (target.shape[1], target.shape[0])
    field = spread(target, h, w, h / 12)
    for _ in range(LIGHT_PASSES):
        field *= spread(target / grid85(flat * field, cells), h, w, h / 12)
    return field


def blur_map(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x0, y0 = FOCUS_AT[0] * w, FOCUS_AT[1] * h
    d = ((y - y0) - FOCUS_SLOPE * (x - x0)) / np.hypot(1, FOCUS_SLOPE) / h
    beyond = np.clip((np.abs(d) - FOCUS_HALF) / FOCUS_RAMP, 0, None)
    return np.minimum(np.where(d > 0, BLUR_BELOW, BLUR_ABOVE) * beyond, BLUR_MAX) * w / SIZE[0]


def defocused(a, sigma):
    """Blurs each pixel by its own sigma: blends the two precomputed levels on either side of it."""
    scale = a.shape[1] / SIZE[0]
    steps = [s * scale for s in BLUR_LEVELS]
    levels = [gaussian(a, s) for s in steps]
    out = np.zeros_like(a)
    for k in range(len(steps) - 1):
        lo, hi = steps[k], steps[k + 1]
        sel = (sigma >= lo) & (sigma <= hi)
        t = (sigma[sel] - lo) / (hi - lo)
        out[sel] = levels[k][sel] * (1 - t) + levels[k + 1][sel] * t
    return out


def yellowed(tone):
    """Returns TONE pushed towards gold, more in the paper than in the ink."""
    out = []
    for level, (r, g, b) in tone:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h = h + (YELLOW_HUE / 360 - h) * YELLOW_PULL * v * v
        s = min(1.0, s + YELLOW_SATURATION * v * v)
        v = v * (1 - HIGHLIGHTS * v * v)
        out.append((level, tuple(c * 255 for c in colorsys.hsv_to_rgb(h, s, v))))
    return out


def toned(lum):
    tone = yellowed(TONE)
    at = np.array([s for s, _ in tone], np.float32)
    rgb = np.stack([np.interp(lum, at, [c[ch] for _, c in tone]) for ch in range(3)], axis=-1)
    return np.clip(np.round(rgb), 0, 255).astype(np.uint8)


def main():
    im = cropped(without_legato(Image.open(fetch(photo())).convert("RGB")))
    a = np.asarray(im).astype(np.float32)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    h, w = lum.shape

    flat = np.clip(lum / paper_field(lum), 0, 1.05)
    flat = INK + (1 - INK) * flat
    flat = defocused(flat, blur_map(h, w))
    lit = np.clip(flat * light(flat), 0, 1) ** MIDTONES * 255

    whole = Image.fromarray(toned(lit), "RGB")

    desktop = os.path.join(ASSETS, FILE)
    whole.resize(SIZE, Image.LANCZOS).save(desktop, quality=QUALITY, optimize=True, progressive=True)
    print(f"{desktop}: {os.path.getsize(desktop) // 1024} KB")

    left = round(PHONE_LEFT * (w - PHONE[0]))
    phone = os.path.join(SWIFT, FILE)
    whole.crop((left, 0, left + PHONE[0], PHONE[1])).save(
        phone, quality=PHONE_QUALITY, optimize=True, progressive=True)
    print(f"{phone}: {os.path.getsize(phone) // 1024} KB")


if __name__ == "__main__":
    sys.exit(main())
