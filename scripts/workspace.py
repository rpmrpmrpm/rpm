"""Where the rpm folders are when the repos are checked out side by side.

The generators here read and write files in several apps: gen_locales.py, for example, writes the
string files of the desktop, iOS and Android apps. They expect the repos as siblings:

    rpm/            this repo: shared data and the generators
    rpm-desktop/    RPM.Desktop, RPM.Core, RPM.Fingerprint, scripts/tool-versions.txt, ...
    rpm-apple/      RPM.iOS, RPM.tvOS
    rpm-android/    RPM.Android
    rpm-server/     rpm.Api (the credits page), private; skipped when it is not checked out

Set RPM_WORKSPACE to use another parent folder. A repo that is not checked out is skipped, and a
generator that needs it stops with the path it could not find.
"""
import os
import pathlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.environ.get("RPM_WORKSPACE") or os.path.dirname(ROOT)
REPOS = ["rpm", "rpm-desktop", "rpm-apple", "rpm-android", "rpm-server"]


def path(*parts: str) -> str:
    """The full path of a file or folder named as in one tree, for example
    path("RPM.Desktop", "Strings") or path("scripts", "tool-versions.txt").

    The first repo that has the whole path wins. For a file that does not exist yet (an output),
    the first repo that has the top folder wins, so "RPM.iOS/..." lands in rpm-apple.
    """
    rel = os.path.join(*parts)
    top = rel.split(os.sep)[0]
    homes = [os.path.join(PARENT, r) for r in REPOS]
    for home in homes:
        if os.path.exists(os.path.join(home, rel)):
            return os.path.join(home, rel)
    for home in homes:
        if os.path.isdir(os.path.join(home, top)):
            return os.path.join(home, rel)
    return os.path.join(ROOT, rel)


def at(rel: str) -> pathlib.Path:
    """`path` for code that uses pathlib."""
    return pathlib.Path(path(*rel.split("/")))
