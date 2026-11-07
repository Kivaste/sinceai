"""Follow-up #89 through the real CLI (seam: `pets-release run` / `pets-release verify`). Synthetic rows only.

Rule: the HEALTH-S1 hand plan releases arrival_ts at ts.month_hour. It moves to ts.hour_of_day (coarser than
month, sacrifice-only) only as the policy-enumerated rung sacrifice, only when per-person k measured at
month_hour needs more local suppression than the policy budget and H-U8 still passes strictly at hour_of_day;
the manifest's H-U8 sacrifice then records the step and the measured k at month_hour. A manifest releasing a
sacrifice-only rung without that record is invalid (verify fails closed).

Failure rows (trigger -> wrong result before the fix):
  C1 kit where month_hour reaches k within budget -> hour_of_day shipped anyway
                                                    -> test_month_hour_kept_when_k_passes_within_budget
  C2 kit where month_hour fails k beyond budget -> hour_of_day shipped with no recorded k result or step
                                                    -> test_hour_of_day_adopted_as_recorded_sacrifice
  C3 manifest with hour_of_day released and the rungStep record removed -> verify passes
                                                    -> test_verify_refuses_hour_of_day_without_record

Follow-up #109. Rule: sacrifices are checked against the rung the bound contract actually applies
(``contract.files[<table>.csv].columns[<outputColumn>].params.rung``, with that rung's form), never against the
justification's planned rung; a mismatch or a missing contract rung refuses in the manifest validator, so both
verify tiers fail.
  C4 re-signed release whose arrival cells, contract form and params.rung are hour-of-day while the justification
     still says month+hour and no rungStep is recorded -> limited and full verify exit 0
                                                    -> test_verify_refuses_contract_rung_not_justified
  C5 contract column with no params.rung, or whose form is not its rung's form -> verify passes
                                                    -> test_verify_refuses_missing_or_unsupported_contract_rung
  C6 extra hour-of-day contract column (derived_from arrival_ts, listed as QI) no justification backs
     -> verify passes                               -> test_verify_refuses_contract_column_no_justification_backs
  C7 arrival_ts relabelled keep (justification + contract) with an hour-only regex and cells -> verify passes
                                                    -> test_verify_refuses_rung_off_the_policy_ladder
"""
from __future__ import annotations

import json
import re
import shutil

import pandas as pd
import pytest
from run_helpers import build_kit, cli, run_args

MONTH_HOUR = re.compile(r"^\d{4}-\d{2}-01T\d{2}:00$")
HOUR_OF_DAY = re.compile(r"^\d{2}:00$")


def spread_arrivals(folder):
    """Edit the synthetic copy: shared date of birth and municipality (like ``coarse_qis``); each visit's
    arrival spread over 12 months x 24 hours, so month+hour classes are small and hour-of-day classes large."""
    p = folder / "ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    for c in ("date_of_birth", "municipality"):
        df.loc[:, c] = df.at[0, c]
    df["arrival_ts"] = [f"2025-{i % 12 + 1:02d}-15 {(i // 12) % 24:02d}:30:00" for i in range(len(df))]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def _manifest(out):
    return json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))


def _arrival(out):
    return pd.read_csv(out / "ed_visits.csv", dtype=str, keep_default_na=False)["arrival_ts"]


def _just(m, column):
    return next(f for f in m["fieldJustifications"] if f["table"] == "ed_visits" and f["column"] == column)


def test_month_hour_kept_when_k_passes_within_budget(released):
    _, out, proc = released  # coarse_qis kit: month_hour reaches k with a small suppression share
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m = _manifest(out)
    assert _just(m, "arrival_ts")["rung"] == "ts.month_hour"
    assert _arrival(out).map(lambda v: bool(MONTH_HOUR.match(v))).all()
    assert not any("rungStep" in s for s in m["sacrifices"])


@pytest.fixture(scope="module")
def spread(tmp_path_factory):
    base = tmp_path_factory.mktemp("spread")
    kit = build_kit(base / "kit", spread_arrivals)
    out = base / "out" / "rel"
    return kit, out, cli(*run_args(kit, out))


