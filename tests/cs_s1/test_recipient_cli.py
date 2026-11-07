"""``pets-release run --scenario CS-S1 --recipient`` through the real CLI on the synthetic minikit (ticket 28 keys).

Rows (trigger -> result):
  recipient A and B, same kit and key    -> both exit 0; zero shared conversation tokens
  manifest of each                       -> release.recipient is the ID; scope IDs differ
  verify (limited) and verify --full     -> exit 0 for each
  same recipient twice                   -> byte-identical
  invalid / reserved recipient ID        -> exit 2, no output folder
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest
from cs_kit import build_cs_kit, cs_run_args
from run_helpers import cli


@pytest.fixture(scope="module")
def cs_rcp(tmp_path_factory):
    base = tmp_path_factory.mktemp("csrcp")
    kit = build_cs_kit(base / "kit")
    outs, procs = {}, {}
    for name, rid in (("a", "recipient-a"), ("b", "recipient-b"), ("a2", "recipient-a")):
        outs[name] = base / "out" / name
        procs[name] = cli(*cs_run_args(kit, outs[name]), "--recipient", rid)
    return kit, outs, procs


def _conv_tokens(out):
    return set(pd.read_csv(out / "conversations.csv", dtype=str, keep_default_na=False, na_filter=False)["conversation_id"])


def _release(out):
    return json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["release"]


def test_cs_recipients_release_with_disjoint_tokens(cs_rcp):
    _, outs, procs = cs_rcp
    for name in ("a", "b"):
        assert procs[name].returncode == 0, procs[name].stdout + procs[name].stderr
    ta, tb = _conv_tokens(outs["a"]), _conv_tokens(outs["b"])
    assert ta and tb and ta.isdisjoint(tb)


def test_cs_manifest_records_the_recipient(cs_rcp):
    _, outs, _ = cs_rcp
    ra, rb = _release(outs["a"]), _release(outs["b"])
    assert ra["recipient"] == "recipient-a" and rb["recipient"] == "recipient-b"
    assert ra["releaseScopeId"] != rb["releaseScopeId"]


def test_cs_each_recipient_verifies_in_both_tiers(cs_rcp):
    kit, outs, _ = cs_rcp
    for name in ("a", "b"):
        lim = cli("verify", str(outs[name]))
        assert lim.returncode == 0, lim.stdout + lim.stderr
        full = cli("verify", "--full", "--kit", str(kit), str(outs[name]))
        assert full.returncode == 0 and "VERIFIED (full)" in full.stdout, full.stdout + full.stderr


def test_cs_same_recipient_byte_identical(cs_rcp):
    _, outs, procs = cs_rcp
    assert procs["a2"].returncode == 0

    def dig(d):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())}

    assert dig(outs["a"]) == dig(outs["a2"])


@pytest.mark.parametrize("bad", ["bad id", "default"])
def test_cs_invalid_recipient_exits_2_without_output(tmp_path, bad):
    kit = build_cs_kit(tmp_path / "kit")
    out = tmp_path / "out" / "rel"
    proc = cli(*cs_run_args(kit, out), "--recipient", bad)
    assert proc.returncode == 2
    assert not out.exists()
