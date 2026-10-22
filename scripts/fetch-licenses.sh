#!/usr/bin/env bash
#
# Downloads the licence texts the About screen shows, verbatim, into scripts/licenses/.
#
# They are committed, because they ship inside the app: scripts/gen_credits.py copies them into
# RPM.Desktop/Assets/Licenses, into RPMKit's resources and into the Android phone app's assets. This
# script exists so that no licence is typed by hand: a licence that is nearly right is not the licence.
#
# Three sources, in order of preference:
#
#   1. The SPDX licence list at one pinned tag, so a second run produces the same bytes.
#   2. The project, for a licence SPDX does not carry (HarfBuzz).
#   3. A NuGet package, for an aggregate notices file that exists only in the package and not in
#      the project's repository. These are read at the version that Directory.Packages.props pins,
#      so after a package version is raised, running this script again picks up its new notices.
#
#   scripts/fetch-licenses.sh
#
set -euo pipefail

SPDX_TAG="v3.27.0"
HARFBUZZ_TAG="11.2.1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/scripts/licenses"

# SPDX identifiers. Each one is the name of the file written, and the name that credits.json uses
# in its "license" field.
declare -a SPDX=(
  MIT
  Apache-2.0
  BSD-3-Clause
  MS-PL
  LGPL-2.0-only
  LGPL-2.0-or-later
  LGPL-2.1-only
  LGPL-2.1-or-later
  Zlib
  OFL-1.1
  FTL
  IJG
  Unicode-3.0
  CC-BY-SA-4.0
  CC0-1.0
  blessing
  MPL-2.0
)

# The version that Directory.Packages.props pins for a package, so a notices file always matches
# the binary it describes.
pinned() {
  local package="$1"
  local version
  version="$(sed -n "s/.*Include=\"${package//./\\.}\" *Version=\"\([^\"]*\)\".*/\1/p" \
    "$ROOT/Directory.Packages.props" | head -n 1)"
  if [ -z "$version" ]; then
    echo "fetch-licenses: $package is not in Directory.Packages.props" >&2
    exit 1
  fi
  echo "$version"
}

# Extracts one file from a NuGet package, which is a zip. Used for notices files that are written
# into the package at build time and are in no repository.
from_nupkg() {
  local package="$1" version="$2" inside="$3" out="$4"
  local lower
  lower="$(printf '%s' "$package" | tr '[:upper:]' '[:lower:]')"
  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL \
    "https://api.nuget.org/v3-flatcontainer/${lower}/${version}/${lower}.${version}.nupkg" \
    -o "$tmp/package.zip"
  unzip -p "$tmp/package.zip" "$inside" > "$DEST/$out"
  rm -rf "$tmp"
  if [ ! -s "$DEST/$out" ]; then
    echo "fetch-licenses: $inside is not in $package $version" >&2
    exit 1
  fi
}

mkdir -p "$DEST"

for id in "${SPDX[@]}"; do
  echo "fetching $id..."
  curl -fsSL "https://raw.githubusercontent.com/spdx/license-list-data/${SPDX_TAG}/text/${id}.txt" \
    -o "$DEST/$id.txt"
done

echo "fetching HarfBuzz..."
curl -fsSL "https://raw.githubusercontent.com/harfbuzz/harfbuzz/${HARFBUZZ_TAG}/COPYING" \
  -o "$DEST/HarfBuzz.txt"

# Notices for everything statically linked into libSkiaSharp and libHarfBuzzSharp: FreeType,
# libjpeg-turbo, libpng, libwebp, expat, ICU, zlib, ANGLE and the rest. This file exists only in the
# native-asset packages, and the licences inside it require it to travel with the binary. The macOS
# and Windows packages carry the same bytes, so the macOS one is read.
SKIA_VERSION="$(pinned SkiaSharp)"
echo "fetching Skia third-party notices ($SKIA_VERSION)..."
from_nupkg "SkiaSharp.NativeAssets.macOS" "$SKIA_VERSION" \
  "THIRD-PARTY-NOTICES.txt" "SkiaSharp-THIRD-PARTY-NOTICES.txt"

# The same for onnxruntime: notices for everything inside it, from Eigen to protobuf to the CPU
# kernels. The repository has it as ThirdPartyNotices.txt, but it is read from the package so that
# the notices and the binary come from one build.
ONNX_VERSION="$(pinned Microsoft.ML.OnnxRuntime)"
echo "fetching ONNX Runtime third-party notices ($ONNX_VERSION)..."
from_nupkg "Microsoft.ML.OnnxRuntime" "$ONNX_VERSION" \
  "ThirdPartyNotices.txt" "OnnxRuntime-THIRD-PARTY-NOTICES.txt"

echo
echo "Wrote $(ls -1 "$DEST" | wc -l | tr -d ' ') files to $DEST"
echo "Run scripts/gen_credits.py to copy them into both heads."
