"""The recipient-derived key is scanned by producer.key-material, in the gate context and in verify --full.

Rows (trigger -> result):
  recipient run context, derived key planted in a release (hex, base64)  -> production check hits
  no recipient (default)                                                  -> context scans master + signing key only
  verify --full context for a recipient release                          -> carries the same recipient key
All keys and rows are synthetic.
"""
from __future__ import annotations

import base64

import pandas as pd
import pytest
from run_helpers import TEST_KEY, build_kit, cli, coarse_qis, run_args

from pets_release.checks import all_checks, run_checks
from pets_release.kit import Kit
from pets_release.policy import get_policy
from pets_release.pseudonym import MasterKey, recipient_key
from pets_release.run.context import producer_context, verify_context

KEYCHECK = {c.name: c for c in all_checks()}["producer.key-material"]


def _ctx(tmp_path, recipient):
    kit = Kit(build_kit(tmp_path / "kit"))
    policy = get_policy("HEALTH-S1")
    return producer_context(scenario_id="HEALTH-S1", policy=policy, source=kit.load_dataset("health"),
                            master=MasterKey.from_text(TEST_KEY), scope_id="0123456789abcdef",
                            recipient=recipient, contract={}, released=None)


def _scan(tmp_path, ctx, cell):
    rel = tmp_path / "rel"
    rel.mkdir()
    pd.DataFrame({"note": ["ok", cell]}, dtype=str).to_csv(rel / "ed_visits.csv", index=False)
    return run_checks(rel, {}, ctx, checks=[KEYCHECK]).to_dict()["records"][0]


@pytest.mark.parametrize("enc", [lambda b: b.hex(), lambda b: base64.b64encode(b).decode()])
def test_planted_recipient_key_is_a_hit(tmp_path, enc):
    ctx = _ctx(tmp_path, "recipient-a")
    planted = enc(recipient_key(MasterKey.from_text(TEST_KEY), "recipient-a")._k)
    rec = _scan(tmp_path, ctx, planted)
    assert rec["status"] == "fail" and rec["hits"] >= 1, rec


def test_default_recipient_scans_no_extra_key(tmp_path):
    assert len(_ctx(tmp_path / "d", "default")["keys"]) == 2
    assert len(_ctx(tmp_path / "r", "recipient-a")["keys"]) == 3


def test_verify_full_context_carries_the_recipient_key(tmp_path):
    kit_root = build_kit(tmp_path / "kit2", coarse_qis)
    out = tmp_path / "out"
    proc = cli(*run_args(kit_root, out), "--recipient", "recipient-a")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ctx = verify_context(Kit(kit_root), MasterKey.from_text(TEST_KEY), out)
    want = recipient_key(MasterKey.from_text(TEST_KEY), "recipient-a")  # opaque key objects (#84)
    assert any(k == want for k in ctx["keys"])
