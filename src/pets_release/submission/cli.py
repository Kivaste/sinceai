"""``pets-release submission --out <dir> --release <dir> [--release <dir> ...] [--kit PATH]``.

Exit 0 built, 1 refused (content-free reason code), 2 usage error or unknown state (no key, kit or release).
Prints the file list with SHA-256 digests and aggregate scorecard numbers only.
"""
from __future__ import annotations

import argparse
import os
import sys

from pets_release.kit import Kit, KitError
from pets_release.pseudonym import KeyConfigError, MasterKey
from pets_release.submission.build import build_submission
from pets_release.submission.errors import SubmissionRefused


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def main(argv: list[str]) -> int:
    p = _Parser(prog="pets-release submission",
                description="Build pets_submission/ outside the public repo from verified releases.")
    p.add_argument("--out", required=True)
    p.add_argument("--release", action="append", default=[], help="a release folder (repeat per dataset)")
    p.add_argument("--kit", help="kit path (default: PETS_KIT)")
    a = p.parse_args(argv)
    kit_path = a.kit or os.environ.get("PETS_KIT")
    if not kit_path:
        print("pets-release submission: no kit path: pass --kit or set PETS_KIT", file=sys.stderr)
        return 2
    if not a.release:
        print("pets-release submission: pass at least one --release", file=sys.stderr)
        return 2
    try:
        master = MasterKey.from_env()
        kit = Kit(kit_path)
    except (KeyConfigError, KitError) as e:
        print(f"pets-release submission: {e}", file=sys.stderr)
        return 2
    try:
        res = build_submission(kit=kit, releases=a.release, out=a.out, master=master)
    except SubmissionRefused as e:
        print(f"REFUSED: {e.code}")
        return 1
    print(f"SUBMISSION BUILT: {res.out.name} (scoring: {res.scoring.name})")
    for rel, digest in res.files.items():
        print(f"  {digest}  {rel}")
    for d in res.datasets:
        s = d["scorecard"]
        print(f"scorecard {d['dataset']} ({d['scenario']}): privacy={s['privacy']} utility={s['utility']} "
              f"composite={s['composite']} tasks={len(s['tasks'])} tables={len(s['tables'])}")
    cs = res.index["customerServiceEval"]
    print(f"cs-eval: conversations={cs['conversations']} turns={cs['turns']} spans={cs['spans']}; "
          f"unseen columns={res.index['unseen']['columns']}")
    return 0
