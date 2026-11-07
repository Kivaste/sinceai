"""#61 through the real CLIs: a signed manifest whose narrative carries an identifier fails every reader.

Rows (trigger -> result), on a release built by the real ``pets-release run`` (synthetic minikit):
  test card added to a residual-risk description, re-signed -> verify --full exit 1, recipient verify exit 1,
                                                              dashboard exit 1 writing nothing; value never echoed
"""
from __future__ import annotations

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
