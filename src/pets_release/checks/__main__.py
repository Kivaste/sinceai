"""``python -m pets_release.checks --contract C.json [--phase gate|verify] [--scope release] [--check NAME]... RELEASE``

Without ``--check`` every registered check runs (the gate); ``--check`` narrows to named checks
for diagnostics. A not_run, error or fail status refuses either way.

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
    ap.add_argument("--check", action="append", default=None, metavar="NAME",
                    help="run only this registered check (repeatable); default: every check")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    selected = None
    if a.check is not None:
        from pets_release.checks.registry import RegistryError, all_checks

        try:
            by_name = {c.name: c for c in all_checks()}
        except RegistryError:
            by_name = None
        if by_name is not None:
            unknown = sorted(set(a.check) - set(by_name))
            if unknown:
                print("unknown check: " + ", ".join(unknown), file=sys.stderr)
                return 2
            selected = [by_name[n] for n in sorted(set(a.check))]
        # registry broken: fall through with selected=None so run_checks refuses with registry_error
    try:
        with open(a.contract, encoding="utf-8") as fh:
            contract = json.load(fh)
    except (OSError, ValueError):
        print("contract unreadable", file=sys.stderr)
        return 2
    res = run_checks(a.release, contract, {"phase": a.phase}, scope=a.scope, checks=selected)
    print(json.dumps(res.summary(), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 1 if res.refused else 0


if __name__ == "__main__":
    sys.exit(main())
