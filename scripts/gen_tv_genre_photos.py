"""Cuts the desktop's genre photographs to the shape of the Android TV genre page's photograph box.

It uses the same photographs as the desktop's genre page: the Pexels ids in scripts/genre-photos.json, cached in
scripts/.photocache by gen_genre_photos.py. Each cut is centred on the same point as the desktop's: the middle of
the hand placed window ('frame'), or of the automatic band ('focus'). It is mirrored where the desktop's is
('flip'). The desktop's band is six to one. The TV's box is the right 0.5625 of the screen width, by 0.324 of that
width (ArtistPage's PHOTO_SHARE, BAND_HEIGHT x BAND_FOOT), about 1.74 to one. The TV's cut is the tallest window of
that shape that the photograph has, centred on that point.

Writes RPM.Android/tv/src/main/assets/genre-photos/<slug>.jpg, one per genre, named as the desktop's are. It also
writes the same file to RPM.tvOS/rpm/GenrePhotos/genre-<slug>.jpg for the Apple TV, whose genre page uses the same
box shape. The prefix keeps the names apart in the app bundle, which holds its resources in one folder. It removes
any file that no genre asks for in either folder. Run it after changing genre-photos.json:

    python scripts/gen_tv_genre_photos.py
"""

import json
import workspace
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_genre_photos as desk  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

OUT = workspace.path("RPM.Android", "tv", "src", "main", "assets", "genre-photos")
APPLE_TV = workspace.path("RPM.tvOS", "rpm", "GenrePhotos")
APPLE_TV_PREFIX = "genre-"

# The TV box's shape, and the width the files are written at. 1280 pixels is enough for a picture that the page fades
# out at two sides, and it keeps the 36 files near 4 MB in total.
SHAPE = 0.5625 / (0.27 * 1.2)
WIDTH = 1280
QUALITY = 82


def middle(image, photo, shape):
    """Where the desktop's band is centred on the photograph, in its pixels."""
    w, h = image.size
    frame = photo.get("frame")
    if frame:
        x0, y0, x1, y1 = desk.window(w, h, shape, frame)
        return (max(x0, 0) + x1) / 2, (y0 + y1) / 2
    if w / h > shape:
        return w / 2, h / 2
    keep = w / shape
    top = (h - keep) * photo.get("focus", 0.42)
    return w / 2, top + keep / 2


def cut(path, photo, desk_shape):
    image = Image.open(path).convert("RGB")
    if photo.get("flip", False):
        image = ImageOps.mirror(image)
    w, h = image.size
    cx, cy = middle(image, photo, desk_shape)
    # The tallest window of the TV's shape inside the photograph, centred on the desktop's middle point and kept inside.
    height = min(h, w / SHAPE)
    width = height * SHAPE
    x = min(max(cx - width / 2, 0), w - width)
    y = min(max(cy - height / 2, 0), h - height)
    box = (round(x), round(y), round(x + width), round(y + height))
    return image.crop(box).resize((WIDTH, round(WIDTH / SHAPE)), Image.LANCZOS)


def main():
    with open(desk.SOURCE, encoding="utf-8") as f:
        doc = json.load(f)
    desk_shape = doc["shape"]
    api_key = desk.key()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(APPLE_TV, exist_ok=True)
    wanted = {desk.slug(p["genre"]) + ".jpg" for p in doc["photos"]}
    for folder, prefix in ((OUT, ""), (APPLE_TV, APPLE_TV_PREFIX)):
        for stale in os.listdir(folder):
            if stale.endswith(".jpg") and stale[len(prefix):] not in wanted:
                os.remove(os.path.join(folder, stale))
                print(f"  removed {stale}")
    total = 0
    for photo in doc["photos"]:
        name = desk.slug(photo["genre"]) + ".jpg"
        out = os.path.join(OUT, name)
        cut(desk.fetch(photo, api_key), photo, desk_shape).save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        shutil.copyfile(out, os.path.join(APPLE_TV, APPLE_TV_PREFIX + name))
        total += os.path.getsize(out)
    print(f"{len(doc['photos'])} photographs, {total // 1024} KB, in {os.path.relpath(OUT, desk.ROOT)}")


if __name__ == "__main__":
    main()
