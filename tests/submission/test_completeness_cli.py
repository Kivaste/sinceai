"""Completeness through the real CLI (D37, D46): a complete bundle is the default; partial needs ``--partial``.

Rule (D46: CS-S1 is dropped; the CS eval exports still ship under D37): a complete bundle holds a verified
HEALTH-S1 release (tables, validated row maps, manifest) plus the root outputs: the unseen labels and the
independently gated CS eval CSV/spans. It neither needs nor accepts a CS-S1 release. ``submission_index.json``
records ``complete: true``, the D46 target datasets and, as a field, that CS-S1 is out of scope (deferred, D46).
Without ``--partial`` a missing part refuses (exit 1) and nothing that looks like a bundle is written.

Failure rows (trigger -> result):
  default build, HEALTH-S1 release only          -> exit 0 "SUBMISSION BUILT (COMPLETE)", index complete, CS-S1 out of scope
  --partial, HEALTH-S1 release (nothing missing)  -> exit 0 COMPLETE (the flag only permits missing parts)
  no release at all, no --partial                -> exit 1 "REFUSED: incomplete (missing datasets: health ...)", nothing written
  no release at all, --partial                   -> exit 1 "REFUSED: no_release", nothing written
  kit without the CS eval export                 -> exit 1 "REFUSED: cs_eval_unavailable", nothing written
  kit without the unseen export                  -> exit 1 "REFUSED: unseen_unavailable", nothing written
  a decoy bundle planted next to --out           -> output only at --out; the decoy is untouched
  a decoy bundle planted at --out                -> exit 1 out_exists; the decoy is untouched, nothing reported built
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from sub_helpers import submission

INDEX = "submission_index.json"  # the one root index the wizard reads (stage 5)
CS_FILES = ["customer_service_eval_redacted.csv", "customer_service_eval_spans.jsonl"]
OUT_OF_SCOPE = [{"scenario": "CS-S1", "dataset": "customer_service", "status": "deferred", "decision": "D46"}]


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _assert_complete(p, out: Path) -> None:
    assert p.returncode == 0, p.stdout + p.stderr
    built = [line for line in p.stdout.splitlines() if "SUBMISSION BUILT" in line]
    assert built and all("(COMPLETE)" in line for line in built) and "PARTIAL" not in p.stdout
    assert sorted(p.name for p in out.glob("*.json")) == [INDEX]  # exactly one root index
    idx = json.loads((out / INDEX).read_text("utf-8"))
    assert idx["complete"] is True
    assert idx["targetDatasets"] == ["health"] and idx["datasetsPresent"] == ["health"]
    assert idx["datasetsMissing"] == []
    assert idx["outOfScope"] == OUT_OF_SCOPE
    for f in [*CS_FILES, "unseen_field_labels.csv"]:
        assert f in idx["rootFiles"] and (out / f).is_file()
    assert (out / "health" / "privacy_manifest.json").is_file()
    assert list((out / "health").glob("rowmap_*.csv"))
    assert not (out / "customer_service").exists()


def test_default_build_with_only_a_health_release_is_complete_under_d46(world, tmp_path):
    kit, rel = world
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit))
    _assert_complete(p, out)


def test_partial_flag_with_nothing_missing_still_builds_complete(world, tmp_path):
    kit, rel = world
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    _assert_complete(p, out)


def test_no_release_without_partial_refuses_incomplete_and_writes_nothing(world, tmp_path):
    kit, _ = world
    parent = tmp_path / "x"
    p = submission("--out", str(parent / "pets_submission"), "--kit", str(kit))
    assert p.returncode == 1, p.stdout + p.stderr
    assert p.stdout.startswith("REFUSED: incomplete (missing datasets: health;"), p.stdout
    assert "SUBMISSION BUILT" not in p.stdout
    assert not parent.exists() or not list(parent.iterdir())  # no bundle, no scoring folder, no temp folder


def test_no_release_with_partial_refuses_and_writes_nothing(world, tmp_path):
    kit, _ = world
    parent = tmp_path / "x"
    p = submission("--out", str(parent / "pets_submission"), "--kit", str(kit), "--partial")
    assert (p.returncode, p.stdout.strip()) == (1, "REFUSED: no_release"), p.stdout + p.stderr
    assert not parent.exists() or not list(parent.iterdir())


def _kit_without(world, tmp_path, part: str) -> Path:
    kit, _ = world
    k = tmp_path / "kit"
    shutil.copytree(kit, k)
    shutil.rmtree(k / "data" / part)
    return k


def test_missing_cs_eval_export_refuses_and_writes_nothing(world, tmp_path):
    _, rel = world
    k = _kit_without(world, tmp_path, "customer_service")
    parent = tmp_path / "x"
    p = submission("--out", str(parent / "pets_submission"), "--release", str(rel), "--kit", str(k))
    assert (p.returncode, p.stdout.strip()) == (1, "REFUSED: cs_eval_unavailable"), p.stdout + p.stderr
    assert not parent.exists() or not list(parent.iterdir())


def test_missing_unseen_export_refuses_and_writes_nothing(world, tmp_path):
    _, rel = world
    k = _kit_without(world, tmp_path, "unseen")
    parent = tmp_path / "x"
    p = submission("--out", str(parent / "pets_submission"), "--release", str(rel), "--kit", str(k))
    assert (p.returncode, p.stdout.strip()) == (1, "REFUSED: unseen_unavailable"), p.stdout + p.stderr
    assert not parent.exists() or not list(parent.iterdir())


def test_output_goes_to_the_out_argument_not_to_a_planted_decoy(world, tmp_path):
    kit, rel = world
    decoy = tmp_path / "pets_submission"
    decoy.mkdir()
    (decoy / INDEX).write_text(json.dumps({"complete": True}), encoding="utf-8")
    before = _tree(decoy)
    out = tmp_path / "chosen" / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit))
    assert p.returncode == 0, p.stdout + p.stderr
    assert (out / INDEX).is_file() and _tree(decoy) == before


def test_a_decoy_planted_at_out_refuses_and_is_left_alone(world, tmp_path):
    kit, rel = world
    out = tmp_path / "pets_submission"
    out.mkdir()
    (out / INDEX).write_text(json.dumps({"complete": True}), encoding="utf-8")
    before = _tree(out)
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit))
    assert p.returncode == 1 and "out_exists" in p.stdout and "SUBMISSION BUILT" not in p.stdout
    assert _tree(out) == before
