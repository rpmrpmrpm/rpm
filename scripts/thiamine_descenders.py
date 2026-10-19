#!/usr/bin/env python3
"""Shortens the descenders of 'Thiamine RPM' to the same depth as the ascender height.

The face is drawn small inside its em box: the x-height is 140, and after thiamine_shorten.py the
ascenders reach 247, which is 107 units above the x-height band that the word is read on. The
descenders are not changed by that script and run to -185, so g, j and y would hang 185 below the
baseline against 107 above the body, and the word would look as if it falls out of its line.

The descenders are cut to the same 107, and each letter is cut in the way its drawing allows:

- y Y (and the accented ones) are polygons whose tail already ends in a FLAT terminal. Clipping the
  outline at -107 shortens the tail and keeps the same flat end, higher up. Nothing is squashed.
- g G j J end in a hook, which a squash would ruin. Instead a horizontal band is removed from the
  STRAIGHT stem above the hook, and everything below it moves up rigidly. The hook keeps its exact
  shape and only the stem gets shorter. thiamine_shorten.py uses the same method on the ascenders.

Nothing else is changed: no advance widths, no sidebearings, and not the vertical metrics of the
font. hhea/OS2 still declare the original descent, so every line box in the app stays where it is.

It runs on the shipped font IN PLACE. The shipped file is the master: its sidebearings do not match
a fresh run of thiamine_shorten.py, so it must not be derived again from Thiamine.otf. The script is
idempotent: a font that is already cut is left alone.

Usage: python3 scripts/thiamine_descenders.py
"""
import os
import workspace
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

FONT = workspace.path("RPM.Desktop", "Assets", "Fonts", "ThiamineRPM.otf")

DEPTH = 107                  # how far below the baseline a descender may reach: ascender minus x-height
OLD_DEPTH = 185
CUT = OLD_DEPTH - DEPTH      # 78 units of stem to remove

# The band removed from the stem. It must lie where BOTH edges of the stem are straight and vertical,
# between the bottom of the bowl or body and the top of the hook, so that removing it cannot bend
# anything. For g/G that range is -130..13 and for j/J it is -130..142; this band is inside both.
BAND_HI = -22
BAND_LO = BAND_HI - CUT      # -100

CLIP = {"y", "Y", "yacute", "Yacute", "ydieresis", "Ydieresis"}
STEM = {"g", "G", "j", "J"}

POINT_CMDS = {"moveTo", "lineTo", "curveTo", "qCurveTo"}
FLOOR = -DEPTH


def shorten_stem(y):
    """Lifts everything under the band by the height of the band; the hook below stays whole."""
    if y > BAND_HI:
        return y
    if y >= BAND_LO:
        return BAND_HI          # nothing is drawn inside the band, so this does not happen in practice
    return y + CUT


def clip_contour(cmds):
    """Cuts the tail off at FLOOR. It is only valid where the outline is straight there, as in the y
    family, whose tails are polygons. Each crossing edge is intersected with the line and the part
    below it is dropped."""
    pts = []
    for cmd, args in cmds:
        if cmd in POINT_CMDS:
            if cmd == "curveTo" or cmd == "qCurveTo":
                for p in args:
                    if p[1] < FLOOR:
                        raise ValueError("a curve crosses the clip line; this glyph needs cutting, not clipping")
            pts.append((cmd, list(args)))
        else:
            pts.append((cmd, list(args) if args else []))

    flat = [(c, p) for c, a in pts if c in POINT_CMDS for p in a]
    if not flat or min(p[1] for _, p in flat) >= FLOOR:
        return cmds

    def cross(a, b):
        """Where the segment from a to b meets the clip line."""
        t = (FLOOR - a[1]) / (b[1] - a[1])
        return (a[0] + (b[0] - a[0]) * t, FLOOR)

    ring = [p for _, p in flat]
    out = []
    for i, cur in enumerate(ring):
        nxt = ring[(i + 1) % len(ring)]
        if cur[1] >= FLOOR:
            out.append(cur)
            if nxt[1] < FLOOR:
                out.append(cross(cur, nxt))
        elif nxt[1] >= FLOOR:
            out.append(cross(cur, nxt))

    rebuilt = [("moveTo", [out[0]])]
    rebuilt += [("lineTo", [p]) for p in out[1:]]
    rebuilt.append(("closePath", []))
    return rebuilt


def split_contours(rec):
    contours, cur = [], []
    for cmd, args in rec.value:
        if cmd == "addComponent":
            contours.append([(cmd, args)])
            continue
        if cmd == "moveTo" and cur:
            contours.append(cur)
            cur = []
        cur.append((cmd, args))
    if cur:
        contours.append(cur)
    return contours


def replay(cmds, out, fy=None):
    for cmd, args in cmds:
        if cmd in POINT_CMDS:
            pts = [(p[0], fy(p[1])) for p in args] if fy else [tuple(p) for p in args]
            getattr(out, cmd)(*pts)
        elif cmd == "closePath":
            out.closePath()
        elif cmd == "endPath" and hasattr(out, "endPath"):
            out.endPath()
        elif cmd == "addComponent":
            out.addComponent(*args)


def main():
    f = TTFont(FONT)
    cff = f["CFF "].cff
    cs = cff[cff.fontNames[0]].CharStrings
    gs = f.getGlyphSet()
    hmtx = f["hmtx"]

    done = 0
    for name in sorted(CLIP | STEM):
        if name not in cs:
            continue
        rec = RecordingPen()
        cs[name].draw(rec)
        contours = split_contours(rec)

        depth = min((p[1] for cmd, args in rec.value if cmd in POINT_CMDS for p in args), default=0)
        if depth >= FLOOR - 1:
            continue                                  # already cut: the script can be run twice

        out = T2CharStringPen(hmtx[name][0], gs)
        for cmds in contours:
            lo = min((p[1] for cmd, args in cmds if cmd in POINT_CMDS for p in args), default=0)
            if lo >= FLOOR:
                replay(cmds, out)                     # above the line: unchanged, accents included
            elif name in CLIP:
                replay(clip_contour(cmds), out)
            else:
                replay(cmds, out, shorten_stem)
        new = out.getCharString()
        new.private = cs[name].private
        new.globalSubrs = cs[name].globalSubrs
        cs[name] = new
        done += 1

    if done == 0:
        print("nothing to do — the descenders are already at", DEPTH)
        return

    f.save(FONT)
    print(f"cut {done} glyphs to {DEPTH} below the baseline (was {OLD_DEPTH})")


if __name__ == "__main__":
    main()
