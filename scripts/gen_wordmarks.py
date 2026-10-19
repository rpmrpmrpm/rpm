#!/usr/bin/env python3
"""Writes RPM.Desktop/Presentation/Main/Genres/GenreWordmarks.Data.cs, the iPhone's
GenreWordmarks.Data.swift and the Android TV app's GenreWordmarkTable.kt from scripts/wordmarks.json.

What this is for
----------------
Every shelf on the genres wall is set in its own typeface: Anton for Rock, Monoton for Disco, a
blackletter for Religious, an eight-by-eight bitmap face for Video Game, and so on. There are 35
faces. Shipping 35 fonts to draw 36 words would cost several megabytes of app size, and every font
would have to be licensed, loaded and given a fallback at runtime.

So the words are cut here instead. Each name is set once, at build time, and the result is the
OUTLINE of that setting as a path: the letterforms as vector shapes, with no font behind them. The
app draws a Path and scales it. There is nothing to load and no fallback is needed, and a name is
the same drawing at 40 points on the wall and at 200 on the genre's own page.

Every face named in wordmarks.json is under the SIL Open Font License, which allows the outlines to
be embedded in and distributed with a work. Nothing here is redistributed AS a font: the .ttf files
are downloaded to a scratch cache and read, and they never leave this machine.

What comes out
--------------
Two paths per genre. A wordmark in the left column of the wall is written flush LEFT and one in the
right column flush RIGHT (see the wall's template), and for a name set on two lines these are two
different drawings. A single-line name gets one string that is used twice.

The colour is written here too, because the face and the colour over the photograph are one
decision about one shelf, and they must not be able to drift apart in two files.

Run after editing scripts/wordmarks.json:

    python3 scripts/gen_wordmarks.py

The first run needs the network. The faces are cached under scripts/.fontcache after that.
"""

import json
import workspace
import math
import os
import re
import sys
import urllib.request

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = workspace.path("scripts", "wordmarks.json")
SHELVES = workspace.path("scripts", "subgenres.json")
PALETTE = workspace.path("RPM.Desktop", "Assets", "RpmPalette.xaml")
CACHE = workspace.path("scripts", ".fontcache")
# In RPMSharedUI, which the phone and the Apple TV app both use.
SWIFT_TARGET = workspace.path("RPM.iOS", "Modules", "RPMSharedUI", "Sources", "RPMSharedUI",
                            "GenreWordmarks.Data.swift")
KOTLIN_TARGET = workspace.path("RPM.Android", "core", "src", "main", "java", "com", "rpm", "player",
                             "core", "library", "GenreWordmarkTable.kt")
TARGET = workspace.path(
    "RPM.Desktop", "Presentation", "Main", "Genres", "GenreWordmarks.Data.cs")

# The wall's own name for music that has no genre (GenreWall.Unclassified). A person cannot pick it
# as a shelf, so it is not in subgenres.json, but it still needs a wordmark.
UNCLASSIFIED = "Other"

# The most shelves that may share one palette colour. Ten colours over 36 shelves is about four
# each. With more than five, one colour starts to dominate the wall.
MOST_PER_COLOUR = 5

# The height of every wordmark, in drawing units. All paths use the same units, so a caller can
# work with width as a ratio. The app scales the paths; this is only the scale used in the
# calculations.
EM = 1000.0


# ── the faces ───────────────────────────────────────────────────────────────────────────────────

