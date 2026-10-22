#!/usr/bin/env python3
"""Writes the credits tables that the apps (the "heads") read, from scripts/credits.json.

What it writes
--------------
    RPM.Desktop/Presentation/About/Credits.Data.cs          the desktop's list
    RPM.Desktop/Assets/Licenses/*.txt                       the licence texts it shows
    RPM.iOS/Modules/RPMKit/Sources/RPMKit/CreditsData.swift the iPhone's list
    RPM.iOS/Modules/RPMKit/Sources/RPMKit/Licenses/*.txt    the licence texts it shows
    RPM.Android/phone/src/main/java/com/rpm/player/phone/profile/CreditsData.kt
                                                            the Android phone's list
    RPM.Android/phone/src/main/assets/credits/*.txt         the licence texts it shows
    rpm.Api/Views/Site/Credits.cshtml                       rpmrpmrpm.com/credits, every head's entries
    rpm.Api/wwwroot/licenses/*.txt                          the licence texts that page links
    rpm.Api/wwwroot/source/                                 the ffmpeg build scripts and their versions

Do not edit the generated files by hand. The asset folders are emptied and rewritten, so that a
licence file is never left behind after the last entry using it is removed (the app would carry a
licence text it does not name). The Android phone's folder is called credits and not licenses
because `:core`, which the phone links, has an assets/licenses folder of its own for the TV app's
fonts, and assets of the same folder are merged into one in the APK.

The lists differ, which is the purpose of the "heads" field. The iPhone ships no ffmpeg, no ONNX
runtime and no SQLite, so naming them on its screen would be false. The Android phone ships
Media3, Compose, OkHttp, Coil, ML Kit and an FFmpeg of its own with three decoders. Each head gets
the entries that head ships or calls, and only the licence texts those entries need.

Two sections are not written by hand. The wordmark typefaces come from scripts/wordmarks.json and
the photographs from scripts/genre-photos.json, scripts/playlist-photos.json and
scripts/backdrop-photos.json. Those files are already the source for the assets themselves, and
copying them into credits.json would create a second place that can go out of date. On the
Android phone a photograph is credited when its file is in the app, and a photograph in the app's
genre-photos or playlist-photos folder that no table names is an error.

The Android files are written into the RPM.Android folder of rpm-android, or of the folder that
RPM_ANDROID names (a worktree, for example). When neither is there, the Android phone's files are
not written. The website's page lists every head, so it is then not written either: it stops with
an error rather than leave the Android entries off it.

Failure behaviour
-----------------
It never fails quietly. It exits non-zero if an entry names a string key that is not in
strings.json, a licence that is not in the map, a licence whose text file is missing, or a
version_from key that is not in scripts/tool-versions.txt, or if a file in scripts/licenses is
named by no entry. A wrong credits screen is worse than none. The Kotlin table names each string
as R.string.<key>, so a key that `:core`'s string tables do not have fails the Android build too.

Run it after editing scripts/credits.json, and after gen_locales.py has written the strings:

    python3 scripts/gen_credits.py
"""

from __future__ import annotations

import json
import workspace
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDITS = workspace.path("scripts", "credits.json")
STRINGS = workspace.path("scripts", "strings.json")
WORDMARKS = workspace.path("scripts", "wordmarks.json")
PHOTOS = workspace.path("scripts", "genre-photos.json")
LIST_PHOTOS = workspace.path("scripts", "playlist-photos.json")
BACKDROP_PHOTOS = workspace.path("scripts", "backdrop-photos.json")
LICENSES = workspace.path("scripts", "licenses")
TOOL_VERSIONS = workspace.path("scripts", "tool-versions.txt")

CS_OUT = workspace.path("RPM.Desktop", "Presentation", "About", "Credits.Data.cs")
CS_LICENSES = workspace.path("RPM.Desktop", "Assets", "Licenses")
SWIFT_OUT = workspace.path(
    "RPM.iOS", "Modules", "RPMKit", "Sources", "RPMKit", "CreditsData.swift")
SWIFT_LICENSES = workspace.path(
    "RPM.iOS", "Modules", "RPMKit", "Sources", "RPMKit", "Licenses")

# rpmrpmrpm.com, served by rpm.Api: the same list as a page, with the licence texts and the ffmpeg
# build script next to it, because the LGPL requires them to be available. rpm.Api is in the private
# server repo; when it is not checked out next to this repo (RPM_SITE sets another folder), the page
# is not written and the apps' files still are.
SITE = os.environ.get("RPM_SITE") or workspace.path("rpm.Api")
SITE_VIEW = os.path.join(SITE, "Views", "Site", "Credits.cshtml")
SITE_LICENSES = os.path.join(SITE, "wwwroot", "licenses")
SITE_SOURCE = os.path.join(SITE, "wwwroot", "source")
BUILD_SCRIPT = workspace.path("scripts", "build-ffmpeg.sh")

