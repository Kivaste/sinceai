"""`pets-release run --recipient` through the real CLI on the synthetic minikit.

Rows (trigger -> result):
  recipient A and B, same kit and key         -> both exit 0; zero shared visit tokens
  within each release                          -> every lab visit token is an ed_visits token
  manifest of each                             -> release.recipient is the ID; scope IDs differ
  verify (limited) and verify --full, each     -> exit 0
  verify --full with the other recipient's ... n/a (the ID is read from the manifest)
  same recipient twice                         -> byte-identical
  no --recipient vs recipient                  -> zero shared tokens
  invalid / reserved recipient ID              -> exit 2, no output folder
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest
from run_helpers import build_kit, cli, coarse_qis, run_args


@pytest.fixture(scope="module")
def releases(tmp_path_factory):
    base = tmp_path_factory.mktemp("rcp")
    kit = build_kit(base / "kit", coarse_qis)
    outs, procs = {}, {}
    for name, extra in (("a", ["--recipient", "recipient-a"]), ("b", ["--recipient", "recipient-b"]),
                        ("a2", ["--recipient", "recipient-a"]), ("none", [])):
        out = base / "out" / name
        procs[name] = cli(*run_args(kit, out), *extra)
        outs[name] = out
    return kit, outs, procs


def _tokens(out):
    """Every token column of the released tables, from the manifest contract: (visit tokens of ed, of lab, all)."""
    contract = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["contract"]
    cols = {(t["table"], t["column"]) for t in contract["tokens"]}
    assert ("ed_visits", "visit_id") in cols and len(cols) >= 3
    allt = set()
    for table, col in sorted(cols):
        df = pd.read_csv(out / f"{table}.csv", dtype=str, keep_default_na=False)
        allt |= set(df[col])
    ed = pd.read_csv(out / "ed_visits.csv", dtype=str, keep_default_na=False)
    lab = pd.read_csv(out / "lab_results.csv", dtype=str, keep_default_na=False)
    return set(ed["visit_id"]), set(lab["visit_id"]), allt


def _tree(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_both_recipient_releases_succeed(releases):
    _, _, procs = releases
    for name in ("a", "b", "none"):
        assert procs[name].returncode == 0, procs[name].stdout + procs[name].stderr


def test_recipients_share_zero_tokens_and_joins_survive(releases):
    _, outs, _ = releases
    ed_a, lab_a, all_a = _tokens(outs["a"])
    ed_b, lab_b, all_b = _tokens(outs["b"])
    _, _, all_n = _tokens(outs["none"])
    assert ed_a and ed_b and lab_a and lab_b
    assert all_a.isdisjoint(all_b)
    assert all_a.isdisjoint(all_n)
    assert lab_a <= ed_a and lab_b <= ed_b


def test_manifest_records_the_recipient_scope(releases):
    _, outs, _ = releases
    ma = json.loads((outs["a"] / "privacy_manifest.json").read_text(encoding="utf-8"))["release"]
    mb = json.loads((outs["b"] / "privacy_manifest.json").read_text(encoding="utf-8"))["release"]
    assert ma["recipient"] == "recipient-a" and mb["recipient"] == "recipient-b"
    assert ma["releaseScopeId"] != mb["releaseScopeId"]


def test_each_recipient_release_verifies_in_both_tiers(releases):
    kit, outs, _ = releases
    for name in ("a", "b"):
        assert cli("verify", str(outs[name])).returncode == 0
        full = cli("verify", "--full", "--kit", str(kit), str(outs[name]))
        assert full.returncode == 0, full.stdout + full.stderr
        assert "VERIFIED (full)" in full.stdout


def test_same_recipient_is_byte_identical(releases):
    _, outs, procs = releases
    assert procs["a2"].returncode == 0
    assert _tree(outs["a"]) == _tree(outs["a2"])


@pytest.mark.parametrize("bad", ["bad id", "default", "manifest-signature", "-x"])
def test_invalid_recipient_exits_2_without_output(tmp_path, bad):
    kit = build_kit(tmp_path / "kit", coarse_qis)
    out = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, out), "--recipient", bad)
    assert proc.returncode == 2
    assert not out.exists()
    text = proc.stderr + proc.stdout
    if bad == "bad id":
        assert bad not in text
    else:  # the reserved / flag-like IDs may appear in generic usage text, but never echoed as a quoted value
        assert f"'{bad}'" not in text and f'"{bad}"' not in text and f"recipient {bad}" not in text


def test_release_tokens_are_keyed_by_the_recipient_key(releases):
    """Tokens in the release are the recipient-keyed pseudonyms (production derivation), not master-keyed ones."""
    from run_helpers import TEST_KEY

    from pets_release.ladders import PseudonymKeys
    from pets_release.pseudonym import MasterKey, Scope, pseudonymiser_for

    kit, outs, _ = releases
    master = MasterKey.from_text(TEST_KEY)
    src = pd.read_csv(kit / "data" / "health" / "ed_visits.csv", dtype=str, keep_default_na=False)["visit_id"]
    for name, rid in (("a", "recipient-a"), ("b", "recipient-b")):
        rsid = json.loads((outs[name] / "privacy_manifest.json").read_text(encoding="utf-8"))["release"][
            "releaseScopeId"]
        released = _tokens(outs[name])[0]
        for recipient, expect_in in ((rid, True), (None, False)):
            keys = PseudonymKeys(pseudonymiser_for(master, recipient=recipient), Scope.release(rsid))
            got = {keys.token(v, "RECORD_KEY") for v in src}
            assert (released and released <= got) if expect_in else got.isdisjoint(released)
