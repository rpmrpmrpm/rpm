#!/usr/bin/env python3
"""Restores the tops of the short glyphs of 'Thiamine RPM': the digits, ( ) / ? & % # @ [ ] { } * ©,
Ø ø, I and J.

thiamine_shorten.py shortens the tall stems by removing the band 165..905 from every glyph, and a
point inside that band is flattened to 165. A glyph with no tall stem has nothing to remove, but
its top can still be inside the band: Thiamine draws its digits and most punctuation up to about
205, so they would lose their top 40 units and come out sliced flat (a 0 with a straight lid, a 1
with no flag). thiamine_shorten.py leaves such glyphs alone; this script repairs the shipped font,
which is the master copy and must not be derived again from Thiamine.otf (see
thiamine_descenders.py).

The repair changes only what is needed. For each glyph whose own top in Thiamine.otf is at or below
STEMLESS_TOP and above the floor of the band, the shipped outline and the original are compared
point by point. They must have the same commands in the same order, and every point must be equal
except the points that the band flattened (original y above 165, shipped y exactly 165). Those
points, and only those, get their original y back.

In some glyphs the collapse also dropped points: [ ] lost their top arms, the registered sign
became an arc, and the trademark sign and the spacing circumflex and caron became a flat line. The
outlines then no longer line up, and the original outline is put back whole. This is safe only
because nothing else changed those glyphs: the band does not change anything below 165, the
descender pass touches g G j J y Y only, and the script checks, before it writes anything, that the
advance of the glyph is still equal to the original and that its outline is within the horizontal
span of the original.

Three kinds of glyph are left as shipped on purpose: the accented letters, whose accents
thiamine_shorten.py moved down deliberately; I and J, which Thiamine draws as a stack of separate
dots and which the cut turns into a short stem with a dot; and any glyph shaped by the descender
pass. The script is idempotent: a repaired glyph matches the original and is left alone.

Usage: python3 scripts/thiamine_short_glyphs.py      (needs ~/Library/Fonts/Thiamine.otf, CC0)
Then copy RPM.Desktop/Assets/Fonts/ThiamineRPM.otf to the phone's RPMUI resources.
"""
import os
import workspace

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

SRC = os.path.expanduser("~/Library/Fonts/Thiamine.otf")
FONT = workspace.path("RPM.Desktop", "Assets", "Fonts", "ThiamineRPM.otf")

CUT_LO = 165          # the floor of the band in thiamine_shorten.py: where flattened points end up
STEMLESS_TOP = 340    # the tallest glyph with no stem is the registered sign at 334; stems reach 869 or more
FLOAT_MINY = 260      # the floating-accent test of thiamine_shorten.py: such contours are not the glyph's body
POINT_CMDS = {"moveTo", "lineTo", "curveTo", "qCurveTo"}
STACKED = {"I", "J"}                            # dot stacks; the short stem made by the cut is their shipped form
DESCENDERS = {"g", "G", "j", "J", "y", "Y"}     # shaped by thiamine_descenders.py


def record(charstrings, name):
    rec = RecordingPen()
    charstrings[name].draw(rec)
    return rec.value


def body_top(cmds):
    """The top of the body of the glyph: the highest point of a contour that is not a floating accent."""
    tops, contour = [], []
    for cmd, args in cmds + [("moveTo", ())]:
        if cmd == "moveTo" and contour:
            ys = [p[1] for c, a in contour if c in POINT_CMDS for p in a]
            if ys and min(ys) < FLOAT_MINY:
                tops.append(max(ys))
            contour = []
        contour.append((cmd, args))
    return max(tops) if tops else None


def repaired(shipped, original):
    """The shipped commands with the flattened points lifted back, or None if the two do not match."""
    if len(shipped) != len(original):
        return None
    out, lifted = [], 0
    for (sc, sa), (oc, oa) in zip(shipped, original):
        if sc != oc or len(sa) != len(oa):
            return None
        if sc not in POINT_CMDS:
            out.append((sc, sa))
            continue
        points = []
        for sp, op in zip(sa, oa):
            if sp == op:
                points.append(sp)
            elif sp[0] == op[0] and sp[1] == CUT_LO and op[1] > CUT_LO:
                points.append(op)
                lifted += 1
            elif sp[0] == op[0] and op[1] < 0:
                points.append(sp)          # the descender pass moved it: keep the shipped point
            else:
                return None
        out.append((sc, tuple(points)))
    return out, lifted


def accented(cmap):
    """The glyphs that carry an accent, found from Unicode in the same way as in thiamine_shorten.py."""
    import unicodedata
    names = set()
    for cp, name in cmap.items():
        composed = unicodedata.decomposition(chr(cp))
        if (composed and not composed.startswith("<")) or unicodedata.category(chr(cp)) == "Sk":
            names.add(name)
    return names


def extent(glyphset, name):
    pen = BoundsPen(glyphset)
    glyphset[name].draw(pen)
    return (pen.bounds[0], pen.bounds[2]) if pen.bounds else None


def main():
    original = TTFont(SRC)
    ocs = original["CFF "].cff[original["CFF "].cff.fontNames[0]].CharStrings
    font = TTFont(FONT)
    cff = font["CFF "].cff
    cs = cff[cff.fontNames[0]].CharStrings
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]

    keep = accented(original.getBestCmap()) | STACKED | DESCENDERS
    ogs = original.getGlyphSet()
    changed = []
    for name in cs.keys():
        if name not in ocs or name in keep:
            continue
        try:
            o = record(ocs, name)
            s = record(cs, name)
        except Exception:
            continue
        top = body_top(o)
        if top is None or not (CUT_LO < top <= STEMLESS_TOP):
            continue
        result = repaired(s, o)
        if result is None:
            # Points were lost, not only flattened: put the original back whole, if it is still where
            # the shipped glyph is.
            # The collapse only moves points down, never sideways, so the shipped glyph must lie
            # within the horizontal span of the original (a collapsed accent is narrower: a flat line
            # at 165).
            shipped, drawn = extent(gs, name), extent(ogs, name)
            inside = shipped is None or (drawn is not None and drawn[0] <= shipped[0] and shipped[1] <= drawn[1])
            if hmtx[name] != original["hmtx"][name] or not inside:
                print(f"skipped {name}: its width or position differs from Thiamine.otf")
                continue
            cmds, lifted = o, "whole"
        else:
            cmds, lifted = result
            if not lifted:
                continue
        pen = T2CharStringPen(hmtx[name][0], gs)
        for cmd, args in cmds:
            getattr(pen, cmd)(*args)
        new = pen.getCharString()
        new.private = cs[name].private
        new.globalSubrs = cs[name].globalSubrs
        cs[name] = new
        changed.append(f"{name} ({lifted})")

    if changed:
        font.save(FONT)
        print(f"lifted {len(changed)} glyphs: " + ", ".join(changed))
    else:
        print("nothing to lift; the font is already repaired")


if __name__ == "__main__":
    main()
