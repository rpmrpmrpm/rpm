#!/usr/bin/env python3
"""Writes RPM.Desktop/Assets/PlaylistPhotos/*.jpg and PlaylistPhotos.Data.cs from
scripts/playlist-photos.json.

What this is for
----------------
The cover of a generated playlist is a picture with the app's own frame over it. For most of these
lists the picture is a photograph. The photographs are chosen once, here, and shipped with the app:
one Pexels photograph per list, cut to the square that a cover is composed at. Every install draws
the same covers with no key, no network, no cache and no setting.

The choice is the id in playlist-photos.json. The query next to it only records how the photograph
was found and is not run again: a search gives different results over time, and the app would then
show whatever Pexels ranks highest on the day of the run instead of a fixed set of pictures.

What comes out
--------------
One JPEG per list under Assets/PlaylistPhotos, cut to `edge` and `quality` from the JSON, and a
generated table that names them. The table also holds the photographer. The Pexels licence does not
require a credit, but one is recorded anyway.

The mood's colour and the app's mark are NOT written into these files. Both are added when the
cover is drawn, from the palette entry of the list, so changing either affects every cover without
running this script again.

Run after editing scripts/playlist-photos.json:

    python scripts/gen_playlist_photos.py

It ends by running gen_playlist_photos_phone.py, which copies the same files into the iPhone app
(RPM.iOS/Modules/RPMArt) and writes the phone's table of them, and gen_playlist_photos_tv.py, which
does the same for the Android TV app.

Needs the network, but only for photographs that are not downloaded yet: the sources are cached
under scripts/.photocache, which gen_genre_photos.py shares, so a re-run after a crop change does
not use the network. A pinned `source` is fetched without a key. An entry with an id and no source
needs a Pexels key to ask for the renditions of that id. The key is read from PEXELS_API_KEY or
from the app's pexels.json. The key is never stored in this repository.
"""

import io
import json
import workspace
import os
import re
import sys
import urllib.request

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("This needs Pillow: python -m pip install pillow")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = workspace.path("scripts", "playlist-photos.json")
CACHE = workspace.path("scripts", ".photocache")
ASSETS = workspace.path("RPM.Desktop", "Assets", "PlaylistPhotos")
TARGET = workspace.path(
    "RPM.Desktop", "Presentation", "Common", "PlaylistPhotos.Data.cs")

# Pexels refuses Python's default User-Agent with a 403, which looks like a bad key but is not one.
# Any other User-Agent is accepted.
AGENT = "rpm-playlist-photos/1.0"

KEYFILES = [
    os.path.expanduser("~/Library/Application Support/RPM/pexels.json"),
    os.path.expanduser("~/.local/share/RPM/pexels.json"),
    os.path.expandvars(r"%LOCALAPPDATA%\RPM\pexels.json"),
]


