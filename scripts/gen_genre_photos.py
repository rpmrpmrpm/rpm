#!/usr/bin/env python3
"""Writes RPM.Desktop/Assets/GenrePhotos/*.jpg and GenrePhotos.Data.cs from scripts/genre-photos.json.

What this is for
----------------
The top of a genre page is a coloured band with the genre's name at one end and a photograph in a
panel at the other. The photograph is chosen once, here, and shipped with the app: one Pexels
photograph per genre, cut to a band six times as wide as it is high, which is the shape of the page
top. The page opens with no lookup, no model, no network and no cache, and it looks the same on
every machine.

The choice is the id in genre-photos.json. The query next to it only records how the photograph was
found and is not run again: a search gives different results over time, and the app would then show
whatever Pexels ranks highest on the day of the run instead of a fixed set of pictures.

What comes out
--------------
One JPEG per genre under Assets/GenrePhotos, cut to `shape` and `width` from the JSON, and a
generated table that names them. The table also holds the photographer. The Pexels licence does not
require a credit, but one is recorded anyway.

Run after editing scripts/genre-photos.json:

    python3 scripts/gen_genre_photos.py

Needs the network and a Pexels key, but only for photographs that are not downloaded yet: the
sources are cached under scripts/.photocache, so a normal re-run after a crop change uses neither.
The key is read from pexels.json in the app's local data folder, or from PEXELS_API_KEY. It is never
stored in this repository, and the app itself does not read it: both photo tables are generated here
and shipped.
"""

import json
import workspace
import os
import re
import sys
import urllib.request

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("This needs Pillow: python3 -m pip install pillow")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = workspace.path("scripts", "genre-photos.json")
WORDMARKS = workspace.path("scripts", "wordmarks.json")
PALETTE = workspace.path("RPM.Desktop", "Assets", "RpmPalette.xaml")
CACHE = workspace.path("scripts", ".photocache")
ASSETS = workspace.path("RPM.Desktop", "Assets", "GenrePhotos")
TARGET = workspace.path(
    "RPM.Desktop", "Presentation", "Main", "Genres", "GenrePhotos.Data.cs")

# Pexels refuses Python's default User-Agent with a 403, which looks like a bad key but is not one.
# Any other User-Agent is accepted.
AGENT = "rpm-genre-photos/1.0"

KEYFILES = [
    os.path.expanduser("~/Library/Application Support/RPM/pexels.json"),
    os.path.expanduser("~/.local/share/RPM/pexels.json"),
    os.path.expandvars(r"%LOCALAPPDATA%\RPM\pexels.json"),
]


def slug(name):
    """The genre's file name. Lowercase, and each run of characters that are not letters or digits
    becomes one hyphen, so "Hip-Hop / Rap" is hip-hop-rap and "R&B" is r-b. main checks for
    collisions: two genres with the same slug would overwrite each other's photograph."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def key():
    """The Pexels key, from the environment or from the file in the app's local data folder."""
    if os.environ.get("PEXELS_API_KEY", "").strip():
        return os.environ["PEXELS_API_KEY"].strip()
    for path in KEYFILES:
        try:
            with open(path) as f:
                written = json.load(f).get("api_key", "").strip()
            if written:
                return written
        except (OSError, ValueError):
            continue
    return None


