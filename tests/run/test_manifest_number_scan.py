"""#120: the manifest value scan reads a JSON number by its integer digits only, through the measure CLI.

Seam: the module CLI ``python -m pets_release.measure.wire`` (``wire.main``) on the synthetic health minikit.
Only the measurer's scoring is stubbed (it needs the challenge kit); the baselines block comes from the
production ``baseline_rows`` over a synthetic ``results/benchmark.json``, and the two ``run_release`` passes, the
writer and manifest validation (the value scan) are production code.

Rule: a JSON number is an identifier candidate only by its integer digits; digits after a decimal point never
start or extend a match; an exponent-form number is scanned by the integer digits of its value. Strings are
scanned as before.

Failure rows (trigger -> result):
  published baseline 0.4111111111111111 (Luhn-valid fraction)        -> today REFUSED (PAYMENT_CARD); must release
  aggregate 4.111111111111111e-05 (exponent form, Luhn mantissa)     -> must release
  planted 4111111111111111 (Luhn-valid integer) as a JSON number      -> refused, PAYMENT_CARD
  planted 4111111111111111.0 (same, as a float)                       -> refused, PAYMENT_CARD
  planted 4.111111111111135e+16 (exponent form; its integer value 41111111111111352 is Luhn-valid, issuer 4)
                                                                      -> today RELEASED; must refuse, PAYMENT_CARD
  card / decimal-text card / email in a manifest STRING               -> refused (strings scanned as before)
Synthetic values only (published test card number digits).
"""
from __future__ import annotations

import json

import pytest
from run_helpers import TEST_KEY, build_kit, coarse_qis, run_args

from pets_release.manifest import MANIFEST_FILENAME, loads_strict
from pets_release.measure import baseline_rows, wire
from pets_release.writer import scoring_dir
from pets_release.writer.core import REFUSAL_REPORT

FRACTION_CARD = 0.4111111111111111  # fractional digits = published test card number (Luhn-valid, issuer 4)
NOT_MEASURED = {"status": "not_measured", "reason": "stub"}


def _bench(privacy: float) -> dict:
    rec = {"privacy": privacy, "utility": 0.5, "composite": 0.5, "worst_reid": 0.25, "residual_identifiers": 0.0,
           "utility_tasks": {"H-U2": 0.5}, "utility_by_scenario": {"HEALTH-S1": 0.5}, "runtime_s": 1.0}
    return {"generated": "x", "baselines": {f"{p}_health": dict(rec) for p in ("B0", "B2", "B2K")}}


def _kit(tmp_path, monkeypatch, *, privacy=FRACTION_CARD, search_risk=None, source="published benchmark"):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=coarse_qis)
    (kit / "results").mkdir()
    (kit / "results" / "benchmark.json").write_text(json.dumps(_bench(privacy)), encoding="utf-8")

    def measure(scid, *, root, **_kw):
        block = {k: dict(NOT_MEASURED) for k in ("utility", "privacy", "search", "redaction")}
        block["baselines"] = {"status": "measured", "source": source,
                              "rows": baseline_rows(root, scid, "health")}
        if search_risk is not None:
            block["search"] = {"status": "measured", "source": "stub", "candidates": 1, "accepted": 1,
                               "boundReached": False,
                               "points": [{"step": 0, "risk": search_risk, "utility": 0.5, "accepted": True}]}
        return block

    monkeypatch.setattr(wire, "measure", measure)
    monkeypatch.setattr(wire, "person_k_components", lambda *a, **k: [])
    monkeypatch.setattr(wire, "_person_k_from_release", lambda **k: None)
    return kit, tmp_path / "rel"


@pytest.mark.parametrize("privacy", [FRACTION_CARD, 4.111111111111111e-05])
def test_decimal_aggregate_with_luhn_fraction_releases(tmp_path, monkeypatch, capsys, privacy):
    kit, out = _kit(tmp_path, monkeypatch, privacy=privacy)
    code = wire.main(run_args(kit, out)[1:])
    err = capsys.readouterr()
    assert code == 0, err.out + err.err
    rows = loads_strict((out / MANIFEST_FILENAME).read_bytes())["measured"]["baselines"]["rows"]
    assert privacy in [r["value"] for r in rows if r["metric"] == "privacy"]  # the value really is in the manifest


@pytest.mark.parametrize("risk", [4111111111111111, 4111111111111111.0, 4.111111111111135e+16])
def test_card_shaped_integer_number_still_refuses(tmp_path, monkeypatch, capsys, risk):
    kit, out = _kit(tmp_path, monkeypatch, privacy=0.5, search_risk=risk)
    code = wire.main(run_args(kit, out)[1:])
    err = capsys.readouterr()
    assert code == 1, err.out + err.err
    assert "REFUSED" in err.out
    assert not out.exists()
    report = (scoring_dir(out) / REFUSAL_REPORT).read_text(encoding="utf-8")
    assert "manifest:$.measured.search.points[0].risk: identifier-shape:PAYMENT_CARD" in report, report
    assert "4111111111111" not in report  # content-free: the planted digits are never echoed


@pytest.mark.parametrize(("source", "label"), [
    ("published benchmark 4111111111111111", "PAYMENT_CARD"),  # card as string, beside a Luhn-fraction number
    ("published benchmark 0.4111111111111111", "PAYMENT_CARD"),  # decimal TEXT is still scanned as text
    ("published benchmark someone@example.com", "EMAIL"),
])
def test_identifier_in_manifest_string_still_refuses(tmp_path, monkeypatch, capsys, source, label):
    kit, out = _kit(tmp_path, monkeypatch, source=source)
    code = wire.main(run_args(kit, out)[1:])
    err = capsys.readouterr()
    assert code == 1, err.out + err.err
    assert not out.exists()
    report = (scoring_dir(out) / REFUSAL_REPORT).read_text(encoding="utf-8")
    assert f"manifest:$.measured.baselines.source: identifier-shape:{label}" in report, report
    assert "4111111111111" not in report and "someone@example.com" not in report
