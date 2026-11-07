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