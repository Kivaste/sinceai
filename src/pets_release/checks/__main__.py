"""``python -m pets_release.checks --contract C.json [--phase gate|verify] [--scope release] RELEASE``

Prints the aggregate summary as canonical JSON (no values, no locations).
Exit 0 = every check passed, 1 = refusal, 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import sys

from pets_release.checks.runner import run_checks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pets_release.checks")
    ap.add_argument("release")
    ap.add_argument("--contract", required=True)
    ap.add_argument("--phase", choices=["gate", "verify"], default="verify")
    ap.add_argument("--scope", choices=["release", "producer"], default=None)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        with open(a.contract, encoding="utf-8") as fh:
            contract = json.load(fh)
    except (OSError, ValueError):
        print("contract unreadable", file=sys.stderr)
        return 2
    res = run_checks(a.release, contract, {"phase": a.phase}, scope=a.scope)
    print(json.dumps(res.summary(), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 1 if res.refused else 0


if __name__ == "__main__":
    sys.exit(main())
