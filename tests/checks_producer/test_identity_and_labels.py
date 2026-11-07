"""#57: person-k identity keying, content-free violation labels, numbers in the manifest.

Rules added (trigger -> result), all through ticket 04's runner and the production checks:
  two source spellings of one person (pseudonymiser-normalised equal), token linked   -> one person (k=1 < 2: fail)
  two spellings, person not released                                                   -> denominator counts one person
  spellings equal under the person label's normalisation (NATIONAL_ID case)           -> one person
  no normaliser in the context / normaliser raises or returns a non-string            -> not_run / error
  producer context                                                                     -> injects pseudonym.normalise
  one canonical person released under two different tokens                            -> error (conflicting mapping)
  two canonical persons released under one token                                      -> error (conflicting mapping)
  identifier planted in an undeclared header and its cell                             -> record holds no raw name
  identifier planted in an undeclared released file name                              -> record holds no raw name
  declared file and column names                                                      -> kept in the record
  numeric identifier stored as a JSON number in the manifest                          -> original-values fail
  digit-only key material stored as a JSON integer in the manifest                     -> key-material fail
  non-finite JSON constant (NaN) in the manifest                                       -> error (unsupported scalar)
All values are synthetic and hand-made.
"""

from __future__ import annotations

import json

import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.pseudonym import RECORD_KEY, normalise
from pets_release.run.context import person_normaliser


def _run(name, release, contract, context):
    chk = {c.name: c for c in all_checks()}[name]
    return run_checks(release, contract, context, checks=[chk]).to_dict()["records"][0]


PERSON_K = "producer.person-k"
ORIGINALS = "producer.original-values"
HASHES = "producer.unkeyed-hashes"
KEYS = "producer.key-material"


def _ctx(h, visits, persons, label="RECORD_KEY"):
    return {
        "k": 2,
        "source": {"ed_visits": h.frame({"visit_id": visits, "patient_hetu": persons})},
        "rowmaps": {"ed_visits": h.rowmap(visits)},
        "record_keys": {"ed_visits": "visit_id"},
        # the production injection: the pseudonymiser's own normalise, bound to the person label
        "person": {"table": "ed_visits", "column": "patient_hetu", "normalise": person_normaliser(label)},
        "joins": [],
    }


LINKED = {"tokens": [("ed_visits", "patient_hetu")]}


# --- 1. person-k identity keying -------------------------------------------------------


def test_two_spellings_of_one_linked_person_are_one_person(h):
    visits = ["V0", "V1"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "patient_hetu": ["T1", "T1"], "hour": ["08", "08"]}})
    contract = h.contract([("ed_visits", "hour")], k=2, **LINKED)
    rec = _run(PERSON_K, rel, contract, _ctx(h, visits, ["P-0001", " P-0001 "]))
    assert rec["denominator"]["n"] == 1
    assert rec["status"] == "fail" and rec["hits"] == 1


def test_two_spellings_unlinked_count_as_one_person(h):
    visits = ["V0", "V1", "V2"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "hour": ["08", "08", "08"]}})
    contract = h.contract([("ed_visits", "hour")], k=2)
    rec = _run(PERSON_K, rel, contract, _ctx(h, visits, ["P-0001", "P-0001\t", "P-0002"]))
    assert rec["denominator"]["n"] == 2
    assert rec["status"] == "pass"


def test_identity_uses_the_person_labels_pseudonymiser_normalisation(h):
    visits = ["V0", "V1"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "patient_hetu": ["T1", "T1"], "hour": ["08", "08"]}})
    contract = h.contract([("ed_visits", "hour")], k=2, **LINKED)
    ctx = _ctx(h, visits, ["010101-123a", "010101-123A"], label="NATIONAL_ID")
    rec = _run(PERSON_K, rel, contract, ctx)
    assert rec["denominator"]["n"] == 1 and rec["status"] == "fail"


def test_missing_normaliser_is_not_run_and_a_failing_one_is_an_error(h):
    visits = ["V0", "V1"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "hour": ["08", "08"]}})
    contract = h.contract([("ed_visits", "hour")], k=2)
    ctx = _ctx(h, visits, ["P-0001", "P-0002"])
    ctx["person"].pop("normalise")
    assert _run(PERSON_K, rel, contract, ctx)["status"] == "not_run"

    def boom(_v):
        raise ValueError("x")

    for bad in (boom, lambda v: None, "not callable"):
        ctx["person"]["normalise"] = bad
        assert _run(PERSON_K, rel, contract, ctx)["status"] == "error"


def test_unknown_person_label_is_refused_by_the_context_builder():
    with pytest.raises(ValueError):
        person_normaliser("NOT_A_LABEL")


def test_producer_context_injects_the_pseudonymiser_normalisation():
    import pandas as pd

    from pets_release.policy import get_policy
    from pets_release.pseudonym import MasterKey
    from pets_release.run.context import producer_context

    src = {"ed_visits": pd.DataFrame({"visit_id": ["V0"], "patient_hetu": ["P-0001"]}, dtype=str)}
    ctx = producer_context(scenario_id="HEALTH-S1", policy=get_policy("HEALTH-S1"), source=src,
                           master=MasterKey(b"m" * 32), scope_id="s", recipient="default", contract={},
                           released=None)
    norm = ctx["person"]["normalise"]
    assert norm(" P-0001 ") == norm("P-0001") == normalise("P-0001", RECORD_KEY)


