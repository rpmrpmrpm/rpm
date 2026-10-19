#!/usr/bin/env python3
"""Builds RPM.Desktop/Assets/radio-set.png, the radio set that the player tunes.

This is the counterpart of the record. When a station is playing there is no record: nothing is
pressed and nothing is turning, so the disc on the strip would be wrong. The radio set is the object
that is correct then: a pocket transistor radio seen from the front, in the same light and at the
same exposure as the disc next to it, so the two look like two objects photographed in one
morning and not like an illustration swapped in for a render.

WHAT IS SHARED WITH THE RECORD
------------------------------
It imports the phone renderer for the parts that do not depend on being a record: the anisotropic
BRDF, the blackbody curve and the tonemap. It also copies the TABLE's morning lighting exactly: the
same sun in the same place at the same temperature, the same weak second sun on the far side, and
the same sky (see make_vinyl_table.MORNING). If the sun is moved there, this image must move with
it, because the light is what the two objects have in common.

The final exposure is the DISC's, not the table's (DISC_MEAN / DISC_SPREAD), for the same reason the
disc has its own: a single object that fills a square, exposed for a frame that is mostly the dark
between records, comes out grey.

NEUTRAL, like the disc
----------------------
The materials are plain dark plastic and plain chrome with no colour of their own, because the app
tints the image per station, in the same way as it presses a record per sleeve: a neutral render
multiplied by a unit-luminance hue is one asset for every colour. VinylPressing does the multiplying.

There is no needle. The dial is rendered EMPTY (its card, its rule and its printed figures only),
because the needle is the one moving part. The app draws its own needle over the glass and moves it.
The record uses the same split: the disc is baked, and the label that turns is drawn by the app.

Usage: python3 make_radio_set.py
"""
import os
import workspace
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_vinyl_ground as g                                            # noqa: E402
import make_vinyl_table as t                                             # noqa: E402

ASSETS = workspace.path("RPM.Desktop", "Assets")
OUT = os.path.join(ASSETS, "radio-set.png")

# The size of the finished asset, and the supersampling factor. The shell draws the set at a few
# hundred points, as it draws the disc. The supersampling keeps the grille from shimmering: the holes
# are two millimetres across and all that can be seen of them is at their rim.
W = H = 1024
SS = 3

# The width of the whole picture in millimetres. Everything below is in millimetres from the CASE's
# centre. The frame is centred on the drawn objects and not on the case, so the aerial has room in
# its corner.
CANVAS_MM = 236.0
FRAME_AT = (17.0, -46.0)

# ── the set ────────────────────────────────────────────────────────────────────────────────────────
#
# A pocket transistor radio, about the real size of such sets: a little wider than a hand, with a
# dial across the top, the speaker below it and the tuning knob to the right of the speaker. The
# proportions are all that says "radio" at forty points, so keep them: a squarer set looks like a
# lunchbox and a wider one looks like a car stereo.
CASE_W, CASE_H = 190.0, 118.0
CASE_R = 16.0

# The rounding of the case's edge. A moulded plastic shell has no sharp corner, and the band of light
# that runs round this rounding is most of what makes the object look solid.
BEVEL = 7.0

# The dial: a window across the top, its glass sunk into a chamfered channel.
DIAL = (-78.0, -47.0, 78.0, -17.0)      # left, top, right, bottom
DIAL_R = 5.0
DIAL_CHAMFER = 3.4

# The speaker and its punched holes. The grille sits slightly below the face, so the light catches its
# rim. A grille level with the case looks like a pattern printed on the front.
SPEAKER_AT = (-45.0, 22.0)
SPEAKER_R = 34.0
GRILLE_R = 31.0
HOLE_R = 1.15
HOLE_STEP = 4.6

# The tuning knob: a dome with a knurled rim, as a real knob has for a thumb to grip.
KNOB_AT = (50.0, 24.0)
KNOB_R = 20.0
KNOB_RISE = 7.0
KNURLS = 44

# The aerial, from the top right corner. It is a tapering rod, like a telescopic aerial.
ROD_FROM = (72.0, -55.0)
ROD_TO = (126.0, -148.0)
ROD_R0, ROD_R1 = 2.3, 1.35
ROD_TIP = 2.7

