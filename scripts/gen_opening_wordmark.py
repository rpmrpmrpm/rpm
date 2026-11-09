#!/usr/bin/env python3
"""Writes the Android TV app's dimmed opening wordmark from the wordmark in :core (res/drawable/wordmark.xml).

It writes two files:

- wordmark_dim.xml, the wordmark at the opening screen's dim level. OpeningSplash draws it, and the
  window background shows it before the app's first frame;
- opening_window.xml, that window background: black, with the dimmed wordmark at the size and
  position used by the opening screen.

The band of light that sweeps across the wordmark is drawn in code (SweepSurface in Opening.kt).
Run this script after changing the wordmark or the dim level:

    python scripts/gen_opening_wordmark.py
"""

import os
import workspace
import re

ANDROID = workspace.path('RPM.Android')
# wordmark.xml and wordmark_dim.xml are used by code, so they are in :core with the other resources that
# code names. opening_window.xml is named only by the TV theme, so it is in :tv.
RES = os.path.join(ANDROID, 'core', 'src', 'main', 'res', 'drawable')
TV_RES = os.path.join(ANDROID, 'tv', 'src', 'main', 'res', 'drawable')

# The viewport of wordmark.xml, and the size the opening screen draws it at: 260 wide at 1080 (WORDMARK_WIDE).
W, H = 507, 195
WIDE_DP, HIGH_DP = 130, 50

# How bright the wordmark is outside the band of light. The dimmed wordmark in Opening.kt is this drawable.
DIM = 0.32


def main():
    with open(os.path.join(RES, 'wordmark.xml'), encoding='utf-8') as f:
        path = re.search(r'android:pathData="([^"]+)"', f.read()).group(1)

    dim = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- The rpm wordmark at the opening screen's dim level (OpeningSplash). It is also the window's
     background at launch (opening_window.xml), which the system draws before any of the app has run.
     Written by scripts/gen_opening_wordmark.py from the path in wordmark.xml: run the script again,
     do not edit by hand. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="{WIDE_DP}dp"
    android:height="{HIGH_DP}dp"
    android:viewportWidth="{W}"
    android:viewportHeight="{H}">
    <group android:translateX="-18" android:translateY="143">
        <path android:fillColor="#FFFFFF" android:fillAlpha="{DIM}" android:pathData="{path}" />
    </group>
