"""Builds the two pictures that are drawn over a whole CD, from the original artwork.

Sources, in RPM.Desktop/Assets/Brand/cd-overlays (kept out of the shipped app):
  cd-face-source.png     a clean rim ring and the rpm hub, transparent elsewhere
  cd-spindle-source.png  a CD player's spindle, transparent elsewhere

Both are 1500x1569, drawn about (750, 767), with the disc's outer edge at radius 700. The parts are
not quite concentric in the originals (measured in source pixels):

  rim outer edge  centre (750.29, 767.51)  r 700.0
  rim inner edge  centre (750.00, 766.16)  r 676.5
  hub outer edge  centre (748.98, 766.66)  r 214.6
  spindle         centre (749.48, 766.00)  r 86.0

The centres are up to 1.3 px apart, which is about 0.1% of the diameter and shows as a wobble when
the disc turns. So each part is put on the output's centre separately:

  - The rim ring is one colour all the way round, so it is redrawn concentric from its own radial
    profile: each source pixel's place across the ring is measured against the inner and outer edge
    at that angle, and the profile is averaged over every angle. The ring is opaque out to the
    disc's edge, which is cut sharp, so none of the photograph under it shows past the ring.
  - The hub carries the rpm mark, so it is moved and not redrawn: it is shifted by the sub-pixel
    offset of the centre of its outer edge.
  - The spindle is cropped around its own centre.

Output, in RPM.Desktop/Assets (shipped, drawn by Presentation/Controls/CdOverlay.cs):
  cd-face.png     1024 square, the disc's edge on the inscribed circle
  cd-spindle.png  176 square at the source's scale; CdOverlay draws it at 176/1400 of the diameter

Run from the repo's RPM folder:  python scripts/make_cd_overlays.py
"""

import os
import workspace

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCES = workspace.path("RPM.Desktop", "Assets", "Brand", "cd-overlays")
ASSETS = workspace.path("RPM.Desktop", "Assets")

# Measured in the original images, in pixel-edge coordinates (pixel i covers i..i+1).
RIM_OUTER = (750.29, 767.51, 700.01)
RIM_INNER = (750.00, 766.16, 676.52)
HUB_CENTRE = (748.98, 766.66)
SPINDLE_CENTRE = (749.48, 766.00)

# The disc's outer radius, which is also the half-size of the square that the face is laid out on,
# in source pixels.
DISC_RADIUS = 700

# The radius of the redrawn ring's inner edge: 5% of the radius in from the disc's edge. It must be
# at least as wide as the clear rim of a photographed CD, which is about 4.3% of the radius. A ring
# that is narrower (the original's inner edge is at 676.5, or 3.4%) lets a sliver of that clear rim
# show inside it.
RING_INNER = 665
FACE_EDGE = 1024

# Everything inside this radius is the hub; the ring starts well outside it.
HUB_EXTENT = 230

# The half-size of the spindle's square. The spindle's radius is about 86, so 88 keeps its
# antialiased edge whole.
SPINDLE_HALF = 88


def premultiplied(rgba):
    out = rgba.astype(np.float64)
    out[..., :3] *= out[..., 3:4] / 255.0
    return out


def unpremultiplied(pm):
    out = pm.copy()
    alpha = out[..., 3:4]
    out[..., :3] = np.where(alpha > 0, out[..., :3] * 255.0 / np.maximum(alpha, 1e-6), 0)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def shifted(image, centre_x, centre_y, half):
    """Returns a square of side 2*half from image, centred on the source point (centre_x, centre_y).
    It is resampled with premultiplied alpha, so a sub-pixel shift does not darken the edges."""
    size = 2 * half
    # Image.transform maps each output pixel to source = (a*x + b*y + c, d*x + e*y + f).
    coefficients = (1, 0, centre_x - half, 0, 1, centre_y - half)
    return image.convert("RGBa").transform((size, size), Image.AFFINE, coefficients, Image.BICUBIC)


