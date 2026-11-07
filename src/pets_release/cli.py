"""pets-release command-line dispatcher.

Each subcommand lives in its own package and exposes `main(argv: list[str]) -> int` in `<package>.cli`.
A missing package means "not implemented" and exits 2. A `run` implementation calls `resolve_run_context`
to get the validated kit, scenario, creation time and key.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from pets_release.kit import Kit, KitError
from pets_release.offline import entry_point

COMMAND_PACKAGES: dict[str, str] = {
    "run": "pets_release.run",
    "verify": "pets_release.verify",
    "detect": "pets_release.detect",
    "dashboard": "pets_release.dashboard",
    "submission": "pets_release.submission",
}
HELP = {
    "run": "produce a protected release for a scenario",
    "verify": "re-run checks on a release folder",
    "detect": "detect personal-data types in a dataset",
    "dashboard": "render the judge dashboard",
    "submission": "build the submission bundle",
}
MIN_KEY_LEN = 32


class UsageError(Exception):
    """Exit-2 error."""


@dataclass(frozen=True)
class RunContext:
    kit: Kit
    scenario: dict
    created: str
    key: str
    args: argparse.Namespace


def _install_guard() -> None:
    from pets_release.offline import install

    install()


def _normalise_created(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise UsageError(f"--created is not an ISO UTC timestamp: {value!r}") from e
    if dt.tzinfo is None:
        raise UsageError("--created must carry a UTC offset (e.g. 2026-11-07T00:00:00Z)")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _created(arg: str | None) -> str:
    if arg:
        return _normalise_created(arg)
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde:
        try:
            return datetime.fromtimestamp(int(sde), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OverflowError, OSError) as e:
            raise UsageError("SOURCE_DATE_EPOCH is not an integer timestamp") from e
    raise UsageError("no creation time: pass --created or set SOURCE_DATE_EPOCH")


def run_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pets-release run", description=HELP["run"])
    p.add_argument("--scenario", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--created")
    p.add_argument("--kit")
    p.add_argument("--recipient")
    p.add_argument("--plan")
    p.add_argument("--sample", type=int)
    p.add_argument("--workers", type=_workers, default=None,
                   help=f"search scoring processes (default ${WORKERS_ENV} or 1); never recorded in the release")
    return p


WORKERS_ENV = "PETS_WORKERS"


def _workers(value: str) -> int:
    """A positive worker count (#127, D44); the release is identical at every count."""
    try:
        n = int(value, 10)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("--workers must be a positive integer") from None
    if n < 1:
        raise argparse.ArgumentTypeError("--workers must be a positive integer")
    return n


def resolve_run_context(argv: list[str]) -> RunContext:
    args = run_parser().parse_args(argv)
    if args.workers is None:  # the web app sets the count through the environment
        env = os.environ.get(WORKERS_ENV)
        try:
            args.workers = _workers(env) if env else 1
        except argparse.ArgumentTypeError:
            raise UsageError(f"{WORKERS_ENV} must be a positive integer") from None
    created = _created(args.created)
    key = os.environ.get("PETS_HMAC_KEY", "")
    if len(key) < MIN_KEY_LEN:
        raise UsageError(f"PETS_HMAC_KEY must be set and at least {MIN_KEY_LEN} characters")
    kit_path = args.kit or os.environ.get("PETS_KIT")
    if not kit_path:
        raise UsageError("no kit path: pass --kit or set PETS_KIT")
    try:
        kit = Kit(kit_path)
        scenario = kit.scenario(args.scenario)
    except KitError as e:
        raise UsageError(str(e)) from e
    return RunContext(kit, scenario, created, key, args)


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse default already exits 2; keep explicit
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def _kit_info(argv: list[str]) -> int:
    p = _Parser(prog="pets-release kit-info", description="print table names, row counts and input digests")
    p.add_argument("--dataset", required=True)
    p.add_argument("--kit")
    a = p.parse_args(argv)
    kit_path = a.kit or os.environ.get("PETS_KIT")
    if not kit_path:
        raise UsageError("no kit path: pass --kit or set PETS_KIT")
    try:
        kit = Kit(kit_path)
        digests = kit.input_digests(a.dataset)
        for name, df in kit.load_dataset(a.dataset).items():
            print(f"{a.dataset}/{name}\trows={len(df)}\tcols={len(df.columns)}\tsha256={digests[name]}")
    except KitError as e:
        raise UsageError(str(e)) from e
    return 0


@entry_point
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    top = _Parser(prog="pets-release", description="Purpose-first PETs release tool.")
    sub = top.add_subparsers(dest="command", metavar="COMMAND")
    for name, text in HELP.items():
        sub.add_parser(name, help=text, add_help=False)
    sub.add_parser("kit-info", help="print table names, row counts and input digests", add_help=False)
    if not argv:
        top.print_help(sys.stderr)
        return 2
    if argv[0] in ('-h', '--help'):
        top.print_help()
        return 0
    command, rest = argv[0], argv[1:]
    if command not in COMMAND_PACKAGES and command != "kit-info":
        top.error(f"unknown command {command!r}")
    _install_guard()
    try:
        if command == "kit-info":
            return _kit_info(rest)
        if command == "run":
            if "-h" in rest or "--help" in rest:
                run_parser().parse_args(rest)
            resolve_run_context(rest)
        pkg = COMMAND_PACKAGES[command]
        try:
            module = importlib.import_module(f"{pkg}.cli")
        except ModuleNotFoundError as e:
            if e.name not in (pkg, f"{pkg}.cli") and not pkg.startswith(str(e.name)):
                raise
            print(f"pets-release {command}: not implemented", file=sys.stderr)
            return 2
        code = module.main(rest)
        if type(code) is not int:
            print(f"pets-release {command}: handler returned {type(code).__name__}, not an int", file=sys.stderr)
            return 2
        return code
    except UsageError as e:
        print(f"pets-release {command}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