def key():
    """The Pexels key, from the environment or from the file in the app's local data folder."""
    if os.environ.get("PEXELS_API_KEY", "").strip():
        return os.environ["PEXELS_API_KEY"].strip()
    for path in KEYFILES:
        try:
            with io.open(path, encoding="utf-8") as f:
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
            sys.exit(f"{photo['file']}: no source URL pinned and no Pexels key to ask for one.\n"
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


def square(path, edge):
    """The middle square of a photograph, at the size that a cover is composed at.

    The cut is centred, because nothing here knows where the subject of a picture is, and the middle
    is wrong less often than any corner. It is the same cut that GeneratedCoverService makes when it
    draws, done once here, so the app ships only the pixels that are drawn and not a landscape
    photograph three times larger.

    A picture smaller than `edge` on its short side is still cut and then scaled UP. Pexels
    renditions are 940 pixels wide, so this does not happen for an entry pinned with a source."""
    with Image.open(path) as opened:
        # Apply the EXIF orientation first: a phone photograph stored sideways would otherwise be cut
        # along the wrong axis, and the cut cannot be corrected later.
        picture = ImageOps.exif_transpose(opened).convert("RGB")
        return ImageOps.fit(picture, (edge, edge), method=Image.LANCZOS, centering=(0.5, 0.5))


def narrowed(photo):
    """How this list is narrowed, for messages. A decade is written as its number and a genre as its
    name. A list for the whole library is narrowed by neither."""
    if photo["decade"] > 0:
        return f"{photo['decade']}s"
    return photo["genre"] or "whole shelf"


def escape(text):
    """A C# string literal's contents."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def table(photos):
    """The generated C# table."""
    lines = [
        "// <auto-generated>",
        "//     Written by scripts/gen_playlist_photos.py from scripts/playlist-photos.json. Do not",
        "//     edit: this file is overwritten whole on every run, and a list taken out of the JSON",
        "//     disappears from here and its picture is deleted from Assets/PlaylistPhotos.",
        "//",
        "//     One photograph per generated playlist that has one, chosen once and shipped, cut to",
        "//     the square a cover is composed at (640). Every one is under the Pexels License: free",
        "//     use, commercial included, no attribution required, and redistribution as part of a",
        "//     work permitted -- which is what shipping them here is. The photographer is recorded",
        "//     anyway; see the note in playlist-photos.json.",
        "//",
        "//     The mood's colour and the app's mark are not in these files. Both go on at the moment",
        "//     the cover is drawn, so changing either reaches every picture here with no re-export.",
        "// </auto-generated>",
        "",
        "// Written inside an explicit annotations context: the compiler will not take a `?` in",
        "// auto-generated code on the project's setting alone (CS8669).",
        "#nullable enable",
        "",
        "using RPM.Core.Library;",
        "",
        "namespace RPM.Desktop.Presentation.Common;",
        "",
        "/// <summary>One generated playlist's photograph, and who took it.</summary>",
        "/// <param name=\"List\">Which list, as <see cref=\"SmartPlaylistId\"/> keys it. Not named",
        "/// <c>Id</c>: Uno's key-equality generator claims any record member of that name and refuses",
        "/// a record it cannot make partial (KE0001).</param>",
        "/// <param name=\"File\">The file's name under <c>Assets/PlaylistPhotos</c>. The name and not",
        "/// a path: where the assets sit is <see cref=\"PlaylistPhotos\"/>'s business and it is the",
        "/// only thing that knows it.</param>",
        "/// <param name=\"Alt\">What the picture is, in words, as Pexels describes it. Nothing draws",
        "/// this; it is here so the next person to open the table can tell the eighty-three apart",
        "/// without looking at them.</param>",
        "/// <param name=\"By\">Who took it. The licence asks for no credit and this is the credit",
        "/// anyway.</param>",
        "internal readonly record struct PlaylistPhoto(",
        "    SmartPlaylistId List, string File, string Alt, string By);",
        "",
        "internal static partial class PlaylistPhotos",
        "{",
        "    /// <summary>Every list that has one, in the order the playlists tree shows them.</summary>",
        "    internal static readonly IReadOnlyList<PlaylistPhoto> All =",
        "    [",
    ]

    mood = None
    for photo in photos:
        if photo["kind"] != mood:
            mood = photo["kind"]
            lines.append(f"        // {'-' * 4} {mood} {'-' * 4}")
        genre = f'"{escape(photo["genre"])}"' if photo["genre"] else "null"
        lines += [
            f'        new(new(SmartPlaylistKind.{photo["kind"]}, {genre}, {photo["decade"]}),',
            f'            "{photo["file"]}",',
            f'            "{escape(photo["alt"])}",',
            f'            "{escape(photo["by"])}"),',
        ]

    lines += [
        "    ];",
        "}",
        "",
    ]
    return "\n".join(lines)


def main():
    with io.open(SOURCE, encoding="utf-8") as f:
        book = json.load(f)

    edge, quality, photos = book["edge"], book["quality"], book["photos"]

    seen = {}
    for photo in photos:
        if photo["file"] in seen:
            sys.exit(f"two entries write {photo['file']}: {seen[photo['file']]} and "
                     f"{photo['kind']}/{narrowed(photo)}")
        seen[photo["file"]] = f"{photo['kind']}/{narrowed(photo)}"

    api_key = key()
    os.makedirs(ASSETS, exist_ok=True)

    for photo in photos:
        cut = square(fetch(photo, api_key), edge)
        at = os.path.join(ASSETS, photo["file"])
        cut.save(at, "JPEG", quality=quality, optimize=True, progressive=True)
        print(f"  {photo['file']:<34} {os.path.getsize(at) // 1024:>4} KB   {photo['by']}")

    # A list removed from the JSON has its picture removed here, so the assets folder always matches
    # the JSON.
    for stale in sorted(set(os.listdir(ASSETS)) - set(seen)):
        os.remove(os.path.join(ASSETS, stale))
        print(f"  removed {stale}")

    with io.open(TARGET, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(table(photos))

    total = sum(os.path.getsize(os.path.join(ASSETS, p["file"])) for p in photos)
    print(f"\n{len(photos)} photographs, {total // 1024} KB")
    print(f"{os.path.relpath(TARGET, ROOT)} written")

    # The phone app ships the same files and has its own table of them. They are written from here,
    # so one run after a JSON edit updates both apps.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen_playlist_photos_phone
    gen_playlist_photos_phone.main()

    # The Android TV app, in the same way.
    import gen_playlist_photos_tv
    gen_playlist_photos_tv.main()


main()
