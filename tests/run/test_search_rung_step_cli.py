"""Search default x enumerated rung sacrifice (#89), through the real CLI (seam: `pets-release run` / `verify`).

Synthetic rows only.

Rule: when the search's own plan holds a policy-enumerated rung sacrifice's `to` rung (arrival_ts at
ts.hour_of_day), `run` records the manifest `rungStep` with k measured at `from` on the search's released plan
(that column back at `from`) through the same `protect`/`k_at_from` as the hand path, and `verify --full`
re-measures that figure for a search release as it does for the hand plan. A manifest whose recorded figure
differs from a fresh measurement still fails `--full`.

Failure rows (trigger -> wrong result before the fix):
  S1 search adopts hour_of_day on a kit where month+hour fails k beyond budget
     -> writer refuses `rung-sacrifice-missing` (no rungStep recorded)    -> test_search_rung_step_is_recorded
  S2 same release, verify --full                                          -> "not reproducible" (hand plan only)
                                                                          -> test_search_rung_step_is_recorded
  S3 search release with atFrom forged and re-signed -> verify --full must still fail on the re-measure
                                                                          -> test_verify_full_re_measures_search_step
"""
from __future__ import annotations

import json
import shutil

import pytest
from run_helpers import CREATED, TEST_KEY, build_kit, cli, grouped_spread_arrivals


@pytest.fixture(scope="module")
def searched(tmp_path_factory):
    base = tmp_path_factory.mktemp("search-rung")
    kit = build_kit(base / "kit", grouped_spread_arrivals)
    out = base / "out" / "rel"
    proc = cli("run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED)
    return kit, out, proc


def _manifest(out):
    return json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))


def _hu8(m):
    return next(s for s in m["sacrifices"] if s["check"] == "H-U8")


def test_search_rung_step_is_recorded(searched):
    kit, out, proc = searched
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m = _manifest(out)
    arrival = next(f for f in m["fieldJustifications"] if (f["table"], f["column"]) == ("ed_visits", "arrival_ts"))
    assert (arrival["rung"], arrival["source"]) == ("ts.hour_of_day", "search")
    step = _hu8(m)["rungStep"]
    assert {k: step[k] for k in ("table", "column", "from", "to", "privacyTarget", "k")} == {
        "table": "ed_visits", "column": "arrival_ts", "from": "ts.month_hour", "to": "ts.hour_of_day",
        "privacyTarget": "qi-k", "k": 5}
    at = step["atFrom"]
    assert at["withinBound"] is False and at["share"] > at["maxShare"] and at["unitsBefore"] > 0
    assert [s for s in m["sacrifices"] if "rungStep" in s] == [_hu8(m)]
    lim = cli("verify", str(out))
    assert lim.returncode == 0, lim.stdout + lim.stderr
    full = cli("verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 0, full.stdout + full.stderr


def test_verify_full_re_measures_search_step(searched, tmp_path):
    from pets_release.manifest import canonical_bytes, compute_signature
    from pets_release.pseudonym import MasterKey, manifest_signing_key

    kit, out, proc = searched
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dst = tmp_path / "rel"
    shutil.copytree(out, dst)
    m = _manifest(dst)
    at = _hu8(m)["rungStep"]["atFrom"]
    at["unitsSuppressed"] -= 1
    at["share"] = round(at["unitsSuppressed"] / at["unitsBefore"], 6)
    m["signature"]["value"] = compute_signature(m, manifest_signing_key(MasterKey.from_text(TEST_KEY)))
    (dst / "privacy_manifest.json").write_bytes(canonical_bytes(m))
    assert cli("verify", str(dst)).returncode == 0  # self-consistent: only a re-measure can tell
    res = cli("verify", "--full", "--kit", str(kit), str(dst))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "rungStep: H-U8: re-measure differs from the manifest" in res.stdout


def test_search_plan_not_reproducible_from_its_rungs_is_unknown_state(tmp_path, monkeypatch):
    """S4: verify --full rebuilds a search plan from the manifest's rungs, so `run` refuses (exit 2, no folder)
    a search plan whose params differ from the search's own param rule (planted at the search's return)."""
    import copy
    import dataclasses

    from run_helpers import grouped_qis

    from pets_release.cli import main
    from pets_release.run import pipeline

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", grouped_qis)
    real = pipeline.search

    def altered(*a, **k):
        res = copy.deepcopy(real(*a, **k))
        e = next(e for e in res.plan if any(type(v) is int for v in e["params"].values()))
        p = next(n for n, v in e["params"].items() if type(v) is int)
        e["params"][p] += 1
        return dataclasses.replace(res, plan=res.plan)

    monkeypatch.setattr(pipeline, "search", altered)
    out = tmp_path / "out" / "rel"
    code = main(["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED])
    assert code == 2
    assert not out.exists()