# The Android phone app. RPM_ANDROID names another RPM.Android folder, such as one in a worktree, so
# the table can be written there without touching the shared checkout.
ANDROID = os.environ.get("RPM_ANDROID") or workspace.path("RPM.Android")
KT_OUT = os.path.join(
    ANDROID, "phone", "src", "main", "java", "com", "rpm", "player", "phone", "profile", "CreditsData.kt")
KT_LICENSES = os.path.join(ANDROID, "phone", "src", "main", "assets", "credits")
# Where the Android phone carries the photographs, as the scripts that copy them write them.
ANDROID_GENRE_PHOTOS = os.path.join(ANDROID, "phone", "src", "main", "assets", "genre-photos")
ANDROID_LIST_PHOTOS = os.path.join(ANDROID, "core", "src", "main", "assets", "playlist-photos")
ANDROID_BACKDROPS = os.path.join(ANDROID, "phone", "src", "main", "res", "drawable-nodpi")
# The script that builds the FFmpeg libraries the Android app's FFmpeg decoder links. It is in
# rpm-android's scripts folder, beside RPM.Android.
ANDROID_BUILD_SCRIPT = os.path.join(os.path.dirname(ANDROID), "scripts", "build-android-ffmpeg.sh")

# The first line is what Roslyn reads to decide that a file is generated. The analyser rule RPM002
# (a catalogue's address written outside the API) skips generated code, and it must skip this file:
# a credit that names where a catalogue lives is attribution, not a request, and the rule exists to
# stop the app from calling one. The second line tells a person who wrote the file.
BANNER = ("// <auto-generated/>\n"
          "// Written by scripts/gen_credits.py from scripts/credits.json. Do not edit.")


# The apps a credit can be on: the desktop app (Mac and Windows), the iPhone and the Android phone.
HEADS = {"desktop", "iphone", "android"}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# --- the two generated sections ------------------------------------------------------------

def tool_versions() -> dict[str, str]:
    """The KEY=VALUE lines of scripts/tool-versions.txt, which holds the ffmpeg and fpcalc versions."""
    versions: dict[str, str] = {}
    with open(TOOL_VERSIONS, encoding="utf-8") as handle:
        for line in handle:
            match = re.match(r"^\s*([A-Z0-9_]+)=(.*)$", line)
            if match:
                versions[match.group(1)] = match.group(2).strip()
    return versions


def resolve_versions(sections: list[dict]) -> None:
    """Copies each 'version_from' entry's version from scripts/tool-versions.txt, then fills
    '{version}' in each source link.

    An entry gives its version either directly or with version_from, never both. A key that is not
    in the file is an error, not an entry with no version. An entry under an LGPL licence must give
    a source link that contains '{version}'.
    """
    versions = tool_versions()
    problems: list[str] = []
    for section in sections:
        for entry in section["entries"]:
            key = entry.get("version_from")
            if key is None:
                continue
            where = f"{section['id']}/{entry['id']}"
            if "version" in entry:
                problems.append(f"{where} gives both a version and version_from")
            elif key not in versions:
                problems.append(f"{where} takes its version from {key}, which is not in tool-versions.txt")
            else:
                entry["version"] = versions[key]

    # The LGPL requires the source of the shipped version, not of the project in general. So an entry
    # under it has {version} in its source, and the version it is credited at replaces it.
    for section in sections:
        for entry in section["entries"]:
            where = f"{section['id']}/{entry['id']}"
            source = entry.get("source")
            lgpl = any(key.startswith("LGPL") for key in entry["license"])
            if lgpl and (not source or "{version}" not in source):
                problems.append(f"{where} is under the LGPL but its source does not name the version")
            if source and "{version}" in source:
                if not entry.get("version"):
                    problems.append(f"{where} has {{version}} in its source but no version")
                else:
                    entry["source"] = source.replace("{version}", entry["version"])
    if problems:
        for problem in problems:
            print(f"gen_credits: {problem}", file=sys.stderr)
        sys.exit(1)


def google_fonts_url(family: str) -> str:
    return "https://fonts.google.com/specimen/" + family.replace(" ", "+")


def wordmark_entries() -> list[dict]:
    """One entry per typeface used for the lettering on the genres wall.

    One entry per family, because the typeface is what is credited and two shelves may share one.
    No font file is shipped for these: the app carries the letterforms as outlines, which the SIL
    Open Font License permits. All of them are under the same OFL text. The Android phone carries
    the same outlines (GenreWordmarkTable.kt, written by gen_wordmarks.py) and draws its genres wall
    with them.
    """
    data = load(WORDMARKS)
    seen: dict[str, dict] = {}

    for shelf in data["genres"]:
        family = shelf["font"]
        if family in seen:
            continue
        seen[family] = {
            "id": "Wordmark" + re.sub(r"[^A-Za-z0-9]", "", family),
            "name": family,
            "license": ["OFL-1.1"],
            "url": shelf.get("url") or google_fonts_url(family),
            "heads": ["desktop", "android"],
        }

    return [seen[family] for family in sorted(seen)]


