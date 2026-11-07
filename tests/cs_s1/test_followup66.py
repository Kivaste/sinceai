"""#66: only an executed, passing turn-ID prerequisite permits raw keep.

Seams: production CS prepare/check registry; generated contract; real CLI publication/verification.
Failure rows (trigger -> result):
  absent / errored / skipped / inapplicable prerequisite -> pseudonym candidate, never raw keep
  passing prerequisite -> raw keep still available
  plan strips prerequisite metadata -> generated contract still binds it
  absent / nonpassing / wrong-scope gate record -> manifest invalid, no publication
  planted assessment file -> cannot replace a fresh check
All rows and kits are synthetic.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import json
import random
import subprocess
import sys

import pandas as pd
import pytest

from cs_kit import GOLD, build_cs_kit, cs_run_args
from run_helpers import cli, env
from pets_release.checks import registry
from pets_release.checks.records import Outcome
from pets_release.contract import ContractError, digest, generate
from pets_release.cs_s1 import prepare
from pets_release.manifest import validate_manifest
from pets_release.policy import get_policy, hand_plan

NAME = "turn-id-synthetic"


def _shuffled(minikit):
    source = {k: v.copy() for k, v in minikit.items()}
    perm = list(range(1, len(source["turns"]) + 1))
    random.Random(23).shuffle(perm)
    source["turns"]["turn_id"] = [f"SYNT-{i:07d}" for i in perm]
    return source


def _error(*args):
    raise RuntimeError("synthetic prerequisite error")


@pytest.mark.parametrize("replacement", [None, _error, lambda *a: Outcome.not_run(),
                                        lambda *a: Outcome.not_applicable()])
def test_unavailable_prerequisite_cannot_keep_raw_ids(monkeypatch, minikit, make_keys, replacement):
    checks = registry.all_checks()
    selected = tuple(c if c.name != NAME else replace(c, run=replacement)
                     for c in checks if c.name != NAME or replacement is not None)
    monkeypatch.setattr(registry, "all_checks", lambda: selected)
    source = _shuffled(minikit)
    result = prepare(source, make_keys())
    assert not result.turn_id.kept
    assert next(e for e in result.plan if (e["table"], e["column"]) == ("turns", "turn_id"))["rung"] == "id.pseudonym"
    assert not set(result.tables["turns"].turn_id) & set(source["turns"].turn_id)


def test_contract_binds_prerequisite_even_if_plan_metadata_removed():
    plan = hand_plan("CS-S1")
    next(e for e in plan if (e["table"], e["column"]) == ("turns", "turn_id"))["params"] = {}
    contract = generate(get_policy("CS-S1"), plan)
    params = contract["files"]["turns.csv"]["columns"]["turn_id"]["params"]
    assert params.get("requires_check") == NAME


@pytest.mark.parametrize("required", [None, "unknown-check"])
def test_digest_rejects_unbound_prerequisite(required):
    contract = generate(get_policy("CS-S1"), hand_plan("CS-S1"))
    params = contract["files"]["turns.csv"]["columns"]["turn_id"]["params"]
    if required is None:
        params.pop("requires_check", None)
    else:
        params["requires_check"] = required
    with pytest.raises(ContractError, match="turn-id prerequisite"):
        digest(contract)


@pytest.fixture(scope="module")
def kept_release(tmp_path_factory):
    base = tmp_path_factory.mktemp("fu66")
    kit = build_cs_kit(base / "kit")
    path = kit / "data" / "customer_service" / "turns.csv"
    turns = pd.read_csv(path, dtype=str, keep_default_na=False)
    old = turns.turn_id.tolist()
    perm = list(range(1, len(turns) + 1))
    random.Random(23).shuffle(perm)
    turns["turn_id"] = [f"SYNT-{i:07d}" for i in perm]
    mapping = dict(zip(old, turns.turn_id))
    turns.to_csv(path, index=False, lineterminator="\n")
    gold = kit / "metadata" / "pii_spans" / GOLD
    records = [json.loads(line) for line in gold.read_text(encoding="utf-8").splitlines()]
    for record in records:
        record["record_id"] = mapping[record["record_id"]]
    gold.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    out = base / "kept"
    proc = cli(*cs_run_args(kit, out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return kit, out, json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutation", ["missing", "not_applicable", "scope", "unit", "hits"])
def test_manifest_requires_executed_zero_hit_producer_check(kept_release, mutation):
    _, _, original = kept_release
    manifest = copy.deepcopy(original)
    record = next(c for c in manifest["gate"]["checks"] if c["check"] == NAME)
    if mutation == "missing":
        manifest["gate"]["checks"].remove(record)
        manifest["bindings"]["checkVersions"].pop(NAME)
    elif mutation == "not_applicable":
        record.update(status="not_applicable", denominator={"unit": "turns", "n": 0})
    elif mutation == "scope":
        record["scope"] = "release"
    elif mutation == "unit":
        record["denominator"]["unit"] = "cells"
    else:
        record["hits"] = 1
    assert any("turn-id-prerequisite" in e for e in validate_manifest(manifest))


def test_real_cli_keeps_only_after_check_and_both_verify_tiers_pass(kept_release):
    kit, out, manifest = kept_release
    justification = next(j for j in manifest["fieldJustifications"]
                         if (j["table"], j["column"]) == ("turns", "turn_id"))
    assert justification["rung"] == "keep"
    assert validate_manifest(manifest) == []
    assert cli("verify", str(out)).returncode == 0
    assert cli("verify", "--full", "--kit", str(kit), str(out)).returncode == 0


def test_real_cli_missing_check_refuses_despite_planted_prior_assessment(kept_release):
    kit, previous, _ = kept_release
    assessment = (previous.parent / "kept.scoring" / "turn_id_assessment.json").read_bytes()
    (kit / "turn_id_assessment.json").write_bytes(assessment)
    (previous.parent / "turn_id_assessment.json").write_bytes(assessment)
    out = previous.parent / "missing-check"
    # Fault at the plugin catalog boundary; the real CLI, pipeline and writer remain untouched.
    code = ("import sys; from pets_release.checks import registry; registry.all_checks(); "
            "registry._CHECKS.pop('turn-id-synthetic'); "
            "from pets_release.cli import main; raise SystemExit(main(sys.argv[1:]))")
    proc = subprocess.run([sys.executable, "-c", code, *cs_run_args(kit, out)],
                          capture_output=True, text=True, encoding="utf-8", env=env(), check=False)
    assert proc.returncode != 0
    assert not out.exists()
    report = json.loads((previous.parent / "missing-check.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    assert any("turn-id-prerequisite" in reason for reason in report["reasons"])