@pytest.mark.parametrize(
    "persons,tokens",
    [
        (["P-0001", "P-0001 ", "P-0002", "P-0002"], ["T1", "T2", "T3", "T3"]),  # one person, two tokens
        (["P-0001", "P-0002", "P-0003", "P-0003"], ["T1", "T1", "T3", "T3"]),  # two persons, one token
    ],
)
def test_conflicting_person_token_mapping_is_an_error(h, persons, tokens):
    visits = ["V0", "V1", "V2", "V3"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "patient_hetu": tokens, "hour": ["08"] * 4}})
    contract = h.contract([("ed_visits", "hour")], k=2, **LINKED)
    assert _run(PERSON_K, rel, contract, _ctx(h, visits, persons))["status"] == "error"


# --- 2. content-free labels in violation records -----------------------------------------

HETU = "121285-987X"
KEY = "synthetic-test-key-0123456789-abcdefghij"


@pytest.fixture
def vctx(h):
    return {
        "source": {"ed_visits": h.frame({"visit_id": ["V1", "V2"], "patient_hetu": [HETU, "010203A123B"],
                                         "phone": ["12345678901", "10987654321"]})},
        "identifiers": [{"table": "ed_visits", "column": "patient_hetu"},
                        {"table": "ed_visits", "column": "phone"}],
        "keys": [KEY, "98765432109876543210"],
    }


DECLARED = {"files": {"ed_visits.csv": {"columns": {"sex": {}, "note": {}}}}}


def test_identifier_in_undeclared_header_and_cell_never_reaches_the_record(h, vctx):
    rel = h.release({"ed_visits": {"sex": ["F", "M"], HETU: [HETU, "x"]}})
    rec = _run(ORIGINALS, rel, DECLARED, vctx)
    assert rec["status"] == "fail"
    dumped = json.dumps(rec)
    assert HETU not in dumped and HETU.casefold() not in dumped.casefold()
    assert {v["file"] for v in rec["violations"]} == {"ed_visits.csv"}  # declared file name kept
    assert all(v["column"] in {"column#1", "<header>"} for v in rec["violations"])


def test_identifier_in_undeclared_file_name_never_reaches_the_record(h, vctx):
    rel = h.release({HETU: {"note": [HETU, "x"]}})
    for name in (ORIGINALS, KEYS):
        rec = _run(name, rel, DECLARED, vctx)
        assert HETU not in json.dumps(rec), name
    rec = _run(ORIGINALS, rel, DECLARED, vctx)
    assert rec["status"] == "fail"
    assert {v["file"] for v in rec["violations"]} == {"file#0"}
    assert {v["column"] for v in rec["violations"]} == {"column#0"}  # column of an undeclared file


def test_declared_names_are_kept(h, vctx):
    rel = h.release({"ed_visits": {"sex": ["F", "M"], "note": ["ok", HETU]}})
    rec = _run(ORIGINALS, rel, DECLARED, vctx)
    assert [(v["file"], v["column"], v["locations"]) for v in rec["violations"]] == [("ed_visits.csv", "note", [1])]


# --- 3. JSON numbers in the manifest are scanned --------------------------------------------


def _clean(h):
    return h.release({"ed_visits": {"sex": ["F", "M"], "note": ["ok", ""]}})


def test_numeric_identifier_as_json_number_in_manifest_is_refused(h, vctx):
    rel = _clean(h)
    (rel / "privacy_manifest.json").write_text('{"x": 12345678901}', encoding="utf-8")
    rec = _run(ORIGINALS, rel, DECLARED, vctx)
    assert rec["status"] == "fail"
    assert rec["violations"][0]["file"] == "privacy_manifest.json"
    assert "12345678901" not in json.dumps(rec)


def test_digit_only_key_as_json_integer_in_manifest_is_refused(h, vctx):
    rel = _clean(h)
    (rel / "privacy_manifest.json").write_text('{"x": [1, 98765432109876543210]}', encoding="utf-8")
    rec = _run(KEYS, rel, DECLARED, vctx)
    assert rec["status"] == "fail"
    assert "98765432109876543210" not in json.dumps(rec)


@pytest.mark.parametrize("name", [ORIGINALS, HASHES, KEYS])
def test_non_finite_json_constant_in_manifest_is_an_error(h, vctx, name):
    rel = _clean(h)
    (rel / "privacy_manifest.json").write_text('{"x": NaN}', encoding="utf-8")
    assert _run(name, rel, DECLARED, vctx)["status"] == "error"


@pytest.mark.parametrize("name", [ORIGINALS, HASHES, KEYS])
def test_clean_manifest_with_numbers_bools_null_passes(h, vctx, name):
    rel = _clean(h)
    (rel / "privacy_manifest.json").write_text('{"k": 5, "share": 0.05, "ok": true, "x": null}', encoding="utf-8")
    assert _run(name, rel, DECLARED, vctx)["status"] == "pass"
