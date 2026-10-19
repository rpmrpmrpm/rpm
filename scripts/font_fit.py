#!/usr/bin/env python3
"""Gives the diagonal letters of Thiamine RPM a sidebearing, which they do not have.

The defect
----------
In ThiamineRPM.otf, v w x y z (and their capitals) are drawn starting to the LEFT of their own
origin (y begins 20 units before it) and end at or past their advance. Any letter in front of one
of them therefore has its ink overlapped rather than merely crowded:

    r  ink ends 5 units before its advance
    y  ink starts 20 units before its origin
    ry overlap: 15 units, which at a 96pt header is about a point and a half

It is not a kerning problem and tracking cannot fix it. Tracking adds the same space to every pair,
so a pair that overlaps by 15 units stays 15 units tighter than its neighbours however much space
is added. In "library", for example, every other pair is fine but the y touches the r.

164 letter pairs in this font overlap. All of them are "something, then one of these five".

The fix
-------
Move those five glyphs away from their own origin and widen their advance to match, so each has a
small positive sidebearing on both sides. This is one change per glyph, not 164 kern pairs, because
the defect is in five glyphs and not in the pairs.

The numbers are small on purpose. This is a compressed display face and it is MEANT to be tight.
The rest of the alphabet sits about 30 units apart at these sizes, and diagonals normally take less
than that. So the glyph gets 6 units of ink-free space on the left and 4 on the right. This removes
the overlap and keeps the spacing of the face.

Idempotent: a font whose diagonals already clear their origin is left exactly as it is, so the
script can be run again after the face is re-cut from source.

Usage:  python3 scripts/font_fit.py [path/to/ThiamineRPM.otf]
"""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform

# The five letters that reach back past their origin, in both cases. Each case is a separate glyph.
DIAGONALS = "vwxyzVWXYZ"

# The ink-free space each glyph should have on each side, in units of a 1000-unit em.
LEFT = 6
RIGHT = 4


def fit(path: Path) -> int:
    font = TTFont(path)
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]
    charstrings = font["CFF "].cff[font["CFF "].cff.fontNames[0]].CharStrings

    changed = 0

    for char in DIAGONALS:
        name = cmap.get(ord(char))
        if name is None:
            continue

        advance, _ = hmtx[name]

        bounds = BoundsPen(glyphs)
        glyphs[name].draw(bounds)
        if bounds.bounds is None:
            continue

        xmin, xmax = bounds.bounds[0], bounds.bounds[2]

        shift = LEFT - xmin
        wanted = round(xmax + shift + RIGHT)

        # Already clear of its own origin and of the next glyph: nothing to do.
        if shift <= 0 and advance >= wanted:
            continue

        shift = max(0, round(shift))
        pen = T2CharStringPen(max(advance, wanted), glyphs)
        glyphs[name].draw(TransformPen(pen, Transform().translate(shift, 0)))

        charstrings[name].program = pen.getCharString().program
        hmtx[name] = (max(advance, wanted), LEFT)

        print(f"  {char}: ink {xmin}..{xmax} advance {advance}"
              f"  ->  shifted {shift}, advance {max(advance, wanted)}")
        changed += 1

    if changed:
        font.save(path)

    return changed


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "RPM.Desktop/Assets/Fonts/ThiamineRPM.otf")
    if not path.exists():
        print(f"no font at {path}")
        return 1

    print(f"fitting {path}")
    changed = fit(path)
    print(f"{changed} glyph(s) changed" if changed else "already fitted; nothing to do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
