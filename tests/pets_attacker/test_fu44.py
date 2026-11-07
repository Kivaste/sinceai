"""Follow-up #44: attacker fail-open paths must refuse; unknown QI kinds raise."""

from __future__ import annotations

import pandas as pd
import pytest

from pets_attacker.linkage import QI, Matcher, RungError, qis_from_spec
from pets_attacker.personas import MappingError, broker_attack

RUNGS = {"municipality": "keep", "arrival_ts": "ts.exact", "date_of_birth": "dob.year", "sex": "keep",
         "postcode": "keep", "patient_name": "keep", "mh": "ts.month_hour"}


def _prot():
    return pd.DataFrame({
        "patient_name": ["Anna Virtanen", "Pekka Korhonen"], "municipality": ["Turku", "Raisio"],
        "arrival_ts": ["2025-03-01T10:30:00", "2025-03-09T08:00:00"], "date_of_birth": ["1980", "1950"],
        "sex": ["F", "M"], "postcode": ["20***", "21***"], "mh": ["2025-03-01T10:00", "2025-03-01T11:00"]})


# item 2
@pytest.mark.parametrize("kind", ["geo", "suffix", "number", "bogus"])
def test_unknown_qi_kind_raises(kind):
    with pytest.raises(ValueError):
        qis_from_spec([{"kind": kind, "adversary": ["a"], "protected": ["municipality"]}], ["municipality"])


def test_qi_with_absent_protected_columns_is_still_dropped():
    assert qis_from_spec([{"kind": "exact", "adversary": ["a"], "protected": ["gone"]}], ["municipality"]) == []


def test_qi_with_unknown_kind_raises_even_when_column_absent():
    with pytest.raises(ValueError):
        qis_from_spec([{"kind": "geo", "adversary": ["a"], "protected": ["gone"]}], ["municipality"])


# item 1
@pytest.mark.parametrize("val", ["abc", "1980", "-3", "250"])
def test_unparsable_or_implausible_adversary_age_is_refused(val):
    m = Matcher(_prot(), [QI("age", ("a",), ("date_of_birth",))], RUNGS)
    with pytest.raises(RungError):
        m.candidates({"a": val})


def test_plausible_adversary_age_still_matches():
    m = Matcher(_prot(), [QI("age", ("a",), ("date_of_birth",))], RUNGS)
    cand, used = m.candidates({"a": "45"})
    assert used == 1 and list(cand) == [0]


def test_unparsable_adversary_time_is_refused():
    m = Matcher(_prot(), [QI("time", ("t",), ("arrival_ts",))], RUNGS)
    with pytest.raises(RungError):
        m.candidates({"t": "yesterday"})


def test_broker_attack_refuses_on_unparsable_adversary_age():
    adv = pd.DataFrame({"adv_row_id": ["a0"], "a": ["1980"]})
    with pytest.raises(RungError):
        broker_attack(adv, pd.DataFrame({"x": ["a0"], "y": ["p0"]}), _prot(),
                      pd.DataFrame({"protected_row": ["0", "1"], "original_record_id": ["v0", "v1"]}),
                      pd.DataFrame({"r": ["v0", "v1"], "p": ["p0", "p1"]}),
                      [QI("age", ("a",), ("date_of_birth",))], rungs=RUNGS)


# item 3
def test_all_wildcard_column_does_not_count_as_used():
    prot = pd.DataFrame({"municipality": ["", "***"]})
    m = Matcher(prot, [QI("exact", ("p",), ("municipality",))], RUNGS)
    cand, used = m.candidates({"p": "Turku"})
    assert used == 0 and len(cand) == 2


def test_all_wildcard_one_row_release_mints_no_claim():
    prot = pd.DataFrame({"municipality": [""]})
    m = Matcher(prot, [QI("exact", ("p",), ("municipality",))], RUNGS)
    _, used = m.candidates({"p": "Turku"})
    assert used == 0


# item 4
def test_month_hour_exact_instant_window_is_tight():
    m = Matcher(_prot(), [QI("time", ("t",), ("mh",), window=(0, 0))], RUNGS)
    cand, _ = m.candidates({"t": "2025-03-01T10:30:00"})
    assert list(cand) == [0]
    cand, _ = m.candidates({"t": "2025-03-01T11:00:00"})
    assert list(cand) == [1]
    cand, _ = m.candidates({"t": "2025-03-01T09:59:00"})
    assert len(cand) == 0


# item 5
@pytest.mark.parametrize("kind,col", [("name", "patient_name"), ("sex", "sex"), ("postcode", "postcode")])
def test_name_sex_postcode_need_valid_rung(kind, col):
    adv = ("a",)
    with pytest.raises(RungError):
        Matcher(_prot(), [QI(kind, adv, (col,))], {})
    with pytest.raises(RungError):
        Matcher(_prot(), [QI(kind, adv, (col,))], {col: "ts.exact"})
    Matcher(_prot(), [QI(kind, adv, (col,))], {col: "keep"})
    Matcher(_prot(), [QI(kind, adv, (col,))], {col: "withheld"})


# item 7
def test_truth_with_too_few_columns_is_a_mapping_error():
    prot = _prot()
    with pytest.raises(MappingError):
        broker_attack(pd.DataFrame({"adv_row_id": ["a0"], "p": ["Turku"]}), pd.DataFrame({"only": ["a0"]}), prot,
                      pd.DataFrame({"protected_row": ["0", "1"], "original_record_id": ["v0", "v1"]}),
                      pd.DataFrame({"r": ["v0", "v1"], "p": ["p0", "p1"]}),
                      [QI("exact", ("p",), ("municipality",))], rungs=RUNGS)


def test_identity_with_too_few_columns_is_a_mapping_error():
    with pytest.raises(MappingError):
        broker_attack(pd.DataFrame({"adv_row_id": ["a0"], "p": ["Turku"]}), pd.DataFrame({"a": ["a0"], "b": ["p0"]}), _prot(),
                      pd.DataFrame({"protected_row": ["0", "1"], "original_record_id": ["v0", "v1"]}),
                      pd.DataFrame({"r": ["v0", "v1"]}),
                      [QI("exact", ("p",), ("municipality",))], rungs=RUNGS)
