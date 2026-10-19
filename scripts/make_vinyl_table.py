#!/usr/bin/env python3
"""The desktop's backdrop: a table of records, at two times of day.

This is the same table that the phone's ground is a close-up of, seen from further back. It is
photographed twice: once by a summer morning through the window, and once by two lamps at night. The
night picture is background-night.jpg in Assets. Gold is the same table pressed in gold
(background-gold.jpg). Both are backdrops in Settings (Backdrop.cs). The morning render,
background.jpg, is not used by the app, so it is not kept in Assets and is rendered only when it is
asked for by name.

It imports the shipped phone renderer for the parts that do not change: the BRDF, the blackbody
curve, the tonemap and the record's own dimensions. It replaces what does change: what a record's
face looks like when the whole of it is visible, how many records are on the table, and the light.

Everything about the RECORDS is shared between the two times of day: the same lattice, pressings,
colours and labels. It is one crate, and only the light changes. See MORNING and NIGHT.

WHAT IS DIFFERENT FROM THE PHONE'S
----------------------------------
The phone's ground has three records, and the centre of every one is outside the frame. So it is all
groove field, and no record ever shows as a disc. When the view is pulled back, that is no longer
true, and the things that a close-up never shows must exist:

  * A label, and a real one: a hundred millimetres across on a three-hundred-millimetre disc, which
    is the ratio of a real LP. It is paper, not vinyl: matte, isotropic, and much lighter than the
    black around it, so it is the first thing that attracts attention.

  * Smooth ground on either side of the music. There is no groove inside the run-out or outside the
    lead-in. A record with grooves that run up to the label looks drawn, not real.

  * The spindle hole. It is seven and a quarter millimetres, which is a standard size, and dark
    because it is a hole.

  * A table under the records. With the whole disc in the frame, something that is not a record
    must be under it.

Every disc is the same size, as every twelve-inch record is.

Usage: python3 make_vinyl_table.py [morning|night ...]      (both, if none named)
"""
import os
import workspace
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_vinyl_ground as g                                            # noqa: E402

ASSETS = workspace.path("RPM.Desktop", "Assets")

# Set for each run (see the bottom of the file).
OUT = os.path.join(ASSETS, "background.jpg")

# The size of the asset, so that nothing is scaled when it is placed.
W, H = 3840, 2351
SS = 2
STRIP = 256

# One record's radius, in finished pixels. All other sizes on the face are given in millimetres
# and converted with PX_PER_MM.
RADIUS = 650.0
PX_PER_MM = RADIUS / g.RECORD_RADIUS_MM

# The face, in millimetres from the centre out. A 12-inch LP has a label 100 mm across, a 7.24 mm
# spindle hole, a few millimetres of run-out inside the music and a lead-in lip outside it.
SPINDLE_MM = 3.62
LABEL_MM = 50.0
RUNOUT_MM = 7.5

# ── the lead-in ──
#
# The band between the rim and the first track. The needle is set down here, and the groove is wide
# enough to carry it in from wherever it lands. It is the shiny ring around the outside of every LP.
# It is shiny because it is WIDE: it advances a couple of millimetres a turn instead of a tenth of
# one, so there is far more flat land between one wall and the next, and the light comes off it in
# one piece instead of being scattered across the groove.
#
# This is also why it has to be modelled and not just drawn darker. At this distance the music is
# microstructure that the BRDF carries, and the lead-in is the one groove on the record that is big
# enough to see. It has three turns, and you can count them.
LEAD_IN_MM = 6.0
LEAD_PITCH_MM = 1.9

# How far the lead-in gives up the music's anisotropy. More land per groove gives less streak and
# more mirror, and that is what makes the ring look polished.
LEAD_SMOOTH = 0.55

# Where the music has to stop: the flat part of the record, less the lead-in.
MUSIC_OUTER_MM = g.RECORD_RADIUS_MM - g.LIP_MM - LEAD_IN_MM

# A black label. A black label is still PAPER, so it does not look black because it is darker. It
# looks black because it is MATTE and has no groove in it. The vinyl around it answers the light with
# a sheen, and the label answers with almost nothing. Its own edge ring stops it from looking like a
# hole.
#
# Why the albedo alone cannot make it black:
#
# A matte surface returns a little of the light EVERYWHERE. A glossy one returns a lot along two
# narrow wings and almost nothing over the rest of the disc. So the ratio between them depends on the
# lighting. In a dim room with a big soft ambient light, the matte surface collects light from the
# whole sky and is brighter on average. No albedo above zero makes it darker than the vinyl, and an
# albedo of zero gives a hole and not a label.
#
# With a SUN in the sky this reverses. The vinyl has a hard directional source to answer, its wings
# are much brighter than any diffuse surface can be, and the label, which has no wings, becomes one of
# the darkest parts of the picture on its own. A black label needs a strong directional light such as
# the sun (see the lights below).
LABEL_ALBEDO = 0.0062
LABEL_ROUGH = 0.88

# Paper has a surface. Black paper especially: it is the one place on a record where the fibre is
# visible, because there is no gloss over it to hide it. Without this the label looks like a hole cut
# in the picture and not like a disc stuck onto it. The value is low because the paper is very dark,
# and a larger grain would lift the label back up.
LABEL_GRAIN = 0.20

# What is printed on it: the app's own typeface, from the repository. The text is dim on purpose,
# because a label is ink on dark paper, not light shining through it. LABEL_INK is how much lighter
# the ink is than the paper around it.
LABEL_FONT = workspace.path("RPM.Desktop", "Assets", "Fonts",
                          "ThiamineRPM.otf")
LABEL_TEXT = "rpm"
LABEL_INK = 6.0

# How much of the label's width the wordmark takes, and how far above the spindle hole it sits. The
# hole is at the exact centre, so text centred on the label would be cut through the middle. On a
# real label the name goes above the hole and the small print below it.
LABEL_WIDTH = 0.52
LABEL_RISE = 0.34               # of the label's radius
LABEL_ART_PX = 512

# How much of the surface reflection paper keeps. Almost none, and this number is what makes a black
# label black.
#
# A dark albedo alone gives a label LIGHTER than the vinyl around it. A rough surface has the same
# Fresnel reflectance as a smooth one, but it spreads it over the whole hemisphere. So a matte label
# returns a little of the lamp EVERYWHERE, while the glossy vinyl returns a lot along two narrow wings
# and almost nothing over the rest of the disc. Averaged across the face, the matte surface is
# brighter.
#
# A rough mirror is the wrong model for paper. Its surface is fibre: light that meets it is scattered
# into the body and is not bounced off a tilted facet, so the lobe does not survive as a lobe.
LABEL_SPEC = 0.020

# The table: dark, and rough enough that its own highlight is not worth looking at. It is only
# there to be the thing that the records are NOT.
TABLE_ALBEDO = 0.016
TABLE_ROUGH = 0.62

# ── the groove, at this distance ──
#
# The phone's model is not right at this distance. On the phone a record is bigger than the frame and
# a groove is seven pixels across, so the groove is RESOLVED: the wall is modelled, the normal is
# tilted, and the light finds it. Here a whole disc is about thirteen hundred pixels wide, and a real
# groove is a quarter of a PIXEL (0.06 mm at four pixels to the millimetre). Drawing it as geometry at
# four pixels would make it twenty times too big, and a surface of ridges that are twenty times too
# big looks like corrugation. That gives the plastic look. The shading is not the cause.
#
# So at this distance the groove is microstructure, as it is physically, and the BRDF carries it. A
# field of fine parallel V-cuts scatters widely ACROSS the groove and hardly at all ALONG it. Those
# two numbers are all that is needed: an alpha of about 0.4 across is a wall of about twenty-five
# degrees, which is a groove, and a small alpha along is polished vinyl. The long soft streak of sheen
# on a record follows from that, with no ridge to alias and nothing that looks moulded.
#
# What remains as geometry is very small: just enough that the surface is not glass.
GROOVE_PITCH = 3.0
GROOVE_DEPTH = 0.085

