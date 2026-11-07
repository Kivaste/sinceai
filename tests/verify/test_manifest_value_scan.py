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
  card as release.releaseScopeId (all digits, fits the [0-9a-f]{16} pattern) -> PAYMENT_CARD (not exempt)
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


def _scope_id_digits(m):
    # round-3 review (Grok): an all-digit value in a digest-pattern position is scanned, not exempt. The card's
    # 16 digits fully match releaseScopeId's [0-9a-f]{16} pattern, so only the all-digit rule catches it.
    m["release"]["releaseScopeId"] = CARD


PLANTS = [_evidence_n, _gate_hits, _measured_number, _lexicon_key, _inputs_key, _check_versions_key,
          _scope_id_digits]


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


# --- the scan is a registered release-scope check (round-3 review, Sol): named, versioned record in the gate,
# re-run by recipient (limited) verify -------------------------------------------------------------------------
SCAN = "release.manifest-values"


def test_real_run_gate_records_the_manifest_scan(real_bed, tb):
    m = tb.load(real_bed.release)
    rec = next((r for r in m["gate"]["checks"] if r["check"] == SCAN), None)
    assert rec is not None, "the real run's gate carries no manifest-scan record"
    assert (rec["scope"], rec["status"], rec["hits"]) == ("release", "pass", 0)
    assert rec["denominator"]["n"] >= 1
    assert m["bindings"]["checkVersions"][SCAN] == rec["version"]


def test_recipient_verify_reruns_the_manifest_scan(real_bed, verify_cli, tb):
    """An attested not_applicable is contradicted by the re-run: proof that limited verify runs it by name."""
    m = tb.load(real_bed.release)
    rec = next(r for r in m["gate"]["checks"] if r["check"] == SCAN)
    rec.update(status="not_applicable", hits=0, denominator={**rec["denominator"], "n": 0})
    real_bed.resign(m)
    r = verify_cli(real_bed.release, env=real_bed.env())
    assert r.returncode == 1, r.stdout
    assert f"check {SCAN} [release]: status mismatch (manifest not_applicable, re-run pass)" in r.stdout, r.stdout


# --- no echo of a flagged map key (round-2 review, Sol) -------------------------------------------------------
SECRET_KEY = "passwordHunterTwo"  # schema-valid param name that the secrets detector flags (cue + value)
LOGIN_KEY = "loginAliceSmith"  # username detector: cue + handle


def _plant_keys(m):
    params = m["pets"][0]["params"]
    params[SECRET_KEY] = "x"
    params[LOGIN_KEY] = "someone@example.com"  # its value is flagged too: the parent key must not appear in its path


def _no_echo(text):
    for s in (SECRET_KEY, LOGIN_KEY, "HunterTwo", "AliceSmith", "someone@example.com"):
        assert s not in text, s


def test_flagged_keys_never_echoed_by_validation_verify_or_dashboard(real_bed, verify_cli, cli, tb, tmp_path):
    from pets_release.manifest import validate_manifest

    m = tb.load(real_bed.release)
    _plant_keys(m)
    m = real_bed.resign(m)
    errs = validate_manifest(m)
    assert any(e.endswith("identifier-shape:SECRET") for e in errs), errs
    assert any(e.endswith("identifier-shape:USERNAME") for e in errs), errs
    assert any(e.endswith("identifier-shape:EMAIL") for e in errs), errs
    _no_echo("\n".join(errs))
    for args in (["--full", "--kit", real_bed.kit, real_bed.release], [real_bed.release]):
        r = verify_cli(*args, env=real_bed.env())
        assert r.returncode == 1, r.stdout
        assert "identifier-shape:SECRET" in r.stdout
        _no_echo(r.stdout + r.stderr)
    d = _dashboard_refuses(cli, real_bed.release, tmp_path)
    assert "identifier-shape:SECRET" in d.stderr
    _no_echo(d.stdout + d.stderr)
