#!/usr/bin/env python3
"""Derives 'Thiamine RPM' from Thiamine.otf by CUTTING the very tall ascenders.

Thiamine (unitsPerEm 1000) has an x-height of 140, but its ascenders, capitals and i-dot reach
about 987: small bodies under giant stems. This script only shortens things going UP; descenders
(y, g, j, p, q) are left as drawn. To avoid squashing terminals (the f hook, serifs), the ascender
is CUT and not compressed: a horizontal band of the straight stem is removed and everything above
it moves down rigidly, so the terminal keeps its shape.

Cut = remove the band [CUT_LO, CUT_HI]: points above CUT_HI move down by (CUT_HI-CUT_LO); points
inside the band collapse to CUT_LO; points below are unchanged. Floating accents (the i and j dot)
are moved down whole so they stay round.

An accent on a letter is also a floating contour, and it must be recognised as one, or the band
takes it: a grave is at y 172-248 in Thiamine, which is INSIDE [165, 905], so it would collapse to
a flat line at 165 and the letter would render as a bare e. The dot threshold cannot simply be
lowered to catch accents, because I and J are drawn as stacks of separate segments, and every
segment above the threshold would pile onto the same line. So the letters that carry an accent are
found from Unicode, and only they use the lower floor.

Usage: python3 scripts/thiamine_shorten.py   (needs ~/Library/Fonts/Thiamine.otf, CC0)
Output: RPM.Desktop/Assets/Fonts/ThiamineRPM.otf   (family "Thiamine RPM")
"""
import os
import workspace
import unicodedata
from fontTools.ttLib import TTFont
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import RecordingPen

SRC = os.path.expanduser("~/Library/Fonts/Thiamine.otf")
OUT = workspace.path("RPM.Desktop", "Assets", "Fonts", "ThiamineRPM.otf")

X_HEIGHT = 140
CAP = 987
CUT_LO = 165                 # bottom of the removed band
CUT_HI = 905                 # top of the removed band
CUT = CUT_HI - CUT_LO        # stem length removed (520): caps and ascenders go from 987 to 467
FLOAT_MINY = 260             # a contour entirely above this is a floating accent (dot)
ACCENT_MINY = X_HEIGHT + 10  # the same test, for a letter that is KNOWN to carry an accent
DOT_BOTTOM = 175             # where a floating accent's bottom lands
NEW_ASCENT = 300
# A glyph whose own body tops out at or below this has no tall stem, and cutting it only flattens
# its top: the digits and most punctuation reach about 205, inside the band, so the cut gives them
# a flat lid. The tallest such glyph is the registered sign at 334; real stems start at 869.
# thiamine_short_glyphs.py repairs the shipped font for these glyphs.
STEMLESS_TOP = 340
# I and J are drawn as stacks of separate dots up to the cap height, so their body is short but they
# are not stemless: they keep the cut that turns them into a short stem with a dot.
STACKED = {"I", "J"}

def cut(y):
    """Only shortens going up; never changes y <= X_HEIGHT (so descenders are unchanged)."""
    if y <= X_HEIGHT:
        return y
    if y <= CUT_LO:
        return y
    if y <= CUT_HI:
        return CUT_LO            # collapse the removed band
    return y - CUT               # terminal above the band drops rigidly

POINT_CMDS = {"moveTo", "lineTo", "curveTo", "qCurveTo"}


def accented(cmap):
    """Glyph names whose top contour is an accent and not part of the letter.

    The names come from Unicode and not from a hand-written list, so no letter is left flat by
    mistake. A character that DECOMPOSES into a base plus a combining mark carries an accent, and a
    spacing accent on its own (`´`, `¨`) is an accent.
    """
    names = set()

    for cp, name in cmap.items():
        ch = chr(cp)
        composed = unicodedata.decomposition(ch)

        if composed and not composed.startswith("<"):
            names.add(name)
        elif unicodedata.category(ch) == "Sk":
            names.add(name)

    return names

def contour_bounds(cmds):
    ys = [p[1] for c, a in cmds if c in POINT_CMDS for p in a]
    return (min(ys), max(ys)) if ys else (0, 0)

def replay(cmds, out, fy):
    for c, a in cmds:
        if c in POINT_CMDS:
            getattr(out, c)(*[(p[0], fy(p[1])) for p in a])
        elif c == "closePath":
            out.closePath()
        elif c == "endPath" and hasattr(out, "endPath"):
            out.endPath()
        elif c == "addComponent":
            out.addComponent(*a)

def main():
    f = TTFont(SRC)
    cff = f["CFF "].cff
    cs = cff[cff.fontNames[0]].CharStrings
    gs = f.getGlyphSet()
    hmtx = f["hmtx"]
    marks = accented(f.getBestCmap())
    for name in cs.keys():
        rec = RecordingPen()
        try:
            cs[name].draw(rec)
        except Exception:
            continue
        contours, cur = [], []
        for cmd, args in rec.value:
            if cmd == "addComponent":
                contours.append([(cmd, args)]); continue
            if cmd == "moveTo" and cur:
                contours.append(cur); cur = []
            cur.append((cmd, args))
        if cur:
            contours.append(cur)

        width = hmtx[name][0] if name in hmtx.metrics else 0
        out = T2CharStringPen(width, gs)
        floor = ACCENT_MINY if name in marks else FLOAT_MINY
        body = [contour_bounds(c)[1] for c in contours
                if c and c[0][0] != "addComponent" and contour_bounds(c)[0] < floor]
        stemless = body and max(body) <= STEMLESS_TOP and name not in STACKED
        shape = (lambda y: y) if stemless else cut
        for cmds in contours:
            if cmds and cmds[0][0] == "addComponent":
                replay(cmds, out, cut); continue
            lo, hi = contour_bounds(cmds)
            if lo >= floor:                            # floating accent: move it whole, keep it round
                dy = DOT_BOTTOM - lo
                replay(cmds, out, lambda y, dy=dy: y + dy)
            else:
                replay(cmds, out, shape)
        newcs = out.getCharString()
        newcs.private = cs[name].private
        newcs.globalSubrs = cs[name].globalSubrs
        cs[name] = newcs

    f["hhea"].ascent = NEW_ASCENT
    f["OS/2"].usWinAscent = NEW_ASCENT
    f["OS/2"].sTypoAscender = NEW_ASCENT
    if hasattr(f["OS/2"], "sCapHeight"):
        f["OS/2"].sCapHeight = CAP - CUT
    nm = f["name"]
    for nid, val in [(1, "Thiamine RPM"), (4, "Thiamine RPM"), (6, "ThiamineRPM"), (16, "Thiamine RPM")]:
        nm.setName(val, nid, 3, 1, 0x409)
    f.save(OUT)
    print("wrote", OUT, "| cut", CUT, "→ caps/ascenders", CAP - CUT)

if __name__ == "__main__":
    main()