</vector>
'''
    with open(os.path.join(RES, 'wordmark_dim.xml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(dim)

    window = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- The window's background while the app starts: black, with the dimmed wordmark where the opening
     screen draws it, so the opening screen is visible from the moment the app is launched and not only from
     its first frame. MainActivity sets the background back to plain black after that frame.
     Written by scripts/gen_opening_wordmark.py. -->
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@android:color/black" />
    <item
        android:drawable="@drawable/wordmark_dim"
        android:gravity="center"
        android:width="{WIDE_DP}dp"
        android:height="{HIGH_DP}dp" />
</layer-list>
'''
    with open(os.path.join(TV_RES, 'opening_window.xml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(window)
    print('wordmark_dim.xml, opening_window.xml: written')

    write_ios(path)


# ── the iPhone's launch screen ──

# The iPhone app's asset catalog. Its launch screen (UILaunchScreen in rpm/Info.plist) is the colour
# OpeningGround with the image OpeningWordmark in the middle, at its own size: the dimmed wordmark, 130 by 50
# points, where the opening screen (RPMUI/Opening.swift) draws it.
IOS_ASSETS = workspace.path('RPM.iOS', 'rpm', 'Assets.xcassets')

ASSET_INFO = '"info" : {\n    "author" : "xcode",\n    "version" : 1\n  }'


def write_ios(path):
    if not os.path.isdir(IOS_ASSETS):
        print('RPM.iOS not checked out: iPhone launch screen skipped')
        return

    image = os.path.join(IOS_ASSETS, 'OpeningWordmark.imageset')
    os.makedirs(image, exist_ok=True)
    with open(os.path.join(image, 'opening-wordmark.pdf'), 'wb') as f:
        f.write(wordmark_pdf(path))
    # One vector image with no scale: Xcode draws it at each screen's scale when it builds the app.
    with open(os.path.join(image, 'Contents.json'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('{\n  "images" : [\n    {\n      "filename" : "opening-wordmark.pdf",\n'
                '      "idiom" : "universal"\n    }\n  ],\n  ' + ASSET_INFO + ',\n'
                '  "properties" : {\n    "preserves-vector-representation" : true\n  }\n}\n')

    colour = os.path.join(IOS_ASSETS, 'OpeningGround.colorset')
    os.makedirs(colour, exist_ok=True)
    with open(os.path.join(colour, 'Contents.json'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('{\n  "colors" : [\n    {\n      "color" : {\n        "color-space" : "srgb",\n'
                '        "components" : {\n          "alpha" : "1.000",\n          "blue" : "0.000",\n'
                '          "green" : "0.000",\n          "red" : "0.000"\n        }\n      },\n'
                '      "idiom" : "universal"\n    }\n  ],\n  ' + ASSET_INFO + '\n}\n')
    print('OpeningWordmark.imageset, OpeningGround.colorset: written')


def wordmark_pdf(path):
    """The wordmark as a one-page PDF, WIDE_DP by HIGH_DP points, filled in grey at DIM.

    Grey and not white at DIM: the launch screen is black under it, and white at DIM over black is this grey,
    so the PDF needs no transparency.
    """
    scale = WIDE_DP / W

    def at(x, y):
        # The path's box starts at (18, -143), as the group in wordmark_dim.xml moves it, and a PDF counts y upward.
        return f'{(x - 18) * scale:.3f} {(H - (y + 143)) * scale:.3f}'

    ops = []
    here = (0.0, 0.0)
    start = here
    tokens = re.findall(r'[MLHVCQZmlhvcqz]|-?\d*\.?\d+(?:e-?\d+)?', path)
    i = 0
    command = None

    def number():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command in 'Zz':
                ops.append('h')
                here = start
                continue
        relative = command.islower()
        dx, dy = here if relative else (0.0, 0.0)
        c = command.upper()
        if c == 'M':
            here = (number() + dx, number() + dy)
            start = here
            ops.append(f'{at(*here)} m')
            command = 'l' if relative else 'L'
        elif c == 'L':
            here = (number() + dx, number() + dy)
            ops.append(f'{at(*here)} l')
        elif c == 'H':
            here = (number() + (here[0] if relative else 0.0), here[1])
            ops.append(f'{at(*here)} l')
        elif c == 'V':
            here = (here[0], number() + (here[1] if relative else 0.0))
            ops.append(f'{at(*here)} l')
        elif c == 'C':
            a = (number() + dx, number() + dy)
            b = (number() + dx, number() + dy)
            here = (number() + dx, number() + dy)
            ops.append(f'{at(*a)} {at(*b)} {at(*here)} c')
        elif c == 'Q':
            q = (number() + dx, number() + dy)
            end = (number() + dx, number() + dy)
            a = (here[0] + 2 / 3 * (q[0] - here[0]), here[1] + 2 / 3 * (q[1] - here[1]))
            b = (end[0] + 2 / 3 * (q[0] - end[0]), end[1] + 2 / 3 * (q[1] - end[1]))
            here = end
            ops.append(f'{at(*a)} {at(*b)} {at(*here)} c')
        else:
            raise ValueError(f'path command {command} is not read here')

    content = f'{DIM:.2f} g\n' + '\n'.join(ops) + '\nf\n'
    objects = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {WIDE_DP} {HIGH_DP}] /Contents 4 0 R /Resources << >> >>',
        f'<< /Length {len(content)} >>\nstream\n{content}endstream',
    ]
    out = '%PDF-1.4\n'
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f'{n} 0 obj\n{body}\nendobj\n'
    table = len(out)
    out += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'
    out += ''.join(f'{o:010d} 00000 n \n' for o in offsets)
    out += f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{table}\n%%EOF\n'
    return out.encode('ascii')


if __name__ == '__main__':
    main()
