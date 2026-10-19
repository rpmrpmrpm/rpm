"""Build the desktop app icons from the iPhone app's icon.

The phone icon (RPM.iOS/.../appicon.png, exported from Assets/Icons/icons.icon) is a
1024x1024 opaque square: the rounded tile with pure black in the corners, a light rim
along its edge, and a shadow outside it. The two desktop platforms need different things from it.

macOS draws its own icon shape, which is not the phone's. Both are superellipses, but the
phone's corner is rounder (it fits an exponent near 4.5, where every macOS icon fits 5), so
the phone tile in the Dock looks smaller than the icons beside it, although both occupy the same
824 of 1024 pixels. The shape cannot be redrawn by hand: icons.icon is an Icon Composer document,
and actool renders it for any platform it is asked about. So the macOS icon is compiled from that
document into Assets/Icons/AppIcon.icns, which the app gives to the Dock (see MacDockIcon) and the
release script copies into the bundle.

Assets/Icons/icon.png is also written. It holds the tile alone, transparent around it, inset to
824 of 1024. It is the UnoIcon that Resizetizer turns into the icon set for every OTHER platform,
and it is the fallback on a machine without Xcode, where actool cannot run.

Windows needs a full square with no rounding and no edge effects: the same wordmark on the
same background gradient, from corner to corner. The tile cannot be cropped into that shape (the
rim and the rounding are part of the image), so it is rebuilt: the vertical gradient is read from
a background column and extended over the whole square, and the wordmark is recovered from the
source by how much brighter each pixel is than the background. Output is
Assets/Icons/window-icon.png and window-icon.ico, which the app sets on its window.
"""

import os
import workspace
import shutil
import subprocess
import sys
import tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = workspace.path("RPM.iOS", "rpm", "Assets.xcassets", "AppIcon.appiconset", "appicon.png")
OUT = workspace.path("RPM.Desktop", "Assets", "Icons", "icon.png")
OUT_WIN_PNG = workspace.path("RPM.Desktop", "Assets", "Icons", "window-icon.png")
OUT_WIN_ICO = workspace.path("RPM.Desktop", "Assets", "Icons", "window-icon.ico")
ICON_DOC = workspace.path("RPM.Desktop", "Assets", "Icons", "icons.icon")
OUT_ICNS = workspace.path("RPM.Desktop", "Assets", "Icons", "AppIcon.icns")
# actool reads the .icon document only from macOS 26. On older versions it writes nothing.
ICON_DOC_MIN_MACOS = "26.0"

CANVAS = 1024
CONTENT = 824
# A column of pure background: left of the "r", inside the rim.
BG_COLUMN = (56, 104)
# Rows to read the gradient from. Outside this band the rim highlight is in the way, so the
# gradient is extended to the edges by the straight line fitted through the band.
BG_ROWS = (60, 950)
# The area that the wordmark is taken from. The rim highlight and the rounded corners are also
# brighter than the background, and this keeps them out: the wordmark covers
# x 132-891, y 402-693, so nothing within 120 px of an edge belongs to it.
GLYPH_INSET = 120
# The sizes in the .ico. Windows picks a size for each place: 16 in the title bar, 256 in the task view.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# The corners are pure black, and the darkest pixel of the tile itself is (21, 22, 20). Any pixel
# at or below this value is outside the tile.
CORNER_MAX = 8


def clear_corners(im):
    """Make the pure-black area around the tile transparent, by flood fill from the four corners."""
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    stack = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        i = y * w + x
        if seen[i]:
            continue
        r, g, b, a = px[x, y]
        if a == 0:
            seen[i] = 1
            continue
        if max(r, g, b) > CORNER_MAX:
            continue
        seen[i] = 1
        px[x, y] = (0, 0, 0, 0)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return im


