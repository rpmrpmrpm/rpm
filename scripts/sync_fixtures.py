"""Copies the sample libraries in fixtures/migration into the test projects that read them.

The import readers exist twice, in C# (rpm-desktop, RPM.Core) and in TypeScript (rpm-web), and both
are tested against the same samples. Each repo is built on its own, so each keeps its own copy:

    rpm-desktop/RPM.Core.Tests/Assets/Migration/
    rpm-web/test/fixtures/migration/

Run this after changing anything in fixtures/migration. A copy is replaced whole, so a file removed
here is removed there too. A repo that is not checked out is skipped.
"""
import os
import shutil
import sys

import workspace

SOURCE = os.path.join(workspace.ROOT, "fixtures", "migration")
TARGETS = [
    ("rpm-desktop", os.path.join("RPM.Core.Tests", "Assets", "Migration")),
    ("rpm-web", os.path.join("test", "fixtures", "migration")),
]


def main() -> int:
    if not os.path.isdir(SOURCE):
        print(f"missing: {SOURCE}", file=sys.stderr)
        return 1
    for repo, rel in TARGETS:
        home = os.path.join(workspace.PARENT, repo)
        if not os.path.isdir(home):
            print(f"skipped (not checked out): {repo}")
            continue
        target = os.path.join(home, rel)
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(SOURCE, target)
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