def font_path(genre):
    """Returns the path of the face on this machine, downloading it if it is not there yet.

    There are two ways to name a face. Most faces are named by FAMILY and fetched from Google Fonts,
    which serves a static instance for any weight that a family declares. A request for Josefin Sans
    at 600 comes back already cut at 600, so this script never has to interpolate a variable font.

    The other faces are named by URL, because the best display faces are not all in one place. The
    League of Moveable Type and Velvetyne publish theirs as files, and a `url` in the JSON points
    straight at one. For both ways the rule is the licence and not the host: the face must allow its
    outlines to be embedded in and distributed with a work, as the SIL Open Font License does, and
    every face in wordmarks.json is under that licence. Nothing is redistributed AS a font: the files
    are downloaded to a scratch cache and read, and they never leave this machine."""
    family = genre["font"]
    axes = genre.get("axes") or {}
    url = genre.get("url")

    os.makedirs(CACHE, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    if axes:
        slug += "-" + "-".join(f"{k}{v}" for k, v in sorted(axes.items()))
    kept = os.path.join(CACHE, slug + os.path.splitext(url)[1] if url else CACHE)
    kept = os.path.join(CACHE, slug + (os.path.splitext(url)[1] if url else ".ttf"))
    if os.path.exists(kept):
        return kept

    if url is None:
        query = family.replace(" ", "+")
        if axes:
            names = ",".join(sorted(axes))
            values = ",".join(str(axes[k]) for k in sorted(axes))
            query += f":{names}@{values}"
        page = f"https://fonts.googleapis.com/css2?family={query}"

        # An old user agent on purpose: for a modern one Google Fonts answers with woff2, which
        # fontTools can read only if brotli is installed. For an old one it answers with a plain
        # TrueType file.
        request = urllib.request.Request(page, headers={"User-Agent": "Mozilla/4.0"})
        try:
            css = urllib.request.urlopen(request, timeout=30).read().decode("utf8")
        except Exception as error:
            sys.exit(f"{family}: could not ask Google Fonts for it ({error}).")

        found = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if not found:
            sys.exit(f"{family}: Google Fonts returned no TrueType file for {axes or 'the regular'}.")
        url = found.group(1)

    try:
        data = urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    except Exception as error:
        sys.exit(f"{family}: could not download it from {url} ({error}).")

    with open(kept, "wb") as f:
        f.write(data)
    return kept


def kerning(font):
    """Returns every kern pair the face carries, as {(left, right): units}.

    A face can keep them in two places: the old `kern` table, and GPOS pair positioning under the
    `kern` feature, which is where newer fonts keep them. Without the pairs, a display face set
    large has visible gaps. A face like Anton is defined by how tightly it sets, and a wordmark
    drawn from advance widths alone does not look like that face."""
    pairs = {}

    if "kern" in font:
        for table in font["kern"].kernTables:
            pairs.update(table.kernTable)

    if "GPOS" not in font:
        return pairs

    gpos = font["GPOS"].table
    if not gpos.FeatureList or not gpos.LookupList:
        return pairs

    wanted = set()
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == "kern":
            wanted.update(record.Feature.LookupListIndex)

    for index in sorted(wanted):
        lookup = gpos.LookupList.Lookup[index]
        for subtable in lookup.SubTable:
            # An extension lookup wraps a pair-positioning lookup; use the wrapped one.
            if getattr(subtable, "ExtSubTable", None) is not None:
                subtable = subtable.ExtSubTable
            _pairs_from(subtable, pairs)

    return pairs


def _pairs_from(subtable, pairs):
    """Adds the pairs of one PairPos subtable to `pairs`, whichever of its two formats it uses."""
    if getattr(subtable, "Format", None) == 1 and getattr(subtable, "PairSet", None):
        firsts = subtable.Coverage.glyphs
        for first, pairset in zip(firsts, subtable.PairSet):
            for record in pairset.PairValueRecord:
                value = getattr(record.Value1, "XAdvance", 0) if record.Value1 else 0
                if value:
                    pairs[(first, record.SecondGlyph)] = value
        return

    if getattr(subtable, "Format", None) == 2 and getattr(subtable, "Class1Record", None):
        first_class = getattr(subtable.ClassDef1, "classDefs", {})
        second_class = getattr(subtable.ClassDef2, "classDefs", {})
        covered = set(subtable.Coverage.glyphs)

        # Class 0 means "covered glyphs that are in no other class". It is not listed in the class
        # definition, so it is found by absence.
        by_first = {}
        for glyph in covered:
            by_first.setdefault(first_class.get(glyph, 0), []).append(glyph)
        by_second = {}
        for glyph, klass in second_class.items():
            by_second.setdefault(klass, []).append(glyph)

        for i, class1 in enumerate(subtable.Class1Record):
            for j, class2 in enumerate(class1.Class2Record):
                value = getattr(class2.Value1, "XAdvance", 0) if class2.Value1 else 0
                if not value:
                    continue
                for left in by_first.get(i, []):
                    for right in by_second.get(j, []):
                        pairs[(left, right)] = value


# ── the setting ─────────────────────────────────────────────────────────────────────────────────

class OutlinePen(BasePen):
    """A pen that writes the XAML path mini-language, using only the four commands that a letterform
    needs.

    Quadratic curves are not used on purpose: BasePen turns a TrueType quadratic into a cubic, so
    the output is only M, L, C and Z, whatever the face was drawn in. One output dialect means less
    for the XAML parser to get wrong.

    <b>The pen also writes as little as it can.</b> Coordinates are whole units of a drawing that is
    1000 units tall, which is a tenth of a pixel at the largest size the app draws one. A curve whose
    handles lie on its own chord is written as a line. A line that continues straight on from the
    line before it is merged into it. Some faces are drawn with thousands of tiny nodes (a
    distressed typewriter face, a spiked metal logo, letters that break apart like a bad scan). For
    these faces, these steps remove most of the file."""

    # How far a control point may be from the chord, or a corner from the line of its neighbours,
    # before the shape counts as a real curve or a real corner. In units of a 1000-tall drawing.
    #
    # This value comes from the largest size at which a name is drawn: a card's name box, 0.28 of a
    # card and up to 300 points tall, on a panel with two pixels to the point. That is about 168
    # pixels for a drawing 1000 units tall, so one unit is about a sixth of a pixel and two units are
    # a third of a pixel. Nobody can see an error that small. A smaller value only costs time: every
    # command becomes a XAML object that is built on the thread that draws the wall, and the Punk
    # face alone has 4,032 of them.
    FLAT = 2.0

    # A contour smaller than this across is dropped. The distressed and glitched faces have hundreds
    # of speckles a few units wide (Punk has 306 contours, 85 of them under 24 units). At the largest
    # size, eight units is about a pixel and a half. These are specks of dirt that are not visible on
    # screen, and each one that is removed saves three or four XAML objects.
    SPECK = 8.0

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.parts = []
        self._here = (0.0, 0.0)
        self._pending = None          # a line not yet written, in case the next one continues it

    @staticmethod
    def _n(value):
        return str(int(round(value)))

    def _pt(self, point):
        return f"{self._n(point[0])},{self._n(point[1])}"

    @staticmethod
    def _off(a, b, p):
        """Returns how far p is from the line ab. If ab has zero length, returns the plain distance
        from a to p."""
        (ax, ay), (bx, by), (px, py) = a, b, p
        dx, dy = bx - ax, by - ay
        span = math.hypot(dx, dy)
        if span < 1e-9:
            return math.hypot(px - ax, py - ay)
        return abs(dy * (px - ax) - dx * (py - ay)) / span

    def _flush(self):
        if self._pending is not None:
            self.parts.append("L" + self._pt(self._pending))
            self._pending = None

    def _line(self, point):
        """Holds the point instead of writing it, so that a run of points along one line is written
        as one L."""
        if self._pending is not None and self._off(self._start_of_run, point, self._pending) <= self.FLAT:
            self._pending = point      # the corner is not a real corner; continue to the further point
            return
        self._flush()
        self._start_of_run = self._here
        self._pending = point
        self._here = point

    def _moveTo(self, point):
        self._flush()
        self.parts.append("M" + self._pt(point))
        self._here = point
        self._start_of_run = point

    def _lineTo(self, point):
        was = self._here
        if self._pending is not None:
            self._here = self._pending
        self._line(point)
        self._here = point
        if self._pending is None:
            self._start_of_run = was

    def _curveToOne(self, a, b, c):
        start = self._pending if self._pending is not None else self._here
        if self._off(start, c, a) <= self.FLAT and self._off(start, c, b) <= self.FLAT:
            self._lineTo(c)            # a curve along its own chord is a line
            return
        self._flush()
        self.parts.append(f"C{self._pt(a)} {self._pt(b)} {self._pt(c)}")
        self._here = c
        self._start_of_run = c

    def _closePath(self):
        self._flush()
        self.parts.append("Z")

    def _endPath(self):
        self._flush()

    def data(self):
        self._flush()
        return " ".join(self._without_specks())

    def _without_specks(self):
        """Returns the parts with every contour that is too small to see removed.

        This is done here and not in the pen's callbacks, because the size of a contour is not known
        until all of it has been walked. The pen receives points one at a time, and a speck and a
        letter start in the same way."""
        kept, contour, numbers = [], [], []

        def close():
            if not contour:
                return
            xs, ys = numbers[0::2], numbers[1::2]
            if xs and max(max(xs) - min(xs), max(ys) - min(ys)) >= self.SPECK:
                kept.extend(contour)

        for part in self.parts:
            if part.startswith("M"):
                close()
                contour, numbers = [], []
            contour.append(part)
            numbers.extend(float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", part))

        close()
        return kept


def run(font, cmap, text):
    """Returns one line as glyph names, so a missing character is found here and not on screen."""
    names = []
    for character in text:
        name = cmap.get(ord(character))
        if name is None:
            return None, character
        names.append(name)
    return names, None


def line_width(names, widths, kern, tracking_units):
    """Returns how wide one line sets: advances, kerns, and the tracking between the letters.
    Tracking is applied only BETWEEN letters, so a line of n letters has n-1 gaps of it. A trailing
    gap would move the flush-right setting by one gap."""
    total = sum(widths[n] for n in names)
    total += sum(kern.get((a, b), 0) for a, b in zip(names, names[1:]))
    total += tracking_units * max(0, len(names) - 1)
    return total


def draw(genre, face):
    """Returns one shelf's two wordmarks and their shape.

    The result is ({"left": path, "right": path}, width, height, base), in units where the drawing
    is EM tall. The caller scales it; nothing here knows how big a card is."""
    font = TTFont(face["file"])
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    widths = {name: font["hmtx"][name][0] for name in font.getGlyphOrder()}
    kern = kerning(font)
    glyphset = font.getGlyphSet()

    tracking_units = genre.get("tracking", 0.0) * upem
    leading = genre.get("leading", 1.0) * upem

    lines = []
    for text in face["lines"]:
        names, missing = run(font, cmap, text)
        if names is None:
            sys.exit(f"{genre['genre']}: {genre['font']} has no glyph for {missing!r} "
                     f"(in {text!r}). Pick another face or spell the name differently.")
        lines.append((names, line_width(names, widths, kern, tracking_units)))

    widest = max(width for _, width in lines)

    def compose(flush):
        """Returns the whole setting as one outline, in font units, with y pointing up. `flush` is
        where a short line sits against the longest one: 0 is flush left, 0.5 is centred, 1 is flush
        right."""
        strokes = []
        for row, (names, width) in enumerate(lines):
            x = (widest - width) * flush
            y = -row * leading
            for i, name in enumerate(names):
                strokes.append((name, x, y))
                x += widths[name] + tracking_units
                if i + 1 < len(names):
                    x += kern.get((name, names[i + 1]), 0)
        return strokes

    def bounds(strokes):
        box = None
        for name, x, y in strokes:
            pen = BoundsPen(glyphset)
            glyphset[name].draw(TransformPen(pen, (1, 0, 0, 1, x, y)))
            if pen.bounds is None:
                continue                      # a space, which has no ink
            box = pen.bounds if box is None else (
                min(box[0], pen.bounds[0]), min(box[1], pen.bounds[1]),
                max(box[2], pen.bounds[2]), max(box[3], pen.bounds[3]))
        return box

    settings = {name: compose(flush) for name, flush in (("left", 0.0), ("right", 1.0))}
    left_strokes = settings["left"]

    # ONE box for both settings. The two drawings are the same words at the same size, so they must
    # have the same shape. Otherwise the wall would set the left column at a different size from the
    # right column.
    box = bounds(left_strokes)
    if box is None:
        sys.exit(f"{genre['genre']}: the setting has no ink in it.")
    x0, y0, x1, y1 = box
    scale = EM / (y1 - y0)

    # Where the FIRST BASELINE is inside the drawing. The wall aligns the names by this number. The
    # height of the drawing cannot be used, because it includes all the ink. A face with a shadow
    # under it (Vast Shadow for Rock), a name with a descender and a name set on two lines all have
    # ink where another name has none. If those boxes were set to one height, the LETTERS would have
    # three different sizes.
    #
    # The top of the drawing IS the top of the first line (the lines below it are drawn downwards),
    # so the top of the text is the top of the drawing, and its baseline is this value. If those two
    # are aligned on every card, the letters have the same size and stand on the same line. Anything
    # below the baseline hangs down, as it does on a printed page.
    #
    # The value is measured from the drawing and not read from the face. The cap height in the OS/2
    # table is often wrong (Rye reports a fifth of the height it draws), and it is also the wrong
    # question: what matters is the ink that this setting puts on the card.
    base = (y1 - 0) * scale / EM

    def path(strokes):
        pen = OutlinePen(glyphset)
        for name, x, y in strokes:
            # y is flipped here and nowhere else: a font is drawn upwards from its baseline and XAML
            # draws downwards from the top left, so this one sign is the whole difference.
            transform = (scale, 0, 0, -scale, (x - x0) * scale, (y1 - y) * scale)
            glyphset[name].draw(TransformPen(pen, transform))
        # F1 (non-zero fill) is required. Letterforms are wound for non-zero fill, and script faces
        # overlap their own strokes. With even-odd fill (which the parser assumes by default) every
        # crossing in Yellowtail or Sedgwick Ave would become a hole.
        return "F1 " + pen.data()

    # Both settings use the same box, so they are interchangeable: the same words at the same size.
    return ({name: path(strokes) for name, strokes in settings.items()},
            (x1 - x0) * scale, EM, base)


# ── the colours ─────────────────────────────────────────────────────────────────────────────────

# ── a shelf uses its palette entry unchanged ──────────────────────────────────────────────────────
#
# No colour is changed here. A shelf names a palette entry and gets exactly that entry. The artists
# wall uses the same ten accents at the same tile size and also takes each entry unchanged, and it
# dims the colour as it PAINTS, evenly for every hue (ArtistGround). How strongly a colour is drawn
# is decided by the card, not by this script. If this script changed some colours, a genre card and
# an artist card in the same collection would show two different limes or azures from one palette.
def palette():
    """Returns the app's ten accent colours, read unchanged from the asset that defines them.

    They are read and not copied into this file, so there is only one set of colours. If someone
    changes the colours in the asset, a copy here would be a second, different set. A shelf names a
    colour by its short name and gets the current value of that entry."""
    with open(PALETTE, encoding="utf8") as f:
        asset = f.read()

    found = {}
    for key, value in re.findall(r'<Color x:Key="Rpm(\w+)Color">#([0-9A-Fa-f]{8})</Color>', asset):
        found[key.lower()] = "0x" + value.upper()

    if not found:
        sys.exit(f"{PALETTE}: no colours in it. The palette is the only place a shelf's colour "
                 f"may come from, so there is nothing to write.")
    return found


# ── the file ────────────────────────────────────────────────────────────────────────────────────

def quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def cased(name, how):
    if how == "upper":
        return name.upper()
    if how == "title":
        return name
    return name


def main():
    with open(SOURCE, encoding="utf8") as f:
        source = json.load(f)
    with open(SHELVES, encoding="utf8") as f:
        shelves = {s["genre"] for s in json.load(f)["shelves"]}

    genres = source["genres"]
    known = shelves | {UNCLASSIFIED}

    named = [g["genre"] for g in genres]
    if len(set(named)) != len(named):
        sys.exit(f"{SOURCE}: a genre is listed twice.")
    for name in named:
        if name not in known:
            sys.exit(f"{SOURCE}: {name!r} is not a shelf in subgenres.json.")
    for name in sorted(known - set(named)):
        sys.exit(f"{SOURCE}: {name!r} has no wordmark, and every shelf on the wall needs one.")

    colours = palette()
    for genre in genres:
        if genre.get("palette") not in colours:
            sys.exit(f"{SOURCE}: {genre['genre']} asks for the palette colour "
                     f"{genre.get('palette')!r}, which {os.path.relpath(PALETTE, ROOT)} does not "
                     f"have. It lists: {', '.join(sorted(colours))}.")
        if genre.get("finish") not in ("glass", "frost"):
            sys.exit(f"{SOURCE}: {genre['genre']} has finish {genre.get('finish')!r}; it is glass "
                     f"or frost.")

    # The wall must spread over the app's ten colours, not have four cards in one colour and twelve
    # in another.
    spread = {}
    for genre in genres:
        spread.setdefault(genre["palette"], []).append(genre["genre"])
    for name, shelves in sorted(spread.items()):
        if len(shelves) > MOST_PER_COLOUR:
            sys.exit(f"{SOURCE}: {len(shelves)} shelves are {name} and the wall wants at most "
                     f"{MOST_PER_COLOUR} — {', '.join(shelves)}.")

    cut = []
    for genre in genres:
        face = {
            "file": font_path(genre),
            "lines": [cased(line, genre.get("case", "as-is"))
                      for line in genre.get("lines") or [genre["genre"]]],
        }
        settings, width, height, base = draw(genre, face)
        cut.append((genre, settings, width, height, base))
        spent = sum(len(v) for k, v in settings.items() if k == "left" or v != settings["left"])
        print(f"  {genre['genre']:22} {genre['font']:22} {genre['palette']:10} "
              f"{genre['finish']:6} {spent:>7} chars")

    rows = []
    for genre, settings, width, height, base in cut:
        colour = colours[genre["palette"]]

        def other(which):
            # A name set on one line is one drawing however it is flushed. Writing it out twice would
            # copy a very long string (Metal Mania's path has about 30,000 characters).
            return "null" if settings[which] == settings["left"] else quote(settings[which])

        rows.append(
            f"        new({quote(genre['genre'])}, {quote(genre['font'])}, {colour}, "
            f"GenreFinish.{genre['finish'].capitalize()},\n"
            f"            {width / height:.4f}, {base:.4f},\n"
            f"            {quote(settings['left'])},\n"
            f"            {other('right')}),\n")

    body = "".join(rows).rstrip().rstrip(",")

    with open(TARGET, "w", encoding="utf8") as f:
        f.write(f'''// <auto-generated>
//     Written by scripts/gen_wordmarks.py from scripts/wordmarks.json. Do not edit: this file is
//     overwritten whole on every run, and a genre taken out of the JSON disappears from here.
//
//     Each shelf's name, set once in a face chosen for that shelf and kept as OUTLINES. No font
//     is shipped or loaded -- what is below is the lettering itself, as path data, so a genre is
//     the same drawing at any size and the app links none of the {len(cut) - 1} faces it is set in.
//     Every face is under the SIL Open Font License, which allows the outlines to be embedded in
//     and distributed with a work.
// </auto-generated>

// Generated code is nullable-oblivious unless it says otherwise, and the record below has a
// member that is null by design (Right).
#nullable enable

namespace RPM.Desktop.Presentation.Main.Genres;

/// <summary>One shelf's lettering, its shape, and the colour that falls over its photograph.</summary>
/// <param name="Genre">The shelf, spelled as <c>Genres.All</c> spells it.</param>
/// <param name="Typeface">The face it was set in. Kept for the credit and for the eye that has to
/// find it again in wordmarks.json; nothing in the app loads it.</param>
/// <param name="Colour">The shelf's colour, as 0xAARRGGBB. One of the app's ten and never anything
/// else -- see the palette note in wordmarks.json.</param>
/// <param name="Finish">Whether the card wears its colour as a tint over a sharp picture or as a haze
/// over a soft one.</param>
/// <param name="Aspect">How wide the drawing is for every one of its height. A caller that knows
/// the height it wants knows the width without measuring a thing.</param>
/// <param name="Base">Where the first line's BASELINE is, measured down from the top of the drawing
/// as a fraction of the drawing's own height.
///
/// <para>This is what the wall sizes a name by, and the drawing's height is not. The top of the
/// drawing is the top of the first line's letters; this is the line they stand on; and setting those
/// two the same on every card is what makes the lettering one size across the wall. The drawing
/// itself is taller than that by whatever hangs below the baseline -- a shadow, a descender, a
/// second line -- and how much that is has nothing to do with how big the letters are.</para></param>
/// <param name="Left">The name set flush left, which is the setting every caller falls back to.</param>
/// <param name="Right">The same name set flush right, or null where that is the same drawing -- which
/// is every single-line name, and most of them.</param>
public sealed record GenreWordmark(
    string Genre, string Typeface, uint Colour, GenreFinish Finish,
    double Aspect, double Base, string Left, string? Right)
{{
    /// <summary>The drawing for one way of setting the name. Falls back to the flush-left one, which
    /// is the same drawing wherever the name is a single line.</summary>
    public string On(GenreFlush flush) => flush == GenreFlush.Right ? Right ?? Left : Left;
}}

public static partial class GenreWordmarks
{{
    /// <summary>Every shelf, in the order wordmarks.json lists them.</summary>
    private static readonly GenreWordmark[] Cut =
    [
{body}
    ];
}}
''')

    size = os.path.getsize(TARGET)
    print(f"\n{os.path.relpath(TARGET, ROOT)}: {len(cut)} wordmarks, {size / 1024:.0f} KB")

    write_swift(cut, colours)
    write_kotlin(cut, colours)


def write_kotlin(cut, colours):
    """The same lettering for the Android TV app, flush left only, as the phone has it: the path data
    without its fill-rule prefix, and the rule as its own field. Each path is one string constant, which
    the JVM caps at 65535 bytes; the run stops rather than write a table that does not compile."""
    rows = []
    for genre, settings, width, height, base in cut:
        data = settings["left"]
        even_odd = data.startswith("F0")
        if data[:2] in ("F0", "F1"):
            data = data[2:].lstrip()
        if len(data.encode("utf8")) > 65535:
            sys.exit(f"{genre['genre']}: its outline is {len(data)} characters, over the JVM's limit for one "
                     f"string constant.")
        colour = colours[genre['palette']]
        rows.append(
            f"        GenreWordmark({quote(genre['genre'])}, {colour}L, "
            f"glass = {'true' if genre['finish'] == 'glass' else 'false'}, "
            f"aspect = {width / height:.4f}, base = {base:.4f}, "
            f"evenOdd = {'true' if even_odd else 'false'},\n"
            f"            path = {quote(data)}),\n")

    with open(KOTLIN_TARGET, "w", encoding="utf8") as f:
        f.write(f'''// <auto-generated>
//     Written by scripts/gen_wordmarks.py from scripts/wordmarks.json, beside the desktop's
//     GenreWordmarks.Data.cs and the phone's GenreWordmarks.Data.swift. Do not edit: every run
//     overwrites this file.
//
//     Each genre's name as the outlines of the face chosen for it, so no font is shipped. Every
//     face is under the SIL Open Font License, which allows the outlines to be embedded in and
//     distributed with a work.
// </auto-generated>

package com.rpm.player.core.library

/** One genre's lettering and colour. [colour] is 0xAARRGGBB. [aspect] is width over height; [base] is where
 * the first line's baseline is, as a share of the height from the top. [path] is SVG path data in the
 * drawing's own units, filled even-odd where [evenOdd] says so and non-zero otherwise. */
class GenreWordmark(
    val genre: String,
    val colour: Long,
    val glass: Boolean,
    val aspect: Double,
    val base: Double,
    val evenOdd: Boolean,
    val path: String,
)

object GenreWordmarkTable {{
    /** Every genre, in the order wordmarks.json lists them. */
    val all: List<GenreWordmark> = listOf(
{"".join(rows)}    )
}}
''')
    print(f"{os.path.relpath(KOTLIN_TARGET, ROOT)}: {len(cut)} wordmarks, "
          f"{os.path.getsize(KOTLIN_TARGET) / 1024:.0f} KB")


def write_swift(cut, colours):
    """The same lettering for the iPhone, flush left only: the phone sets every name flush left.

    The path data is the C# table's, less its fill-rule prefix: XAML writes the rule into the data
    ("F0" even-odd, "F1" non-zero) and the phone's VectorPath does not read it, so it is passed as
    its own field."""
    rows = []
    for genre, settings, width, height, base in cut:
        data = settings["left"]
        even_odd = data.startswith("F0")
        if data[:2] in ("F0", "F1"):
            data = data[2:].lstrip()
        rows.append(
            f"        GenreWordmark(genre: {quote(genre['genre'])}, colour: {colours[genre['palette']]}, "
            f"glass: {'true' if genre['finish'] == 'glass' else 'false'},\n"
            f"                      aspect: {width / height:.4f}, base: {base:.4f}, "
            f"evenOdd: {'true' if even_odd else 'false'},\n"
            f"                      path: {quote(data)}),\n")

    with open(SWIFT_TARGET, "w", encoding="utf8") as f:
        f.write(f'''// <auto-generated>
//     Written by scripts/gen_wordmarks.py from scripts/wordmarks.json, beside the desktop's
//     GenreWordmarks.Data.cs. Do not edit: every run overwrites this file.
//
//     Each genre's name as the outlines of the face chosen for it, so no font is shipped. Every
//     face is under the SIL Open Font License, which allows the outlines to be embedded in and
//     distributed with a work.
// </auto-generated>

/// One genre's lettering and colour. `aspect` is width over height; `base` is where the first
/// line's baseline is, as a share of the height from the top. `path` is in the drawing's own units.
public struct GenreWordmark: Sendable {{
    public let genre: String
    public let colour: UInt32
    public let glass: Bool
    public let aspect: Double
    public let base: Double
    public let evenOdd: Bool
    public let path: String
}}

public enum GenreWordmarkTable {{
    /// Every genre, in the order wordmarks.json lists them.
    public static let all: [GenreWordmark] = [
{"".join(rows)}    ]
}}
''')
    print(f"{os.path.relpath(SWIFT_TARGET, ROOT)}: {len(cut)} wordmarks, "
          f"{os.path.getsize(SWIFT_TARGET) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