# Along the groove, a value as low as 0.03 would be a mirror and would give a hard white beam across
# each disc. A cut groove is smooth lengthways but it is not polished glass, and the lamp it answers
# has a real width, so both widen the streak. 0.09 gives a sheen and not a searchlight.
ROUGH_ALONG = 0.090
ROUGH_ACROSS = 0.420

# ── where one track ends and the next begins ──
#
# In MILLIMETRES, like everything else on the face. The shipped renderer draws its bands from a median
# of 250 pixels, which suits a phone: there a record is bigger than the frame and 250 px is a track.
# Here the whole of the music is 776 pixels across, so a 500-pixel band would give most records ONE
# separator and many records none.
#
# A twelve-inch side carries four to eight tracks over about ninety millimetres of playing radius. The
# widths use a lognormal distribution and not a flat range, because track lengths are not evenly
# spread: most are around three or four minutes, a few are long, and some are half as long.
TRACK_MEDIAN_MM = 12.5
TRACK_SPREAD = 0.55
TRACK_MIN_MM, TRACK_MAX_MM = 4.5, 30.0

# How wide the separator itself is. It is a single wider cut, not a band: a real record has one
# groove there.
SEAM_MM = 0.42

# How far towards smooth the separator goes.
#
# Fully isotropic is too far. The land would become a small mirror, and a mirror returns light in
# only one direction, so over most of a disc it returns nothing and the separators become hard dark
# rings. At this distance a separator is a couple of pixels of land with grooves on either side, and
# those grooves still dominate what the viewer sees. So the separator gives up a third of its spread,
# not all of it: it is a little darker, and it has a glint where the angle is right.
SEAM_SMOOTH = 0.32

# ── no two records the same ──
#
# These are all things that differ between two records in a crate, and each one changes how a disc
# looks: how black the compound was pressed (recycled vinyl is greyer), how polished it came off the
# stamper, how much haze it has picked up since, how densely it was cut, and how dark the label was
# printed.
DISC_TONE = (0.62, 1.22)        # albedo, relative to the vinyl's own
DISC_POLISH = (0.80, 1.25)      # gloss: a dull pressing spreads its sheen and looks lighter
DISC_HAZE = (0.55, 1.90)        # how much of the room a worn surface scatters back
DISC_PITCH = (0.86, 1.18)       # groove pitch: how much music was cut onto it
DISC_LABEL = (0.45, 1.7)        # the label's ink

# The colour of the VINYL: the compound itself, not the light coming off it.
#
# The values above change how much light a record RETURNS, and almost all of that goes into the sheen.
# They would make the discs differ in their highlights but not in their material. This value changes
# the material: where a record sits between the darkest blue in the ramp and the lightest, before any
# lamp touches it.
#
# It is applied to the body of the picture and NOT to the sheen, because a lamp does not change colour
# for landing on a paler record. The same split already exists for the warm-white highlights, and this
# value uses it.
DISC_VINYL = (0.58, 1.12)

# ── coloured pressings ──
#
# A crate is not all black. Vinyl takes pigment as easily as it takes carbon black, and the coloured
# pressings are the ones people keep. So the table has them, in the app's own palette and not in
# colours invented for a picture.
#
# The order is the order of the colour wheel, because the dealing below scores by it: two records next
# to each other should be two different COLOURS, not two numbers that happen to be far apart.
RPM_PALETTE = [
    ("crimson",   "#EA154E"),
    ("red",       "#EE0709"),
    ("vermilion", "#D2310E"),
    ("rust",      "#CC6E11"),
    ("gold",      "#EFAF12"),
    ("lime",      "#ADD038"),
    ("forest",    "#134C27"),
    ("azure",     "#0371D0"),
    ("indigo",    "#4750AE"),
    ("magenta",   "#AC528D"),
]

# How much of the table is a coloured pressing rather than a black one.
COLOURED_SHARE = 0.66

# A crate pressed in one warm metal, for the supporter's backdrop. It does not use a second palette
# invented for a picture. It is the warm arc of the app's own wheel (rust and gold), opened out into
# the shades that a gold pressing comes in, because a table of ten identical golds looks like a
# texture and not like a crate. Every disc should look like the SAME metal seen at a different angle.
# The rest of this file does that with light, and it works only if the hues are close enough to be
# one material.
GOLD_PALETTE = [
    ("bronze",     "#9A6A18"),
    ("amber",      "#CE9310"),
    ("gold",       "#EFAF12"),
    ("champagne",  "#EBD07A"),
    ("brass",      "#CBA430"),
    ("honey",      "#E0AE2C"),
    ("wheat",      "#D9BE55"),
    ("old gold",   "#B98B1E"),
]

# More of them are coloured, because black is the contrast here and not the ground. On the default
# table black is most of the picture and the colours land on it. A gold crate with a third of it black
# would look like the default table under a warm lamp.
GOLD_SHARE = 0.84


def palette():
    """Returns the compounds this run is pressing in. A preset may have its own; most do not."""
    return P.get("palette") or RPM_PALETTE


def coloured_share():
    return P.get("coloured_share", COLOURED_SHARE)

# What a pigmented compound RETURNS, compared with the carbon-black compound that ALBEDO describes.
#
# Without this the colour does not appear. Carbon black is in a record to absorb light, which is why
# this picture's material is at about two per cent. A red record given a black record's albedo is a
# black record. Pigment reflects, so a colour needs the reflectance that goes with it.
COLOUR_ALBEDO = (2.2, 4.0)

# How far a coloured record is carried towards its own hue, compared with the blue that everything
# else sits in. It is not all the way: a record in a blue-lit room is lit blue, and a pressing that
# ignored the room would look like a sticker laid on the picture and not like part of it.
DISC_SATURATION = (0.88, 1.00)

# The largest value any one channel of a tint may reach once the brightness is taken out of it. A
# saturated hue at unit luminance has a channel several times its own brightness (pure red is nearly
# all red). When that is multiplied by the picture's own tone it clips, which removes the modelling
# from the highlight and leaves a flat patch where the grooves were. With this limit, the brightest
# place on a red record still shows its grooves.
TINT_CEILING = 4.0

# The pile covers the frame: no table is visible, only records over records.
#
# The records lie on a hexagonal lattice, which covers a plane with the fewest discs. Circles of
# radius R cover the plane once the lattice spacing is under R times root three. This spacing is well
# inside that, so no gap can open between three neighbours. The positions are jittered, because a
# lattice that can be SEEN is the one thing a pile of records never looks like, and then shuffled, so
# that the overlaps do not all lean the same way.
SPACING = 1.28                  # of a radius
JITTER = 0.42                   # of the spacing

# Two cases where a pair of discs makes a shape that looks like a mistake. The lattice produces both
# on its own. Nearly COINCIDENT: the lower disc shows as a thin crescent. Nearly TANGENT: the upper
# disc shows as a thin lune. On a hexagonal lattice the next-nearest neighbour is at the spacing times
# root three. At the spacing above that is 2.2 radii, outside the grazing band. TOO_CLOSE and GRAZING
# reject whatever the jitter still puts into either band.
TOO_CLOSE = 0.95                # of a radius
GRAZING = (1.80, 2.20)
LATTICE_SEED = 7      # picked by trying several seeds and scoring the layouts

