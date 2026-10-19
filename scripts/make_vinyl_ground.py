#!/usr/bin/env python3
"""Builds background-vinyl.jpg, the phone's background for both phone apps.

The picture shows three records, lit.

The desktop's dialog header (RPM.Desktop/Assets/header-vinyl.jpg) is rendered by this same code,
with one record close up, by make_header_vinyl.py. Both pictures are matched to the same
brightness and spread (HEADER_MEAN, HEADER_SPREAD).

HOW IT IS RENDERED
------------------
The picture is rendered, not painted as a brightness field. There is a light at a position, a
surface with a normal at every pixel, and a BRDF between them. Because the light has a position, it
can cast shadows onto a second surface, and the result is correct at any point without hand tuning.

  * The grooves are GEOMETRY, not a ripple added to a brightness. At 7 px pitch and 2x
    supersampling there are fourteen pixels across every groove, which is enough to carry the real
    profile. The surface normal tilts radially with the groove wall and the light is evaluated
    against it. Every stretched lobe of sheen that a record shows comes from this by itself.

  * On top of the resolved groove, the microfacet term is ANISOTROPIC, because the cut is: a lathe
    drags along the groove and leaves it smoother lengthways than across. This is the difference
    between vinyl and black plastic, and it is one number per axis (see ROUGH_ALONG / ROUGH_ACROSS).

  * Three records lie in a pile, each across the ones below it. They hide each other and cast real
    shadows: the ray from a point on a lower record to the light is tested against every disc above
    it. The offset of the shadows is the record's real thickness, 1.9 mm against a 302 mm disc,
    scaled to this image (see THICKNESS_MM). The soft edge is the size of the lamp seen from that
    distance, which is what a penumbra is, and it widens with the gap, so the shadow two records
    down is softer.

  * The crevices where the records meet are darker, because a point in the angle between two
    surfaces sees less of the sky than a point in the open. This is ambient occlusion.

  * There are two lamps, each with a colour TEMPERATURE and not a fixed colour. Their positions are
    not a matter of taste: see the note above KEY_POS.

The tones at the end are matched to the header's brightness and spread and given a duotone, so the
phone's background and the desktop's dialogs are the same material. Two things may differ from it:
the top of the tonal range, where the bulb is visible and not the vinyl (see the note on
`warmth`), and the supporter's pressing, which returns more light than carbon black (see PRESSINGS).

Usage: python3 scripts/make_vinyl_ground.py [blue] [gold]

It presses TWO backgrounds from one render (see PRESSINGS). The blue one is the app's and the gold
one is the supporter's. They are the same picture in two compounds.
"""
import os
import workspace
import sys
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(__file__)

# The two apps that use this picture. The Uno phone app reads it from its own Assets folder and the
# Swift app reads it from the RPMUI package's resources. Both must be the same file, so the script
# writes both and nobody has to copy it by hand.
UNO = workspace.path("RPM.Mobile", "Assets")
SWIFT = workspace.path("RPM.iOS", "Modules", "RPMUI", "Sources", "RPMUI", "Resources")

# The tallest phone Apple ships (iPhone 16 Pro Max, 3x). UniformToFill crops the rest.
W, H = 1320, 2868

# Supersampling factor. A groove is 7 px across at 1x, and shading geometry that fine without
# supersampling gives aliasing, not detail.
SS = 2

# The image is rendered in horizontal strips. The full frame at 2x is fifteen megapixels and the
# shader holds a couple of dozen arrays at once, which needs gigabytes if done in one pass.
STRIP = 384

# The duotone of the desktop header. It is kept apart from the pressings below because it is not a
# choice: the header and the phone's background are the same material and must keep the same colour.
HEADER_SHADOW = (3, 16, 30)
HEADER_HIGH = (73, 153, 221)

# The brightness and spread (0-255, before the duotone) that both pictures are matched to. They set
# how dark the flat areas are and how far the sheen reaches.
HEADER_MEAN = 48.275
HEADER_SPREAD = 27.133


# ── the pile ───────────────────────────────────────────────────────────────────────────────────
#
# Three records, listed from the bottom of the pile upwards. Centres are in screen widths and heights
# from the top left, and radii are in screen widths. Every centre is outside the frame, so no label
# is visible and the grooves cross the screen as long arcs and not as bullseyes.
#
#   * The ground: the centre is far to the LEFT, and the record is big enough to reach every corner.
#     If the centre is moved further out, the arcs straighten until they look like a record the size
#     of a building. If it is moved in, they curl up and compete with the artwork drawn over them.
#
#   * A corner clip at the TOP RIGHT: its rim enters halfway along the top edge and leaves by the
#     right edge a sixth of the way down. It is only a corner on purpose: every page puts its title
#     at the top LEFT, and that area must stay quiet.
#
#   * The record that carries the picture: its centre is off the BOTTOM RIGHT, and its rim sweeps up
#     across the lower half. Its grooves curve the other way from the ground's, which makes the two
#     look like two records at rest and not like one record drawn twice.
#
# Each record is one record thickness above the one before it. The shadows and the crevices come from
# this.
RECORDS = [
    dict(centre=(-0.75, 0.46), radius=3.40, seed=45),
    dict(centre=(1.28, -0.30), radius=1.05, seed=77),
    dict(centre=(1.30, 1.21), radius=1.72, seed=118),
]

