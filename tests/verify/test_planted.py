"""Verify reads no pass file and reuses no prior result.

Rule: the verdict depends only on the release files, the manifest and (under --full) the kit and key.
Planted rows (trigger -> result):
  forged pass files next to / around a failing release   -> still exit 1
  manifest gate records all "pass" on a failing release  -> still exit 1 (covered in test_recipient)
  verify run twice, release broken in between            -> second run exits 1
  file opens during a real CLI verify                    -> only release files (and the package) are opened
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PASS_NAMES = ("verify_pass.json", "gate_pass.json", ".verified", "VERIFIED", "gate.json", "checks.json")


def _forge(dirpath: Path):
    dirpath.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"refused": False, "status": "pass", "verified": True}).encode()
    for n in PASS_NAMES:
        (dirpath / n).write_bytes(body)


def _break(bed: Path):
    (bed / "ed_visits.csv").write_bytes((bed / "ed_visits.csv").read_bytes() + b"\n")


def test_forged_pass_files_do_not_rescue_failing_release(bed, verify_cli, tmp_path):
    _break(bed)
    _forge(bed.parent)
    _forge(Path(str(bed) + ".scoring"))
    _forge(Path(str(bed) + ".verify"))
    r = verify_cli(bed)
    assert r.returncode == 1


def test_forged_pass_file_inside_release_fails(bed, verify_cli):
    _forge(bed)
    assert verify_cli(bed).returncode == 1


def test_no_prior_result_reused(bed, verify_cli):
    assert verify_cli(bed).returncode == 0
    _break(bed)
    assert verify_cli(bed).returncode == 1


HOOK = r"""
import sys, os
root = os.path.normcase(os.path.realpath(sys.argv[1]))
log = []
def hook(ev, args):
    if ev == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.path.normcase(os.path.realpath(os.fsdecode(args[0])))
        if p.startswith(root):
            log.append(p)
sys.addaudithook(hook)
from pets_release.cli import main
code = main(["verify", *sys.argv[2:]])
sys.stdout.flush()
print("OPENED:" + "|".join(sorted(set(log))))
sys.exit(code)
"""


def test_only_release_files_are_opened(bed, tmp_path):
    _forge(bed.parent)
    _forge(Path(str(bed) + ".scoring"))
    root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in __import__("os").environ.items()
           if k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "VIRTUAL_ENV")}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC", PYTHONPATH=str(root / "src"))
    r = subprocess.run([sys.executable, "-c", HOOK, str(tmp_path), str(bed)], cwd=root, env=env,
                       capture_output=True, text=True, encoding="utf-8", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    opened = [Path(p) for p in r.stdout.split("OPENED:", 1)[1].strip().split("|") if p]
    allowed = {Path(__import__("os").path.normcase(__import__("os").path.realpath(bed / n)))
               for n in ("ed_visits.csv", "lab_results.csv", "privacy_manifest.json")}
    assert opened, "audit hook saw no opens: the test would pass vacuously"
    assert set(opened) <= allowed, sorted(str(p) for p in set(opened) - allowed)