# ── what the parts are made of ─────────────────────────────────────────────────────────────────────
#
# Albedo is how much light the material returns; roughness is along and across its own grain. Both
# matter more than they seem to. The case and the grille differ in this picture not by colour (they
# are within one per cent) but because one is isotropic plastic and the other is metal brushed
# sideways, and a viewer sees two materials from that difference alone.
CASE_ALBEDO = 0.033
CASE_ROUGH = (0.30, 0.33)

GRILLE_ALBEDO = 0.030
GRILLE_ROUGH = (0.09, 0.24)            # brushed across the set, so it is smooth from left to right

HOLE_ALBEDO = 0.004
CARD_ALBEDO = 0.17                      # the dial's card, the only pale part of the set
INK_ALBEDO = 0.020
CHROME_ALBEDO = 0.020

# How much more specular light a material returns than the dielectric that the BRDF assumes (see F0
# in the phone renderer). Chrome is a mirror, glass is a thin sheet of mirror, and plastic is what F0
# already describes.
GAIN_PLASTIC = 1.3
GAIN_GRILLE = 3.6
GAIN_GLASS = 11.0
GAIN_CHROME = 11.0

# The dial's glass. It is a specular-only sheet over the printing: it has no albedo of its own, and
# its effect on the card behind it is the only sign that anything is in front of the card.
#
# The glass is CURVED, and that is why it looks like glass. A flat sheet facing the camera returns
# the same amount of light everywhere, and an even veil over the printing is not a reflection: it
# looks like a lighter card. The plastic window on these sets bulges, so the band of light crosses
# it, and the band is what makes it look like something in front of something else.
GLASS_ROUGH = (0.085, 0.085)
#
# Bowed in BOTH directions, and the sideways bow is needed: the camera looks down z and the sun is
# above and to the right, so the half vector between them has an x component. A window that curves
# only from top to bottom has no point whose normal matches that half vector, so it returns an
# even wash that is brightest where the glass is nearest to correct and dimmest where it is
# furthest. That looks like a lighter card, not a reflection.
GLASS_BOW = (0.10, 0.55)                # how far its normal tips across the window, and down it

# The whole sheet is also tipped a little to the right, which puts the streak on the glass and not
# in its corner. A window whose normals face the camera and a little to each side meets the light's
# half vector at one corner only. Leaning it moves that meeting point into a line across the dial,
# where the reflection on a curved dial really is.
GLASS_LEAN = 0.33

# The bow of the front face. A moulded front is never flat: it swells a millimetre or two towards the
# middle. Under a sun with no falloff, that swell is the ONLY thing that gives the front of the set a
# gradient. Without it, the front renders as one flat tone with a lit edge round it.
FACE_BOW = (0.13, 0.09)

# How much the sky's reflection may add to a highlight. The lamps light the set; the sky's
# reflection fills the parts they miss. At the table's own value the whole set would be edged in blue,
# because every surface would act as a mirror that reflects only the sky.
#
# The value is set per material, because this is the difference between a metal and everything else.
# A dielectric returns about a twentieth of the light that hits it at normal incidence, and a
# polished metal returns nearly all of it: chrome is bright because it shows the sky. A single limit
# for both gives a dark aerial wire or a blue case, and no setting avoids both.
ENV_SPEC = 0.26

# How much of the sky's colour a reflection of it keeps.
ENV_TINT = 0.42
ENV_PLASTIC, ENV_GRILLE, ENV_GLASS, ENV_CHROME = 0.7, 3.0, 5.0, 14.0

# How dark a hole is. This is not a shading term: a hole is a place the sky cannot reach, and this
# is the fraction of the sky that still reaches it.
HOLE_AO = 0.10
RECESS_AO = 0.62

# The morning lighting, taken whole from the table so the two objects share one light.
P = t.MORNING

# The disc's exposure (see the module docstring).
MEAN, SPREAD = t.DISC_MEAN, t.DISC_SPREAD

# The colour saturation, which is NOT the table's. The table's value of 1.35 is for a frame of black
# vinyl, where the only colour is a warm sheen and a blue shadow, and neither is close to clipping. A
# plastic case has twice the albedo of vinyl, so it has a real diffuse colour to amplify, and
# amplifying it that much turns a dark grey set maroon.
SATURATION = 1.12


def px_per_mm(scale):
    return W * scale / CANVAS_MM


def grid(scale):
    """Every pixel's position on the set, in millimetres from the case's centre."""
    w = h = W * scale
    ppm = px_per_mm(scale)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    return ((xs - w / 2) / ppm + FRAME_AT[0],
            (ys - h / 2) / ppm + FRAME_AT[1])