# The record whose radius sets the scale: the millimetre values below are measured against it.
SCALE_RECORD = 2

# How much dimmer each step down the pile is. A record at the bottom of a pile is in a shallow well:
# less of the sky reaches it, and what arrives comes at a low angle. This is that effect as one
# number, and it makes the ground look underneath the others and not merely beside them.
LAYER_DIMMING = 0.62

# A 12" record is 302 mm across and 1.9 mm thick. The values are scaled to this image: the record
# named by SCALE_RECORD is 151 mm in radius, so one millimetre is its radius in pixels divided by
# 151. The whole sense of depth depends on this number, because it is the only thing that separates
# one surface from the next.
THICKNESS_MM = 1.9
RECORD_RADIUS_MM = 151.0

# The rounded edge of a pressing, and the smooth lip inside it that carries no groove. Both are in
# millimetres, for the same reason.
BEVEL_MM = 1.5
LIP_MM = 3.4

# How much rougher that rounded edge is than the face. The rim of a pressing is the one part that is
# not polished, and a mirror-smooth rim would return the lamp as a white wire with a hard edge and
# not as the soft line of light that a real record edge shows.
BEVEL_ROUGHEN = 3.4


# ── the surface ────────────────────────────────────────────────────────────────────────────────

GROOVE_PITCH = 7.0          # px at 1x, about 2 pt on a 3x phone
GROOVE_DEPTH = 1.15         # px at 1x. Shallower than it is wide, as a real groove is.

# A lit groove is not a sine. The light catches the land as a broad flat area and the wall falls
# away steeply, so the profile is a wide crown over a narrow valley. A half-cosine raised to a power
# has that shape, and its derivative (which is what the shading needs) is one line.
RIDGE_POWER = 3.0

# How rough the surface is along the groove and across it. The cut is dragged lengthways, so the
# surface is smoother in that direction, and that difference is why the highlight on a record is a
# long streak and not a round spot. Both values are GGX alphas.
ROUGH_ALONG = 0.055
ROUGH_ACROSS = 0.115

# Vinyl. Very black (an albedo of two per cent) with the ordinary dielectric reflectance of
# polished plastic over it (n of about 1.55 gives F0 of about 0.047).
ALBEDO = 0.022
F0 = 0.047

# How much radius one track takes. It is drawn from a lognormal distribution and not a flat range,
# because track lengths are not evenly spread: most are around three or four minutes, a few are
# long, and an occasional short one is half that. A flat range gives bands that all have about the
# same width, which a real record face never has.
TRACK_MEDIAN = 250              # px at 1x
TRACK_SPREAD = 0.62             # log-sigma; about 0.5x to 2x the median
TRACK_MIN, TRACK_MAX = 85, 780

# The ungrooved land between two tracks, in px at 1x, and the depth of its shallow valley. Both are
# zero here: at the phone's scale a seam is one wider groove. make_header_vinyl.py sets both,
# because at the header's scale the gap is wide enough to be seen as smooth vinyl.
SEAM_LAND = 0.0
SEAM_LAND_DEPTH = 0.0

# Per-pixel variation in how much light the pressing returns, as a standard deviation around 1.
GRAIN = 0.030


# ── the light ──────────────────────────────────────────────────────────────────────────────────
#
# Positions are in screen widths and heights, with z pointing out of the screen towards the viewer.
# The camera is orthographic and looks straight down the z axis, which is correct for a background
# lying flat under a phone's glass.
#
# WHERE THE KEY LIGHT HAS TO BE (this is not a matter of taste):
#
#   * A groove's normal tilts along the RADIUS, so a groove returns light to the camera only where
#     the in-plane direction of the half-vector lies along that radius. A key light at the top left
#     (where a room light usually is in photographs of records) fails here: the lower record has its
#     centre at the left, so its radii run across the frame, at right angles to the half-vector, and
#     its grooves disappear completely.
#
#   * The shadow falls AWAY from the light, and it can only be seen on the lower record, which is
#     above and to the left of the upper record's rim. So the key must be below and to the right of
#     the upper record.
#
# Both conditions give the same answer: the key is at the lower right, close enough that its
# distance across the frame is what draws the sheen.
KEY_POS = (1.26, 1.06, 0.60)
KEY_POWER = 0.62

# A fill light at the LEFT, which is also needed. The key lies along the radius of the record it
# lights, and the radii of the ground run the other way across the frame. With the key alone, the
# ground has a gradient and no grooves, so it looks like a sheet of plastic and not a record. A
# second lamp on the ground's own axis restores the grooves. It is weaker and low, so it draws the
# texture and not a second sheen that competes with the first.
FILL_POS = (-0.62, 0.34, 0.52)
FILL_POWER = 0.30

