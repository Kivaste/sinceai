"""healthInText refuses only where the contract requires it; lexicon digest is canonical."""
import shutil

from pets_release.checks import text as health

CUSTOMER = "customer"


def test_health_term_refuses_when_contract_requires(gate, release, contract):
    folder = release([[(CUSTOMER, "I could not pay because of my diabetes")]])
    rec = gate("text.health", folder, contract(health_required=True))
    assert rec["status"] == "fail" and rec["hits"] == 1
    (v,) = rec["violations"]
    assert v["label"] == "HEALTH" and v["severity"] == "high"


def test_inflected_finnish_and_swedish_terms_are_hits(gate, release, contract):
    folder = release([[
        (CUSTOMER, "olin sairaalassa viikon"),
        (CUSTOMER, "jag var sjukskriven"),
    ]])
    rec = gate("text.health", folder, contract(health_required=True))
    assert rec["status"] == "fail" and rec["hits"] == 2


def test_health_term_does_not_refuse_when_not_required(gate, release, contract):
    folder = release([[(CUSTOMER, "I could not pay because of my diabetes")]])
    rec = gate("text.health", folder, contract(health_required=False))
    assert rec["status"] == "pass"
    assert rec["hits"] == 1
    assert rec["violations"][0]["severity"] == "low"


def test_no_health_terms_passes(gate, release, contract):
    folder = release([[(CUSTOMER, "my invoice is wrong")]])
    rec = gate("text.health", folder, contract(health_required=True))
    assert rec["status"] == "pass" and rec["hits"] == 0
    assert rec["denominator"] == {"unit": "turns", "n": 1}


def test_health_placeholder_is_not_a_hit(gate, release, contract):
    folder = release([[(CUSTOMER, "because of my [HEALTH_1]")]])
    rec = gate("text.health", folder, contract(health_required=True))
    assert rec["status"] == "pass" and rec["hits"] == 0


def test_contract_without_requirement_refuses(gate, release, contract):
    """#56: an absent healthInTextRequired is treated as required (fail closed)."""
    folder = release([[(CUSTOMER, "because of my diabetes")]])
    c = contract()
    del c["healthInTextRequired"]
    rec = gate("text.health", folder, c)
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["severity"] == "high"


def test_malformed_requirement_in_contract_is_an_error(gate, release, contract):
    folder = release([[(CUSTOMER, "my invoice is wrong")]])
    c = contract()
    c["healthInTextRequired"] = "yes"
    rec = gate("text.health", folder, c)
    assert rec["status"] == "error"


def test_bound_lexicon_digest_mismatch_is_an_error(gate, release, contract):
    folder = release([[(CUSTOMER, "my invoice is wrong")]])
    manifest = {"bindings": {"lexiconDigests": {health.LEXICON_NAME: "0" * 64}}}
    rec = gate("text.health", folder, contract(), {"phase": "gate", "manifest": manifest})
    assert rec["status"] == "error"
    manifest["bindings"]["lexiconDigests"][health.LEXICON_NAME] = health.lexicon_digest()
    rec = gate("text.health", folder, contract(), {"phase": "gate", "manifest": manifest})
    assert rec["status"] == "pass"


def test_lexicon_digest_ignores_line_endings_and_row_order(tmp_path):
    src = health.LEXICON_PATH.read_text(encoding="utf-8").splitlines()
    shuffled = tmp_path / "lex.csv"
    shuffled.write_bytes(("\r\n".join([src[0]] + list(reversed(src[1:]))) + "\r\n").encode("utf-8"))
    assert health.lexicon_digest(shuffled) == health.lexicon_digest()
    copy = tmp_path / "copy.csv"
    shutil.copy(health.LEXICON_PATH, copy)
    with open(copy, "a", encoding="utf-8") as fh:
        fh.write("newterm,en,exact\n")
    assert health.lexicon_digest(copy) != health.lexicon_digest()
    assert len(health.lexicon_digest()) == 64