# ── the shapes, as distances ───────────────────────────────────────────────────────────────────────
#
# Every part is a signed distance in millimetres (positive inside), not a drawn mask, because the
# distance does three jobs at once. It gives the coverage, antialiased over one pixel by clipping. It
# gives the bevel, since the distance IS how far a point is from the edge. And its gradient is the
# direction the edge faces, which is the normal of every rounded edge on the set. A mask can only do
# the first of these.

def rounded_rect(x, y, box, radius):
    left, top, right, bottom = box
    cx, cy = (left + right) / 2, (top + bottom) / 2
    hw, hh = (right - left) / 2 - radius, (bottom - top) / 2 - radius
    dx = np.abs(x - cx) - hw
    dy = np.abs(y - cy) - hh
    outside = np.hypot(np.maximum(dx, 0), np.maximum(dy, 0))
    inside = np.minimum(np.maximum(dx, dy), 0)
    return radius - (outside + inside)


def disc(x, y, at, radius):
    return radius - np.hypot(x - at[0], y - at[1])


def rod(x, y, a, b, r0, r1):
    """A tapering capsule: the distance to the aerial, and how far along it each point is."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = float(np.hypot(dx, dy))
    ux, uy = dx / length, dy / length

    along = np.clip((x - ax) * ux + (y - ay) * uy, 0.0, length)
    across = (x - ax) * -uy + (y - ay) * ux
    radius = r0 + (r1 - r0) * (along / length)
    return radius - np.hypot((x - ax) - along * ux, (y - ay) - along * uy), across, radius, (ux, uy)


def cover(distance, ppm):
    """Converts a distance to a coverage: a ramp one pixel wide at the edge."""
    return np.clip(distance * ppm + 0.5, 0.0, 1.0)


def facing(distance, ppm):
    """Which way the edge of a shape faces: the gradient of the distance field, normalised.

    It is read from the field and not calculated for each shape, so a rounded edge on a rounded
    rectangle, a circle and a rod all use the same three lines of code.
    """
    gy, gx = np.gradient(distance)
    gx = gx * ppm
    gy = gy * ppm
    norm = np.maximum(np.hypot(gx, gy), 1e-6)
    return -gx / norm, -gy / norm


def roll(normal, distance, out_x, out_y, width, drop, mask):
    """Tips the surface over an edge: a quarter round `width` millimetres wide.

    `distance` is how far inside the shape a point is, so this tilts what is within `width` of the
    edge and leaves the middle of the face alone.
    """
    t = np.clip(1.0 - np.clip(distance, 0.0, width) / width, 0.0, 1.0)
    angle = (np.pi / 2) * (t ** 0.85) * drop
    sin, cos = np.sin(angle), np.cos(angle)
    nx, ny, nz = normal
    nx = np.where(mask, out_x * sin, nx)
    ny = np.where(mask, out_y * sin, ny)
    nz = np.where(mask, cos, nz)
    return nx, ny, nz


def dial_card(scale):
    """What is printed behind the glass: the rule and its figures only.

    It is drawn with the drawing library, not with arithmetic, because it is PRINTING: a ruled scale
    and a row of numbers is what that library is for, and the render only needs to know where the
    ink is.
    """
    ppm = px_per_mm(scale)
    left, top, right, bottom = DIAL
    box = (int((left - FRAME_AT[0]) * ppm + W * scale / 2),
           int((top - FRAME_AT[1]) * ppm + H * scale / 2),
           int((right - FRAME_AT[0]) * ppm + W * scale / 2),
           int((bottom - FRAME_AT[1]) * ppm + H * scale / 2))

    ink = Image.new("L", (W * scale, H * scale), 0)
    pen = ImageDraw.Draw(ink)

    x0, y0, x1, y1 = box
    inset = int(11.0 * ppm)
    x0, x1 = x0 + inset, x1 - inset

    # The scale is ruled as on every radio: a long mark where a figure is printed and short marks
    # between them. The marks get closer towards the top of the band, because a dial is a frequency
    # scale and frequency is not spaced evenly along it.
    marks = 41
    rule = int(max(1, 0.55 * ppm))
    for i in range(marks):
        u = i / (marks - 1)
        place = u ** 1.22                        # the marks get closer at the far end
        x = int(x0 + (x1 - x0) * place)
        long = (i % 5 == 0)
        length = (y1 - y0) * (0.40 if long else 0.22)
        pen.line([(x, y1 - int((y1 - y0) * 0.14)),
                  (x, y1 - int((y1 - y0) * 0.14) - int(length))], fill=255, width=rule)

    # The figures. A megahertz scale, as the band of a station is measured in megahertz.
    size = int((y1 - y0) * 0.30)
    font = None
    for face in ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(face):
            font = ImageFont.truetype(face, size)
            break

    if font is not None:
        for i, figure in enumerate(("88", "92", "96", "100", "104", "108")):
            u = i / 5
            x = int(x0 + (x1 - x0) * (u ** 1.22))
            box_ = pen.textbbox((0, 0), figure, font=font)
            pen.text((x - (box_[2] - box_[0]) / 2, y0 + (y1 - y0) * 0.10), figure,
                     fill=210, font=font)

    return np.asarray(ink, dtype=np.float32) / 255.0


def build(scale):
    """The set as fields: what each pixel is made of and which way it faces."""
    ppm = px_per_mm(scale)
    x, y = grid(scale)

    shell = rounded_rect(x, y, (-CASE_W / 2, -CASE_H / 2, CASE_W / 2, CASE_H / 2), CASE_R)
    rod_d, rod_across, rod_r, rod_dir = rod(x, y, ROD_FROM, ROD_TO, ROD_R0, ROD_R1)
    tip = disc(x, y, ROD_TO, ROD_TIP)
    aerial = np.maximum(rod_d, tip)

    alpha = np.maximum(cover(shell, ppm), cover(aerial, ppm))

    # Everything starts as the flat front of the case, facing the camera.
    nx = np.zeros_like(x)
    ny = np.zeros_like(x)
    nz = np.ones_like(x)

    albedo = np.full_like(x, CASE_ALBEDO)
    along = np.full_like(x, CASE_ROUGH[0])
    across = np.full_like(x, CASE_ROUGH[1])
    gain = np.full_like(x, GAIN_PLASTIC)
    env = np.full_like(x, ENV_PLASTIC)
    ao = np.ones_like(x)

    # The tangent that every anisotropic surface is brushed along. It is sideways across the set for
    # the grille and along the rod for the aerial. The other surfaces are isotropic, so it does not
    # matter for them.
    tx = np.ones_like(x)
    ty = np.zeros_like(x)

    # The swell of the front: the normals tip with the position on the face, so the sun makes a
    # gradient across a surface that is otherwise one plane facing the camera.
    nx = nx + FACE_BOW[0] * np.clip(x / (CASE_W / 2), -1, 1)
    ny = ny + FACE_BOW[1] * np.clip(y / (CASE_H / 2), -1, 1)

    # ── the rounded edge of the case ──
    out_x, out_y = facing(shell, ppm)
    nx, ny, nz = roll((nx, ny, nz), shell, out_x, out_y, BEVEL, 1.0, shell > 0)

    # A moulded shell is not a mirror: a fine pebble grain over the whole shell stops the band of
    # light on the bevel from looking like a smooth gradient.
    grain = pebble(x.shape, ppm, scale)
    nx = nx + grain[0]
    ny = ny + grain[1]

    # ── the dial, sunk into the front ──
    dial = rounded_rect(x, y, DIAL, DIAL_R)
    inside = dial > 0
    face_x, face_y = facing(dial, ppm)

    # Its chamfer: the wall of the recess, tipped INWARD (the edge of the shell tips outward), so the
    # light along the top of the case runs the other way along the top of the channel.
    nx, ny, nz = roll((nx, ny, nz), dial, -face_x, -face_y, DIAL_CHAMFER, 1.0, inside)

    # The bezel: the channel round the window is a chrome ring, as on most sets. It is the only bright
    # line on the front, and at the size the app draws this image it is most of what shows that
    # there is a dial.
    bezel = inside & (dial <= DIAL_CHAMFER)
    albedo = np.where(bezel, CHROME_ALBEDO, albedo)
    along = np.where(bezel, 0.10, along)
    across = np.where(bezel, 0.16, across)
    gain = np.where(bezel, GAIN_CHROME * 0.7, gain)
    env = np.where(bezel, ENV_CHROME * 0.18, env)

    card = dial_card(scale)
    lit_card = inside & (dial > DIAL_CHAMFER)
    albedo = np.where(lit_card, CARD_ALBEDO + (INK_ALBEDO - CARD_ALBEDO) * card, albedo)
    along = np.where(lit_card, 0.55, along)
    across = np.where(lit_card, 0.55, across)
    gain = np.where(lit_card, 0.35, gain)
    env = np.where(lit_card, ENV_GLASS, env)
    sunk = np.clip((dial - DIAL_CHAMFER) / 4.0, 0.0, 1.0)
    ao = np.where(inside, np.where(dial > DIAL_CHAMFER, 0.55 + 0.40 * sunk, RECESS_AO), ao)
    albedo = np.where(lit_card, albedo * (0.72 + 0.28 * sunk), albedo)

    # ── the speaker ──
    well = disc(x, y, SPEAKER_AT, SPEAKER_R)
    in_well = well > 0
    well_x, well_y = facing(well, ppm)
    nx, ny, nz = roll((nx, ny, nz), well, -well_x, -well_y, 2.6, 1.0, in_well)

    plate = well > 2.6
    albedo = np.where(plate, GRILLE_ALBEDO, albedo)
    along = np.where(plate, GRILLE_ROUGH[0], along)
    across = np.where(plate, GRILLE_ROUGH[1], across)
    gain = np.where(plate, GAIN_GRILLE, gain)
    env = np.where(plate, ENV_GRILLE, env)
    ao = np.where(in_well, np.where(plate, 0.94, RECESS_AO), ao)

    # The holes. They are punched, so each has a rounded lip and a dark inside. The lip is what makes
    # the grille look like pierced metal and not like a dotted pattern.
    holes = punched(x, y)
    lip = 0.45
    pierced = holes > -lip
    hole_x, hole_y = facing(holes, ppm)
    nx, ny, nz = roll((nx, ny, nz), np.maximum(-holes, 0.0), -hole_x, -hole_y,
                      lip, 0.85, pierced & plate)

    dark = (holes > 0) & plate
    albedo = np.where(dark, HOLE_ALBEDO, albedo)
    gain = np.where(dark, 0.25, gain)
    env = np.where(dark, 0.4, env)
    ao = np.where(dark, HOLE_AO, ao)

    # ── the tuning knob ──
    knob = disc(x, y, KNOB_AT, KNOB_R)
    on_knob = knob > 0
    dx, dy = x - KNOB_AT[0], y - KNOB_AT[1]
    reach = np.clip(np.hypot(dx, dy) / KNOB_R, 0.0, 1.0)

    # A dome: flat in the middle and curving down at the rim, which is the profile of a thumbwheel
    # and not half a ball. The knurling is added on top of it, in the radial direction, as it is cut.
    slope = (KNOB_RISE / KNOB_R) * reach ** 2.4
    angle = np.arctan(slope * 2.2)
    unit = np.maximum(np.hypot(dx, dy), 1e-6)
    kx, ky = dx / unit, dy / unit

    knurl = np.sin(np.arctan2(dy, dx) * KNURLS) * 0.16 * np.clip((reach - 0.55) / 0.35, 0, 1)
    angle = angle + knurl

    nx = np.where(on_knob, kx * np.sin(angle), nx)
    ny = np.where(on_knob, ky * np.sin(angle), ny)
    nz = np.where(on_knob, np.cos(angle), nz)
    albedo = np.where(on_knob, CASE_ALBEDO * 1.25, albedo)
    along = np.where(on_knob, 0.22, along)
    across = np.where(on_knob, 0.22, across)
    gain = np.where(on_knob, 1.4, gain)

    # What a raised part does to the face under it: less sky reaches where it meets the case.
    ao = np.where(on_knob, ao, np.minimum(ao, 0.55 + 0.45 * np.clip(-knob / 5.0, 0, 1)))

    # ── the aerial ──
    on_rod = rod_d > 0
    curve = np.clip(rod_across / np.maximum(rod_r, 1e-6), -1.0, 1.0)
    ux, uy = rod_dir
    px, py = -uy, ux                                   # across the rod, the direction in which it curves

    nx = np.where(on_rod, px * curve, nx)
    ny = np.where(on_rod, py * curve, ny)
    nz = np.where(on_rod, np.sqrt(np.clip(1.0 - curve ** 2, 0.0, 1.0)), nz)

    # The ball on the end of the aerial.
    on_tip = tip > 0
    tdx, tdy = x - ROD_TO[0], y - ROD_TO[1]
    tcurve = np.clip(np.hypot(tdx, tdy) / ROD_TIP, 0.0, 1.0)
    tunit = np.maximum(np.hypot(tdx, tdy), 1e-6)
    nx = np.where(on_tip, tdx / tunit * tcurve, nx)
    ny = np.where(on_tip, tdy / tunit * tcurve, ny)
    nz = np.where(on_tip, np.sqrt(np.clip(1.0 - tcurve ** 2, 0.0, 1.0)), nz)

    chrome = on_rod | on_tip
    albedo = np.where(chrome, CHROME_ALBEDO, albedo)
    along = np.where(chrome, 0.11, along)
    across = np.where(chrome, 0.19, across)
    gain = np.where(chrome, GAIN_CHROME, gain)
    env = np.where(chrome, ENV_CHROME, env)
    tx = np.where(chrome, ux, tx)
    ty = np.where(chrome, uy, ty)

    # The glass over the dial is kept apart from everything above: it has no colour of its own and
    # does not dim what is behind it, so it is a separate specular sheet that is added at the end. Its
    # normal is the flat front of the case, bent a little at the channel.
    glass = lit_card
    left, top, right, bottom = (DIAL[0] + DIAL_CHAMFER, DIAL[1] + DIAL_CHAMFER,
                                DIAL[2] - DIAL_CHAMFER, DIAL[3] - DIAL_CHAMFER)
    bow_x = GLASS_LEAN + np.clip((x - (left + right) / 2) / ((right - left) / 2), -1.0, 1.0) * GLASS_BOW[0]
    bow_y = np.clip((y - (top + bottom) / 2) / ((bottom - top) / 2), -1.0, 1.0) * GLASS_BOW[1]
    glass_nx, glass_ny = bow_x, bow_y
    glass_nz = np.sqrt(np.clip(1.0 - bow_x ** 2 - bow_y ** 2, 0.0, 1.0))

    norm = np.maximum(np.sqrt(nx * nx + ny * ny + nz * nz), 1e-6)
    return dict(alpha=alpha, nx=nx / norm, ny=ny / norm, nz=nz / norm,
                albedo=albedo, along=along, across=across, gain=gain, env=env, ao=ao,
                tx=tx, ty=ty, glass=glass,
                glass_nx=glass_nx, glass_ny=glass_ny, glass_nz=glass_nz)


def punched(x, y):
    """The grille's holes, as one distance field: how far inside a hole each point is.

    A square lattice on the set's own axes, not a hexagonal one: real sets were punched on a press,
    and a press works in rows.
    """
    ox = (x - SPEAKER_AT[0]) % HOLE_STEP - HOLE_STEP / 2
    oy = (y - SPEAKER_AT[1]) % HOLE_STEP - HOLE_STEP / 2
    holes = HOLE_R - np.hypot(ox, oy)

    # Only where there is metal to punch, and away from the rim of the plate.
    return np.where(disc(x, y, SPEAKER_AT, GRILLE_R) > 0, holes, -HOLE_R)


def pebble(shape, ppm, scale):
    """The moulded grain of the shell: a fine random tilt, at the size of a real grain.

    It is built by blurring random noise, not with a noise function. Blurred noise has no direction,
    which is the property that matters here, and a grain with a direction looks like brushed metal.
    """
    rng = np.random.default_rng(4471)
    field = rng.integers(0, 256, shape, dtype=np.uint8)
    field = np.asarray(
        Image.fromarray(field, mode="L").filter(ImageFilter.GaussianBlur(0.34 * ppm)),
        dtype=np.float32) / 255.0
    gy, gx = np.gradient(field)
    strength = 0.014 / max(float(np.abs(gx).mean()), 1e-6)
    return gx * strength, gy * strength


def sky(dx, dy, dz):
    """The colour of the morning sky in a given direction: the table's gradient, from horizon to zenith.

    Screen up is -y, so a surface facing up the frame faces the sky.
    """
    up = np.clip(-dy, -1.0, 1.0)
    t = np.clip((up * 0.5 + 0.5), 0.0, 1.0) ** P["bend"]
    zenith = np.asarray(P["zenith"], dtype=np.float32)
    horizon = np.asarray(P["horizon"], dtype=np.float32)
    tint = horizon + (zenith - horizon) * t[..., None]
    tint = tint / max(float(np.asarray(P["horizon"]) @ g.LUMA), 1e-6)

    # Moved back towards grey before anything reflects it. The table's sky is blue and the records
    # under it are nearly black, so the blue appears as a cast in their shadows. A chrome aerial and
    # a chrome bezel are MIRRORS, and a mirror that reflects that same sky becomes a blue wire and a
    # neon outline, which looks like a lit sign and not a radio on a table.
    grey = (tint * g.LUMA.astype(np.float32)).sum(-1, keepdims=True)
    return grey + (tint - grey) * ENV_TINT


def render(scale):
    parts = build(scale)
    nx, ny, nz = parts["nx"], parts["ny"], parts["nz"]
    tx, ty = parts["tx"], parts["ty"]

    # The tangent, made perpendicular to the normal so that the anisotropy lies in the surface and
    # not through it.
    dot = tx * nx + ty * ny
    ttx, tty, ttz = tx - dot * nx, ty - dot * ny, -dot * nz
    tn = np.maximum(np.sqrt(ttx ** 2 + tty ** 2 + ttz ** 2), 1e-6)
    ttx, tty, ttz = ttx / tn, tty / tn, ttz / tn

    lit = np.zeros(nx.shape + (3,), dtype=np.float32)

    for light in P["lights"]:
        lx, ly, lz = np.asarray(light["at"], dtype=np.float32) / \
            np.linalg.norm(light["at"])
        colour = g.kelvin(light["kelvin"]) * light["power"]

        ndl, spec = g.shade(nx, ny, nz, ttx, tty, ttz, lx, ly, lz,
                            parts["along"], parts["across"])

        lit += (parts["albedo"] * ndl)[..., None] * colour
        lit += (spec * ndl * parts["gain"])[..., None] * colour

        # The glass on the dial, added over the printing behind it and not mixed into it.
        gx, gy, gz = parts["glass_nx"], parts["glass_ny"], parts["glass_nz"]
        gndl, glare = g.shade(gx, gy, gz,
                              np.ones_like(gy), np.zeros_like(gy), np.zeros_like(gy),
                              lx, ly, lz, GLASS_ROUGH[0], GLASS_ROUGH[1])
        lit += (glare * gndl * GAIN_GLASS * parts["glass"])[..., None] * colour

    # The sky: what a surface receives from everything that is not a lamp, and the reflection of it,
    # which is most of what chrome looks like.
    ambient = sky(nx, ny, nz) * P["fill"] * g.kelvin(P["fill_kelvin"])
    lit += ambient * (parts["albedo"] * parts["ao"])[..., None]

    rz = 2.0 * nz * nz - 1.0                          # the view is down z, so this is the mirror direction
    rx, ry = 2.0 * nz * nx, 2.0 * nz * ny
    fresnel = g.F0 + (1.0 - g.F0) * (1.0 - np.clip(nz, 0, 1)) ** 5
    lit += (sky(rx, ry, rz) * P["fill"] * g.SKY_SPEC * ENV_SPEC) * \
        (fresnel * parts["env"] * parts["ao"])[..., None]

    return lit, parts["alpha"]


def shrink(array, mode):
    image = Image.fromarray(np.clip(array * 255, 0, 255).astype(np.uint8), mode=mode)
    return np.asarray(image.resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0


def main():
    lit, alpha = render(SS)

    out = shrink(g.tonemap(lit), "RGB")
    coverage = shrink(alpha[..., None].repeat(3, axis=2), "RGB")[:, :, 0]

    luma = g.LUMA.astype(np.float32)
    grey = out @ luma

    # The set's exposure, measured over the set only: the frame is mostly empty, and including that
    # would raise every tone to compensate. The numbers are the DISC's, so the two objects have the
    # same brightness on the strip.
    body = grey[coverage > 0.5]
    gain = float((SPREAD / 255.0) / max(body.std(), 1e-5))
    out = np.clip(out * gain + (MEAN / 255.0 - float(body.mean()) * gain), 0.0, 1.0)

    grey = out @ luma
    out = np.clip(grey[..., None] + (out - grey[..., None]) * SATURATION, 0.0, 1.0)

    rgba = np.dstack([out * 255, coverage * 255]).astype(np.uint8)
    image = Image.fromarray(rgba, mode="RGBA")
    image.save(OUT, optimize=True)
    print("wrote", OUT, image.size, f"{os.path.getsize(OUT) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
