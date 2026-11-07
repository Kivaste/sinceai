"""``python -m pets_release.manifest validate <manifest.json | release_dir>``

Exit 0: VALID. Exit 1: INVALID (error codes printed, never values). Exit 2: usage error or unreadable path.
"""

from __future__ import annotations

import sys

from pets_release.manifest.validate import validate_manifest_file

USAGE = "usage: python -m pets_release.manifest validate <manifest.json | release_dir>"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "validate":
        print(USAGE, file=sys.stderr)
        return 2
    try:
        errs = validate_manifest_file(args[1])
    except OSError:
        print("ERROR: manifest not readable", file=sys.stderr)
        return 2
    if errs:
        print(f"INVALID: {len(errs)} error(s)")
        for e in errs:
            print(f"  {e}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
