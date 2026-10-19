#!/usr/bin/env python3
"""Cut the desktop's backdrops to the phone's shape.

Two of the phone's backdrops are the desktop's own: the Pegasus room and RPaMp's ground. They are
drawn for a window (3840x2351 and 2560x1600, landscape) and a phone is portrait, so each one is
cut to a centre column of the full height of the source and scaled to the size that the phone's
other backgrounds are drawn at.

The desktop's table of records (Night, and Gold, the same table in gold) is not cut for the phone.
The phone's version of that table is the vinyl ground (make_vinyl_ground.py), in blue and in gold.

THE CENTRE COLUMN IS ENOUGH. Both pictures are smooth fields, so a smarter crop would have nothing
to choose from.

Run it after any of the desktop's backdrops is rebuilt:

    python3 scripts/make_phone_backdrops.py

The Sheet music backdrop is not in this list: make_sheet_music.py writes its own phone cut from a
render at the phone's height, because a centre column of the desktop file would have to be
stretched from 1082 pixels wide to 1320.

Writes into the RPMUI resources of the Swift app. The Uno phone app reads the desktop's Assets
folder directly and needs nothing from here.
"""

import os
import workspace
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = workspace.path("RPM.Desktop", "Assets")
SWIFT = workspace.path("RPM.iOS", "Modules", "RPMUI", "Sources", "RPMUI", "Resources")

# The size of background-vinyl.jpg (make_vinyl_ground.py), so that every background in the app has
# the same picture size and the same decoding cost.
WIDE, TALL = 1320, 2868

# High enough that a smooth field shows no visible bands, and low enough that the files stay small.
QUALITY = 82

PICTURES = ["background-pegasus.jpg", "background-rpamp.jpg"]

# These pictures are rotated by 180 degrees.
#
# RPaMp's ground is lit from one end, and its detail is gathered there. On the desktop that end is
# at the window's title bar. On a phone the same orientation would put the dark, empty half at the
# top, where every page in this app shows its title. Rotating the picture puts the light where the
# text is.
#
# The rotation is done here and not when the picture is drawn: which way up a picture is belongs to
# the picture, and a rotation done by the code that draws it would have to be known by every place
# that draws it, including the profile tiles.
TURNED = {"background-rpamp.jpg"}


def cut(name: str) -> None:
    with Image.open(os.path.join(SOURCE, name)) as picture:
        whole = picture.convert("RGB")

    column = round(whole.height * WIDE / TALL)
    if column > whole.width:
        # The source is already taller than the phone shape: take its full width and cut the height.
        row = round(whole.width * TALL / WIDE)
        top = (whole.height - row) // 2
        box = (0, top, whole.width, top + row)
    else:
        left = (whole.width - column) // 2
        box = (left, 0, left + column, whole.height)

    cut = whole.crop(box).resize((WIDE, TALL), Image.LANCZOS)

    if name in TURNED:
        cut = cut.rotate(180)

    out = os.path.join(SWIFT, name)
    cut.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    print(f"{name}: {box[2] - box[0]}x{box[3] - box[1]} -> {WIDE}x{TALL}, "
          f"{os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    for name in PICTURES:
        cut(name)