# ── two times of day ───────────────────────────────────────────────────────────────────────────────
#
# The same crate, photographed twice. Everything above this line is the records themselves (where
# they lie, what they were pressed in, what is printed on them), and it is the same in both pictures.
# Only the lighting changes, and it changes completely, because a summer morning outdoors and a room
# with two lamps are not the same rig with the numbers turned down.
#
#   MORNING is a SUN: 150 million kilometres away, so its rays are parallel and there is no falloff
#   across the table. Shadows are sharp, because the sun is half a degree wide, which is a fraction
#   of a pixel over a record's thickness. The sky is the second light and not a floor under the
#   picture: it is the whole upper hemisphere, which fills the shadows and makes the picture vibrant
#   and not only high in contrast.
#
#   NIGHT is two LAMPS: close enough that the inverse square law is visible and the direction of the
#   light changes across the frame, which says "indoors". Shadows are soft, because a lamp has real
#   width. The room is nearly dark, so the picture is what the lamps land on and very little else.
#
# A light is a direction when it is the sun and a position when it is a lamp. The renderer handles
# both and does not treat one as the other.
#
#   kind    "sun" for parallel rays and no falloff, "lamp" for a point at a place
#   at      the direction, or the position in frame widths/heights
#   size    the source's width, as penumbra per unit of shadow length
#   glow    how much brighter the environment is towards it, and how tightly the brightness is gathered
MORNING = dict(
    name="morning",
    lights=[
        dict(kind="sun", at=(0.58, -0.60, 0.55), power=1.45, kelvin=5200,
             size=0.013, shadows=True, glow=(9.0, 9.0)),
        # The rest of the sky, from the far side. It is nearly neutral, because it is most of the
        # hemisphere.
        dict(kind="sun", at=(-0.46, 0.50, 0.73), power=0.20, kelvin=7000,
             size=0.10, shadows=False, glow=(0.0, 1.0)),
    ],
    fill=0.112,
    fill_kelvin=12000,
    zenith=(0.16, 0.34, 0.90),
    horizon=(0.72, 0.80, 0.94),
    bend=0.55,
    mean=47.0,
    spread=47.0,
    saturation=1.35,
)

NIGHT = dict(
    name="night",
    lights=[
        # Where the sun is, so that the two pictures show the same table. The light is warm white and
        # not yellow: a domestic bulb is about this colour temperature, and a lower value makes vinyl
        # look amber.
        dict(kind="lamp", at=(0.88, -0.32, 0.60), power=0.92, kelvin=4000,
             size=0.85, shadows=True, glow=(22.0, 5.0)),
        dict(kind="lamp", at=(-0.30, 1.10, 0.55), power=0.42, kelvin=3600,
             size=1.10, shadows=False, glow=(9.0, 4.0)),
    ],
    # A dark room: about one fifteenth of the morning's fill, which is about the ratio between a sky
    # and a ceiling.
    fill=0.0075,
    # The room itself is BLUE, which is why a warm lamp looks warm. A neutral ambient light plus a
    # warm key light gives a sepia photograph; the contrast between the two is the picture.
    fill_kelvin=11000,
    # What the vinyl mirrors indoors: not a sky but a dim ceiling. It is darker overhead than at the
    # walls, because the ceiling is further from the lamps than the walls are and returns less.
    zenith=(0.04, 0.09, 0.26),
    horizon=(0.10, 0.16, 0.34),
    bend=0.9,
    mean=38.0,
    spread=46.0,
    saturation=1.28,
)

# The third table is not a time of day: it is the same crate pressed in gold, under two warm lamps.
# It is the supporter's backdrop, so it has to look like a DIFFERENT ROOM and not like the night table
# with a filter over it. For that reason the lamps are nearly a thousand kelvin lower and the ceiling
# they bounce off is not blue.
#
# The room still stays COOLER than the lamps, and this is essential. A warm key light in a warm room
# gives a sepia photograph: nothing in the frame is warm relative to anything else, so nothing looks
# gold. Here the fill is a dim neutral and the ceiling that the vinyl mirrors is only slightly warm,
# so the gold comes from the lamps and from the compound and not from a wash laid over everything.
GOLD = dict(
    name="gold",
    palette=GOLD_PALETTE,
    coloured_share=GOLD_SHARE,
    lights=[
        # Where the night's key light is, but warmer: 3150 K is closer to a filament than the 4000 K
        # domestic LED that lights the night table. The glow is wide, because what makes metal look like
        # metal is a long soft sheen travelling across the disc, not a hot spot sitting on it.
        dict(kind="lamp", at=(0.86, -0.30, 0.58), power=1.02, kelvin=3150,
             size=0.90, shadows=True, glow=(26.0, 4.2)),
        # The second lamp is warmer still and further round, so a disc that is dark under the key light
        # has a second angle to catch the light. Gold with only one light on it is half a black record.
        dict(kind="lamp", at=(-0.34, 1.05, 0.52), power=0.50, kelvin=2750,
             size=1.15, shadows=False, glow=(11.0, 3.6)),
    ],
    # Brighter than the night room, because the pressings themselves return several times what a
    # black one does, and a room this dark would crush the shadow side of every disc to nothing.
    fill=0.0125,
    # Neutral and not blue. Blue here would push the shadow side of a gold record towards green, and
    # gold must never go that way.
    fill_kelvin=8200,
    # A low warm ceiling: what the vinyl mirrors between the lamps. It is warm, so the mirror image
    # is part of the metal and not a cold streak across it, but it is dim enough that it never
    # becomes the main light.
    zenith=(0.055, 0.042, 0.030),
    horizon=(0.150, 0.108, 0.062),
    bend=0.85,
    mean=38.5,
    spread=46.0,
    saturation=1.24,
)

PRESETS = {p["name"]: p for p in (MORNING, NIGHT, GOLD)}

# The distance from which a lamp's falloff is measured: the reference distance at which its stated
# power is the power it delivers (a fraction of the frame height). Meaningless for the sun, which has
# no falloff.
FALLOFF_REF = 0.72

# ── the environment, traced ────────────────────────────────────────────────────────────────────────
#
# What a record reflects, and why one averaged number is not enough.
#
# The view is straight down and the discs are flat, so a mirror would show only the zenith. But a
# record is not a mirror across the groove. The lobe is wide across the groove and narrow along it, so
# each point reflects an ARC of the room running from one horizon to the other, and the picture is
# that arc swept round the disc. If the arc is replaced by its average, every record gets the same
# flat sheen. If it is kept, the sheen brightens where the arc passes the light's side of the room and
# goes dark where the arc points straight up. That is the gleam.
#
# So the code samples the lobe, looks up the environment along each sample, and tests it against the
# records in the way. The light sources themselves are NOT in this environment: a half-degree sun
# found by fourteen random samples is noise, and the direct lights above already handle both exactly.
# What is here is the brightening AROUND them, which indoors is most of what is seen in a record.
RAYS = 14                       # 0 falls back to a constant ambient

# What the underside of a record reflects back. No light falls on it, but the value is not zero:
# it is a dark object in a lit room, not a hole in space.
UNDERSIDE = 0.035

# ── translucency ──
#
# A coloured pressing is not painted, it is DYED, and the compound is translucent. Two things follow:
#
#   * Light goes in and comes back out coloured by the medium, so the body returns far more than
#     carbon black's two per cent. That is COLOUR_ALBEDO.
#
#   * Light also travels sideways INSIDE the compound. So a shadow across a translucent record is not
#     black: it is lit from within by light that landed a centimetre away and scattered, and it keeps
#     the record's colour. TRANSLUCENCY is how much light a shadowed part of a translucent pressing
#     still gets. Black vinyl gets none of it, being opaque by design.
TRANSLUCENCY = 0.62

# ── the finish ──
#
# Each preset states its own tonality (`mean`, `spread` and `saturation` above). The tonality is not
# matched to a photograph, because a match would fix one time of day, and this picture has several.
#
# Nothing here decides the colour of a dark pixel. A morning shadow is blue because it is lit by a
# 12000 K sky and the material multiplies that per channel. A night shadow is warm and nearly black
# because the room is. Only the brightness, the contrast and the final vibrance are stated, and
# vibrance is the one number in this file that is taste and not physics.
#
# The preset in force. Set by main(), read by everything that draws.
P = MORNING


