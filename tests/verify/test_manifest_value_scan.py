"""#61 through the real CLIs: a signed manifest that carries an identifier fails every reader.

Rows (trigger -> result), on a release built by the real ``pets-release run`` (synthetic minikit):
  test card added to a residual-risk description, re-signed -> verify --full exit 1, recipient verify exit 1,
                                                              dashboard exit 1 writing nothing; value never echoed
Round-1 review rows (each through validate_manifest AND the dashboard CLI; card = published test number):
  card as an assertion-evidence denominator.n (+ matching gate record) -> identifier-shape:PAYMENT_CARD
  card as a non-evidence gate record's hits                             -> PAYMENT_CARD
  card as a measured score (number outside params)                      -> PAYMENT_CARD
  card as a bindings.lexiconDigests key                                 -> PAYMENT_CARD
  card as a bindings.inputs key                                         -> PAYMENT_CARD
  card as bindings.checkVersions key (check name)                       -> PAYMENT_CARD
  card as signature.keyId                                               -> PAYMENT_CARD
  unchanged real release                                                -> [] (digests, HMAC, key ID not flagged)
"""
from __future__ import annotations

import pytest

CARD = "4111111111111111"  # published test card number


def test_card_in_manifest_narrative_fails_verify_and_dashboard(real_bed, verify_cli, cli, tb, tmp_path):
    m = tb.load(real_bed.release)
    m["residualRisks"][0]["description"] = f"call back card {CARD}"
    real_bed.resign(m)
    for args in (["--full", "--kit", real_bed.kit, real_bed.release], [real_bed.release]):
        r = verify_cli(*args, env=real_bed.env())
        assert r.returncode == 1, r.stdout
        assert "identifier-shape:PAYMENT_CARD" in r.stdout
        assert CARD not in r.stdout + r.stderr
    out = tmp_path / "dash" / "d.html"
    d = cli("dashboard", str(real_bed.release), "--out", str(out))
    assert d.returncode == 1, d.stdout + d.stderr
    assert not out.exists()
    assert CARD not in d.stdout + d.stderr


def _evidence_n(m):
    name = sorted(m["assertionEvidence"])[0]
    ev = m["assertionEvidence"][name]
    ev["denominator"]["n"] = int(CARD)
    for rec in m["gate"]["checks"]:
        if rec["check"] == ev["check"]:
            rec["denominator"]["n"] = int(CARD)


def _gate_hits(m):
    backing = {e["check"] for e in m["assertionEvidence"].values()}
    rec = next(r for r in m["gate"]["checks"] if r["check"] not in backing and r["status"] == "pass")
    rec["hits"] = int(CARD)


def _measured_number(m):
    m["measured"]["privacy"] = {"status": "measured", "source": "synthetic",
                                "components": [{"component": "c1", "before": int(CARD), "after": 0.0}]}


def _lexicon_key(m):
    m["bindings"]["lexiconDigests"][CARD] = "a" * 64


def _inputs_key(m):
    m["bindings"]["inputs"][CARD] = "b" * 64


def _check_versions_key(m):
    m["bindings"]["checkVersions"][CARD] = "1.0.0"


PLANTS = [_evidence_n, _gate_hits, _measured_number, _lexicon_key, _inputs_key, _check_versions_key]


def _shape_errors(m):
    from pets_release.manifest import validate_manifest

    return [e for e in validate_manifest(m) if e.endswith("identifier-shape:PAYMENT_CARD")]


def _dashboard_refuses(cli, release, tmp_path):
    out = tmp_path / "dash" / "d.html"
    d = cli("dashboard", str(release), "--out", str(out))
    assert d.returncode == 1, d.stdout + d.stderr
    assert not out.exists()
    assert CARD not in d.stdout + d.stderr
    return d


@pytest.mark.parametrize("plant", PLANTS, ids=lambda f: f.__name__)
def test_card_in_counts_bindings_fails_validation_and_dashboard(real_bed, cli, tb, tmp_path, plant):
    m = tb.load(real_bed.release)
    plant(m)
    m = real_bed.resign(m)
    assert _shape_errors(m), "planted card must be an identifier-shape error"
    d = _dashboard_refuses(cli, real_bed.release, tmp_path)
    assert "identifier-shape:PAYMENT_CARD" in d.stderr


def test_card_as_signature_key_id_fails_validation_and_dashboard(real_bed, cli, tb, tmp_path):
    m = real_bed.resign(tb.load(real_bed.release))
    m["signature"]["keyId"] = CARD  # outside the signed payload; schema id pattern admits it
    tb.save(real_bed.release, m)
    assert _shape_errors(m)
    d = _dashboard_refuses(cli, real_bed.release, tmp_path)
    assert "identifier-shape:PAYMENT_CARD" in d.stderr


def test_unchanged_real_manifest_has_no_shape_errors(real_bed, tb):
    from pets_release.manifest import validate_manifest

    assert validate_manifest(tb.load(real_bed.release)) == []