def gradient(im):
    """The background colour of every row, read from a clean column and extended to the edges."""
    px = im.load()
    x0, x1 = BG_COLUMN
    y0, y1 = BG_ROWS
    read = {}
    for y in range(y0, y1):
        band = sorted(sum(px[x, y][:3]) / 3.0 for x in range(x0, x1))
        read[y] = band[len(band) // 2]

    # A straight line through the band, so the rows under the rim get the colour they would have
    # without it.
    n = y1 - y0
    mean_y = (y0 + y1 - 1) / 2.0
    mean_v = sum(read.values()) / n
    span = sum((y - mean_y) ** 2 for y in read)
    slope = sum((y - mean_y) * (v - mean_v) for y, v in read.items()) / span
    return [max(0.0, min(255.0, mean_v + slope * (y - mean_y))) for y in range(im.size[1])]


def windows_square(src):
    """The same artwork as a full square: gradient from corner to corner, wordmark on top."""
    im = src.convert("RGB")
    w, h = im.size
    px = im.load()
    bg = gradient(im)
    out = Image.new("RGB", (w, h))
    dst = out.load()
    for y in range(h):
        base = bg[y]
        ground = (round(base), round(base), round(base))
        headroom = 255.0 - base
        inside_rows = GLYPH_INSET <= y < h - GLYPH_INSET
        for x in range(w):
            if not inside_rows or not (GLYPH_INSET <= x < w - GLYPH_INSET):
                dst[x, y] = ground
                continue
            r, g, b = px[x, y]
            # The wordmark is white, so the brightness of a pixel above the background is its coverage.
            cover = 0.0 if headroom <= 0 else ((r + g + b) / 3.0 - base) / headroom
            if cover <= 0.0:
                dst[x, y] = ground
            elif cover >= 1.0:
                dst[x, y] = (255, 255, 255)
            else:
                v = round(base + cover * headroom)
                dst[x, y] = (v, v, v)
    return out


def mac_icns():
    """Compile icons.icon into the macOS icon set, so the Dock gets Apple's own icon shape.

    actool needs the document to be named after the icon and needs an asset catalog next to it.
    The repository layout has neither, so both are staged in a temporary directory. actool also
    writes an Assets.car with the 1024 renderings. The .icns holds sizes 16 to 256, which are all
    the sizes that the Dock and the app switcher use.

    Skipped where it cannot run (not macOS, or no Xcode). The .icns in the repository is then used,
    and a build without any .icns falls back to the icon set built from icon.png.
    """
    if sys.platform != "darwin" or shutil.which("xcrun") is None:
        print(f"skipped {OUT_ICNS}: actool needs macOS with Xcode")
        return

    with tempfile.TemporaryDirectory() as work:
        catalog = os.path.join(work, "Assets.xcassets")
        os.makedirs(catalog)
        with open(os.path.join(catalog, "Contents.json"), "w", encoding="utf-8") as f:
            f.write('{"info":{"author":"xcode","version":1}}')
        staged = os.path.join(work, "AppIcon.icon")
        shutil.copytree(ICON_DOC, staged)
        out = os.path.join(work, "out")
        os.makedirs(out)

        run = subprocess.run(
            ["xcrun", "actool", catalog, staged,
             "--compile", out,
             "--platform", "macosx",
             "--target-device", "mac",
             "--minimum-deployment-target", ICON_DOC_MIN_MACOS,
             "--app-icon", "AppIcon",
             "--output-partial-info-plist", os.path.join(work, "partial.plist")],
            capture_output=True, text=True)

        built = os.path.join(out, "AppIcon.icns")
        if run.returncode != 0 or not os.path.exists(built):
            raise SystemExit(f"actool did not write an icns:\n{run.stdout}{run.stderr}")

        shutil.copyfile(built, OUT_ICNS)
    print(f"wrote {OUT_ICNS} (from {os.path.basename(ICON_DOC)}, macOS shape)")


def main():
    src = Image.open(SRC)

    win = windows_square(src)
    win.save(OUT_WIN_PNG)
    win.save(OUT_WIN_ICO, sizes=[(s, s) for s in ICO_SIZES])
    print(f"wrote {OUT_WIN_PNG} and {OUT_WIN_ICO} ({', '.join(str(s) for s in ICO_SIZES)})")

    mac_icns()

    im = clear_corners(src.convert("RGBA"))
    tile = im.crop(im.getbbox()).resize((CONTENT, CONTENT), Image.LANCZOS)
    out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    off = (CANVAS - CONTENT) // 2
    out.paste(tile, (off, off))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.save(OUT)
    print(f"wrote {OUT} ({CANVAS}x{CANVAS}, tile {CONTENT})")


if __name__ == "__main__":
    main()
