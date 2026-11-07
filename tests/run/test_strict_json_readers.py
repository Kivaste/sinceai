"""Must-fix #131 (incomplete fix of #114): every external JSON record the release, measure and attacker paths read
parses through the one strict loader (``manifest.loads_strict``): a duplicate key or NaN/Infinity refuses, never
last-wins.

Rows (trigger -> result), all through a production CLI with hand-made synthetic data:
  [measure CLI, real pets-eval child] child scorecard with a duplicate top-level "summary", first value NaN
      -> exit 2 ScorecardRejected, nothing released (was: last value kept, released)
  [same] duplicate "risks" inside a table, first value NaN                          -> exit 2 ScorecardRejected
  [measure CLI] kit attack_specs.json with a duplicate "trajectories" key           -> exit 2 ScorecardRejected
  [measure CLI] kit results/benchmark.json with a duplicate "baselines" key          -> exit 2 MeasureRejected
  [measure CLI] gold-span JSONL handed to the child (it reads it raw) with a duplicate "spans", first NaN
      -> exit 2 ScorecardRejected before the child runs, nothing released (control: strict spans release)
  [run CLI] kit scenarios.json entry with a duplicate key                            -> exit 2, nothing released
  [attacker CLI] kit attack_specs.json with a duplicate "attacks" key                -> refused, no output
Guard (defect class found twice, AGENTS.md): no ``json.load``/``json.loads`` call in ``src/`` outside the strict
loader itself and a short, reasoned allowlist; a new raw reader fails this test.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest
from run_helpers import ROOT, SCENARIOS, TEST_KEY, build_kit, cli, coarse_qis, run_args
from test_wire_scorecard_k import CATALOG, _bench

from pets_attacker.cli import main as attacker_main
from pets_release.measure import wire
from tests.pets_attacker.test_cli import _mini_kit, _rungs_file


@pytest.fixture
def measured_kit(tmp_path, monkeypatch):
    """The run minikit plus what the real measurer needs (hand-made catalog, invented baselines), as in #110's test."""
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=coarse_qis)
    (kit / "metadata" / "field_catalog.csv").write_text(CATALOG, encoding="utf-8")
    (kit / "results").mkdir()
    (kit / "results" / "benchmark.json").write_text(json.dumps(_bench()), encoding="utf-8")
    return kit, tmp_path / "rel"


def _rewrite_after_text(monkeypatch, to_text):
    """Run the real pets-eval child; then replace the release pass's report with ``to_text(report)``."""
    real = subprocess.run

    def run(cmd, *a, **k):
        proc = real(cmd, *a, **k)
        if isinstance(cmd, list) and "--protected" in cmd and Path(cmd[cmd.index("--protected") + 1]).name == "pass1":
            out = Path(cmd[cmd.index("--out") + 1]) / "scorecard.json"
            out.write_text(to_text(json.loads(out.read_text(encoding="utf-8"))), encoding="utf-8")
        return proc

    monkeypatch.setattr(subprocess, "run", run)


def _dup_summary_nan_first(report):
    return '{"summary": {"privacy": NaN}, ' + json.dumps(report)[1:]


def _dup_risks_nan_first(report):
    tr = report["tables"]["ed_visits"]
    planted = '{"risks": {"records with k<5": NaN}, ' + json.dumps(tr)[1:]
    return json.dumps({**report, "tables": {**report["tables"], "ed_visits": "@@ED@@"}}).replace('"@@ED@@"', planted)


@pytest.mark.parametrize("to_text", [_dup_summary_nan_first, _dup_risks_nan_first], ids=["dup_summary", "dup_risks"])
def test_duplicate_key_child_scorecard_is_refused_by_the_measure_cli(measured_kit, monkeypatch, capsys, to_text):
    kit, out = measured_kit
    _rewrite_after_text(monkeypatch, to_text)
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert "ScorecardRejected" in capsys.readouterr().err
    assert not out.exists()


def test_duplicate_key_attack_specs_is_refused_by_the_measure_cli(measured_kit, capsys):
    kit, out = measured_kit
    bogus = {"dataset": "health", "table": "ed_visits", "id": "planted"}  # hidden by last-wins
    (kit / "metadata" / "attack_specs.json").write_text(
        '{"attacks": [], "trajectories": ' + json.dumps([bogus]) + ', "trajectories": []}', encoding="utf-8")
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert "ScorecardRejected" in capsys.readouterr().err
    assert not out.exists()


def test_duplicate_key_benchmark_is_refused_by_the_measure_cli(measured_kit, capsys):
    kit, out = measured_kit
    (kit / "results" / "benchmark.json").write_text('{"baselines": {"B0_health": {"privacy": NaN}}, '
                                                    + json.dumps(_bench())[1:], encoding="utf-8")
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert "MeasureRejected" in capsys.readouterr().err
    assert not out.exists()


