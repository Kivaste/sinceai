"""Measure wiring with a search plan (ticket 25 x ticket 22's ``measure/wire.py``), production run on the minikit.

Rule: the measured release keeps the search's own ``measured.search`` (built from its log); the measurer fills
the other ``measured`` keys. Only the measurer's scoring is stubbed (it needs the kit). Rows:
  run_measured, plan_name None (search)  -> manifest measured.search measured, from the search log; utility from
                                            the measurer
  run_measured, plan_name "hand"          -> measured.search stays the measurer's (no search ran)
  entry point (wire.main), no --plan      -> search: search log, justifications from the search, measured.search
  entry point, --plan hand                -> hand plan: no search log, neither holds
  entry point, --recipient                -> the manifest records that recipient
  entry point, search refuses             -> exit 1 (not 2), REFUSED with our reason, nothing published
  `python -m pets_release.measure.wire`   -> pass 1 runs the search without --plan, the hand plan with it
"""
from __future__ import annotations

import json

import pytest
from run_helpers import CREATED, TEST_KEY, build_kit, grouped_qis, run_args

from pets_release.measure import wire
from pets_release.verify import current_tool_revision

BLOCK = {k: {"status": "not_measured", "reason": "stub"} for k in ("utility", "privacy", "baselines", "search", "redaction")}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=grouped_qis)
    monkeypatch.setattr(wire, "measure", lambda *a, **k: json.loads(json.dumps(BLOCK)))
    monkeypatch.setattr(wire, "person_k_components", lambda *a, **k: [])
    monkeypatch.setattr(wire, "_person_k_from_release", lambda **k: None)
    return kit, tmp_path / "rel"


def _run(kit, out, plan_name):
    from pets_release.cli import resolve_run_context

    ctx = resolve_run_context(run_args(kit, out)[1:])
    return wire.run_measured(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key, out=out,
                             plan_name=plan_name, tool_revision=current_tool_revision())


def test_search_keeps_its_measured_search(setup):
    kit, out = setup
    res = _run(kit, out, None)
    assert res.status == "released"
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    s = m["measured"]["search"]
    log = [json.loads(x) for x in (out.parent / "rel.scoring" / "search_log.jsonl").read_text(
        encoding="utf-8").splitlines() if x]
    assert s["status"] == "measured" and s["candidates"] == len([e for e in log if e["step"] != "final"]) >= 1
    assert m["measured"]["utility"] == BLOCK["utility"]
    assert {f["source"] for f in m["fieldJustifications"]} == {"search"}


def _main_args(kit, out, *extra):
    return ["--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED, *extra]


def _scoring(out):
    return out.parent / (out.name + ".scoring")


def test_entry_point_without_plan_runs_the_search(setup):
    """`python -m pets_release.measure.wire` with no --plan defaults to the search, like `pets-release run`."""
    kit, out = setup
    assert wire.main(_main_args(kit, out)) == 0
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert (_scoring(out) / "search_log.jsonl").is_file()
    assert {f["source"] for f in m["fieldJustifications"]} == {"search"}
    assert m["measured"]["search"]["status"] == "measured"


def test_entry_point_explicit_hand_plan_runs_the_hand_plan(setup):
    kit, out = setup
    assert wire.main(_main_args(kit, out, "--plan", "hand")) == 0
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert not (_scoring(out) / "search_log.jsonl").exists()
    assert "search" not in {f["source"] for f in m["fieldJustifications"]}
    assert m["measured"]["search"] == BLOCK["search"]


def test_entry_point_forwards_the_recipient(setup):
    """--recipient reaches both run_release passes (as `pets-release run` does; same change as #94)."""
    kit, out = setup
    assert wire.main(_main_args(kit, out, "--recipient", "recipient-a")) == 0
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert m["release"]["recipient"] == "recipient-a"


def test_entry_point_search_refusal_exits_1_and_publishes_nothing(tmp_path, monkeypatch, capsys):
    """A refusal (RunRefused) is exit 1, not 2; stdout says REFUSED with our own content-free reason only."""
    import pandas as pd

    def drop_crp(folder):  # no lab test the H-U7 check reads: the search finds no acceptable plan
        grouped_qis(folder)
        p = folder / "lab_results.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df["test_code"] = "ZZZ"
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=drop_crp)
    out = tmp_path / "rel"
    assert wire.main(_main_args(kit, out)) == 1
    assert "REFUSED: search found no acceptable plan" in capsys.readouterr().out
    assert not out.exists() and not _scoring(out).exists()


def test_entry_point_subprocess_forwards_no_plan_as_the_search(tmp_path):
    """The real `python -m pets_release.measure.wire` process: the default plan reaches run_release as None
    (search). Its measurer needs the challenge kit, so on the minikit it stops after pass 1 with exit 2; pass 1
    is the search (its scratch scoring folder holds the search log), and nothing is published at --out."""
    import subprocess
    import sys

    from run_helpers import ROOT, env

    kit = build_kit(tmp_path / "kit", edit=grouped_qis)
    out = tmp_path / "rel"
    for extra, logged in (((), True), (("--plan", "hand"), False)):
        o = out.with_name(out.name + ("-hand" if extra else "-search"))
        p = subprocess.run([sys.executable, "-m", "pets_release.measure.wire", *_main_args(kit, o, *extra)],
                           cwd=ROOT, env=env(), capture_output=True, text=True, encoding="utf-8", check=False)
        assert p.returncode in (0, 2), p.stdout + p.stderr
        assert not (o / "privacy_manifest.json").exists() or p.returncode == 0
        scratch = o.with_name(o.name + ".measure") / "pass1.scoring"
        assert (scratch / "search_log.jsonl").is_file() is logged, p.stdout + p.stderr


def test_hand_plan_keeps_the_measurer_search_block(setup):
    kit, out = setup
    res = _run(kit, out, "hand")
    assert res.status == "released"
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert m["measured"]["search"] == BLOCK["search"]