def genre_photo_name(genre: str) -> str:
    """The file a genre's photograph has on the phones: gen_genre_photos.slug with "genre-" before it,
    as gen_genre_photos_phone.py writes it. Written out here rather than imported, because that
    module needs the imaging libraries; if the two ever differ, the check in photo_entries fails."""
    return "genre-" + re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", genre.lower())).strip("-") + ".jpg"


def android_photos(folder: str) -> set[str]:
    """The photographs in one of the Android app's folders, or an empty set when it is not there."""
    if not os.path.isdir(folder):
        return set()
    return {name for name in os.listdir(folder) if name.endswith(".jpg")}


def photo_entries() -> list[dict]:
    """One entry per photograph the app ships: the photographer, and what the picture is used for.

    All three tables are included, because they hold the same kind of item under the same licence
    and a reader does not care which file lists a picture. The genre photographs head a genre's
    page. The playlist photographs sit behind the frame of a generated list. The backdrop
    photographs are desktop backdrops in Settings, after a script has coloured them.

    Every head ships the genre and playlist photographs: the phones' genre photographs are cut by
    gen_genre_photos_phone.py, the iPhone's playlist photographs are copied by
    gen_playlist_photos_phone.py and the Android apps' by gen_playlist_photos_tv.py, so every
    About screen lists them.

    The Pexels licence does not require credit. Credit is given anyway, by the photographer's name,
    because a person took each picture.

    The Android phone is credited with the photographs whose files are in it, looked up where the
    copying scripts put them: the genre photographs in the phone's assets, the playlist photographs
    in `:core`'s (the TV and the phone share them), and a backdrop under its resource name in the
    phone's drawable-nodpi (background-sheet-music.jpg is background_sheet_music.jpg there). The
    other direction is checked for the two photograph folders: a picture there that no table names
    would ship with nobody credited, so it stops the script. The backdrop folder is not checked
    that way, because it also holds the backdrops rpm draws itself.
    """
    entries = []
    genre_files = android_photos(ANDROID_GENRE_PHOTOS)
    list_files = android_photos(ANDROID_LIST_PHOTOS)
    backdrop_files = android_photos(ANDROID_BACKDROPS)

    def heads(*base: str, android: bool) -> list[str]:
        return list(base) + (["android"] if android else [])

    named_genres = set()
    for photo in load(PHOTOS)["photos"]:
        name = genre_photo_name(photo["genre"])
        named_genres.add(name)
        entries.append({
            "id": "Photo" + re.sub(r"[^A-Za-z0-9]", "", photo["genre"]),
            "name": photo.get("by") or "Unknown",
            "detail": photo["genre"],
            "license": ["Pexels"],
            "url": photo.get("page", ""),
            "heads": heads("desktop", "iphone", android=name in genre_files),
        })

    named_lists = set()
    for photo in load(LIST_PHOTOS)["photos"]:
        named_lists.add(photo["file"])
        entries.append({
            "id": "ListPhoto" + re.sub(r"[^A-Za-z0-9]", "", photo["file"]),
            "name": photo.get("by") or "Unknown",
            "detail": photo["list"],
            "license": ["Pexels"],
            "url": photo.get("page", ""),
            "heads": heads("desktop", "iphone", android=photo["file"] in list_files),
        })

    # The Android phone carries the Sheet music backdrop, cut from this photograph by
    # make_sheet_music.py. The iPhone carries the same cut, but its list does not credit it yet:
    # crediting it there changes the iPhone's table, and that is a change of its own.
    for photo in load(BACKDROP_PHOTOS)["photos"]:
        resource = photo["file"].replace("-", "_")
        entries.append({
            "id": "BackdropPhoto" + re.sub(r"[^A-Za-z0-9]", "", photo["backdrop"]),
            "name": photo.get("by") or "Unknown",
            "detail": photo["backdrop"] + " (backdrop)",
            "license": ["Pexels"],
            "url": photo.get("page", ""),
            "heads": heads("desktop", android=resource in backdrop_files),
        })

    unnamed = sorted(genre_files - named_genres) + sorted(list_files - named_lists)
    if unnamed:
        for name in unnamed:
            print(f"gen_credits: the Android app carries the photograph {name}, which no table names",
                  file=sys.stderr)
        sys.exit(1)

    return sorted(entries, key=lambda e: e["detail"])


# --- checking -------------------------------------------------------------------------------