def fetch(photo, api_key):
    """The file of one photograph, from the cache or from Pexels.

    The cache is keyed by id, not by URL, because the URL contains a rendition name and a crop
    change must be able to re-run this without using the network. A photograph never changes at
    Pexels, so a cached file is always the right file."""
    path = os.path.join(CACHE, f"{photo['id']}.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    url = photo.get("source")
    if not url:
        # No pinned rendition: ask the API for the renditions of this id. This is the path for an
        # entry added by hand with only an id copied from the website.
        if not api_key:
            sys.exit(f"{photo['genre']}: no source URL pinned and no Pexels key to ask for one.\n"
                     "Put the key in PEXELS_API_KEY or in the app's pexels.json.")
        request = urllib.request.Request(
            f"https://api.pexels.com/v1/photos/{photo['id']}",
            headers={"Authorization": api_key, "User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=60) as reply:
            src = json.load(reply)["src"]
        url = src.get("large2x") or src.get("large") or src["original"]

    os.makedirs(CACHE, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=120) as reply:
        blob = reply.read()
    with open(path, "wb") as f:
        f.write(blob)
    return path


# Where the band is taken from.
#
# THE DEFINITION OF THIS ARITHMETIC IS RPM.Desktop/Presentation/Dev/GenreBand.cs AND THIS IS A COPY.
# The placer (--place-genres) puts the picture where the user wants it and this script cuts it. If the
# two differ even by a rounding, the page shows something other than what was placed. So change both
# together. GenreBandTests in the desktop tests fix the numbers that this copy must give.

MIN_ACROSS = 320   # the window is never narrower than this, in pixels of the source
CLOSEST = 0.05     # the closest zoom, as a share of the source's height
MAX_GAP = 0.5      # how much of the window may hang off the LEFT of the picture, as a share of its width


def deep_tones():
    """The tone that each palette entry's ramp ends on, read from the asset that defines the palette.

    A gap on the left of the band is filled with this tone. The page top has the same tone as its
    background from the left edge of the picture (GenreWordmarks.Head), so the padding and the
    background have one value and the edge of the padding cannot be seen. The values are read from
    the asset and not copied, for the reason gen_wordmarks.py gives about colours.

    The tone is the darkest stop of the ramp, by the same lightness that the app sorts them by,
    because the asset lists some ramps from light to dark and the app reverses them."""
    with open(PALETTE, encoding="utf8") as f:
        asset = f.read()

    tones = {}
    for name, body in re.findall(
            r'<LinearGradientBrush x:Key="Rpm(\w+)Gradient".*?>(.*?)</LinearGradientBrush>',
            asset, re.S):
        stops = re.findall(r'Color="#[0-9A-Fa-f]{2}([0-9A-Fa-f]{6})"', body)
        if not stops:
            continue
        rgb = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in stops]
        tones[name.lower()] = min(
            rgb, key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    return tones


def widest_for(w, h, shape):
    """The window whose width is the whole picture: the photograph exactly fills the band, which is
    also what a `focus` cut gives. It is not the end of the zoom range, see furthest_for."""
    return min(max(w / (shape * h), 0.01), 1.0)


def furthest_for(w, h, shape):
    """How far OUT the zoom goes: past the point where the photograph fills the band, until the extra
    width equals the largest gap that the colour can cover. The extra width is all on the LEFT (the
    window stays against the right edge of the picture), so the picture looks smaller at the end of
    a coloured band, not like a picture with a hole beside it. The window is never taller than the
    photograph, because nothing covers the top or the bottom."""
    return min(1.0, widest_for(w, h, shape) / (1 - MAX_GAP))


def closest_for(w, h, shape):
    """How far IN the zoom goes. It never goes past furthest_for, so a picture that is too small for
    MIN_ACROSS is shown as wide as it can be instead of being refused."""
    return min(max(CLOSEST, MIN_ACROSS / (shape * h)), furthest_for(w, h, shape))


def window(w, h, shape, frame):
    """The box that a manual placement asks for, in pixels of the photograph: `shape` times as wide
    as it is high, and always inside the picture (except for the gap on the left).

    The cases pinned by GenreBandTests.TheWindowsThePythonMustAnswer, for a 940 x 650 source at six
    to one, as (x, y, width, height). If this function stops giving these results, it no longer
    agrees with the placer tool:

        across 0.5   down 0.4393  height 0.2410  ->  (0,    207, 940, 157)  the focus cut
        across 0.35  down 0.35    height 0.16    ->  (17,   175, 624, 104)  still on the picture
        across 0.0   down 0.0     height 0.12    ->  (-234, 0,   468,  78)  the top holds, the left gives
        across 1.0   down 1.0     height 0.12    ->  (472,  572, 468,  78)  the right never gives
        across 0.05  down 0.5     height 0.16    ->  (-265, 273, 624, 104)  moved right, 265 of gap
    """
    # A frame with no height (for example an entry edited by hand) means the picture FILLS the band,
    # which is what the app does when there is no frame at all.
    height = min(max(frame.get("height", widest_for(w, h, shape)), closest_for(w, h, shape)),
                 furthest_for(w, h, shape)) * h

    # The width may be more than the picture has: that is the far end of the zoom. The RIGHT edge
    # holds: the window never goes past the right edge of the photograph, so all extra width is on the
    # left, where the colour is. This is why the upper bound of x is not limited to zero.
    width = height * shape
    x = min(max(frame.get("across", 0.5) * w - width / 2, -MAX_GAP * width),
            max(-MAX_GAP * width, w - width))
    y = min(max(frame.get("down", 0.5) * h - height / 2, 0), max(0, h - height))

    # Rounded in the same way as GenreWindow.Round, half to even. x may be NEGATIVE (that is the gap),
    # and the width may be more than the picture has, which is the same gap made by zooming out.
    ww = max(round(width), 1)
    hh = min(max(round(height), 1), h)
    xx = round(x)
    yy = min(max(round(y), 0), h - hh)
    return xx, yy, xx + ww, yy + hh


def cut(path, shape, width, focus, frame, flip, pad):
    """The band of a photograph that the page top shows.

    A stock landscape photograph is three by two and the band is six to one, so the cut is a thin
    slice of a much taller picture. Where the slice is taken decides whether the photograph still
    looks good.

    There are TWO WAYS to say where. An entry has one of them, never both.

    `frame` is a placement made by hand in the app's own page top (run the app with --place-genres).
    It sets three things: how far across, how far down, and how close in. Use it when the automatic
    cut is not good enough. It is the only way to move the subject SIDEWAYS or to crop in on it.

    `focus` is the automatic way, and the only setting for an entry without a frame: 0 takes the band
    from the top of the photograph, 1 from the bottom, and the default 0.42 is a little above the
    middle, where a horizon or a face usually is. The slice keeps the full WIDTH of the source, so a
    subject left of centre stays left of centre.

    `flip` mirrors the source before anything else is done to it. Use it when the subject is on the
    wrong side of the band. It is applied FIRST, so the across and down of a frame are measured on
    the picture as it will be seen.

    A GAP ON THE LEFT is allowed and is filled with `pad`, the tone that the page top uses as its
    background under the picture. The left part of the band is covered by solid genre colour where
    the name stands, so a picture that starts a little to the right loses nothing that can be seen.
    The gap appears in two ways: the picture is moved right, or it is zoomed out until it no longer
    fills the band. There is never padding on the RIGHT, because no colour covers it there.

    A source WIDER than the shape (a panorama) is cut from the middle. Nothing is ever letterboxed:
    the band is always filled, and anything beyond its edges is cut off."""
    image = Image.open(path).convert("RGB")
    if flip:
        image = ImageOps.mirror(image)
    w, h = image.size

    if frame:
        x0, y0, x1, y1 = window(w, h, shape, frame)
        if x0 < 0:
            band = Image.new("RGB", (x1 - x0, y1 - y0), pad)
            band.paste(image.crop((0, y0, min(x1, w), y1)), (-x0, 0))
            image = band
        else:
            image = image.crop((x0, y0, x1, y1))
    elif w / h > shape:
        keep = int(round(h * shape))
        left = (w - keep) // 2
        image = image.crop((left, 0, left + keep, h))
    else:
        keep = int(round(w / shape))
        top = int(round((h - keep) * focus))
        image = image.crop((0, top, w, top + keep))

    return image.resize((width, int(round(width / shape))), Image.LANCZOS)


def literal(text):
    """A C# string literal. The alt text and photographer name come from the API, so they may contain
    quotes or backslashes, which must be escaped."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    with open(SOURCE) as f:
        doc = json.load(f)

    shape = doc["shape"]
    width = doc["width"]
    quality = doc.get("quality", 88)
    photos = doc["photos"]

    # Only the genres that the genre wall has. A photograph for an unknown genre is never used. A genre
    # without a photograph is drawn without a picture, which the page handles, so both cases give a
    # warning and not an error.
    with open(WORDMARKS) as f:
        marked = json.load(f)["genres"]
    shelves = [g["genre"] for g in marked]

    # The palette entry of each genre, and the tone its ramp ends on: this fills a gap on the left of
    # the band. It is read once here, not per photograph. A genre that is missing from wordmarks.json
    # gets a dark default colour.
    tones = deep_tones()
    pads = {g["genre"]: tones.get(g.get("palette", ""), (20, 26, 34)) for g in marked}

    named = {p["genre"] for p in photos}
    for genre in shelves:
        if genre not in named:
            print(f"  warning: {genre} has no photograph; its head will have no picture.")
    for genre in sorted(named - set(shelves)):
        print(f"  warning: {genre} is not a genre in wordmarks.json; its photograph is unused.")

    slugs = {}
    for photo in photos:
        s = slug(photo["genre"])
        if s in slugs:
            sys.exit(f"{photo['genre']} and {slugs[s]} both come out as {s}.jpg.")
        slugs[s] = photo["genre"]

    api_key = key()
    os.makedirs(ASSETS, exist_ok=True)

    # The folder is rewritten completely, as in gen_wordmarks.py: a genre removed from the JSON leaves
    # no file in the app.
    for stale in os.listdir(ASSETS):
        if stale.endswith(".jpg") and stale[:-4] not in slugs:
            os.remove(os.path.join(ASSETS, stale))
            print(f"  removed {stale}, which no genre asks for any more.")

    rows, total = [], 0
    for photo in sorted(photos, key=lambda p: shelves.index(p["genre"])
                        if p["genre"] in shelves else len(shelves)):
        name = slug(photo["genre"]) + ".jpg"
        out = os.path.join(ASSETS, name)
        cut(fetch(photo, api_key), shape, width,
            photo.get("focus", 0.42), photo.get("frame"), photo.get("flip", False),
            pads.get(photo["genre"], (20, 26, 34))).save(
            out, "JPEG", quality=quality, optimize=True, progressive=True)
        size = os.path.getsize(out)
        total += size
        rows.append((photo, name, size))
        placed = "placed" if photo.get("frame") else f"focus {photo.get('focus', 0.42)}"
        if photo.get("flip"):
            placed += " mirrored"
        print(f"  {photo['genre']:20} {name:24} {size / 1024:5.0f} KB  {placed:12} "
              f"by {photo.get('by') or '?'}")

    tall = int(round(width / shape))
    with open(TARGET, "w") as f:
        f.write(f"""// <auto-generated>
//     Written by scripts/gen_genre_photos.py from scripts/genre-photos.json. Do not edit: this
//     file is overwritten whole on every run, and a genre taken out of the JSON disappears from
//     here and its picture is deleted from Assets/GenrePhotos.
//
//     One photograph per shelf, chosen once and shipped, cut to the shape of the band a genre
//     page's head IS ({shape} wide for every one of its height, {width}x{tall}) -- the head bleeds, so
//     the picture is drawn across all of it. Every one is
//     under the Pexels License: free use, commercial included, no attribution required, and
//     redistribution as part of a work permitted -- which is what shipping them here is. The
//     photographer is recorded anyway; see the note in genre-photos.json.
// </auto-generated>

// Written inside an explicit annotations context: the compiler will not take a `?` in
// auto-generated code on the project's setting alone (CS8669).
#nullable enable

namespace RPM.Desktop.Presentation.Main.Genres;

/// <summary>One shelf's photograph, and who took it.</summary>
/// <param name="Genre">The shelf, spelled as <c>Genres.All</c> spells it.</param>
/// <param name="File">The file's name under <c>Assets/GenrePhotos</c>. The name and not a path:
/// where the assets sit is <see cref="GenrePhotos"/>'s business and it is the only thing that
/// knows it.</param>
/// <param name="Alt">What the picture is, in words, as Pexels describes it. Nothing draws this; it
/// is here so the next person to open the table can tell the thirty-six apart without looking at
/// them.</param>
/// <param name="By">Who took it. The licence asks for no credit and this is the credit anyway.</param>
internal readonly record struct GenrePhoto(string Genre, string File, string Alt, string By);

/// <summary>
/// The photograph at the end of every genre page's head.
///
/// <para><b>Shipped rather than found.</b> The head's picture was once one of the genre's own
/// artists, walked out of the shelf and framed by two models. That is a network round trip and two
/// model runs in front of a reader who has just pressed a genre, and on a shelf where none of the
/// acts has been photographed it answers with nothing. These are chosen once, cut to the panel's
/// own shape at the size it is drawn, and read off the disk -- so a genre page opens the same way
/// on every machine, on a borrowed shelf, and with the network down.</para>
///
/// <para><b>A genre with no entry is not an error, and neither is a missing file.</b>
/// <see cref="BytesAsync"/> answers null either way and the head draws its colour and its name
/// without a picture, which is what it already does for a genre nobody on it has been photographed
/// for.</para>
/// </summary>
internal static class GenrePhotos
{{
    /// <summary>How wide every one of these is cut for every one of its height. The head's band is
    /// wider than this on most panes and narrower on a few, and the picture fills it either way --
    /// this is the floor of that range rather than the middle of it, because a band this long can
    /// lose width for nothing and loses its subject the moment it loses height. Held there by
    /// GenrePhotoTests rather than by this sentence.</summary>
    public const double Shape = {shape};

    /// <summary>Every shelf that has one, in the order the wall lists them.</summary>
    public static readonly IReadOnlyList<GenrePhoto> All =
    [
""")
        for photo, name, _ in rows:
            f.write(f"        new({literal(photo['genre'])}, {literal(name)},\n"
                    f"            {literal(photo.get('alt') or '')},\n"
                    f"            {literal(photo.get('by') or '')}),\n")
        f.write("""    ];

    private static readonly Dictionary<string, GenrePhoto> ByGenre =
        All.ToDictionary(p => p.Genre, StringComparer.OrdinalIgnoreCase);

    /// <summary>Where the photographs sit next to the built app.</summary>
    private static string Dir => Path.Combine(AppContext.BaseDirectory, "Assets", "GenrePhotos");

    /// <summary>One shelf's entry, or null where it has none.</summary>
    public static GenrePhoto? For(string genre)
        => genre is not null && ByGenre.TryGetValue(genre, out var found) ? found : null;

    /// <summary>Where one shelf's photograph is on this machine, or null where it has none.</summary>
    public static string? PathFor(string genre)
        => For(genre) is { } photo ? Path.Combine(Dir, photo.File) : null;

    /// <summary>
    /// One shelf's photograph, read off the disk.
    ///
    /// <para>Null where the shelf has no entry AND where the file is not there -- an install whose
    /// assets were pruned, a build that dropped the Content item. Both are the same answer to the
    /// caller because both mean the same thing to the reader: a head with no picture in it, which
    /// is a finished head.</para>
    ///
    /// <para>Off the calling thread. Sixty kilobytes is not a stall, but this is called from the
    /// thread drawing a page that is in the middle of coming up, and the one place in this app that
    /// reads a file on that thread is the one place that should not.</para>
    /// </summary>
    public static async Task<byte[]?> BytesAsync(string genre, CancellationToken ct)
    {
        if (PathFor(genre) is not { } path)
            return null;

        try
        {
            return await File.ReadAllBytesAsync(path, ct).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }
}
""")

    print(f"\n{os.path.relpath(ASSETS, ROOT)}: {len(rows)} photographs, {total / 1024 / 1024:.1f} MB")
    print(f"{os.path.relpath(TARGET, ROOT)}: written")


if __name__ == "__main__":
    main()
