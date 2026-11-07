"""Runner contract: errors, not_run, zero denominators, scope selection, determinism, CLI."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pets_release.checks import Check, Outcome, Violation, all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
GATE = {"phase": "gate"}
SRC = Path(__file__).resolve().parents[2] / "src"


def _valid(tmp_path):
    dst = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", dst)
    return dst


def _boom(release, contract, context):
    raise RuntimeError("secret-looking value 4111111111111111")


def _zero(release, contract, context):
    return Outcome(n=0, violations=())


def _skip(release, contract, context):
    return Outcome.not_run()


def _ok(release, contract, context):
    return Outcome(n=3, violations=())


def _low(release, contract, context):
    return Outcome(n=3, violations=(Violation("lowish", "LOCATION", "low", "notes.csv", "note_text", 1, (0,)),))


def _mk(name, fn, scope="release"):
    return Check(name=name, version="1.0.0", scope=scope, unit="cells", run=fn)


def test_check_that_raises_is_error_and_refuses_without_leaking_message(tmp_path):
    res = run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[_mk("ok", _ok), _mk("boom", _boom)])
    recs = {r.check: r for r in res.records}
    assert recs["boom"].status == "error"
    assert recs["ok"].status == "pass"
    assert res.refused
    assert "4111111111111111" not in json.dumps(res.to_dict())


def test_zero_denominator_on_non_empty_release_is_error(tmp_path):
    res = run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[_mk("zero", _zero)])
    assert res.records[0].status == "error"
    assert res.refused


def test_not_run_refuses(tmp_path):
    res = run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[_mk("skip", _skip)])
    assert res.records[0].status == "not_run"
    assert res.refused


def test_low_severity_hit_passes_and_is_counted(tmp_path):
    res = run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[_mk("lowish", _low)])
    rec = res.records[0]
    assert (rec.status, rec.hits, res.refused) == ("pass", 1, False)


def test_empty_selection_refuses(tmp_path):
    assert run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[]).refused


def test_every_record_has_non_zero_denominator_on_valid_release(tmp_path):
    res = run_checks(_valid(tmp_path), CONTRACT, GATE)
    assert all(r.denominator["n"] > 0 for r in res.records)
    assert all(r.denominator["unit"] in {"cells", "turns", "persons", "files", "rows"} for r in res.records)


def test_record_dict_has_exact_pinned_keys(tmp_path):
    res = run_checks(_valid(tmp_path) , CONTRACT, GATE)
    rec = res.to_dict()["records"][0]
    assert set(rec) == {"check", "version", "scope", "status", "denominator", "hits", "violations"}
    assert set(rec["denominator"]) == {"unit", "n"}


def test_scope_release_selects_only_release_checks(tmp_path):
    prod = _mk("prodcheck", _ok, scope="producer")
    res = run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[_mk("ok", _ok), prod], scope="release")
    assert [r.check for r in res.records] == ["ok"]


def test_registry_names_are_unique_sorted_and_versioned():
    names = [c.name for c in all_checks()]
    assert names == sorted(set(names))
    assert all(c.version and c.scope in {"release", "producer"} for c in all_checks())


def test_same_input_gives_byte_identical_result(tmp_path):
    out = tmp_path / "x"
    shutil.copytree(FIX / "card_in_cell" / "release", out)
    a = json.dumps(run_checks(out, CONTRACT, GATE).to_dict(), sort_keys=True)
    b = json.dumps(run_checks(out, CONTRACT, GATE).to_dict(), sort_keys=True)
    assert a == b


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pets_release.checks", *args], check=False, capture_output=True, text=True, env=env)


def test_cli_refuses_planted_card_and_passes_valid(tmp_path):
    c = tmp_path / "contract.json"
    shutil.copy(FIX / "contract.json", c)
    bad = tmp_path / "bad"
    shutil.copytree(FIX / "card_in_cell" / "release", bad)
    r = _cli("--contract", str(c), "--phase", "gate", str(bad))
    assert r.returncode == 1, r.stderr
    summary = json.loads(r.stdout)
    assert summary["refused"] is True
    assert {x["check"]: x["status"] for x in summary["records"]}["rescan.payment-cards"] == "fail"
    assert "4111" not in r.stdout
    good = tmp_path / "good"
    shutil.copytree(FIX / "valid" / "release", good)
    assert _cli("--contract", str(c), "--phase", "gate", str(good)).returncode == 0


def test_cli_usage_error_exits_2(tmp_path):
    assert _cli(str(tmp_path)).returncode == 2