def check(credits: dict, sections: list[dict]) -> set[str]:
    """Validates the table and returns the licence keys that are used.

    Every problem found here is a hard failure. A mistake on this screen credits somebody's work
    under the wrong terms, and nothing at runtime would reveal it.
    """
    strings = load(STRINGS)
    licences = {k: v for k, v in credits["licenses"].items() if not k.startswith("$")}
    problems: list[str] = []
    used: set[str] = set()
    ids: set[str] = set()

    def want_string(key: str, where: str) -> None:
        if key and key not in strings:
            problems.append(f"{where} names the string {key}, which is not in strings.json")

    for section in sections:
        want_string(section["title"], f"section {section['id']}")
        want_string(section.get("note", ""), f"section {section['id']}")

        for entry in section["entries"]:
            where = f"{section['id']}/{entry['id']}"

            if entry["id"] in ids:
                problems.append(f"{where} repeats an id already used")
            ids.add(entry["id"])

            want_string(entry.get("use", ""), where)

            if not entry.get("heads"):
                problems.append(f"{where} ships on no head")
            for head in sorted(set(entry.get("heads", [])) - HEADS):
                problems.append(f"{where} names the head {head}, which is not an app")

            for key in entry["license"]:
                if key not in licences:
                    problems.append(f"{where} names the licence {key}, which is not in the map")
                    continue
                used.add(key)

                name = licences[key].get("file")
                if name and not os.path.exists(os.path.join(LICENSES, name)):
                    problems.append(
                        f"{where} is under {key}, whose text scripts/licenses/{name} is missing"
                        " (run scripts/fetch-licenses.sh)")

            if entry["license"] == ["Terms"] and not entry.get("license_url"):
                problems.append(f"{where} is under 'Terms' but gives no license_url to point at")

    # A notices document is shipped with the app, because the licences inside it require it to travel
    # with the binary, and it is also read at a URL, because it is too long for a dialog. It needs
    # both: without a file nothing ships, and without a url nobody can read it.
    for key, licence in licences.items():
        if licence.get("notices") and not (licence.get("file") and licence.get("url")):
            problems.append(f"the licence {key} is a notices document and needs both a file and a url")

    # The other direction: a licence text that no entry uses would be shipped but never shown.
    named = {licences[key]["file"] for key in used if licences[key].get("file")}
    for name in sorted(os.listdir(LICENSES)):
        if name.endswith(".txt") and name not in named:
            problems.append(f"scripts/licenses/{name} is named by no entry")

    if problems:
        for problem in problems:
            print(f"gen_credits: {problem}", file=sys.stderr)
        sys.exit(1)

    return used


# --- writing --------------------------------------------------------------------------------

def for_head(sections: list[dict], head: str) -> list[dict]:
    """The sections as one head sees them, without the empty ones."""
    kept = []

    for section in sections:
        entries = [e for e in section["entries"] if head in e["heads"]]
        if entries:
            kept.append({**section, "entries": entries})

    return kept


def licences_for(credits: dict, sections: list[dict]) -> dict[str, dict]:
    """The licence map reduced to the licences these sections use, keyed as the entries name them."""
    whole = credits["licenses"]
    keys = {key for section in sections for entry in section["entries"] for key in entry["license"]}
    return {key: whole[key] for key in sorted(keys)}


def copy_licenses(credits: dict, sections: list[dict], dest: str) -> None:
    """Copies one head's licence texts to the folder it reads, and puts nothing else there.

    The folder is emptied first. Otherwise a text would stay after the entry that needed it is
    removed, and that mistake would not show on screen.
    """
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)

    for key, licence in licences_for(credits, sections).items():
        name = licence.get("file")
        if name:
            shutil.copyfile(os.path.join(LICENSES, name), os.path.join(dest, name))