# The distance at which a light's stated power is its actual power. Light falls off with the square
# of the distance, which is most of what draws the sheen into a band and not a wash: the far corner
# of a phone screen is three times further from a lamp at the near corner than the near corner is.
FALLOFF_REF = 0.55          # in screen heights

# The size of the key light, in screen widths. Only the penumbra depends on it: a bigger lamp gives
# a softer edge under the upper record, which is what "soft light" means.
KEY_SIZE = 0.85

# The sky: what a surface facing up receives from everything that is not a lamp. It is small,
# because a record in a dim room is nearly black, but its specular part is not negligible, and it
# keeps a groove readable in the parts of the frame that no lamp reaches.
SKY = 0.024
SKY_SPEC = 2.6


# ── the colour of the light ────────────────────────────────────────────────────────────────────
#
# Both lamps have a colour temperature and are not white, because almost no room has white light.
# The aim is the warm white of a bulb and not the yellow of a candle, so the temperatures are around
# a halogen lamp: warm enough to look warm against the blue, but nowhere near amber.
#
# The sky is the opposite end: the app's own azure, which is also the colour the material is
# duotoned to. A warm key against a cool ambient is the oldest lighting set-up, and it is why a
# highlight can look warm on a surface that is blue everywhere else.
#
# The temperatures themselves are set per pressing: see PRESSINGS.

# How much of the lamp's own colour the highlights get (`warmth` in a pressing).
#
# This is a real physical distinction and not just a setting. Light that comes back from a
# dielectric (vinyl, glass, water) splits in two: the light that goes INTO the material and comes
# back out carries the material's colour, and the light that bounces straight off the surface
# carries the colour of the LIGHT. That is why a black record under a tungsten bulb has warm white
# glints and is black everywhere else, and why tinting the whole picture towards the lamp only
# looks like a colour cast.
#
# So the two are kept apart all the way through: the body of the picture is the material, duotoned
# to the desktop's blue, and the sheen on top of it is the lamp. Zero gives a monochrome picture,
# and one gives every highlight entirely to the bulb.
#
# It is set per pressing, because a gold record is not a dielectric all the way through: the
# metallic flake in the compound reflects with the colour of the METAL and not of the lamp. That is
# why the sweep on a gold pressing is gold and on a black one it is white. See PRESSINGS.

# The level of brightness above which the lamp's colour starts to replace the material's.
#
# This is a decision and not a physical fact. A black record is almost entirely surface reflection,
# because almost no light goes into the vinyl and comes back out. The physically honest result is a
# grey record with warm highlights, and that is what the render gives: the blue disappears from the
# picture. The blue is required, because it makes this the same material as the desktop's dialog
# headers.
#
# So the lamp gets the top of the range and the material keeps the rest. This is also what the eye
# expects: a highlight is where a light source is seen almost directly, and the rest of a lit
# surface looks like the colour of the object and not of the lamp.
#
# The level is HIGH ON PURPOSE, and higher than it looks. The tones are matched to HEADER_MEAN and
# HEADER_SPREAD at the end, and those are dark: the 99th percentile of such tones is only
# about 0.63. So a level of 0.62 catches the rim and a few crests and nothing else, which is the
# aim: a glint, not a lit corner.
#
# Do not read it as a percentile of the finished picture. That puts the ramp in the MIDDLE of the lit
# half, where the picture has small variations that it should have (one band pressed slightly duller
# than the next, the slow mottle of the pressing). Crossing a colour threshold there turns each of
# those into a patch of a different colour, and the bottom corner looks marbled. So this is a fixed
# level that stays above almost everything, and the matching step decides where "almost everything"
# is.
WARM_FROM = 0.62

# How far the crevice darkening reaches from the rim of the upper record, in record thicknesses. A
# point one thickness away from a step still has most of its sky; a point against it has half.
AO_REACH = 5.0


# ── the pressings ──────────────────────────────────────────────────────────────────────────────
# The same three records, in two compounds. Everything above this line is the picture: where the
# discs lie, where the lamps stand, how a groove is cut. Nothing here moves any of it. A pressing
# states a COLOUR and nothing else, so the two backgrounds are the same photograph of the same
# table.
#
# Each pressing states what its material is and what its room is, and nothing else:
#
#   shadow / high   the duotone. Black and white of the matched render map to these, with a straight
#                   line between.
#
#   warmth          how much of a highlight is the lamp's colour and not the material's.
#
#   key / fill      the colour temperatures of the lamps.
#
#   sky, sky_tint   what the room returns, and how far the ambient is moved from neutral white
#                   towards it.
#
#   lift            what the compound returns, compared with the black compound that the tones are
#                   matched to: the header's mean and spread, times these.
#
#   name, heads     the file name suffix and the apps the file is written to.
BLUE = dict(
    name="",
    shadow=HEADER_SHADOW,
    high=HEADER_HIGH,
    # Black vinyl is a dielectric: what comes off the surface is the colour of the bulb, not of the record.
    warmth=0.92,
    # The header's own brightness and spread, which this picture is matched to.
    lift=(1.0, 1.0),
    # A domestic bulb, and no lower: vinyl turns amber below this.
    key=4000,
    fill=3600,
    # The app's azure. A warm key against a cool ambient is the oldest lighting set-up.
    sky=HEADER_HIGH,
    # How blue the ambient may be, from neutral at 0 to the full azure at 1. At 1, the shadows have
    # no red left and the darks go flat.
    sky_tint=0.34,
    heads=(UNO, SWIFT),
)

