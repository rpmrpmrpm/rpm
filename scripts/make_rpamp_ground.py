#!/usr/bin/env python3
"""The RPaMp skin's ground: flowing bands of cyan light in deep blue.

Writes RPM.Desktop/Assets/background-rpamp.jpg, which the four panels of the player wear under
their veils (RPaMpView.xaml). Run it from the repository root:

    python3 scripts/make_rpamp_ground.py

This picture belongs to the RPaMp skin only; nothing else uses it.

HOW IT IS DRAWN
---------------
The picture is made of ribbons, not blobs. Each ribbon is a curve across the frame (two sines at
different rates plus a tilt, so it does not repeat within the width). The light falls off on both
sides of the curve as a Gaussian whose width grows and shrinks along its length. A narrow bright
filament follows the same curve at a fraction of the weight. It gives the band a clear crest
without an outline.

The ribbons are SUMMED and then put through a soft knee (1 - exp(-k*f)). Summing makes two crossing
ribbons look like one brighter sheet, not two lines on top of each other. The knee stops the crossing
from becoming white, which a plain normalisation does not prevent.

The colour is a ramp through the app's own palette, darkened: near-black navy for most of the frame,
the palette's blue in the middle and its cyan along the crests. Both are darker than they are on a
button. The bright end stays well below white on purpose: this is a background, and a background
that reaches white makes the text on top of it hard to read.

WHAT IT IS SIZED FOR
--------------------
Each panel draws the picture UniformToFill in its own rectangle, so each panel shows a different
crop: the player's stack is 440 wide and the library beside it is 880. The bands run the full width
and are spread down the frame, not composed for one view, because no panel shows the whole frame.
"""

from pathlib import Path
import workspace

import numpy as np
from PIL import Image, ImageFilter

W, H = 2560, 1600

# The bands. Each is a curve and a thickness:
#   y0     where it crosses the left edge, as a fraction of the height
#   tilt   how far it falls (or rises) across the frame
#   amp    how far the sine moves it up and down, and freq how many cycles it makes
#   phase  where in that sine it starts
#   width  half-thickness of the light on each side of the curve
#   swell  how much that thickness changes along the length
#   weight how bright it is
BANDS = [
    dict(y0=0.18, tilt=0.30, amp=0.10, freq=0.9, phase=0.0, width=0.20, swell=0.55, weight=1.00),
    dict(y0=0.44, tilt=-0.22, amp=0.13, freq=0.6, phase=2.1, width=0.16, swell=0.70, weight=0.90),
    dict(y0=0.72, tilt=0.18, amp=0.09, freq=1.2, phase=4.0, width=0.22, swell=0.45, weight=0.85),
    dict(y0=1.02, tilt=-0.26, amp=0.11, freq=0.8, phase=1.2, width=0.18, swell=0.60, weight=0.70),
    dict(y0=-0.06, tilt=0.16, amp=0.08, freq=1.5, phase=3.3, width=0.14, swell=0.50, weight=0.55),
]

ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
xs /= W
ys /= H

TAU = np.float32(2 * np.pi)

field = np.zeros((H, W), dtype=np.float32)
for band in BANDS:
    # Two rates, so the curve does not repeat inside the frame and no crop looks like a plain wave.
    curve = (
        band["y0"]
        + band["tilt"] * xs
        + band["amp"] * np.sin(TAU * band["freq"] * xs + band["phase"])
        + 0.35 * band["amp"] * np.sin(TAU * (band["freq"] * 2.3) * xs + band["phase"] * 1.7)
    )

    width = band["width"] * (1.0 + band["swell"] * np.sin(TAU * 0.45 * xs + band["phase"] * 0.6))
    width = np.maximum(width, 0.04)

    d = (ys - curve) / width
    glow = np.exp(-d * d)

    # The filament: the same curve at a fifth of the thickness and about a fifth of the weight. It
    # gives the band a crest without an edge.
    core = np.exp(-(d * 5.0) ** 2)

    field += band["weight"] * (glow + 0.22 * core)

# A wide fall-off from the top left, so the frame is lit from one side and not evenly.
field *= 1.0 - 0.20 * (xs * 0.65 + ys * 0.35)

field -= field.min()
field /= np.percentile(field, 99.0)

# A soft knee, not a clip: two crossing bands add up, and a plain normalisation would turn the
# crossing white and leave the rest of the frame dark.
field = 1.0 - np.exp(-1.05 * np.clip(field, 0, None))
field /= field.max()

# An exponent well above 1: the bands are a background, so most of the frame must stay in the dark
# end of the ramp and only the crests reach the blue.
field = field ** 2.35

# The ramp: deep navy background, the palette's blue in the middle, cyan along the crests.
STOPS = [
    (0.00, (0x03, 0x06, 0x0E)),
    (0.22, (0x04, 0x0C, 0x1C)),
    (0.45, (0x05, 0x16, 0x30)),
    (0.66, (0x05, 0x28, 0x52)),
    (0.84, (0x04, 0x4C, 0x8C)),   # the palette's blue, darkened
    (0.96, (0x05, 0x86, 0xC6)),
    (1.00, (0x14, 0xAE, 0xE2)),   # its cyan, on the crests only
]

pos = np.array([s[0] for s in STOPS], dtype=np.float32)
cols = np.array([s[1] for s in STOPS], dtype=np.float32)
rgb = np.stack([np.interp(field, pos, cols[:, c]) for c in range(3)], axis=-1)

# A vignette, so the corners of the panels stay dark and the text on them stays readable.
vx = (xs - 0.5) * 2
vy = (ys - 0.5) * 2
vignette = 1.0 - 0.26 * np.clip(vx * vx + vy * vy, 0, 1.6) / 1.6
rgb *= vignette[..., None]

img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")

# One soft blur over the whole image. The field is already smooth; this removes the last banding in
# the dark half, where eight bits per channel give the fewest steps.
img = img.filter(ImageFilter.GaussianBlur(radius=W / 300))

# A little grain, for the same reason: a large dark gradient shows bands on a real screen, and noise
# of less than a quarter of a level prevents it.
rng = np.random.default_rng(7)
grain = rng.normal(0, 1.6, (H, W, 1)).astype(np.float32)
out = np.clip(np.asarray(img, dtype=np.float32) + grain, 0, 255).astype(np.uint8)

OUT = workspace.at("RPM.Desktop/Assets/background-rpamp.jpg")
Image.fromarray(out, "RGB").save(OUT, quality=92, optimize=True, progressive=True)
print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