def test_hour_of_day_adopted_as_recorded_sacrifice(spread):
    kit, out, proc = spread
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m = _manifest(out)
    assert _just(m, "arrival_ts")["rung"] == "ts.hour_of_day"
    assert _arrival(out).map(lambda v: bool(HOUR_OF_DAY.match(v))).all()
    hu8 = next(s for s in m["sacrifices"] if s["check"] == "H-U8")
    step = hu8["rungStep"]
    assert {k: step[k] for k in ("table", "column", "from", "to", "privacyTarget", "k")} == {
        "table": "ed_visits", "column": "arrival_ts", "from": "ts.month_hour", "to": "ts.hour_of_day",
        "privacyTarget": "qi-k", "k": 5}
    at = step["atFrom"]
    assert at["withinBound"] is False and at["maxShare"] == 0.1 and at["share"] > at["maxShare"]
    assert at["unitsBefore"] > 0 and at["share"] == round(at["unitsSuppressed"] / at["unitsBefore"], 6)
    assert isinstance(hu8["after"], float) and hu8["after"] >= 0.9  # H-U8 still passes at hour_of_day
    assert [s for s in m["sacrifices"] if "rungStep" in s] == [hu8]

    lim = cli("verify", str(out))
    assert lim.returncode == 0, lim.stdout + lim.stderr
    full = cli("verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 0, full.stdout + full.stderr


def _planted(spread, tmp_path, edit):
    _, out, proc = spread
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dst = tmp_path / "rel"
    shutil.copytree(out, dst)
    from pets_release.manifest import canonical_bytes

    m = _manifest(dst)
    edit(m)
    (dst / "privacy_manifest.json").write_bytes(canonical_bytes(m))
    return dst


def test_verify_refuses_hour_of_day_without_record(spread, tmp_path):
    def drop(m):
        for s in m["sacrifices"]:
            s.pop("rungStep", None)

    res = cli("verify", str(_planted(spread, tmp_path, drop)))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "rung-sacrifice-missing" in res.stdout

def _hu8(m):
    return next(s for s in m["sacrifices"] if s["check"] == "H-U8")


@pytest.mark.parametrize("edit,code", [
    (lambda m: _hu8(m)["rungStep"]["atFrom"].update(share=0.05), "budget-not-exceeded"),
    (lambda m: _hu8(m).update(after=0.5), "rung-sacrifice-check-not-strict"),
    (lambda m: _hu8(m)["rungStep"].update(column="triage"), "field-mismatch"),
], ids=["k-within-budget", "check-below-threshold", "other-column"])
def test_verify_refuses_forged_rung_step(spread, tmp_path, edit, code):
    res = cli("verify", str(_planted(spread, tmp_path, edit)))
    assert res.returncode == 1, res.stdout + res.stderr
    assert code in res.stdout

def test_verify_full_re_measures_k_at_from(spread, tmp_path):
    """A re-signed manifest whose recorded k at month+hour differs from a fresh measurement fails --full."""
    from pets_release.manifest import compute_signature
    from pets_release.pseudonym import MasterKey, manifest_signing_key
    from run_helpers import TEST_KEY

    def forge(m):
        at = _hu8(m)["rungStep"]["atFrom"]
        at["unitsSuppressed"] -= 1
        at["share"] = round(at["unitsSuppressed"] / at["unitsBefore"], 6)
        m["signature"]["value"] = compute_signature(m, manifest_signing_key(MasterKey.from_text(TEST_KEY)))

    kit = spread[0]
    dst = _planted(spread, tmp_path, forge)
    assert cli("verify", str(dst)).returncode == 0  # still self-consistent: only a re-measure can tell
    res = cli("verify", "--full", "--kit", str(kit), str(dst))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "rungStep: H-U8: re-measure differs from the manifest" in res.stdout
    assert "signature" not in res.stdout

def _resign(m):
    from pets_release.manifest import canonical_digest, compute_signature
    from pets_release.pseudonym import MasterKey, manifest_signing_key
    from run_helpers import TEST_KEY

    m["bindings"]["contractDigest"] = canonical_digest(m["contract"])
    m["signature"]["value"] = compute_signature(m, manifest_signing_key(MasterKey.from_text(TEST_KEY)))


def _forged_hour_of_day(released, tmp_path, *, contract_edit, cells=True):
    """Copy of the month+hour release (k within budget) with arrival_ts moved to hour-of-day in the cells and the
    contract only; the justification keeps ts.month_hour and no rungStep is recorded. Bindings and the signature
    are recomputed, so only a contract-vs-justification rule can tell."""
    import hashlib

    from pets_release.manifest import canonical_bytes

    _, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dst = tmp_path / "rel"
    shutil.copytree(out, dst)
    m = _manifest(dst)
    fj = _just(m, "arrival_ts")
    assert fj["rung"] == "ts.month_hour" and not any("rungStep" in s for s in m["sacrifices"])
    if cells:
        p = dst / "ed_visits.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df[fj["outputColumn"]] = df[fj["outputColumn"]].map(lambda v: v[-5:] if v else v)
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
        m["bindings"]["files"]["ed_visits.csv"] = hashlib.sha256(p.read_bytes()).hexdigest()
    contract_edit(m["contract"]["files"]["ed_visits.csv"]["columns"][fj["outputColumn"]])
    _resign(m)
    (dst / "privacy_manifest.json").write_bytes(canonical_bytes(m))
    return dst


def _to_hour_of_day(col):
    col["form"] = r"^\d{2}:00$"
    col["params"]["rung"] = "ts.hour_of_day"


def test_verify_refuses_contract_rung_not_justified(released, tmp_path):
    kit = released[0]
    dst = _forged_hour_of_day(released, tmp_path, contract_edit=_to_hour_of_day)
    lim = cli("verify", str(dst))
    assert lim.returncode == 1, lim.stdout + lim.stderr
    assert "ed_visits.arrival_ts: rung-contract-mismatch" in lim.stdout
    full = cli("verify", "--full", "--kit", str(kit), str(dst))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "ed_visits.arrival_ts: rung-contract-mismatch" in full.stdout


@pytest.mark.parametrize("edit,code", [
    (lambda col: col["params"].pop("rung"), "rung-contract-missing"),
    (lambda col: col.update(form="text"), "rung-form-mismatch"),  # still matches every cell
], ids=["no-contract-rung", "form-not-of-rung"])
def test_verify_refuses_missing_or_unsupported_contract_rung(released, tmp_path, edit, code):
    dst = _forged_hour_of_day(released, tmp_path, contract_edit=edit, cells=False)
    res = cli("verify", str(dst))
    assert res.returncode == 1, res.stdout + res.stderr
    assert f"ed_visits.arrival_ts: {code}" in res.stdout


def test_verify_refuses_contract_column_no_justification_backs(released, tmp_path):
    """C6: an extra hour-of-day column derived from arrival_ts (listed as a QI, cells matching its form) that no
    released justification backs: its rung escapes the sacrifice rule unless every contract column is justified."""
    import hashlib

    def extra(m, dst):
        p = dst / "ed_visits.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df["arrival_hour"] = df[_just(m, "arrival_ts")["outputColumn"]].map(lambda v: v[-5:] if v else v)
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
        m["bindings"]["files"]["ed_visits.csv"] = hashlib.sha256(p.read_bytes()).hexdigest()
        spec = m["contract"]["files"]["ed_visits.csv"]
        spec["columns"]["arrival_hour"] = {"form": r"^\d{2}:00$", "params": {
            "derived_from": "arrival_ts", "nullable": True, "rung": "ts.hour_of_day"}}
        spec["required"] = sorted([*spec["required"], "arrival_hour"])
        m["contract"]["qi"] = sorted([*m["contract"]["qi"], {"table": "ed_visits", "column": "arrival_hour",
                                                             "derived_from": "arrival_ts"}],
                                     key=lambda r: (r["table"], r["column"]))

    from pets_release.manifest import canonical_bytes

    _, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dst = tmp_path / "rel"
    shutil.copytree(out, dst)
    m = _manifest(dst)
    extra(m, dst)
    _resign(m)
    (dst / "privacy_manifest.json").write_bytes(canonical_bytes(m))
    res = cli("verify", str(dst))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "$.contract.files.ed_visits.csv.columns.arrival_hour: rung-unjustified" in res.stdout

def test_verify_refuses_rung_off_the_policy_ladder(released, tmp_path):
    """C7: arrival_ts relabelled ``keep`` in both the justification and the contract, with an hour-only regex form
    (a validator-ID rung may declare a narrower regex) and hour-only cells: a timestamp column must carry a
    timestamp-ladder rung, or the sacrifice rule is bypassed."""
    def relabel(col):
        col["form"] = r"^\d{2}:00$"
        col["params"]["rung"] = "keep"

    dst = _forged_hour_of_day(released, tmp_path, contract_edit=relabel)
    from pets_release.manifest import canonical_bytes

    m = _manifest(dst)
    _just(m, "arrival_ts")["rung"] = "keep"
    _resign(m)
    (dst / "privacy_manifest.json").write_bytes(canonical_bytes(m))
    res = cli("verify", str(dst))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "ed_visits.arrival_ts: rung-not-on-ladder" in res.stdout