FREE_TEXT = "health,ed_visits,chief_complaint,free_text,text,narrative\n"
SPAN = '[{"start": 0, "end": 4, "label": "PERSON", "text": "Zqxw"}]'  # one testable synthetic gold span


def _gold_spans(kit, line_for):
    """Catalog chief_complaint as free text and write its gold-span JSONL (the pets-eval child reads it)."""
    import pandas as pd

    (kit / "metadata" / "field_catalog.csv").write_text(CATALOG + FREE_TEXT, encoding="utf-8")
    vid = pd.read_csv(kit / "data" / "health" / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False,
                      nrows=1)["visit_id"].iloc[0]
    d = kit / "metadata" / "pii_spans"
    d.mkdir()
    (d / "health__ed_visits__chief_complaint.jsonl").write_text(line_for(json.dumps(vid)) + "\n", encoding="utf-8")


def test_strict_gold_spans_release_through_the_measure_cli(measured_kit):
    kit, out = measured_kit
    _gold_spans(kit, lambda vid: '{"record_id": ' + vid + ', "spans": ' + SPAN + '}')
    assert wire.main(run_args(kit, out)[1:]) == 0  # control: the free-text path itself runs
    assert any(out.glob("*.csv"))


def test_duplicate_key_gold_spans_handed_to_the_child_are_refused_by_the_measure_cli(measured_kit, capsys):
    """Review r1 (Sol, Standards) probe on #131: the child reads gold spans with a raw reader, so the wrapper must
    validate them strictly before the child runs."""
    kit, out = measured_kit
    _gold_spans(kit, lambda vid: '{"record_id": ' + vid + ', "spans": [{"start": NaN, "end": 1, "label": "NAME"}], '
                                 '"spans": ' + SPAN + '}')
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert "ScorecardRejected" in capsys.readouterr().err
    assert not out.exists()


def test_duplicate_key_scenarios_is_refused_by_the_run_cli(tmp_path):
    kit, out = build_kit(tmp_path / "kit", edit=coarse_qis), tmp_path / "rel"
    entries = [json.dumps(s) for s in SCENARIOS]
    entries[0] = '{"dataset": "finance", ' + entries[0][1:]  # HEALTH-S1 with a hidden first "dataset"
    (kit / "metadata" / "scenarios.json").write_text("[" + ", ".join(entries) + "]", encoding="utf-8")
    p = cli(*run_args(kit, out))
    assert p.returncode == 2, p.stderr
    assert not out.exists()


def test_duplicate_key_attack_specs_is_refused_by_the_attacker_cli(tmp_path):
    kit = _mini_kit(tmp_path)
    spec = (kit / "metadata" / "attack_specs.json").read_text(encoding="utf-8")
    (kit / "metadata" / "attack_specs.json").write_text('{"attacks": [], ' + spec[1:], encoding="utf-8")
    out = tmp_path / "o.json"
    rc = attacker_main(["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(out)]
                       + _rungs_file(tmp_path))
    assert rc != 0
    assert not out.exists()


# Exact number of raw json.load(s) calls allowed per file in src/, with the reason each is not an external
# record reader. A count, not a whole-file exemption: a new raw reader in one of these files also fails.
RAW_JSON_ALLOWED = {
    "pets_release/manifest/canonical.py": 1,    # the strict loader itself
    "pets_release/minimiser/search.py": 3,      # re-parses its own canonical() bytes (no duplicates, no NaN)
    "pets_release/redaction_eval/frame.py": 1,  # offline redaction metric harness; not a release/verify/measure path
    "pets_release/llm/draft.py": 1,             # already strict: own duplicate-key and non-finite hooks (DraftRejected)
    "pets_release/submission/guards.py": 1,     # key scanner: keeps every duplicate pair (tests/submission/test_build.py)
    "pets_release/run/provenance.py": 1,        # deep copy of its own in-memory params (json.loads(json.dumps(...))); no external bytes
}


def test_no_raw_json_reader_outside_the_strict_loader():
    src = ROOT / "src"
    counts, imported = {}, []
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("load", "loads") and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"):
                counts[rel] = counts.get(rel, 0) + 1
            if isinstance(node, ast.ImportFrom) and node.module == "json" \
                    and any(a.name in ("load", "loads", "*") for a in node.names):
                imported.append(f"{rel}:{node.lineno}")  # `from json import loads [as x]` would dodge the call scan
    assert imported == []
    assert counts == RAW_JSON_ALLOWED
