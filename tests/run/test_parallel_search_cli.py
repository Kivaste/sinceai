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
  r2: socket opened on a LATER candidate (w2, w1) -> refuses (start scored and taken), nothing published
  r2: ordinary exception in a worker, later cand. -> refuses (never a silently rejected candidate)
  r2: worker environment                          -> allow-list only: PETS_HMAC_KEY absent (names probed)
  r2: hung scorer, short result timeout           -> refuses, no release; no worker PID alive afterwards
  r2: results complete out of submission order    -> release byte-identical to the 1-worker run
These run a real minikit search each (15-60 s), so they are in the slow tier.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import sys
import time

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


def _planted_run(kit, out, monkeypatch, plant, workers="2", *pre):
    """In-process `pets-release run --workers N` with the search's purpose check wrapped by ``plant`` (pickled
    into the workers, with leading args ``pre``; the real check is the production kit check)."""
    from pets_release.minimiser import kit as mkit
    from pets_release.run import cli as run_cli
    from pets_release.run import pipeline

    real = pipeline.search_options

    def planted(*a, **k):
        opts = real(*a, **k)
        opts["purpose"] = functools.partial(plant, *pre, mkit.kit_purpose_check)
        return opts

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    monkeypatch.setattr(pipeline, "search_options", planted)
    return run_cli.main(_args(kit, out, "--workers", workers)[1:])


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


@pytest.mark.slow
@pytest.mark.parametrize(("plant", "workers"), [(plants.network_later, "2"), (plants.network_later, "1"),
                                                 (plants.raises_later, "2")],
                         ids=["network-later-w2", "network-later-w1", "raises-later-w2"])
def test_a_scoring_failure_on_a_later_candidate_refuses_the_run(kit, tmp_path, monkeypatch, capsys, plant, workers):
    """r2 (Sol Spec): a scoring exception in a worker, or an offline-guard violation at any worker count, on a
    later or speculative candidate is never a silently rejected candidate: the run refuses, nothing published."""
    out = tmp_path / "rel"
    rc = _planted_run(kit, out, monkeypatch, plant, workers)
    stdout = capsys.readouterr().out
    assert rc == 1, stdout
    assert "REFUSED" in stdout
    assert not out.exists()
    log = [json.loads(x) for x in (_scoring(out) / "search_log.jsonl").read_text(encoding="utf-8").splitlines() if x]
    assert log and log[0]["accepted"] is True  # the start was scored and taken: the failure came later


@pytest.mark.slow
def test_workers_start_without_key_material_in_their_environment(kit, tmp_path, monkeypatch, capsys):
    """r2 (Sol Standards): a worker's environment is the allow-list; PETS_HMAC_KEY (set for this run) is absent.
    The probe records variable NAMES only."""
    probe = tmp_path / "probe"
    probe.mkdir()
    out = tmp_path / "rel"
    rc = _planted_run(kit, out, monkeypatch, plants.env_probe, "2", str(probe))
    assert rc == 0, capsys.readouterr().out
    seen = [json.loads(p.read_text(encoding="utf-8"))["names"] for p in sorted(probe.glob("*.json"))]
    assert seen, "no worker scored a candidate"
    for names in seen:
        assert "PETS_HMAC_KEY" not in names
        assert not [n for n in names if "KEY" in n.upper() or "SECRET" in n.upper()]


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.mark.slow
def test_a_hung_worker_times_out_refuses_and_is_killed(kit, tmp_path, monkeypatch, capsys):
    """r2 (Sol Standards): a scorer that never returns hits the result timeout: the run refuses, nothing is
    published, and no worker process survives the refusal (checked by PID, bounded)."""
    from pets_release.minimiser import parallel

    monkeypatch.setattr(parallel, "RESULT_TIMEOUT_S", 5)
    pids = tmp_path / "pids"
    pids.mkdir()
    out = tmp_path / "rel"
    rc = _planted_run(kit, out, monkeypatch, plants.hangs, "2", str(pids))
    assert rc == 1, capsys.readouterr().out
    assert not out.exists()
    seen = [int(p.stem) for p in pids.glob("*.json")]
    assert seen, "the planted scorer never ran"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and any(_alive(p) for p in seen):
        time.sleep(0.5)
    assert not [p for p in seen if _alive(p)], "a hung search worker survived the refusal"


@pytest.mark.slow
def test_out_of_order_results_give_the_same_release(kit, tmp_path, monkeypatch, capsys):
    """r2 (Sol Standards): results that complete out of submission order (per-candidate worker delays) still give
    the byte-identical release of a 1-worker run."""
    base = tmp_path / "w1" / "rel"
    proc = cli(*_args(kit, base, "--workers", "1"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = tmp_path / "w4" / "rel"
    rc = _planted_run(kit, out, monkeypatch, plants.jitter, "4")
    assert rc == 0, capsys.readouterr().out
    assert (_tree(out), _tree(_scoring(out))) == (_tree(base), _tree(_scoring(base)))
