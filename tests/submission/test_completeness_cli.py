"""Completeness through the real CLI (D37): a complete bundle is the default; partial needs ``--partial``.

Rule: a bundle holds both target scenarios' datasets (CS-S1 customer_service, HEALTH-S1 health) plus the root
outputs. Without ``--partial`` a missing dataset refuses (exit 1) and nothing that looks like a bundle is written.
With ``--partial`` the bundle is built, the CLI says PARTIAL on the built line and names the missing datasets, and
``bundle_index.json`` at the bundle root lists exactly what is present and what is missing.

Failure rows (trigger -> result):
  CS-S1 release omitted, no --partial         -> exit 1 "REFUSED: incomplete", no out, no scoring, no temp dir
  CS-S1 release omitted, --partial            -> exit 0, "SUBMISSION BUILT (PARTIAL)", index lists the missing part
  a decoy bundle planted next to --out        -> output only at --out; the decoy is untouched
  a decoy bundle planted at --out             -> exit 1 out_exists; the decoy is untouched, nothing reported built
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sub_helpers import submission

INDEX = "bundle_index.json"


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_omitted_cs_release_without_partial_refuses_and_writes_nothing(world, tmp_path):
    kit, rel = world
    parent = tmp_path / "x"
    p = submission("--out", str(parent / "pets_submission"), "--release", str(rel), "--kit", str(kit))
    assert p.returncode == 1, p.stdout + p.stderr
    assert "REFUSED: incomplete" in p.stdout and "customer_service" in p.stdout
    assert "SUBMISSION BUILT" not in p.stdout
    assert not parent.exists() or not list(parent.iterdir())  # no bundle, no scoring folder, no temp folder


def test_partial_flag_builds_a_bundle_that_says_partial_and_lists_the_missing_dataset(world, tmp_path):
    kit, rel = world
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 0, p.stdout + p.stderr
    built = [line for line in p.stdout.splitlines() if "SUBMISSION BUILT" in line]
    assert built and all("PARTIAL" in line for line in built)
    assert "missing datasets: customer_service" in p.stdout
    idx = json.loads((out / INDEX).read_text("utf-8"))
    assert idx["complete"] is False
    assert idx["datasetsMissing"] == ["customer_service"]
    assert idx["datasetsPresent"] == ["health"]
    assert idx["targetDatasets"] == ["customer_service", "health"]


def test_output_goes_to_the_out_argument_not_to_a_planted_decoy(world, tmp_path):
    kit, rel = world
    decoy = tmp_path / "pets_submission"
    decoy.mkdir()
    (decoy / INDEX).write_text(json.dumps({"complete": True}), encoding="utf-8")
    before = _tree(decoy)
    out = tmp_path / "chosen" / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 0, p.stdout + p.stderr
    assert (out / INDEX).is_file() and _tree(decoy) == before


def test_a_decoy_planted_at_out_refuses_and_is_left_alone(world, tmp_path):
    kit, rel = world
    out = tmp_path / "pets_submission"
    out.mkdir()
    (out / INDEX).write_text(json.dumps({"complete": True}), encoding="utf-8")
    before = _tree(out)
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 1 and "out_exists" in p.stdout and "SUBMISSION BUILT" not in p.stdout
    assert _tree(out) == before
