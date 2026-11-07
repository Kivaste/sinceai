"""#61 (writer side): identifier-shaped text anywhere in the manifest's narrative or parameters is refused.

Rule: manifest validation runs the independent identifier detectors (the release rescans' finders) over every
manifest string, map key and parameter value, except the pinned digest/signature/token metadata (bindings,
signature, releaseScopeId, created). Any hit is an ``identifier-shape`` error, so the writer refuses after
assembly (``manifest:`` reason) and no release appears. Error codes name a JSON path and a label, never the value.

Failure rows (trigger -> result):
  Luhn-valid test card in a residual-risk description (absent from tables) -> refused, PAYMENT_CARD
  email in a PET parameter string                                       -> refused, EMAIL
  card as a PET parameter number                                        -> refused, PAYMENT_CARD
  test IBAN as a parameter name (map key)                               -> refused, IBAN
  unchanged fixture                                                     -> released (no false refusal)
Synthetic values only (published test card number, example.com address, published test IBAN).
"""
from __future__ import annotations

import copy

import pytest
from writer_helpers import MASTER, make_candidate, make_kit, producer_context

from pets_release.manifest import validate_manifest
from pets_release.writer import scoring_dir, write_release

CARD = "4111111111111111"  # published test card number (Luhn-valid)


def _write(tmp_path, narrative):
    cand = make_candidate(narrative=narrative)
    kit = make_kit(tmp_path / "kit", cand)
    return write_release(cand, tmp_path / "o" / "rel", MASTER, kit, context=producer_context(cand))


def _nar():
    return copy.deepcopy(dict(make_candidate().narrative))


def _risk(n):
    n["residualRisks"][0]["description"] = f"follow up with card {CARD} holder"
    return "PAYMENT_CARD"


def _param_email(n):
    n["pets"][0]["params"]["contact"] = "someone@example.com"
    return "EMAIL"


def _param_number(n):
    n["pets"][0]["params"]["ref"] = int(CARD)
    return "PAYMENT_CARD"


def _param_key(n):
    n["pets"][0]["params"]["FI2112345600000785"] = "x"  # schema-valid param name shaped as a published test IBAN
    return "IBAN"


@pytest.mark.parametrize("plant", [_risk, _param_email, _param_number, _param_key])
def test_identifier_shape_in_manifest_refuses(tmp_path, plant):
    n = _nar()
    label = plant(n)
    res = _write(tmp_path, n)
    assert res.status == "refused", res.reasons
    assert not res.out.exists()
    assert any(r.startswith("manifest:") and r.endswith(f"identifier-shape:{label}") for r in res.reasons), res.reasons
    report = b"".join(p.read_bytes() for p in scoring_dir(res.out).iterdir())
    assert CARD.encode() not in report and b"someone@example.com" not in report and b"FI2112345600000785" not in report


def test_unchanged_fixture_releases(tmp_path):
    res = _write(tmp_path, _nar())
    assert res.status == "released", res.reasons


def test_metadata_digests_are_not_flagged(tmp_path):
    res = _write(tmp_path, _nar())
    from pets_release.manifest import loads_strict

    m = loads_strict((res.out / "privacy_manifest.json").read_bytes())
    assert validate_manifest(m) == []
    m2 = copy.deepcopy(m)
    m2["residualRisks"][0]["description"] = "token " + m["signature"]["value"]  # a 64-hex outside metadata
    assert any(e.endswith("identifier-shape:HEX64_OUTSIDE_TOKEN") for e in validate_manifest(m2))


def test_flagged_param_keys_never_echoed_in_refusal_report(tmp_path):
    """Round-2 review (Sol): a flagged map key (and a flagged value's parent key) is masked in every reason."""
    n = _nar()
    n["pets"][0]["params"]["passwordHunterTwo"] = "x"
    n["pets"][0]["params"]["loginAliceSmith"] = "someone@example.com"
    res = _write(tmp_path, n)
    assert res.status == "refused"
    assert any(r.endswith("identifier-shape:SECRET") for r in res.reasons), res.reasons
    report = b"".join(p.read_bytes() for p in scoring_dir(res.out).iterdir()).decode("utf-8")
    text = report + "\n".join(res.reasons)
    for s in ("passwordHunterTwo", "loginAliceSmith", "HunterTwo", "AliceSmith", "someone@example.com"):
        assert s not in text, s