def write_site(credits: dict, sections: list[dict]) -> None:
    """Writes the /credits page of rpmrpmrpm.com: every entry on either head, in English, and what
    the LGPL requires for the components under it.

    The LGPL (2.1, section 6) requires that whoever receives a binary can also get the source of that
    version, including the scripts that built it. So the page starts with those components and the
    exact source of each, publishes the ffmpeg build script and its pinned versions at /source/, and
    includes the written offer that covers anything the links do not.

    The view is Razor, so every '@' in generated text is doubled.
    """
    import html

    strings = load(STRINGS)
    versions = tool_versions()
    licences = credits["licenses"]

    def text(value: str) -> str:
        return html.escape(value).replace("@", "@@")

    def en(key: str | None) -> str:
        return text(strings[key]["en"]) if key else ""

    def link(url: str, label: str) -> str:
        return f'<a href="{text(url)}">{text(label)}</a>'

    def licence_links(entry: dict) -> str:
        out = []
        for key in entry["license"]:
            licence = licences[key]
            if licence.get("file"):
                out.append(link(f"/licenses/{licence['file']}", licence["name"]))
            else:
                out.append(link(entry.get("license_url") or licence["url"], licence["name"]))
        return ", ".join(out)

    # Which app ships the entry. The text says "Desktop" and does not name Mac and Windows, because
    # the desktop list is one list for both, and some entries (the Windows App SDK, Win2D) are on
    # only one of them. "Android" is the Android phone app.
    def heads(entry: dict) -> str:
        names = [name for head, name in (("desktop", "Desktop"), ("iphone", "iPhone"),
                                         ("android", "Android")) if head in entry["heads"]]
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    # The Android app's FFmpeg decoder, whose version the page names beside the FFmpeg it links.
    decoder = next((e for sec in sections for e in sec["entries"] if e["id"] == "Media3Ffmpeg"), None)
    if decoder is None or not decoder.get("version"):
        raise SystemExit("gen_credits: the page describes the Android app's FFmpeg decoder, "
                         "but credits.json has no Media3Ffmpeg entry with a version")
    if not os.path.exists(ANDROID_BUILD_SCRIPT):
        raise SystemExit(f"gen_credits: the page publishes {ANDROID_BUILD_SCRIPT}, which is not there "
                         "(check out rpm-android beside this repo, or set RPM_ANDROID)")

    lines = [
        "@* Written by RPM/scripts/gen_credits.py from RPM/scripts/credits.json. Not hand-edited: run the script. *@",
        "@{",
        '    ViewData["Title"] = "Credits";',
        "}",
        "",
        '<i class="fa ch-icon" aria-hidden="true">&#xf004;</i>',
        "<h1>Credits</h1>",
        '<p class="lead">What rpm ships that somebody else made, and the services it asks. This is the '
        "same list as the About screen in the app.</p>",
        "",
        '<h2 id="lgpl">Source code for LGPL components</h2>',
        "<p>These parts of rpm are under the GNU Lesser General Public License. Each links to the "
        "source of the exact version rpm ships.</p>",
        "<ul>",
    ]
    lgpl = [e for sec in sections for e in sec["entries"]
            if any(key.startswith("LGPL") for key in e["license"])]
    for entry in lgpl:
        # The detail is part of the name: two entries are FFmpeg at different versions, one built by
        # rpm and one inside fpcalc. If both were just called "FFmpeg", a reader could open the
        # wrong source archive.
        name = f"{text(entry['name'])} {text(entry.get('version') or '')}"
        if entry.get("detail"):
            name += f", {text(entry['detail'])}"
        lines.append(
            f"    <li><strong>{name}</strong> "
            f"({licence_links(entry)}): {link(entry['source'], 'source')}</li>")
    lines += [
        "</ul>",
        "",
        "<h3>ffmpeg, as rpm builds it</h3>",
        f"<p>rpm's ffmpeg is FFmpeg {text(versions['FFMPEG_VERSION'])} with LAME "
        f"{text(versions['LAME_VERSION'])} and zlib {text(versions['ZLIB_VERSION'])}, built by rpm "
        "under the LGPL 2.1 or later, with no GPL or nonfree parts. It is a separate program beside "
        "the app, and <code>ffmpeg -version</code> prints the configuration it was built with.</p>",
        "<ul>",
        f"    <li>Build script: {link('/source/build-ffmpeg.sh', 'build-ffmpeg.sh')}, and the versions and "
        f"checksums it builds from: {link('/source/tool-versions.txt', 'tool-versions.txt')}</li>",
    ]
    for name, url, sha in (
        ("FFmpeg", f"https://ffmpeg.org/releases/ffmpeg-{versions['FFMPEG_VERSION']}.tar.xz", versions["FFMPEG_SHA256"]),
        ("LAME", f"https://downloads.sourceforge.net/project/lame/lame/{versions['LAME_VERSION']}/lame-{versions['LAME_VERSION']}.tar.gz", versions["LAME_SHA256"]),
        ("zlib", f"https://github.com/madler/zlib/releases/download/v{versions['ZLIB_VERSION']}/zlib-{versions['ZLIB_VERSION']}.tar.gz", versions["ZLIB_SHA256"]),
    ):
        lines.append(f'    <li>{text(name)} source: {link(url, url.rsplit("/", 1)[1])} '
                     f'<span class="dim">(SHA-256 <code class="hash">{text(sha)}</code>)</span></li>')
    lines += [
        "</ul>",
        "",
        "<h3>FFmpeg in the Android app</h3>",
        f"<p>The Android app carries FFmpeg {text(versions['FFMPEG_VERSION'])}'s libavcodec, libavutil "
        "and libswresample, built by rpm under the LGPL 2.1 or later with only the ALAC, AC-3 and "
        "E-AC-3 decoders and no GPL or nonfree parts. They are linked into "
        "<code>libffmpegJNI.so</code> together with Media3's FFmpeg decoder "
        f"{text(decoder['version'])}, which is under the Apache License 2.0.</p>",
        "<ul>",
        f"    <li>Build script: {link('/source/build-android-ffmpeg.sh', 'build-android-ffmpeg.sh')}, "
        f"which builds from the same {link('/source/tool-versions.txt', 'tool-versions.txt')}</li>",
        f"    <li>The decoder that links them: "
        f"{link('https://github.com/rpmrpmrpm/rpm-android/tree/main/RPM.Android/ffmpeg', 'RPM.Android/ffmpeg')}"
        f" in rpm-android, from {link(decoder['url'], 'decoder_ffmpeg')} in Media3 "
        f"{text(decoder['version'])}</li>",
        f"    <li>FFmpeg source: the same "
        f"{link('https://ffmpeg.org/releases/ffmpeg-' + versions['FFMPEG_VERSION'] + '.tar.xz', 'ffmpeg-' + versions['FFMPEG_VERSION'] + '.tar.xz')}"
        " as above</li>",
        "</ul>",
        "",
        "<h3>fpcalc, as Chromaprint builds it</h3>",
        f"<p>rpm ships Chromaprint's own published <code>fpcalc</code> "
        f"{text(versions['CHROMAPRINT_VERSION'])} rather than building it, and that binary has "
        f"FFmpeg {text(versions['FPCALC_FFMPEG_VERSION'])} linked into it, which "
        "<code>fpcalc -version</code> prints. Chromaprint builds that FFmpeg with no GPL and no "
        "nonfree parts, so it is under the LGPL 2.1 or later like rpm's own. The scripts that "
        "control both halves of that build are published:</p>",
        "<ul>",
        f"    <li>fpcalc: "
        f"{link('https://github.com/acoustid/chromaprint/blob/v' + versions['CHROMAPRINT_VERSION'] + '/package/build.sh', 'package/build.sh')}"
        f" at tag v{text(versions['CHROMAPRINT_VERSION'])}</li>",
        f"    <li>The FFmpeg inside it: "
        f"{link('https://github.com/acoustid/ffmpeg-build/tree/v' + versions['FPCALC_FFMPEG_VERSION'] + '-1', 'acoustid/ffmpeg-build')}"
        f" at tag v{text(versions['FPCALC_FFMPEG_VERSION'])}-1, which holds the configure flags</li>",
        f"    <li>FFmpeg source: "
        f"{link('https://ffmpeg.org/releases/ffmpeg-' + versions['FPCALC_FFMPEG_VERSION'] + '.tar.gz', 'ffmpeg-' + versions['FPCALC_FFMPEG_VERSION'] + '.tar.gz')}</li>",
        "</ul>",
        "",
        "<h3>Written offer</h3>",
        "<p>For at least three years after we last distribute a version of rpm, we will send anyone "
        "who asks the complete source code of the components above for that version, including the "
        "scripts used to build them, for no more than the cost of sending it. Write to "
        '<a href="mailto:support@@rpmrpmrpm.com">support@@rpmrpmrpm.com</a>.</p>',
        "<p>On the Mac and on Windows, rpm is compiled ahead of time into one program, so TagLib# is "
        "inside it rather than beside it. The same offer covers the build of that version that is not "
        "compiled ahead of time: rpm's own compiled .NET assemblies with TagLib# as a separate file, so "
        "the app can be run, or compiled again, with a modified TagLib#.</p>",
        "<p>In the Android app, FFmpeg is linked statically into <code>libffmpegJNI.so</code>. "
        "Everything else in that library is published above as source, so it can be built again "
        "with a modified FFmpeg; the same offer covers that version's build files.</p>",
    ]

    for section in sections:
        if not section["entries"]:
            continue
        lines += ["", f"<h2>{en(section['title'])}</h2>"]
        if section.get("note"):
            lines.append(f'<p class="dim">{en(section["note"])}</p>')
        lines.append("<ul>")
        for entry in section["entries"]:
            head = f"<strong>{text(entry['name'])}</strong>"
            if entry.get("version"):
                head += f" {text(entry['version'])}"
            if entry.get("detail"):
                head += f", {text(entry['detail'])}"
            parts = [head]
            if entry.get("use"):
                parts.append(en(entry["use"]))
            if entry.get("copyright"):
                parts.append(f'<span class="dim">{text(entry["copyright"])}</span>')
            meta = [licence_links(entry)]
            if entry.get("url"):
                meta.append(link(entry["url"], "website"))
            if entry.get("source"):
                meta.append(link(entry["source"], "source"))
            meta.append(heads(entry))
            parts.append(f'<span class="dim">{" · ".join(meta)}</span>')
            lines.append("    <li>" + "<br />".join(parts) + "</li>")
        lines.append("</ul>")

    with open(SITE_VIEW, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    copy_licenses(credits, sections, SITE_LICENSES)
    shutil.rmtree(SITE_SOURCE, ignore_errors=True)
    os.makedirs(SITE_SOURCE, exist_ok=True)
    shutil.copyfile(BUILD_SCRIPT, os.path.join(SITE_SOURCE, "build-ffmpeg.sh"))
    shutil.copyfile(ANDROID_BUILD_SCRIPT, os.path.join(SITE_SOURCE, "build-android-ffmpeg.sh"))
    shutil.copyfile(TOOL_VERSIONS, os.path.join(SITE_SOURCE, "tool-versions.txt"))


def cs_string(value: str | None) -> str:
    if not value:
        return "null"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def swift_string(value: str | None) -> str:
    if not value:
        return "nil"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_cs(credits: dict, sections: list[dict]) -> None:
    lines = [
        BANNER,
        "",
        "namespace RPM.Desktop.Presentation.About;",
        "",
        "public static partial class Credits",
        "{",
        "    /// <summary>The licences that the entries on this head use, by the key an entry names.",
        "    /// A licence with a file has its text in Assets/Licenses. A licence without a file is a",
        "    /// set of published terms that only the publisher may host, so the screen links to it.</summary>",
        "    public static readonly IReadOnlyDictionary<string, CreditLicense> Licenses =",
        "        new Dictionary<string, CreditLicense>",
        "        {",
    ]

    for key, licence in licences_for(credits, sections).items():
        lines.append(
            f"            [{cs_string(key)}] = new({cs_string(licence['name'])}, "
            f"{cs_string(licence.get('file'))}, {cs_string(licence.get('url'))}, "
            f"{'true' if licence.get('notices') else 'false'}),")

    lines += [
        "        };",
        "",
        "    /// <summary>What this head ships and what it asks, in the order the screen shows it.</summary>",
        "    public static readonly IReadOnlyList<CreditSection> Sections =",
        "    [",
    ]

    for section in sections:
        lines.append(f"        new({cs_string(section['title'])}, "
                     f"{cs_string(section.get('note'))},")
        lines.append("        [")
        for entry in section["entries"]:
            licences = ", ".join(cs_string(key) for key in entry["license"])
            lines.append(
                f"            new({cs_string(entry['name'])}, {cs_string(entry.get('version'))}, "
                f"{cs_string(entry.get('detail'))}, {cs_string(entry.get('copyright'))}, "
                f"{cs_string(entry.get('url'))}, {cs_string(entry.get('source'))}, "
                f"{cs_string(entry.get('use'))}, {cs_string(entry.get('license_url'))}, "
                f"[{licences}]),")
        lines += ["        ]),"]

    lines += ["    ];", "}", ""]

    os.makedirs(os.path.dirname(CS_OUT), exist_ok=True)
    with open(CS_OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def write_swift(credits: dict, sections: list[dict]) -> None:
    lines = [
        BANNER,
        "",
        "extension Credits {",
        "    /// The licences that the entries on this head use, by the key an entry names. A licence",
        "    /// with a file has its text in the Licenses resource folder. A licence without a file is a",
        "    /// set of published terms that only the publisher may host, so the screen links to it.",
        "    public static let licenses: [String: CreditLicense] = [",
    ]

    for key, licence in licences_for(credits, sections).items():
        lines.append(
            f"        {swift_string(key)}: CreditLicense("
            f"name: {swift_string(licence['name'])}, "
            f"file: {swift_string(licence.get('file'))}, "
            f"url: {swift_string(licence.get('url'))}, "
            f"isNotices: {'true' if licence.get('notices') else 'false'}),")

    lines += [
        "    ]",
        "",
        "    /// What this head ships and what it asks, in the order the screen shows it.",
        "    public static let sections: [CreditSection] = [",
    ]

    for section in sections:
        lines.append(f"        CreditSection(title: {swift_string(section['title'])}, "
                     f"note: {swift_string(section.get('note'))}, entries: [")
        for entry in section["entries"]:
            licences = ", ".join(swift_string(key) for key in entry["license"])
            lines.append(
                f"            CreditEntry(name: {swift_string(entry['name'])}, "
                f"version: {swift_string(entry.get('version'))}, "
                f"detail: {swift_string(entry.get('detail'))}, "
                f"copyright: {swift_string(entry.get('copyright'))}, "
                f"url: {swift_string(entry.get('url'))}, "
                f"source: {swift_string(entry.get('source'))}, "
                f"use: {swift_string(entry.get('use'))}, "
                f"termsUrl: {swift_string(entry.get('license_url'))}, "
                f"licenses: [{licences}]),")
        lines += ["        ]),"]

    lines += ["    ]", "}", ""]

    os.makedirs(os.path.dirname(SWIFT_OUT), exist_ok=True)
    with open(SWIFT_OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def kt_string(value: str | None) -> str:
    if not value:
        return "null"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def kt_res(key: str | None) -> str:
    """A string key as `:core`'s resource id, so a key the string tables lack fails the build."""
    return f"R.string.{key}" if key else "null"


def write_kotlin(credits: dict, sections: list[dict]) -> None:
    lines = [
        BANNER,
        "",
        "package com.rpm.player.phone.profile",
        "",
        "import com.rpm.player.core.R",
        "",
        "/** The Android phone's half of [Credits]: the table, which [Credits] reads. */",
        "internal object CreditsData {",
        "    /** The licences that the entries on this head use, by the key an entry names. A licence with a",
        "     * file has its text in the app's assets, under credits/. A licence without a file is a set of",
        "     * published terms that only the publisher may host, so the screen links to it. */",
        "    val licenses: Map<String, CreditLicense> = mapOf(",
    ]

    for key, licence in licences_for(credits, sections).items():
        lines.append(
            f"        {kt_string(key)} to CreditLicense("
            f"name = {kt_string(licence['name'])}, "
            f"file = {kt_string(licence.get('file'))}, "
            f"url = {kt_string(licence.get('url'))}, "
            f"isNotices = {'true' if licence.get('notices') else 'false'}),")

    lines += [
        "    )",
        "",
        "    /** What this head ships and what it asks, in the order the screen shows it. */",
        "    val sections: List<CreditSection> = listOf(",
    ]

    for section in sections:
        lines.append(f"        CreditSection(title = {kt_res(section['title'])}, "
                     f"note = {kt_res(section.get('note'))}, entries = listOf(")
        for entry in section["entries"]:
            licences = ", ".join(kt_string(key) for key in entry["license"])
            lines.append(
                f"            CreditEntry(name = {kt_string(entry['name'])}, "
                f"version = {kt_string(entry.get('version'))}, "
                f"detail = {kt_string(entry.get('detail'))}, "
                f"copyright = {kt_string(entry.get('copyright'))}, "
                f"url = {kt_string(entry.get('url'))}, "
                f"source = {kt_string(entry.get('source'))}, "
                f"use = {kt_res(entry.get('use'))}, "
                f"termsUrl = {kt_string(entry.get('license_url'))}, "
                f"licenses = listOf({licences})),")
        lines += ["        )),"]

    lines += ["    )", "}", ""]

    os.makedirs(os.path.dirname(KT_OUT), exist_ok=True)
    with open(KT_OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    credits = load(CREDITS)

    sections = []
    for section in credits["sections"]:
        made = section.get("generated")
        if made == "wordmarks":
            section = {**section, "entries": wordmark_entries()}
        elif made == "photos":
            # Entries listed by hand in credits.json (the desktop's dialog header) come first.
            section = {**section, "entries": section["entries"] + photo_entries()}
        sections.append(section)

    resolve_versions(sections)
    check(credits, sections)

    desktop = for_head(sections, "desktop")
    iphone = for_head(sections, "iphone")

    write_cs(credits, desktop)
    copy_licenses(credits, desktop, CS_LICENSES)

    write_swift(credits, iphone)
    copy_licenses(credits, iphone, SWIFT_LICENSES)

    has_android = os.path.isdir(os.path.join(ANDROID, "phone"))
    android = for_head(sections, "android")
    if has_android:
        write_kotlin(credits, android)
        copy_licenses(credits, android, KT_LICENSES)
    else:
        print(f"{ANDROID} is not checked out: the Android phone's credits were not written")

    if os.path.isdir(SITE):
        if not has_android:
            # Without the Android app its photographs cannot be looked up, and the page would leave
            # them off while saying it lists every head.
            print(f"gen_credits: the website's page lists the Android app, which is not at {ANDROID} "
                  "(check out rpm-android beside this repo, or set RPM_ANDROID)", file=sys.stderr)
            sys.exit(1)
        write_site(credits, sections)
    else:
        print(f"{SITE} is not checked out: the website's credits page was not written")

    def count(head: list[dict]) -> int:
        return sum(len(section["entries"]) for section in head)

    print(f"desktop: {count(desktop)} entries in {len(desktop)} sections, "
          f"{len(os.listdir(CS_LICENSES))} licence texts")
    print(f"iphone:  {count(iphone)} entries in {len(iphone)} sections, "
          f"{len(os.listdir(SWIFT_LICENSES))} licence texts")
    if has_android:
        print(f"android: {count(android)} entries in {len(android)} sections, "
              f"{len(os.listdir(KT_LICENSES))} licence texts")


if __name__ == "__main__":
    main()