# The supporter's background. It follows the same reasoning as the desktop's gold table
# (make_vinyl_table.py, the GOLD preset): the room changes, not the objects.
#
#   * The compound is the desktop supporter backdrop's own, measured from that picture and not mixed
#     by hand (see the note on `shadow` below). It is the palette's gold, #EFAF12, as the two lamps
#     of that picture return it.
#
#   * The lamps are lowered to filament colour, as in the desktop's gold table. Gold under a 4000 K
#     LED looks like brass.
#
#   * The room stays COOLER than the lamps. This is the main point and is easy to get wrong. A warm
#     key in a warm room gives a sepia photograph: nothing is warm relative to anything else, so
#     nothing looks like gold. So the ambient is not moved towards gold. It is the desktop's 8200 K
#     fill, a pale cool white, and the gold comes from the compound and the lamps and not from a wash
#     over everything.
GOLD = dict(
    name="-gold",
    # Measured from RPM.Desktop/Assets/background-gold.jpg and not mixed by hand: a straight line per
    # channel against that picture's brightness, evaluated at the two ends of the blue ramp. So this
    # is the colour of the desktop's gold crate at black and at white, and the two supporter
    # backgrounds are the same metal on both platforms.
    shadow=(22, 13, 4),
    high=(207, 130, 50),
    # A gold pressing has metallic flake in the compound, and metal reflects with its own colour. Most
    # of the sweep stays gold and does not turn warm white, which is what makes it look like metal.
    # With the bulb's 0.92 the picture washes out to beige.
    warmth=0.45,
    key=3150,
    fill=2750,
    # 8200 K, as sRGB. The fill of the desktop's gold table, which is far cooler than the lamps.
    sky=(218, 228, 255),
    sky_tint=1.0,
    # More light, because this is not carbon black. A record is black because it ABSORBS light, and
    # the desktop gives a pigmented pressing several times the reflectance of a black one for this
    # reason (COLOUR_ALBEDO in make_vinyl_table.py). This is the same photograph, exposed for a
    # material that is not black. Mean and spread are set separately: the mean hardly moves, so the
    # top of the frame (where every page puts its title) stays as dark as before, and the spread
    # carries the sweep up into gold. Raising both together only made a lighter picture, not a
    # brighter metal.
    lift=(1.25, 1.50),
    # The Swift app only: it is the only one with a supporter background so far, and an 800 kB
    # picture that nothing reads is 800 kB added to a download.
    heads=(SWIFT,),
)

PRESSINGS = {"blue": BLUE, "gold": GOLD}

# The pressing in use. Set by __main__ and read by everything that colours.
P = BLUE


def px_per_mm(scale):
    return RECORDS[SCALE_RECORD]["radius"] * W * scale / RECORD_RADIUS_MM


def band_edges(seed, rmax, scale):
    """Where one track ends and the next begins, out to rmax. The result is the same for the same seed."""
    rng = np.random.default_rng(seed)
    edges = [0.0]
    while edges[-1] < rmax:
        length = np.clip(rng.lognormal(np.log(TRACK_MEDIAN), TRACK_SPREAD), TRACK_MIN, TRACK_MAX)
        edges.append(edges[-1] + length * scale)

    edges = np.asarray(edges, dtype=np.float32)
    centres = ((edges[:-1] + edges[1:]) / 2).astype(np.float32)

    # How glossy each band is. A pressing is not uniform: some bands come off the stamper slightly
    # duller than their neighbours. The value is interpolated ACROSS the bands and not held constant
    # within them, because a record is one plane, and a constant value in each band would look like
    # a step down to a lower level.
    gloss = rng.uniform(0.72, 1.18, size=len(centres)).astype(np.float32)
    return edges, centres, gloss