def label_art():
    """Returns the wordmark as a square tile that the label samples.

    The tile is drawn once and sampled by every label on the table, each at its own angle, so it
    costs one text render.
    """
    tile = Image.new("L", (LABEL_ART_PX, LABEL_ART_PX), 0)
    draw = ImageDraw.Draw(tile)

    # Sized by measuring, not by asking. The em box of Thiamine is much bigger than its letters (a
    # request for 150 points draws about thirty pixels of ink), so a fraction of the tile is not a
    # point size. Measure once, scale to the width wanted, and measure again.
    probe = ImageFont.truetype(LABEL_FONT, 200)
    left, top, right, bottom = draw.textbbox((0, 0), LABEL_TEXT, font=probe)

    wanted = LABEL_ART_PX * LABEL_WIDTH
    font = ImageFont.truetype(LABEL_FONT, max(int(200 * wanted / max(right - left, 1)), 8))
    left, top, right, bottom = draw.textbbox((0, 0), LABEL_TEXT, font=font)

    # Centred on the INK, not on the line box: the ascent and descent of a display face have little
    # to do with where its letters sit.
    draw.text(((LABEL_ART_PX - (right - left)) / 2 - left,
               (LABEL_ART_PX - (bottom - top)) / 2 - top - LABEL_RISE * LABEL_ART_PX / 2),
              LABEL_TEXT, font=font, fill=255)

    # A touch of blur: the tile is sampled point by point, and type that is resampled without blur
    # shows stair-steps.
    tile = tile.filter(ImageFilter.GaussianBlur(1.1))
    return np.asarray(tile, dtype=np.float32) / 255.0


ART = label_art()