def ring_profile(source):
    """Returns the ring's colour and alpha against u, the place across the ring: 0 at the inner edge
    and 1 at the outer edge, measured at each angle against the two edges at that angle."""
    pm = premultiplied(np.asarray(source))
    bins = np.linspace(-0.6, 1.0, 321)
    sums = np.zeros((len(bins), 4))
    counts = np.zeros(len(bins))
    for k in range(2880):
        t = 2 * np.pi * k / 2880
        ux, uy = np.cos(t), np.sin(t)
        inner = _edge_along(RIM_INNER, ux, uy)
        outer = _edge_along(RIM_OUTER, ux, uy)
        for i, u in enumerate(bins):
            # The point at place u on this ray, measured from the inner edge's centre.
            r = inner + u * (outer - inner)
            x = RIM_INNER[0] + r * ux
            y = RIM_INNER[1] + r * uy
            xi, yi = int(np.floor(x - 0.5)), int(np.floor(y - 0.5))
            fx, fy = x - 0.5 - xi, y - 0.5 - yi
            if not (0 <= xi < pm.shape[1] - 1 and 0 <= yi < pm.shape[0] - 1):
                continue
            value = (pm[yi, xi] * (1 - fx) * (1 - fy) + pm[yi, xi + 1] * fx * (1 - fy)
                     + pm[yi + 1, xi] * (1 - fx) * fy + pm[yi + 1, xi + 1] * fx * fy)
            sums[i] += value
            counts[i] += 1
    return bins, sums / np.maximum(counts, 1)[:, None]


def _edge_along(circle, ux, uy):
    """Returns the distance from the centre of RIM_INNER, along (ux, uy), at which the given circle
    is crossed."""
    cx, cy, r = circle
    dx, dy = RIM_INNER[0] - cx, RIM_INNER[1] - cy
    # Solve |d + s*u| = r for s > 0.
    b = dx * ux + dy * uy
    return -b + np.sqrt(b * b - (dx * dx + dy * dy - r * r))


def face():
    source = Image.open(os.path.join(SOURCES, "cd-face-source.png")).convert("RGBA")
    size = 2 * DISC_RADIUS
    ys, xs = np.mgrid[0:size, 0:size]
    distance = np.hypot(xs + 0.5 - DISC_RADIUS, ys + 0.5 - DISC_RADIUS)

    # The ring, concentric, with the original's colours across it, drawn from RING_INNER to the disc's
    # edge. The inner fade comes from the original, stretched to the new ring width. From the middle
    # of the ring outwards the ring is opaque, and its outer edge is the disc's edge, cut with one
    # pixel of antialiasing.
    inner_r, outer_r = RING_INNER, RIM_OUTER[2]
    bins, profile = ring_profile(source)
    alpha = profile[:, 3]
    rgb = profile[:, :3] * 255.0 / np.maximum(alpha, 1e-6)[:, None]
    # Where the original is almost transparent its colour is noise. The nearest well-covered colour
    # replaces it, and the alpha gives it no weight anyway.
    covered = alpha > 32
    for channel in range(3):
        rgb[:, channel] = np.interp(bins, bins[covered], rgb[covered, channel])
    alpha = np.where(bins >= 0.5, 255.0, alpha)

    u = (distance - inner_r) / (outer_r - inner_r)
    ring = np.zeros((size, size, 4))
    ring[..., 3] = np.interp(u, bins, alpha, left=0, right=255.0)
    for channel in range(3):
        ring[..., channel] = np.interp(u, bins, rgb[:, channel]) * ring[..., 3] / 255.0
    cover = np.clip(DISC_RADIUS + 0.5 - distance, 0.0, 1.0)
    ring *= cover[..., None]

    # The hub, moved onto the centre and limited to its own radius.
    hub = premultiplied(np.asarray(shifted(source, HUB_CENTRE[0], HUB_CENTRE[1], DISC_RADIUS).convert("RGBA")))
    hub[distance > HUB_EXTENT] = 0

    combined = ring + hub * (1 - ring[..., 3:4] / 255.0)
    square = Image.fromarray(unpremultiplied(combined), "RGBA")
    scaled = square.convert("RGBa").resize((FACE_EDGE, FACE_EDGE), Image.LANCZOS).convert("RGBA")
    scaled.save(os.path.join(ASSETS, "cd-face.png"), optimize=True)


def spindle():
    source = Image.open(os.path.join(SOURCES, "cd-spindle-source.png")).convert("RGBA")
    shifted(source, SPINDLE_CENTRE[0], SPINDLE_CENTRE[1], SPINDLE_HALF).convert("RGBA").save(
        os.path.join(ASSETS, "cd-spindle.png"), optimize=True)


if __name__ == "__main__":
    face()
    spindle()
    print("wrote", os.path.join(ASSETS, "cd-face.png"), "and", os.path.join(ASSETS, "cd-spindle.png"))