class Record:
    """One disc: where it is, how big, and where its tracks fall."""

    def __init__(self, centre, radius, seed, w, h, scale):
        self.cx = centre[0] * w
        self.cy = centre[1] * h
        self.radius = radius * w
        self.scale = scale
        self.pitch = GROOVE_PITCH * scale
        self.depth = GROOVE_DEPTH * scale

        mm = px_per_mm(scale)
        self.bevel = BEVEL_MM * mm
        self.lip = LIP_MM * mm

        # Far enough out to cover any pixel in the frame.
        rmax = np.hypot(max(abs(self.cx), abs(w - self.cx)), max(abs(self.cy), abs(h - self.cy)))
        self.edges, self.centres, self.gloss = band_edges(seed, rmax, scale)

    def surface(self, x, y):
        """The normal, the tangent along the groove, and how glossy it is, at every point given.

        Returns unit vectors as component arrays. A full 3-vector per pixel as an (h,w,3) array is
        three copies of the frame for every intermediate, and there are many intermediates.
        """
        dx = x - self.cx
        dy = y - self.cy
        r = np.hypot(dx, dy)

        inv = 1.0 / np.maximum(r, 1e-6)
        rx = dx * inv                    # radial unit vector, in the plane
        ry = dy * inv

        # ── the groove, as a shape ──
        #
        # h(r) = -depth * (1 - ridge(r)), so the land is at zero and the valley at -depth. The
        # shading needs the slope, and the slope of a raised half-cosine is one product rule.
        phase = r * (2.0 * np.pi / self.pitch)
        crown = 0.5 + 0.5 * np.cos(phase)
        ridge = crown ** RIDGE_POWER
        slope = (self.depth * RIDGE_POWER * crown ** (RIDGE_POWER - 1.0)
                 * (-0.5 * np.sin(phase)) * (2.0 * np.pi / self.pitch))

        # The outer lip carries no groove: a pressing has a few millimetres of smooth land inside the
        # rim before the lead-in starts.
        cut = np.clip((self.radius - self.lip - r) / (0.5 * self.lip), 0.0, 1.0)
        slope = slope * cut

        # The land between tracks, when SEAM_LAND is set: the groove fades out over one pitch and the
        # surface follows a shallow cosine valley, h = -D/2 (1 + cos(pi d / half)), where d is the
        # signed distance to the nearest track edge.
        land = np.zeros_like(r)
        if SEAM_LAND > 0:
            half = 0.5 * SEAM_LAND * self.scale
            flat = r.ravel()
            i = np.clip(np.searchsorted(self.edges, flat), 1, len(self.edges) - 1)
            lo, hi = self.edges[i - 1], self.edges[i]
            d = np.where(flat - lo < hi - flat, flat - lo, flat - hi).reshape(r.shape)
            land = np.clip((half - np.abs(d)) / self.pitch, 0.0, 1.0)
            valley = (SEAM_LAND_DEPTH * self.scale * 0.5 * np.pi / half
                      * np.sin(np.pi * np.clip(d / half, -1.0, 1.0)))
            slope = slope * (1.0 - land) + valley * land
            ridge = ridge * (1.0 - land)

        # ── the rounded edge ──
        #
        # The last millimetre of a record curves over. The normal turns with it, from straight up at
        # the lip to nearly horizontal at the rim. This puts a bright wire of light along the edge,
        # and it is most of what shows that one record is lying on another.
        inside = np.clip((self.radius - r) / max(self.bevel, 1e-6), 0.0, 1.0)
        tilt = (1.0 - inside) ** 0.65 * (0.5 * np.pi * 0.92)

        # N = the bevel's normal, then tilted again by the groove's radial slope.
        st, ct = np.sin(tilt), np.cos(tilt)
        nx = st * rx - slope * ct * rx
        ny = st * ry - slope * ct * ry
        nz = ct + slope * st
        norm = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
        nx *= norm
        ny *= norm
        nz *= norm

        # The groove runs AROUND the record, so its direction is the tangent to the circle. It is made
        # perpendicular to the normal, because a tangent that is not perpendicular gives an
        # anisotropy that points in a direction the surface does not go.
        tx, ty, tz = -ry, rx, np.zeros_like(r)
        d = tx * nx + ty * ny + tz * nz
        tx = tx - d * nx
        ty = ty - d * ny
        tz = tz - d * nz
        tnorm = 1.0 / np.maximum(np.sqrt(tx * tx + ty * ty + tz * tz), 1e-6)
        tx *= tnorm
        ty *= tnorm
        tz *= tnorm

        gloss = np.interp(r.ravel(), self.centres, self.gloss).astype(np.float32).reshape(r.shape)

        # The seam between one track and the next is a SINGLE groove cut wider and deeper, not a dark
        # band. A real record has one groove there, and drawing a band would make the flat areas look like
        # separate panels.
        seam = np.zeros_like(r)
        near = self.edges[(self.edges > r.min() - 4 * self.pitch) & (self.edges < r.max() + 4 * self.pitch)]
        for e in near:
            seam += np.exp(-(((r - e) / (0.85 * self.pitch)) ** 2))

        # How much rougher this pixel is than the face: the seam is a deeper cut with steeper walls,
        # and the rounded rim was never polished.
        rough = 1.0 + 1.6 * np.minimum(seam, 1.0) + (BEVEL_ROUGHEN - 1.0) * (1.0 - inside)
        # The land was never cut, so it is smoother than the grooved face.
        rough = rough * (1.0 - 0.5 * land)

        return r, nx, ny, nz, tx, ty, tz, gloss, rough, ridge


