# Cast receiver

The page a Chromecast loads when an rpm app casts to it. The rpm server serves this folder at
`https://rpmrpmrpm.com/cast/`, and the receiver application registered with Google points at
`receiver.html`.

The desktop, Android TV and iPhone apps talk to this page on rpm's own Cast namespace. The message
types and the protocol version must be the same on both ends, so each app has a test that reads
`receiver.html` from this repo. Check out `rpm` next to the app's repo to run them. A change to the
messages here needs the same change in all three apps.

- `rpm-mark.png` is the rpm logo (see `TRADEMARKS.md`).
- `vinyl-record.png` is drawn by `scripts/make_vinyl_table.py`.
- `fonts/Cabin-*.ttf`: Cabin, Copyright 2018 The Cabin Project Authors, under the SIL Open Font
  License 1.1 (`scripts/licenses/OFL-1.1.txt`).
