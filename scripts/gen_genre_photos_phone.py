#!/usr/bin/env python3
"""Writes the phones' genre photographs from scripts/genre-photos.json.

The desktop crop (gen_genre_photos.py) is a six-to-one band for the top of a genre page on a wide
window. A phone is held upright, so its cards and page headers are portrait, and a band that thin
cannot be cropped to a portrait. This script crops the SAME photographs again, from the same cache,
at three wide by four tall.

The horizontal position of the crop is the `across` value of the entry's frame setting, if it has
one (the subject chosen for the desktop is the subject here too), and the middle otherwise. The
full height of the photograph is kept. `flip` is applied first, as on the desktop.

Output: RPM.iOS/Modules/RPMUI/Sources/RPMUI/Resources/GenrePhotos/genre-<slug>.jpg, where <slug> is
gen_genre_photos.slug, and the same files copied byte for byte to the Android phone's assets
(RPM.Android/phone/src/main/assets/genre-photos), which `GenreMarks.photoName` names the same way.
Both folders are rewritten completely: a genre removed from the JSON leaves no file behind.

Needs the photographs in scripts/.photocache, which gen_genre_photos.py fills. With a Pexels key,
this script also downloads missing photographs in the same way.

    python3 scripts/gen_genre_photos_phone.py
"""

import json
import workspace
import os
import shutil
import sys

from PIL import Image, ImageOps

import gen_genre_photos as desktop

ROOT = desktop.ROOT
TARGET = workspace.path("RPM.iOS", "Modules", "RPMUI", "Sources", "RPMUI", "Resources",
                      "GenrePhotos")
ANDROID = workspace.path("RPM.Android", "phone", "src", "main", "assets", "genre-photos")
SHAPE = 3 / 4          # width over height
WIDEST = 750           # pixels across: a card is under 600, the page header about 1180 at 3x
QUALITY = 82


def cut(path, across, flip):
    image = Image.open(path).convert("RGB")
    if flip:
        image = ImageOps.mirror(image)
    w, h = image.size

    keep = min(w, int(round(h * SHAPE)))
    left = min(max(int(round(across * w - keep / 2)), 0), w - keep)
    tall = int(round(keep / SHAPE))
    top = (h - tall) // 2
    image = image.crop((left, top, left + keep, top + tall))
    if image.width > WIDEST:
        image = image.resize((WIDEST, int(round(WIDEST / SHAPE))), Image.LANCZOS)
    return image


def main():
    with open(desktop.SOURCE) as f:
        photos = json.load(f)["photos"]

    wanted = {f"genre-{desktop.slug(p['genre'])}.jpg" for p in photos}
    for folder in (TARGET, ANDROID):
        os.makedirs(folder, exist_ok=True)
        for stale in os.listdir(folder):
            if stale.endswith(".jpg") and stale not in wanted:
                os.remove(os.path.join(folder, stale))
                print(f"  removed {stale}, which no genre asks for any more.")

    api_key = desktop.key()
    total = 0
    for photo in photos:
        name = f"genre-{desktop.slug(photo['genre'])}.jpg"
        out = os.path.join(TARGET, name)
        across = (photo.get("frame") or {}).get("across", 0.5)
        cut(desktop.fetch(photo, api_key), across, photo.get("flip", False)).save(
            out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        shutil.copyfile(out, os.path.join(ANDROID, name))
        size = os.path.getsize(out)
        total += size
        print(f"  {photo['genre']:20} {name:30} {size / 1024:5.0f} KB  across {across}")

    print(f"{os.path.relpath(TARGET, ROOT)}: {len(photos)} photographs, {total / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
