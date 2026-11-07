"""Parallel candidate scoring in the search (#127, D44), through `pets-release run --workers N`.

Rule: `--workers N` (default 1) scores search candidates in a spawn-context process pool. The release does not
depend on N: every artefact is byte-identical at every worker count, so the worker count is recorded nowhere.
The offline guard is active in every worker, and any failed worker makes the run refuse (no release, never a
plan picked from partial results).

Rows (trigger -> result):
  run (search) at --workers 1, 2 and 4          -> exit 0 each; release folder and scoring folder byte-identical
                                                   (file names and sha256), so no artefact carries the count
  --workers 0 / -1 / x                           -> exit 2, no output folders
  planted socket open inside a worker's scoring  -> the offline guard blocks it: the run refuses, no release
  planted worker task that raises                -> exit 1, REFUSED, no release folder, refusal report written
  planted worker killed mid-run (os._exit)       -> exit 1, REFUSED, no release folder, refusal report written
"""
from __future__ import annotations

import functools
import hashlib
import json

import parallel_plants as plants
import pytest
from run_helpers import CREATED, TEST_KEY, build_kit, cli, grouped_qis


def _args(kit, out, *extra):
    return ["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED, *extra]


def _scoring(out):
    return out.parent / (out.name + ".scoring")


def _tree(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def kit(tmp_path_factory):
    return build_kit(tmp_path_factory.mktemp("par") / "kit", grouped_qis)


@pytest.mark.slow
def test_release_is_byte_identical_at_every_worker_count(kit, tmp_path):
    trees = {}
    for n in (1, 2, 4):
        out = tmp_path / f"w{n}" / "rel"
        proc = cli(*_args(kit, out, "--workers", str(n)))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        trees[n] = (_tree(out), _tree(_scoring(out)))
    log = (tmp_path / "w1" / "rel.scoring" / "search_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([x for x in log if json.loads(x)["step"] != "final"]) > 2  # the pool scored several candidates
    assert trees[1] == trees[2] == trees[4]
    assert trees[1][0] and "search_log.jsonl" in trees[1][1]


@pytest.mark.parametrize("bad", ["0", "-1", "x"])
def test_bad_worker_count_is_a_usage_error(kit, tmp_path, bad):
    out = tmp_path / "rel"
    proc = cli(*_args(kit, out, "--workers", bad))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert not out.exists() and not _scoring(out).exists()


def _planted_run(kit, out, monkeypatch, plant):
    """In-process `pets-release run --workers 2` with the search's purpose check wrapped by ``plant`` (pickled
    into the workers; the real check is the production kit check)."""
    from pets_release.minimiser import kit as mkit
    from pets_release.run import cli as run_cli
    from pets_release.run import pipeline

    real = pipeline.search_options

    def planted(*a, **k):
        opts = real(*a, **k)
        opts["purpose"] = functools.partial(plant, mkit.kit_purpose_check)
        return opts

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    monkeypatch.setattr(pipeline, "search_options", planted)
    return run_cli.main(_args(kit, out, "--workers", "2")[1:])


@pytest.mark.slow
@pytest.mark.parametrize("plant", [plants.network, plants.raises, plants.killed], ids=["network", "raises", "killed"])
def test_a_failed_or_offline_violating_worker_refuses_the_run(kit, tmp_path, monkeypatch, capsys, plant):
    out = tmp_path / "rel"
    rc = _planted_run(kit, out, monkeypatch, plant)
    stdout = capsys.readouterr().out
    assert rc == 1, stdout
    assert "REFUSED" in stdout
    assert not out.exists()
    rep = json.loads((_scoring(out) / "refusal_report.json").read_text(encoding="utf-8"))
    assert rep["status"] == "refused"
    assert not any(p.name.startswith("privacy_manifest") for p in _scoring(out).iterdir())
