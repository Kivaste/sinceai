"""``pets-release verify [--full --kit <path>] <release_dir>``. Exit 0 verified, 1 failed, 2 usage/unknown."""
from __future__ import annotations

import argparse
import os
import sys

from pets_release.verify.core import VerifyUsageError, verify_release


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def parser() -> argparse.ArgumentParser:
    p = _Parser(prog="pets-release verify",
                description="Re-run the release checks. Recipient mode reports limited verification only; "
                            "--full (kit + PETS_HMAC_KEY) re-runs every check plus signature, input digests "
                            "and tool revision.")
    p.add_argument("release_dir")
    p.add_argument("--full", action="store_true", help="controller/auditor mode (needs kit and key)")
    p.add_argument("--kit", help="kit path (default: PETS_KIT); --full only")
    return p


def _producer_context(kit, master, release_dir) -> dict | None:
    """Ticket 21 wiring: the run's own producer context, rebuilt from kit + key + release (never a file).

    Any failure gives None: producer checks then return not_run, which fails ``--full`` (fail closed).
    """
    try:
        from pets_release.kit import Kit
        from pets_release.run.context import verify_context

        return verify_context(Kit(kit), master, release_dir)
    except Exception:  # noqa: BLE001 - content-free; unknown state fails through not_run
        return None


def main(argv: list[str]) -> int:
    a = parser().parse_args(argv)
    try:
        master = None
        kit = None
        if not a.full:
            if a.kit:
                raise VerifyUsageError("--kit is only used with --full")
        else:
            from pets_release.pseudonym import KeyConfigError, MasterKey

            kit = a.kit or os.environ.get("PETS_KIT")
            if not kit:
                raise VerifyUsageError("--full needs the kit: pass --kit or set PETS_KIT")
            try:
                master = MasterKey.from_env()
            except KeyConfigError as e:
                raise VerifyUsageError(str(e)) from None
        context = _producer_context(kit, master, a.release_dir) if a.full else None
        report = verify_release(a.release_dir, full=a.full, kit=kit, master_key=master, context=context)
    except VerifyUsageError as e:
        print(f"pets-release verify: {e}", file=sys.stderr)
        return 2
    for line in report.lines:
        print(line)
    return report.exit_code