def shade(nx, ny, nz, tx, ty, tz, lx, ly, lz, rough_along, rough_across):
    """One light on one surface: anisotropic GGX, Smith masking, Schlick Fresnel.

    The camera looks straight down z, so the view vector is (0,0,1) and drops out of most of this.
    """
    ndl = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)

    # Half vector between the light and the view. V = (0,0,1), so this is L with 1 added to z.
    hx, hy, hz = lx, ly, lz + 1.0
    hn = 1.0 / np.maximum(np.sqrt(hx * hx + hy * hy + hz * hz), 1e-6)
    hx *= hn
    hy *= hn
    hz *= hn

    # The bitangent: across the groove, where the surface is rougher.
    bx = ny * tz - nz * ty
    by = nz * tx - nx * tz
    bz = nx * ty - ny * tx

    ht = hx * tx + hy * ty + hz * tz
    hb = hx * bx + hy * by + hz * bz
    hn_ = np.clip(hx * nx + hy * ny + hz * nz, 1e-6, 1.0)

    at, ab = rough_along, rough_across
    denom = (ht / at) ** 2 + (hb / ab) ** 2 + hn_ ** 2
    d_term = 1.0 / (np.pi * at * ab * np.maximum(denom, 1e-8) ** 2)

    # Smith masking, isotropic in the effective alpha. An anisotropic G would make a difference that
    # is invisible next to the D term and costs four more arrays.
    a2 = (at * ab)
    ndv = np.clip(nz, 1e-4, 1.0)
    g1l = 2.0 * ndl / np.maximum(ndl + np.sqrt(a2 * a2 + (1.0 - a2 * a2) * ndl * ndl), 1e-6)
    g1v = 2.0 * ndv / np.maximum(ndv + np.sqrt(a2 * a2 + (1.0 - a2 * a2) * ndv * ndv), 1e-6)

    # Fresnel: the light that comes back off a dielectric at a glancing angle, which on a record at
    # the far edge of the sheen is most of what is seen.
    ldh = np.clip(hx * lx + hy * ly + hz * lz, 0.0, 1.0)
    fres = F0 + (1.0 - F0) * (1.0 - ldh) ** 5

    spec = d_term * g1l * g1v * fres / np.maximum(4.0 * ndl * ndv, 1e-6)
    return ndl, spec


def lamp(pos, w, h):
    return np.array([pos[0] * w, pos[1] * h, pos[2] * h], dtype=np.float32)


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


LUMA = np.array([0.2126, 0.7152, 0.0722])


def kelvin(temperature):
    """A blackbody's colour at `temperature`, in linear RGB, normalised to keep its brightness.

    Helland's approximation of the Planckian locus. It is accurate to a couple of per cent across
    the range of room lights, which is far more than a background needs.

    It is normalised by LUMINANCE and not by the brightest channel. This means that changing the
    temperature changes the COLOUR of the light and nothing else: warming the key from 5000 K to
    3000 K does not also dim the picture.
    """
    t = np.clip(temperature, 1000.0, 40000.0) / 100.0

    red = 255.0 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    green = (99.4708025861 * np.log(t) - 161.1195681661 if t <= 66
             else 288.1221695283 * (t - 60) ** -0.0755148492)
    if t >= 66:
        blue = 255.0
    elif t <= 19:
        blue = 0.0
    else:
        blue = 138.5177312231 * np.log(t - 10) - 305.0447927307

    rgb = srgb_to_linear(np.clip([red, green, blue], 0, 255))
    return (rgb / max(float(rgb @ LUMA), 1e-6)).astype(np.float32)


def sky_colour():
    """The colour of the ambient: what the room returns, moved towards neutral by the pressing's
    sky_tint and kept at the same brightness for the same reason as in kelvin()."""
    room = srgb_to_linear(P["sky"])
    room = room / max(float(room @ LUMA), 1e-6)
    return ((1.0 - P["sky_tint"]) + P["sky_tint"] * room).astype(np.float32)