def pigment(hexstr):
    """Returns a palette colour as a unit-luminance tint: the hue on its own, with the brightness removed.

    Multiplied by the picture's own tone, this changes the colour of a pixel without changing how light
    it is. A red record and a black one under the same lamp differ in hue and in the reflectance that
    the render already gave them, but not in their modelling.
    """
    c = np.array([int(hexstr[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float64) / 255.0
    tint = c / max(float(c @ g.LUMA), 1e-6)

    # Pulled back TOWARDS NEUTRAL until no channel is over the ceiling. It is not scaled down, because
    # that would remove again the brightness that unit luminance has just added. Neutral is (1, 1, 1)
    # and its luminance is one, so the pull also leaves the tint at unit luminance. That lets the
    # saturation be read straight back off the plane later.
    peak = float(tint.max())
    if peak > TINT_CEILING:
        tint = 1.0 + (tint - 1.0) * ((TINT_CEILING - 1.0) / (peak - 1.0))

    return tint.astype(np.float32)


def environment(lx, ly, lz, towards):
    """Returns what the room is, looking along a direction, as radiance per channel.

    A gradient and a set of glows. Outdoors this is a clear sky: deep blue overhead, pale and bright
    towards the horizon where there is more air in the way, and brighter still around the sun. Indoors
    the same two numbers are a ceiling and walls, dark overhead and less dark lower down, with a bloom
    around each lamp. It is one function because it is one question.

    Below the horizon there is nothing to see: a ray that goes down hits the table.
    """
    up = np.clip(lz, 0.0, 1.0)
    blend = up ** P["bend"]

    zenith = np.asarray(P["zenith"], dtype=np.float32)
    horizon = np.asarray(P["horizon"], dtype=np.float32)
    colour = horizon[None, :] + (zenith - horizon)[None, :] * blend[:, None]

    for (dx, dy, dz), (glow, tight) in towards:
        if glow <= 0.0:
            continue
        facing = np.clip(lx * dx + ly * dy + lz * dz, 0.0, 1.0)
        colour = colour * (1.0 + glow * facing ** tight)[:, None]

    return colour * (lz > 0.0)[:, None]


def trace(xs, ys, height, nx, ny, nz, tx, ty, tz, along, across, over, pile, heights,
          thickness, towards, rng):
    """Returns the environment, integrated over the surface's own lobe by sampling it.

    Half-vectors are drawn from the anisotropic GGX distribution and reflected, which is importance
    sampling: the samples land where the surface sends light, so a dozen of them are worth thousands
    of uniform ones. Each sample is looked up in the room and tested against the records that could
    be in the way.
    """
    bx, by, bz = ny * tz - nz * ty, nz * tx - nx * tz, nx * ty - ny * tx

    total = np.zeros(xs.shape + (3,), dtype=np.float32)

    for _ in range(RAYS):
        u1 = rng.random(xs.shape).astype(np.float32)
        u2 = rng.random(xs.shape).astype(np.float32)

        phi = np.arctan2(across * np.sin(2.0 * np.pi * u1), along * np.cos(2.0 * np.pi * u1))
        cp, sp = np.cos(phi), np.sin(phi)

        alpha2 = 1.0 / ((cp / along) ** 2 + (sp / across) ** 2)
        tan2 = alpha2 * u2 / np.maximum(1.0 - u2, 1e-6)
        ch = 1.0 / np.sqrt(1.0 + tan2)
        sh = np.sqrt(np.maximum(1.0 - ch * ch, 0.0))

        hx = sh * cp * tx + sh * sp * bx + ch * nx
        hy = sh * cp * ty + sh * sp * by + ch * ny
        hz = sh * cp * tz + sh * sp * bz + ch * nz

        # The view is straight down and orthographic, so v is (0, 0, 1) at every pixel and the
        # reflection is twice the rise of the half-vector.
        vh = np.maximum(hz, 1e-4)
        lx, ly, lz = 2.0 * vh * hx, 2.0 * vh * hy, 2.0 * vh * hz - 1.0

        # Fresnel at the microfacet, and the shadowing term that the estimator needs once the normal
        # distribution has been sampled out of it.
        fresnel = g.F0 + (1.0 - g.F0) * (1.0 - vh) ** 5
        nl = lx * nx + ly * ny + lz * nz

        lt = lx * tx + ly * ty + lz * tz
        lb = lx * bx + ly * by + lz * bz
        shadowing = 2.0 / (1.0 + np.sqrt(1.0 + ((along * lt) ** 2 + (across * lb) ** 2)
                                         / np.maximum(nl * nl, 1e-6)))

        weight = fresnel * shadowing * (nl > 0.0)

        radiance = environment(lx, ly, lz, towards)

        # Now what is in the way. A record above this one blocks the ray, and what it shows instead is
        # its own underside, which no light falls on.
        for j in over:
            above = pile[j]
            rise = max(heights[j] * thickness - height, thickness)
            step = rise / np.maximum(lz, 1e-4)
            inside = ((np.hypot(xs + lx * step - above.cx, ys + ly * step - above.cy) <= above.radius)
                      & (lz > 0.0))
            radiance = np.where(inside[:, None], UNDERSIDE, radiance)

        total += radiance * weight[:, None]

    return total / RAYS


def spread(values, centres, rng, passes=4000, key=None):
    """Deals the pressings out so that no two neighbours are alike.

    Drawing one per record independently puts the pale ones in a clump, because random choice does
    that, and a clump of pale records looks like a lighting accident and not like a crate of different
    pressings. So the values start as an even ladder and are then swapped, pair by pair, for as long
    as a swap increases the difference between neighbouring records.

    `key` scores a value on the axis along which neighbours should differ: the shade itself for a
    shade, and the position of the hue on the wheel for a compound.
    """
    score = key or (lambda value: value)

    order = list(range(len(values)))
    rng.shuffle(order)
    v = [values[i] for i in order]

    near = [[j for j in range(len(centres))
             if j != i and np.hypot(centres[i][0] - centres[j][0],
                                    centres[i][1] - centres[j][1]) < 2.0 * RADIUS]
            for i in range(len(centres))]

    def contrast(i):
        return sum(abs(score(v[i]) - score(v[j])) for j in near[i])

    for _ in range(passes):
        i, j = rng.integers(0, len(v), 2)
        if i == j:
            continue
        before = contrast(i) + contrast(j)
        v[i], v[j] = v[j], v[i]
        if contrast(i) + contrast(j) < before:
            v[i], v[j] = v[j], v[i]

    return v


def clashes(a, b):
    """Returns whether two discs would meet in a shape that looks like a mistake (see GRAZING)."""
    d = np.hypot(a[0] - b[0], a[1] - b[1]) / RADIUS
    return d < TOO_CLOSE or GRAZING[0] < d < GRAZING[1]


def lattice():
    """Returns where the records lie: enough of them, far enough past every edge, in no visible order."""
    rng = np.random.default_rng(LATTICE_SEED)

    step = SPACING * RADIUS
    row = step * np.sqrt(3.0) / 2.0

    centres = []
    y = -RADIUS
    odd = False
    while y < H + RADIUS:
        x = -RADIUS + (step / 2 if odd else 0.0)
        while x < W + RADIUS:
            for _ in range(24):
                c = (x + rng.uniform(-JITTER, JITTER) * step,
                     y + rng.uniform(-JITTER, JITTER) * step)
                if all(not clashes(c, other) for other in centres):
                    break
            centres.append(c)
            x += step
        y += row
        odd = not odd

    rng.shuffle(centres)
    return centres


def stack_heights(centres):
    """Returns how far off the table each record sits, in thicknesses.

    The height is not the position in the painting order, because that would put the last record laid
    down eighty millimetres in the air, with a shadow to match. A record rests on whatever is under it
    AT THAT SPOT, so this counts the records already down that it actually overlaps. The pile is two or
    three deep wherever you look, as a floor covered in records is.
    """
    heights = []
    for i, (x, y) in enumerate(centres):
        under = sum(1 for j in range(i)
                    if np.hypot(x - centres[j][0], y - centres[j][1]) < 2.0 * RADIUS)
        heights.append(min(under, 3))
    return heights


def neighbours(centres):
    """Returns which records can possibly shadow which. A shadow lands just outside the rim that cast it
    (the offset is a record's thickness), so only a disc close enough to touch is worth testing.
    Testing every disc against every other disc would be a thousand times more work."""
    return [[j for j in range(i + 1, len(centres))
             if np.hypot(centres[i][0] - centres[j][0], centres[i][1] - centres[j][1]) < 2.2 * RADIUS]
            for i in range(len(centres))]


class Disc:
    """One record on the table: where it is, and where its tracks fall."""

    def __init__(self, centre, seed, vinyl, slot, scale):
        rng = np.random.default_rng(seed)

        self.cx, self.cy = centre[0] * scale, centre[1] * scale
        self.radius = RADIUS * scale
        self.mm = PX_PER_MM * scale

        # This pressing, as different from every other one on the table. See the DISC_ constants.
        self.tone = rng.uniform(*DISC_TONE)
        self.polish = rng.uniform(*DISC_POLISH)
        self.haze = rng.uniform(*DISC_HAZE)
        self.ink = rng.uniform(*DISC_LABEL)
        self.spin = rng.uniform(0.0, 2.0 * np.pi)

        # What it was pressed in. A black one has no tint and the picture's own reflectance. A coloured
        # one is both lighter and its own hue, and it varies LESS in how dark it came out: the shade
        # ladder comes from how much carbon black went in, and a pigmented compound does not have that
        # range.
        self.name, self.tint, self.saturation, self.through = "black", None, 0.0, 0.0
        if slot is not None:
            self.name, hexstr = palette()[slot]
            self.tint = pigment(hexstr)
            self.saturation = rng.uniform(*DISC_SATURATION)
            # Replaced, not multiplied. DISC_TONE is how much carbon black went into the compound, and a
            # dyed compound does not have that axis at all. Multiplying the two would take the top of
            # the range to nearly six times the picture's vinyl, which is twelve per cent albedo. At
            # that point the body returns so much more than the surface that the gloss is a rounding
            # error and the record looks like paint.
            self.tone = rng.uniform(*COLOUR_ALBEDO)
            self.through = TRANSLUCENCY * self.saturation
            vinyl = 1.0 + (vinyl - 1.0) * (1.0 - 0.5 * self.saturation)

        self.vinyl = vinyl

        self.pitch = GROOVE_PITCH * rng.uniform(*DISC_PITCH) * scale
        self.depth = GROOVE_DEPTH * scale

        # The lead-in's pitch is a real measurement and not the stylised one that the music uses: it is
        # wide enough to see, so it is drawn at its real size. About three turns over the band.
        self.lead_pitch = LEAD_PITCH_MM * PX_PER_MM * scale
        self.bevel = g.BEVEL_MM * self.mm
        self.lip = g.LIP_MM * self.mm

        # Laid out across the MUSIC and not from the middle of the disc outwards: bands drawn from zero
        # would spend most of themselves under the label, where there is nothing to divide.
        self.inner = (LABEL_MM + RUNOUT_MM) * self.mm
        self.outer = MUSIC_OUTER_MM * self.mm
        self.seam = SEAM_MM * self.mm

        edges = [self.inner]
        while edges[-1] < self.outer:
            width = np.clip(rng.lognormal(np.log(TRACK_MEDIAN_MM), TRACK_SPREAD),
                            TRACK_MIN_MM, TRACK_MAX_MM)
            edges.append(edges[-1] + width * self.mm)

        self.edges = np.asarray(edges, dtype=np.float32)
        self.centres = ((self.edges[:-1] + self.edges[1:]) / 2).astype(np.float32)

        # How glossy each band is, because a pressing is not uniform. The value is interpolated ACROSS
        # the bands (see face()) and not held flat within them: a record is one plane, and a band at a
        # constant value looks like a step down to a lower one.
        self.gloss = rng.uniform(0.80, 1.16, size=len(self.centres)).astype(np.float32)


def face(disc, x, y):
    """Returns everything the shading needs, at every point on one record.

    The zones matter here and not on the phone: inside the run-out and outside the lead-in a record is
    smooth, and inside the label it is not a record at all.
    """
    dx = x - disc.cx
    dy = y - disc.cy
    r = np.hypot(dx, dy)

    inv = 1.0 / np.maximum(r, 1e-6)
    rx, ry = dx * inv, dy * inv

    mm = r / disc.mm

    # ── where the music is, and where the lead-in is ──
    #
    # Both fade in and out over about a millimetre and do not switch, or the first and last groove of
    # each would end in a step that catches the light as a hard ring.
    program = (np.clip((mm - (LABEL_MM + RUNOUT_MM)) / 1.2, 0.0, 1.0)
               * np.clip((MUSIC_OUTER_MM - mm) / 1.2, 0.0, 1.0))

    lead = (np.clip((mm - MUSIC_OUTER_MM) / 0.9, 0.0, 1.0)
            * np.clip(((g.RECORD_RADIUS_MM - g.LIP_MM) - mm) / 0.9, 0.0, 1.0))

    def cut(pitch, depth):
        """Returns one spiral: the crown across it, and the slope of the wall."""
        phase = r * (2.0 * np.pi / pitch)
        crown = 0.5 + 0.5 * np.cos(phase)
        return (crown ** g.RIDGE_POWER,
                depth * g.RIDGE_POWER * crown ** (g.RIDGE_POWER - 1.0)
                * (-0.5 * np.sin(phase)) * (2.0 * np.pi / pitch))

    fine, fine_slope = cut(disc.pitch, disc.depth)

    # The lead-in is cut deeper as well as wider: it is one groove doing the work of a hundred, and it
    # is the one the needle has to find on its own.
    wide, wide_slope = cut(disc.lead_pitch, disc.depth * 2.6)

    ridge = fine * (1.0 - lead) + wide * lead
    slope = fine_slope * program + wide_slope * lead

    # ── the rolled edge ──
    inside = np.clip((disc.radius - r) / max(disc.bevel, 1e-6), 0.0, 1.0)
    tilt = (1.0 - inside) ** 0.65 * (0.5 * np.pi * 0.92)

    st, ct = np.sin(tilt), np.cos(tilt)
    nx = st * rx - slope * ct * rx
    ny = st * ry - slope * ct * ry
    nz = ct + slope * st
    norm = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    nx *= norm
    ny *= norm
    nz *= norm

    tx, ty, tz = -ry, rx, np.zeros_like(r)
    d = tx * nx + ty * ny + tz * nz
    tx -= d * nx
    ty -= d * ny
    tz -= d * nz
    tn = 1.0 / np.maximum(np.sqrt(tx * tx + ty * ty + tz * tz), 1e-6)
    tx *= tn
    ty *= tn
    tz *= tn

    gloss = np.interp(r.ravel(), disc.centres, disc.gloss).astype(np.float32).reshape(r.shape)

    seam = np.zeros_like(r)
    for e in disc.edges[1:-1]:
        seam += np.exp(-(((r - e) / disc.seam) ** 2))
    seam = np.minimum(seam, 1.0)

    rough = 1.0 + (g.BEVEL_ROUGHEN - 1.0) * (1.0 - inside)

    gloss = gloss * disc.polish

    along = ROUGH_ALONG / np.maximum(gloss, 0.2) * rough
    across = ROUGH_ACROSS / np.maximum(gloss, 0.2) * rough

    # The separator is SMOOTH LAND, a stretch with no groove cut into it. So it is not rougher than the
    # music on either side, it is less anisotropic. Its across-groove roughness falls back towards its
    # along-groove roughness, and a polished isotropic ring in the middle of a streaked field makes the
    # track divisions glint as they do on a real record.
    across = across * (1.0 - seam * SEAM_SMOOTH) + along * (seam * SEAM_SMOOTH)

    # The same for the lead-in, and further: two millimetres of land between one wall and the next is
    # not a streaked surface, it is a polished one with a groove in it.
    across = across * (1.0 - lead * LEAD_SMOOTH) + along * (lead * LEAD_SMOOTH)
    # How much this pressing returns at all: the picture's own vinyl, times how black this one was
    # pressed, times its place on the shade ladder. This belongs here and not at the end on the
    # finished colour, because a paler pressing is a paler MATERIAL and the light has to leave it with
    # that. The label overwrites this below, which is correct: paper has no compound in it.
    albedo = np.full_like(r, g.ALBEDO * disc.tone * disc.vinyl)

    # ── the label ──
    #
    # Paper: matte, so the two roughnesses are the same number (a printed label has no lathe marks to
    # make it anisotropic). Its edge gets a thin dark ring, which is the shadow under a disc of paper
    # stuck onto a record and stops it looking like a painted circle.
    paper = np.clip((LABEL_MM - mm) / 0.8, 0.0, 1.0)
    if paper.any():
        along = along * (1.0 - paper) + LABEL_ROUGH * paper
        across = across * (1.0 - paper) + LABEL_ROUGH * paper
        albedo = albedo * (1.0 - paper) + LABEL_ALBEDO * disc.ink * paper
        ridge = ridge * (1.0 - paper)

        # The wordmark. The label's own square of art is turned to this record's angle (the records are
        # not all facing the same way) and sampled point by point.
        c, sn = np.cos(disc.spin), np.sin(disc.spin)
        half = LABEL_ART_PX / 2.0
        span = LABEL_MM * disc.mm

        u = np.clip(((dx * c + dy * sn) / span * half + half).astype(np.int32), 0, LABEL_ART_PX - 1)
        v = np.clip(((-dx * sn + dy * c) / span * half + half).astype(np.int32), 0, LABEL_ART_PX - 1)

        albedo *= 1.0 + LABEL_INK * paper * ART[v, u]

        # The fibre. Hashed from the position and not drawn from a generator, so it is the same texture
        # wherever the strips fall.
        fibre = np.sin(x * 12.9898 + y * 78.233) * 43758.5453
        fibre -= np.floor(fibre)
        albedo *= 1.0 + LABEL_GRAIN * paper * (fibre - 0.5)

        lifted = np.exp(-(((mm - LABEL_MM) / 0.7) ** 2))
        albedo *= 1.0 - 0.55 * lifted

    # ── the spindle hole ──
    hole = np.clip((SPINDLE_MM - mm) / 0.5, 0.0, 1.0)
    albedo *= 1.0 - hole
    ridge = ridge * (1.0 - hole)

    # What is left of the surface reflection: all of it on vinyl, almost none on paper, and none at
    # all down the spindle hole.
    specular = (1.0 - paper * (1.0 - LABEL_SPEC)) * (1.0 - hole)

    # The compound's colour: what this record returns per channel, compared with a black record.
    #
    # This is a REFLECTANCE and not a tint painted on at the end. It multiplies the light on its way
    # back out, so a red record under a warm sun and a red record under a blue sky are two different
    # reds. Paper is paper whatever the record was pressed in, and the nothing down the spindle hole
    # has no colour, so both fall back to neutral.
    if disc.tint is None:
        colour = np.ones(mm.shape + (3,), dtype=np.float32)
    else:
        strength = disc.saturation * (1.0 - paper) * (1.0 - hole)
        colour = 1.0 + (disc.tint - 1.0)[None, :] * strength[:, None]

    return (nx, ny, nz, tx, ty, tz, along, across, albedo, ridge, hole, specular,
            disc.haze, colour)


def render(scale, centres=None, slots=None, shades=None):
    """Returns the frame, in linear colour.

    Called with no arguments it lays the whole table. The optional arguments are for the single-record
    render (see <c>disc()</c>), which needs ONE pressing, in the middle, in plain black. Everything
    else here is about arranging a crate.
    """
    centres = centres if centres is not None else lattice()
    heights = stack_heights(centres)
    near = neighbours(centres)

    rng = np.random.default_rng(LATTICE_SEED + 1)
    ladder = np.linspace(DISC_VINYL[0], DISC_VINYL[1], len(centres))
    shades_of = shades if shades is not None else spread(list(ladder), centres, rng)

    if slots is None:
        # The compounds: a palette slot per record, or None for a black pressing. They are dealt out by
        # the same rule as the shades: an even walk round the wheel to begin with, then swaps until no
        # two neighbouring records are the same colour. Black scores below every hue, so the black
        # records separate from each other too and do not settle into a patch.
        wheel = palette()
        coloured = int(round(len(centres) * coloured_share()))
        slots = [i * len(wheel) // max(coloured, 1) for i in range(coloured)]
        slots += [None] * (len(centres) - coloured)
        slots = spread(slots, centres, rng,
                       key=lambda s: 0.0 if s is None else 1.0 + s / len(wheel))

    pile = [Disc(c, 45 + 31 * i, shades_of[i], slots[i], scale) for i, c in enumerate(centres)]
    print(f"{len(pile)} record{'s' if len(pile) != 1 else ''}, pile at most {max(heights) + 1} deep, "
          f"{sum(1 for d in pile if d.tint is not None)} coloured")

    w, h = W * scale, H * scale
    thickness = g.THICKNESS_MM * PX_PER_MM * scale

    # The rig, resolved. A sun is a DIRECTION, the same at every pixel: that is what a light 150
    # million kilometres away means in a renderer, and it is why there is no falloff and no change
    # across the frame. A lamp is a POSITION, and has both.
    lights = []
    for spec in P["lights"]:
        light = dict(spec)
        if spec["kind"] == "sun":
            vector = np.asarray(spec["at"], dtype=np.float32)
            light["vector"] = vector / np.linalg.norm(vector)
        else:
            light["vector"] = g.lamp(spec["at"], w, h)
        light["colour"] = g.kelvin(spec["kelvin"])
        lights.append(light)

    ref = FALLOFF_REF * h

    # One frame, in colour. The material has a real per-channel reflectance, so the body and the sheen
    # do not need to be kept in separate layers.
    frame = np.empty((h, w, 3), dtype=np.float32)
    fill_colour = g.kelvin(P["fill_kelvin"])

    # One random stream for the ray samples, so that rendering again gives the same picture and not a
    # differently noisy one.
    rays = np.random.default_rng(4242)

    # The pressing's slow mottle. A pressing varies over something like a hand's width, which at this
    # scale is hundreds of pixels, and with little amplitude. A much smaller cell would look like
    # cloud and not like the variation of a surface.
    cell = max(int(300 * scale), 2)
    rng = np.random.default_rng(9)
    mottle = rng.normal(0.0, 1.0, size=(h // cell + 2, w // cell + 2)).astype(np.float32)
    mottle = np.asarray(Image.fromarray(mottle, mode="F").resize((w, h), Image.BICUBIC))

    for y0 in range(0, h, STRIP):
        y1 = min(y0 + STRIP, h)
        y, x = np.mgrid[y0:y1, 0:w]
        x = x.astype(np.float32)
        y = y.astype(np.float32)

        # Layer 0 is the table, which is never seen when the pile covers the frame. It is left in to show
        # up if the lattice ever opens a gap.
        layer = np.zeros(x.shape, dtype=np.int16)
        for i, disc in enumerate(pile):
            layer[np.hypot(x - disc.cx, y - disc.cy) <= disc.radius] = i + 1

        matter = np.zeros(x.shape + (3,), dtype=np.float32)
        mirror = np.zeros(x.shape + (3,), dtype=np.float32)
        planes = [np.zeros_like(x) for _ in lights]

        for i in range(len(pile) + 1):
            mask = layer == i
            if not mask.any():
                continue

            xs, ys = x[mask], y[mask]
            height = (heights[i - 1] if i else -1) * thickness

            over = near[i - 1] if i else range(len(pile))

            if i == 0:
                # The table. Flat, matte, and given the same grain as everything else so that it does not
                # look like a hole cut in the picture.
                nx = np.zeros_like(xs)
                ny = np.zeros_like(xs)
                nz = np.ones_like(xs)
                tx, ty, tz = np.ones_like(xs), np.zeros_like(xs), np.zeros_like(xs)
                along = np.full_like(xs, TABLE_ROUGH)
                across = np.full_like(xs, TABLE_ROUGH)
                albedo = np.full_like(xs, TABLE_ALBEDO)
                ridge = np.zeros_like(xs)
                hole = np.zeros_like(xs)
                specular = np.ones_like(xs)
                haze = 1.0
                colour = np.ones(xs.shape + (3,), dtype=np.float32)
            else:
                (nx, ny, nz, tx, ty, tz, along, across,
                 albedo, ridge, hole, specular, haze, colour) = face(pile[i - 1], xs, ys)

            # Where each light is FROM, at every point on this surface. A sun answers the same in every
            # pixel; a lamp does not, and that difference is half of what makes a room look like a room.
            aim = []
            for light in lights:
                if light["kind"] == "sun":
                    vector = light["vector"]
                    lx = np.full_like(xs, float(vector[0]))
                    ly = np.full_like(xs, float(vector[1]))
                    lz = np.full_like(xs, float(vector[2]))
                    reach = np.full_like(xs, light["power"])
                else:
                    pos = light["vector"]
                    lx = pos[0] - xs
                    ly = pos[1] - ys
                    lz = np.full_like(xs, pos[2] - height)
                    d2 = lx * lx + ly * ly + lz * lz
                    inv = 1.0 / np.sqrt(d2)
                    lx, ly, lz = lx * inv, ly * inv, lz * inv
                    # The inverse square law, which a lamp obeys and a sun does not. Without it a point light
                    # is not a point light, and the picture looks like a wash and not like a room.
                    reach = light["power"] * (ref * ref) / d2

                aim.append((lx, ly, lz, reach))

            lit = [np.ones_like(xs) for _ in lights]
            occl = np.ones_like(xs)

            for j in over:
                above = pile[j]

                # How far above this surface that record sits: its own place in the pile, not its place
                # in the painting order. Never less than one thickness: it is on top of this one, so it
                # is at least a record above it.
                gap = max(heights[j] * thickness - height, thickness)

                for k, light in enumerate(lights):
                    if not light["shadows"]:
                        continue

                    # Where that record's shadow falls on this one. For the sun the shadows are parallel,
                    # so every shadow on the table has the same length and leans the same way, and that
                    # is what you recognise as sunlight, more than the colour. A lamp throws its shadows
                    # outwards from where it stands.
                    if light["kind"] == "sun":
                        vector = light["vector"]
                        step = gap / max(float(vector[2]), 1e-6)
                        qx = xs + float(vector[0]) * step
                        qy = ys + float(vector[1]) * step
                        # The sun is half a degree wide, so the edge is sharp: over a record's thickness
                        # the penumbra is a fraction of a pixel. It is held at one pixel so that it
                        # resolves smoothly and does not jag.
                        penumbra = max(gap * light["size"], 1.0)
                    else:
                        pos = light["vector"]
                        step = gap / max(pos[2] - height, 1e-6)
                        qx = xs + (pos[0] - xs) * step
                        qy = ys + (pos[1] - ys) * step
                        # A lamp has real width, and a shadow softens with distance from what cast it.
                        penumbra = max(gap * (light["size"] * w) / max(pos[2], 1e-6), 1.0)

                    edge = np.hypot(qx - above.cx, qy - above.cy) - above.radius
                    lit[k] *= np.clip(0.5 + 0.5 * edge / penumbra, 0.0, 1.0)

                outside = np.hypot(xs - above.cx, ys - above.cy) - above.radius
                occl *= 1.0 - 0.62 * np.exp(-np.maximum(outside, 0.0) / (g.AO_REACH * gap))

            # A hole sees almost nothing of the room: it is a shaft, not a surface.
            occl *= 1.0 - 0.85 * hole

            # What a shadow on a translucent record looks like: not black. Light that landed a
            # centimetre away travels sideways inside the compound and comes back up here, still
            # carrying the record's colour. Only the BODY gets this: a sheen is a surface reflection,
            # and nothing that went inside the material comes back out as one.
            through = pile[i - 1].through if i else 0.0
            body_occl = occl + 0.5 * through * (1.0 - occl)

            for slot, light in enumerate(lights):
                lx, ly, lz, reach = aim[slot]

                ndl, spec = g.shade(nx, ny, nz, tx, ty, tz, lx, ly, lz, along, across)

                # Per channel, and both colours are in it: the light's and the record's own. This is
                # what rendering in colour means: a red pressing under a 5200 K sun returns a different
                # red from the same pressing under a 4000 K bulb, and a greyscale image with a tint
                # laid over it cannot show that.
                shade = lit[slot]
                body = reach * ndl * (shade + through * (1.0 - shade))
                matter[mask] += ((body * (albedo / np.pi))[:, None]
                                 * light["colour"][None, :] * colour)

                planes[slot][mask] = reach * ndl * shade * spec * specular

                del ndl, spec, body, shade

            up = np.clip(nz, 0.0, 1.0)

            matter[mask] += ((P["fill"] * body_occl * haze * albedo * (0.35 + 0.65 * up))[:, None]
                             * fill_colour[None, :] * colour)

            if RAYS:
                # The room as it is along the lobe, and not as one number. See trace().
                towards = [((lx, ly, lz), light["glow"])
                           for (lx, ly, lz, _), light in zip(aim, lights)]

                mirror[mask] = (trace(xs, ys, height, nx, ny, nz, tx, ty, tz, along, across,
                                      over, pile, heights, thickness, towards, rays)
                                # Masked by the groove crown, as the constant term was. The lobe carries
                                # the wall's own tilt, but here the wall is only a small amount of
                                # geometry. The fine concentric texture shows how much of the surface at
                                # that radius is crown and how much is valley, and without it the
                                # record's grain would be lost.
                                # No AO here. That term is how much of the SKY a point can see for its
                                # diffuse gather. The rays test the records in the way themselves, so
                                # multiplying by it as well would count the same occlusion twice and
                                # flatten exactly the slivers between discs where a gleam should be.
                                * (P["fill"] * haze * specular
                                   * (0.42 + 0.58 * ridge))[:, None])
            else:
                mirror[mask] = ((P["fill"] * occl * haze * g.SKY_SPEC * g.F0 * ridge
                                 * (1.0 - up * 0.5))[:, None] * fill_colour[None, :])

            del nx, ny, nz, tx, ty, tz, along, across, albedo, ridge, hole, specular
            del lit, occl, body_occl, up, colour, aim

        grain = np.random.default_rng(1000 + y0).normal(1.0, 0.030, size=x.shape).astype(np.float32)
        surface = grain * (1.0 + 0.026 * mottle[y0:y1])

        # The sheen has the light's colour and nothing else: what comes off the SURFACE of a dielectric
        # never entered the material, so the highlight of a red record is the colour of the sun and not
        # of the record. It is added to a material that has a colour of its own.
        glow = mirror.copy()
        for plane, light in zip(planes, lights):
            glow += plane[..., None] * light["colour"]

        frame[y0:y1] = (matter + glow) * surface[..., None]

    return frame


def shrink(array, mode):
    image = Image.fromarray(np.clip(array * 255, 0, 255).astype(np.uint8), mode=mode)
    return np.asarray(image.resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0


def expose(gray, mean, spread):
    """Puts the rendered surface at a stated brightness and contrast.

    The phone's ground takes both from the header photograph, so that the two are the same piece of
    vinyl. This picture states them itself, because the header is a night picture and matching to it
    could not give a morning. It uses a straight line, as the header match does: rank mapping folds
    neighbouring tones together where a picture holds thousands of pixels at nearly the same value,
    and a lit groove field is exactly that.
    """
    src = np.asarray(gray).astype(np.float32)
    out = (src - src.mean()) * (spread / max(src.std(), 1e-6)) + mean
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="L")


def main():
    frame = shrink(g.tonemap(render(SS)), "RGB")

    luma = g.LUMA.astype(np.float32)
    grey = frame @ luma

    # Exposure on the LUMINANCE alone, handed back as a scale.
    #
    # Deciding how bright and how contrasty the picture is must not also decide the colour of anything.
    # Running the affine on each channel would do that: it would pull every channel towards the same
    # mean, which is desaturation under another name.
    lifted = np.asarray(
        expose(Image.fromarray(np.clip(grey * 255, 0, 255).astype(np.uint8), mode="L"),
               P["mean"], P["spread"]), dtype=np.float32) / 255.0

    out = frame * (lifted / np.maximum(grey, 1e-4))[..., None]

    # A last step, on the colour only. Everything above is what the light and the material do; this
    # step makes the picture a background. It is the control that a camera calls vibrance. It is a
    # separate control and not a number in the render, because it is the one decision here that is
    # taste and not physics.
    grey = out @ luma
    out = grey[..., None] + (out - grey[..., None]) * P["saturation"]

    out = Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8), mode="RGB")
    out = out.filter(ImageFilter.GaussianBlur(0.35))
    out.save(OUT, quality=88, optimize=True)
    print("wrote", OUT, out.size, f"{os.path.getsize(OUT)/1024:.0f} KB")


# How the single record is exposed. See disc().
DISC_MEAN = 26.0
DISC_SPREAD = 42.0


def disc():
    """Renders one record, square, on nothing: the disc that the player spins.

    It is the same pressing that the table is made of, so the record turning in the header and the
    records lying in the background are visibly the same object. It is rendered in plain BLACK vinyl
    with no colour of its own, because the app tints it at run time: a neutral render times a
    unit-luminance hue is the same method that the table uses for its coloured pressings, and doing it
    at run time means one asset for every colour and not ten assets for ten colours.

    The alpha is zero outside the rim, so it can lie over the artwork as a disc and not as a square.
    """
    global W, H, RADIUS, PX_PER_MM, LABEL_INK

    # No wordmark on the vinyl. The player lays its OWN label over the middle and turns it, which is
    # where the spin comes from: the grooves are concentric, so a rotating ring is invisible. If the
    # wordmark were baked in, the record would look as if it stands still. The label area is still
    # rendered: matte black paper, which is exactly what the app's label sits on and what shows in the
    # ring around it.
    LABEL_INK = 0.0

    # A record on its own needs no more than this on screen; the shell draws it at a few hundred points.
    W = H = 1024
    RADIUS = W / 2 - 8          # a few pixels of margin, so the rim's own roll-off is not clipped
    PX_PER_MM = RADIUS / g.RECORD_RADIUS_MM

    scale = 2
    frame = render(scale, centres=[(W / 2, H / 2)], slots=[None], shades=[1.0])

    lit = shrink(g.tonemap(frame), "RGB")

    luma = g.LUMA.astype(np.float32)
    grey = lit @ luma

    # The disc itself, and only the disc: a record on a black square is mostly black square, and
    # including that in the exposure would raise every tone to compensate for it.
    y, x = np.mgrid[0:H, 0:W]
    inside = np.hypot(x - W / 2, y - H / 2) <= RADIUS
    face = grey[inside]

    # Its own exposure, not the table's. The table's numbers are set for a frame that is mostly the
    # dark gaps between records. A single disc that fills the square comes out grey at that mean, and a
    # grey record is not a black one. This exposure is darker and has more range, so the vinyl looks
    # black and the sweep of the sun across it stays the brightest thing in the picture, which is what
    # the tint then uses.
    gain = float((DISC_SPREAD / 255.0) / max(face.std(), 1e-5))
    out = np.clip(lit * gain + (DISC_MEAN / 255.0 - float(face.mean()) * gain), 0.0, 1.0)

    grey = out @ luma
    out = np.clip(grey[..., None] + (out - grey[..., None]) * P["saturation"], 0.0, 1.0)

    # The edge, antialiased: the coverage falls over one pixel and does not step, or the rim would
    # look like a sawn circle at every size the shell draws it.
    edge = np.clip(RADIUS + 0.5 - np.hypot(x - W / 2, y - H / 2), 0.0, 1.0)

    rgba = np.dstack([np.clip(out * 255, 0, 255), edge * 255]).astype(np.uint8)
    image = Image.fromarray(rgba, mode="RGBA")

    path = os.path.join(ASSETS, "vinyl-record.png")
    image.save(path, optimize=True)
    print("wrote", path, image.size, f"{os.path.getsize(path)/1024:.0f} KB")


if __name__ == "__main__":
    if sys.argv[1:2] == ["disc"]:
        P = MORNING
        disc()
        raise SystemExit

    wanted = sys.argv[1:] or [name for name in PRESETS if name != "morning"]
    for name in wanted:
        if name not in PRESETS:
            raise SystemExit(f"no such time of day: {name} (have {', '.join(PRESETS)})")

        P = PRESETS[name]
        OUT = os.path.join(ASSETS, "background.jpg" if name == "morning"
                           else f"background-{name}.jpg")
        print(f"── {name} ──")
        main()
