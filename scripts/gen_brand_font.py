#!/usr/bin/env python3
"""Writes rpm-brands, a small icon font with the marks of the music apps rpm imports from.

The import window shows these marks on the buttons that name the apps, in the same size and colour
as the Font Awesome icons around them. A font draws them the same way on every head, where an SVG
would need a different control on each.

The sources are the SVG files in scripts/brands/, one path in one colour each. Where they come from,
and whose marks they are, is in scripts/brands/README.md and in scripts/credits.json.

It writes:

- RPM.Desktop/Assets/Fonts/rpm-brands.ttf, read by the desktop (RpmBrandsFont in Themes/Generic.xaml);
- rpm-web/src/design/fonts/rpm-brands.woff, read by the web app (the 'rpm Brands' face in base.css).

Run it after changing a file in scripts/brands/ or the GLYPHS table below:

    python3 scripts/gen_brand_font.py
"""

import os
import re
import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path.parser import parse_path
from fontTools.ttLib import TTFont

import workspace

SOURCES = workspace.path("scripts", "brands")
DESKTOP = workspace.path("RPM.Desktop", "Assets", "Fonts", "rpm-brands.ttf")
WEB = os.path.join(workspace.PARENT, "rpm-web", "src", "design", "fonts", "rpm-brands.woff")

# Each mark, its code point (Private Use Area), and the file it is drawn from. The code points are
# named in MigrationDialog.xaml and MigrationWindow.svelte; change both when one changes here.
GLYPHS = [
    ("musicbee", 0xE001, "musicbee.svg"),
    ("applemusic", 0xE002, "applemusic.svg"),
    ("jellyfin", 0xE003, "jellyfin.svg"),
    ("plex", 0xE004, "plex.svg"),
    ("navidrome", 0xE005, "navidrome.svg"),
]

# Font Awesome's proportions: the em is the full height of an icon, with an eighth of it below the
# baseline. The marks are fitted into that square and centred, so they line up with the icons beside them.
EM = 1000
DESCENT = 125
MARGIN = 40


def matrix(transform: str):
    """The SVG transform attribute as an affine matrix (a, b, c, d, e, f)."""
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", transform or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "matrix":
            t = tuple(v)
        else:
            raise ValueError(f"transform {name} is not handled")
        m = multiply(m, t)
    return m


def multiply(m, t):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = t
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2, a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def outline(file: str) -> RecordingPen:
    """Every path of the SVG, with the transforms of its groups, in SVG coordinates."""
    recording = RecordingPen()

    def walk(element, m):
        m = multiply(m, matrix(element.get("transform")))
        if element.tag.endswith("path") and element.get("d"):
            parse_path(element.get("d"), TransformPen(recording, m))
        for child in element:
            walk(child, m)

    walk(ET.parse(file).getroot(), (1, 0, 0, 1, 0, 0))
    return recording


def glyph(recording: RecordingPen):
    """The outline fitted into the em square, turned the right way up, as a TrueType glyph."""
    bounds = BoundsPen(None)
    recording.replay(bounds)
    x0, y0, x1, y1 = bounds.bounds
    size = EM - 2 * MARGIN
    scale = size / max(x1 - x0, y1 - y0)
    width, height = (x1 - x0) * scale, (y1 - y0) * scale
    # SVG y runs down and font y runs up, so y is flipped around the top of the shape.
    left = (EM - width) / 2 - x0 * scale
    top = EM - DESCENT - MARGIN - (size - height) / 2 + y0 * scale
    pen = TTGlyphPen(None)
    recording.replay(TransformPen(Cu2QuPen(pen, max_err=1.0, reverse_direction=True), (scale, 0, 0, -scale, left, top)))
    return pen.glyph()


def main():
    names = [".notdef"] + [name for name, _, _ in GLYPHS]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    for name, _, file in GLYPHS:
        glyphs[name] = glyph(outline(os.path.join(SOURCES, file)))

    fb = FontBuilder(EM, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({code: name for name, code, _ in GLYPHS})
    fb.setupGlyf(glyphs)
    table = fb.font["glyf"]
    for name in names:
        table[name].recalcBounds(table)
    fb.setupHorizontalMetrics({name: (EM if name != ".notdef" else 0, getattr(table[name], "xMin", 0)) for name in names})
    fb.setupHorizontalHeader(ascent=EM - DESCENT, descent=-DESCENT)
    fb.setupNameTable({"familyName": "rpm Brands", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=EM - DESCENT, sTypoDescender=-DESCENT, usWinAscent=EM - DESCENT, usWinDescent=DESCENT)
    fb.setupPost()
    fb.font.save(DESKTOP)

    web = TTFont(DESKTOP)
    web.flavor = "woff"
    web.save(WEB)
    print(f"wrote {DESKTOP}\nwrote {WEB}")


if __name__ == "__main__":
    main()
