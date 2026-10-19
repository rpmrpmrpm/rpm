#!/usr/bin/env python3
"""Builds RPM.Desktop/Assets/header-vinyl.jpg, the dialog-header background.

It is rendered with the phone ground's renderer (make_vinyl_ground.py), so the header and the
phone's ground are the same material: the same duotone, matched to the same brightness and spread
(HEADER_MEAN, HEADER_SPREAD).

What differs from the phone ground: one record instead of three, seen close up, with its centre off
the lower left so the grooves cross the strip as steep arcs; finer grooves; a visible strip of
ungrooved vinyl between tracks (SEAM_LAND); and the lights placed for a wide, short frame.

The dialog shows only the middle of this image (a 112 px band at the dialog's width, UniformToFill)
with the title at the left. The seed is chosen so that the bright edge of a track gap is not behind
the title.

Usage: python3 scripts/make_header_vinyl.py
"""
import os
import workspace
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import make_vinyl_ground as ground  # noqa: E402

OUT = workspace.path("RPM.Desktop", "Assets", "header-vinyl.jpg")

W, H = 1200, 320
SS = 2

# One record. The centre is in frame widths and heights from the top left, and the radius is in frame
# widths. The radius is large enough that the rim stays out of the frame.
RECORD = dict(centre=(-0.72, 2.2), radius=1.95, seed=118)

GROOVE_PITCH = 3.5      # px at 1x; the phone uses 7
SEAM_LAND = 34.0        # px at 1x
SEAM_LAND_DEPTH = 5.0   # px at 1x
GRAIN = 0.45

# Positions in frame widths, heights, heights (z towards the viewer). The key light is above the
# frame to the right, along the grooves' radius. The grooves reflect it back only from there.
KEY_POS = (1.1, -1.2, 1.3)
FILL_POS = (-0.3, 1.2, 1.2)
FALLOFF_REF = 1.4       # frame heights


def main():
    ground.W, ground.H = W, H
    ground.RECORDS = [RECORD]
    ground.SCALE_RECORD = 0
    ground.GROOVE_PITCH = GROOVE_PITCH
    ground.GROOVE_DEPTH = ground.GROOVE_DEPTH * GROOVE_PITCH / 7.0
    ground.SEAM_LAND = SEAM_LAND
    ground.SEAM_LAND_DEPTH = SEAM_LAND_DEPTH
    ground.GRAIN = GRAIN
    ground.KEY_POS = KEY_POS
    ground.FILL_POS = FILL_POS
    ground.FALLOFF_REF = FALLOFF_REF
    ground.P = ground.BLUE

    body, sheen = ground.render(W * SS, H * SS, SS)
    body = ground.shrink(ground.tonemap(body), "L")
    sheen = ground.shrink(ground.tonemap(sheen), "RGB")

    out = ground.finish(body, sheen, ground.HEADER_MEAN, ground.HEADER_SPREAD)
    out.save(OUT, quality=88)
    print("wrote", os.path.normpath(OUT), out.size, f"{os.path.getsize(OUT) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