def render(w, h, scale):
    """The frame as two linear parts: what the material returns, and what the lamps do.

    They are kept apart because they are different things (see `warmth`). The body is one number per
    pixel, because the colour of the material is decided at the very end. The sheen is RGB, because
    it already has the colour of the lamps that made it.
    """
    pile = [Record(r["centre"], r["radius"], r["seed"], w, h, scale) for r in RECORDS]

    thickness = THICKNESS_MM * px_per_mm(scale)

    key = lamp(KEY_POS, w, h)
    fill = lamp(FILL_POS, w, h)
    falloff_ref = FALLOFF_REF * h

    # The slow mottle of a pressing, built once at low resolution and stretched. It should be a
    # variation that cannot be pointed at, so it is not drawn at pixel scale.
    cell = max(int(30 * scale), 2)
    rng = np.random.default_rng(9)
    mottle = rng.normal(0.0, 1.0, size=(h // cell + 2, w // cell + 2)).astype(np.float32)
    mottle = np.asarray(Image.fromarray(mottle, mode="F").resize((w, h), Image.BICUBIC))

    body = np.empty((h, w), dtype=np.float32)
    sheen = np.empty((h, w, 3), dtype=np.float32)
    colours = (kelvin(P["key"]), kelvin(P["fill"]), sky_colour())

    for y0 in range(0, h, STRIP):
        y1 = min(y0 + STRIP, h)
        y, x = np.mgrid[y0:y1, 0:w]
        x = x.astype(np.float32)
        y = y.astype(np.float32)

        # Which record a pixel belongs to: the highest one in the pile whose disc contains it. The
        # camera is orthographic and looks straight down, so being covered is simply being inside.
        layer = np.zeros(x.shape, dtype=np.int8)
        for i, record in enumerate(pile):
            if i == 0:
                continue                # the ground, which everything falls back to
            layer[np.hypot(x - record.cx, y - record.cy) <= record.radius] = i

        # The material's share, one number per pixel, and the lamps' share, one per source, so each
        # can be given its own colour once the shading is done.
        matter = np.zeros_like(x)
        planes = [np.zeros_like(x) for _ in range(3)]

        for i, record in enumerate(pile):
            mask = layer == i
            if not mask.any():
                continue

            xs = x[mask]
            ys = y[mask]
            height = i * thickness

            r, nx, ny, nz, tx, ty, tz, gloss, rough, ridge = record.surface(xs, ys)

            # Rougher where the pressing is duller, and rougher again in the seams and along the rim.
            along = ROUGH_ALONG / np.maximum(gloss, 0.2) * rough
            across = ROUGH_ACROSS / np.maximum(gloss, 0.2) * rough

            # ── what the records above this one do to it ──
            #
            # Each of them blocks the key over part of this surface, and each takes away part of its
            # sky where it stands close by. A record at the bottom of a pile is in a well.
            lit = np.ones_like(xs)
            occl = np.ones_like(xs)

            for j in range(i + 1, len(pile)):
                above = pile[j]
                gap = (j - i) * thickness

                # Walk from this point towards the key and find where the ray crosses that record's
                # plane. If that point is inside its disc, this point is in its shadow.
                t = gap / max(key[2] - height, 1e-6)
                qx = xs + (key[0] - xs) * t
                qy = ys + (key[1] - ys) * t
                edge = np.hypot(qx - above.cx, qy - above.cy) - above.radius

                # How sharp that edge is: the width of the lamp, seen from the gap's distance. This
                # is a penumbra calculated from geometry, not set by hand, and it widens with the gap,
                # which is why the shadow two records down is the softer one.
                penumbra = max(gap * (KEY_SIZE * w) / max(key[2], 1e-6), 1.0)
                lit *= np.clip(0.5 + 0.5 * edge / penumbra, 0.0, 1.0)

                # The crevice: a point in the angle between two surfaces sees less sky than one in
                # the open. Only the sky is occluded here; the key has its own shadow, above.
                outside = np.hypot(xs - above.cx, ys - above.cy) - above.radius
                occl *= 1.0 - 0.62 * np.exp(-np.maximum(outside, 0.0) / (AO_REACH * gap))

            # How much less sky reaches this depth in the pile, whatever is directly over it.
            occl *= LAYER_DIMMING ** (len(pile) - 1 - i)

            for slot, (pos, power, shadowed) in enumerate(
                    ((key, KEY_POWER, True), (fill, FILL_POWER, False))):
                # A position, not a direction. This lets the lamp cast shadows, and it gives the
                # inverse-square falloff that draws the sheen into a band and not a wash.
                lx = pos[0] - xs
                ly = pos[1] - ys
                lz = np.full_like(xs, pos[2] - height)
                d2 = lx * lx + ly * ly + lz * lz
                inv = 1.0 / np.sqrt(d2)
                lx *= inv
                ly *= inv
                lz *= inv

                ndl, spec = shade(nx, ny, nz, tx, ty, tz, lx, ly, lz, along, across)

                reach = power * (falloff_ref * falloff_ref) / d2 * ndl * (lit if shadowed else 1.0)

                # What went into the vinyl and came back out has the colour of the vinyl; what
                # bounced off the surface has the colour of the bulb. See `warmth`.
                matter[mask] += reach * (ALBEDO / np.pi)
                planes[slot][mask] = reach * spec

                del lx, ly, lz, d2, inv, ndl, spec, reach

            # The sky. Its specular part is small but not nothing, and it is the reason a groove is
            # still a groove in the parts of the frame that no lamp reaches.
            up = np.clip(nz, 0.0, 1.0)
            ambient = SKY * occl

            matter[mask] += ambient * ALBEDO * (0.35 + 0.65 * up)
            planes[2][mask] = ambient * SKY_SPEC * F0 * ridge * (1.0 - up * 0.5)

            del r, nx, ny, nz, tx, ty, tz, gloss, rough, ridge, up, lit, occl, ambient

        # The pressing itself: grain over everything, and the slow mottle under it. Both are small,
        # because more would make the record look like cloth. They are multiplicative, because what
        # varies is how much light the surface returns, not how much light there is.
        grain = np.random.default_rng(1000 + y0).normal(1.0, GRAIN, size=x.shape).astype(np.float32)
        surface = grain * (1.0 + 0.045 * mottle[y0:y1])

        lit = np.zeros(x.shape + (3,), dtype=np.float32)
        for plane, colour in zip(planes, colours):
            lit += plane[..., None] * colour

        body[y0:y1] = matter * surface
        sheen[y0:y1] = lit * surface[..., None]

    return body, sheen


def tonemap(linear):
    """Linear radiance to displayable values.

    Reinhard, then the usual gamma. A record has a very large ratio between the sheen and the black
    it sits on (the specular peak on a bevel reaches the hundreds), and clipping that gives a white
    wire with a hard edge where a highlight should roll off smoothly.
    """
    mapped = linear / (1.0 + linear)
    return np.clip(mapped, 0.0, 1.0) ** (1.0 / 2.2)


def match(gray, mean, spread):
    """Puts the rendered surface at the given brightness and spread (0-255, before the duotone, where
    the duotone's straight ramp keeps tones from being compressed twice), times the pressing's lift.

    The render provides the structure. How dark the flat areas are and how far the sheen reaches
    comes from HEADER_MEAN and HEADER_SPREAD and is not tuned by hand.

    This is a straight line, not histogram specification. Histogram specification matches the whole
    distribution exactly, but it maps ranks. Where a picture has thousands of pixels with nearly the
    same value, as a lit groove field does, neighbouring tones land on the same output step and the
    gradient shows contours. That shows as a hard edge where the sheen falls away. Matching the
    mean and the spread moves the tones without ever merging two of them.
    """
    src = np.asarray(gray).astype(np.float32)

    mean_lift, spread_lift = P["lift"]

    scale = spread * spread_lift / max(src.std(), 1e-6)
    out = (src - src.mean()) * scale + mean * mean_lift
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="L")


def duotone(gray):
    """The two-colour ramp of the pressing: its shadow at black, its high at white, with a straight
    line between."""
    lut = []
    for ch in range(3):
        s, hi = P["shadow"][ch], P["high"][ch]
        lut += [int(s + (hi - s) * (i / 255)) for i in range(256)]
    return gray.convert("RGB").point(lut)


def shrink(array, mode):
    """Scales down to the finished size. The grooves are a few pixels across and the supersampling is
    the only thing that keeps them from shimmering, so this is where it is used."""
    image = Image.fromarray(np.clip(array * 255, 0, 255).astype(np.uint8), mode=mode)
    return np.asarray(image.resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0


def main():
    body, sheen = render(W * SS, H * SS, SS)

    body = shrink(tonemap(body), "L")
    sheen = shrink(tonemap(sheen), "RGB")

    out = finish(body, sheen, HEADER_MEAN, HEADER_SPREAD)

    for head in P["heads"]:
        path = os.path.join(head, f"background-vinyl{P['name']}.jpg")
        out.save(path, quality=86, optimize=True)
        print("wrote", os.path.normpath(path), out.size, f"{os.path.getsize(path)/1024:.0f} KB")


def finish(body, sheen, mean, spread):
    """The shrunk, tonemapped render as the finished picture: matched to `mean` and `spread`
    (0-255), duotoned, with highlights given the colour of the lamps. Shared with make_header_vinyl.py."""
    # ── the finish ──
    #
    # The tonality of the whole picture is set as follows: matched to the header's mean and spread,
    # then run through the header's duotone. This makes the phone's background and the desktop's
    # dialogs the same piece of vinyl, and the render does not decide it.
    #
    # The render does decide the colour of the light where the light is what is seen. Where the sheen
    # is most of the pixel, the duotone gives way to the lamps' own colour at the SAME brightness. So
    # a highlight goes warm white without going brighter, and the blue stays everywhere that the
    # material is what is seen. See `warmth`.
    total = body + sheen @ LUMA.astype(np.float32)

    gray = match(Image.fromarray(np.clip(total * 255, 0, 255).astype(np.uint8), mode="L"), mean, spread)
    grey = np.asarray(gray, dtype=np.float32) / 255.0
    base = np.asarray(duotone(gray), dtype=np.float32) / 255.0

    lit = sheen @ LUMA.astype(np.float32)

    # How much of this pixel is the lamp and not the vinyl, and how high in the range it is, which
    # keeps the warmth in the highlights and the blue everywhere else. It is smoothstepped, because
    # a threshold with a corner draws a contour line across the sheen.
    bright = np.clip((grey - WARM_FROM) / max(1.0 - WARM_FROM, 1e-6), 0.0, 1.0)
    bright = bright * bright * (3.0 - 2.0 * bright)

    share = np.clip(lit / np.maximum(total, 1e-5), 0.0, 1.0) * bright * P["warmth"]
    share = share[..., None]

    # The colour of the sheen, at the brightness that the match requires: the two lamps mixed in the
    # proportion that reached this pixel, with the ambient's blue in the mix where it is the only
    # light.
    hue = sheen / np.maximum(lit, 1e-5)[..., None]
    lamp = np.clip(hue, 0.0, 4.0) * grey[..., None]

    out = Image.fromarray(
        np.clip((base + share * (lamp - base)) * 255, 0, 255).astype(np.uint8), mode="RGB")

    # A third of a pixel: enough that the grain stops sparkling when the phone scales the image, and
    # not enough to soften the grooves, which are the picture.
    return out.filter(ImageFilter.GaussianBlur(0.35))


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PRESSINGS)
    for name in wanted:
        if name not in PRESSINGS:
            raise SystemExit(f"no such pressing: {name} (have {', '.join(PRESSINGS)})")

        P = PRESSINGS[name]
        print(f"── {name} ──")
        main()
