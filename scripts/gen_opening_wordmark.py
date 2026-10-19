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


if __name__ == '__main__':
    main()
