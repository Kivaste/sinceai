"""Personas on a tiny synthetic world (8 visits, 6 people). Seam: pure functions on DataFrames."""

from __future__ import annotations

import pandas as pd
import pytest

from pets_attacker.linkage import QI
from pets_attacker.personas import (
    AGGREGATE_KEYS,
    MappingError,
    broker_attack,
    insider_attack,
)

REC = [f"v{i}" for i in range(8)]
PERSON = ["p0", "p1", "p2", "p3", "p4", "p5", "p0", "p1"]  # p0, p1 visit twice
DAY = ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05", "2025-02-01", "2025-02-02"]
CITY = ["Turku", "Turku", "Raisio", "Naantali", "Turku", "Raisio", "Turku", "Naantali"]
ICD = ["J10", "S72", "I21", "J10", "S72", "I21", "J10", "S72"]


def _original():
    return pd.DataFrame({"visit_id": REC, "arrival_ts": [d + "T09:00:00" for d in DAY], "municipality": CITY, "icd10_primary": ICD})


def _identity():
    return pd.DataFrame({"record_id": REC, "person_id": PERSON})


def _rowmap(order):
    return pd.DataFrame({"protected_row": [str(i) for i in range(len(order))], "original_record_id": [REC[o] for o in order]})


def _identity_release(order):
    """Protected rows in a shuffled order, identical content (B0-like for the QIs)."""
    o = _original().iloc[order].reset_index(drop=True)
    return o, _rowmap(order)


def test_insider_unique_visits_are_reidentified_and_attribute_inferred():
    prot, rm = _identity_release([3, 1, 0, 2, 5, 4, 7, 6])
    out = insider_attack(_original(), prot, rm, _identity(), date_col="arrival_ts", place_col="municipality",
                         record_key="visit_id", sensitive="icd10_primary")
    # v0 and v1 share day+city -> ambiguous; the other six are unique
    assert out["n_targets"] == 8
    assert out["n_unique_claims"] == 6
    assert out["reidentification_rate"] == pytest.approx(6 / 8)
    assert out["claim_precision"] == 1.0
    assert out["attribute_inference_rate"] >= 6 / 8  # ambiguous pair has different icd, so only the 6 unique


def test_insider_blind_when_date_is_removed():
    prot, rm = _identity_release([0, 1, 2, 3, 4, 5, 6, 7])
    prot = prot.drop(columns=["arrival_ts"])
    out = insider_attack(_original(), prot, rm, _identity(), date_col="arrival_ts", place_col="municipality",
                         record_key="visit_id", sensitive="icd10_primary")
    assert out["reidentification_rate"] == 0.0
    assert out["n_unique_claims"] == 0
    assert out["claim_precision"] is None


def test_insider_rows_dropped_from_release_are_not_targets():
    prot, rm = _identity_release([0, 1, 2, 3])
    out = insider_attack(_original(), prot, rm, _identity(), date_col="arrival_ts", place_col="municipality",
                         record_key="visit_id", sensitive="icd10_primary")
    assert out["n_targets"] == 4


def _adv(rows):
    return pd.DataFrame(rows, columns=["adv_row_id", "display_name", "profile_city", "posted_ts"])


def test_broker_links_by_fuzzy_name_city_and_time():
    prot = _original().assign(patient_name=["Anna Virtanen", "Pekka Korhonen", "Mari Nieminen", "Jussi Laine",
                                             "Liisa Heino", "Eero Salo", "Anna Virtanen", "Pekka Korhonen"])
    rm = _rowmap(list(range(8)))
    qis = [QI("name", ("display_name",), ("patient_name",)), QI("exact", ("profile_city",), ("municipality",)),
           QI("time", ("posted_ts",), ("arrival_ts",), window=(12, 1))]
    adv = _adv([("a0", "Anna Virtanin", "Turku", "2025-01-01T10:00:00"),  # typo, unique name+time
                ("a1", "Zed Nobody", "Turku", "2025-01-01T10:00:00"),     # not in data
                ("a2", "Mari Nieminen", "Raisio", "2025-01-02T10:00:00")])
    atruth = pd.DataFrame({"adv_row_id": ["a0", "a1", "a2"], "person_id": ["p0", "pX", "p2"]})
    out = broker_attack(adv, atruth, prot, rm, _identity(), qis, original=_original(), record_key="visit_id",
                        sensitive="icd10_primary")
    assert out["n_targets"] == 2  # a1 is not in the data
    assert out["reidentification_rate"] == 1.0
    assert out["n_unique_claims"] == 2  # a1 has no candidate: no claim
    assert out["claim_precision"] == 1.0
    assert out["attribute_inference_rate"] == 1.0


def test_broker_wrong_claim_lowers_precision():
    prot = _original().assign(patient_name=["Anna Virtanen"] * 8)
    prot.loc[0, "patient_name"] = "Mari Nieminen"
    rm = _rowmap(list(range(8)))
    qis = [QI("name", ("display_name",), ("patient_name",))]
    adv = _adv([("a0", "Mari Nieminen", "", "")])
    atruth = pd.DataFrame({"adv_row_id": ["a0"], "person_id": ["p4"]})  # attacker's claim lands on the wrong person
    out = broker_attack(adv, atruth, prot, rm, _identity(), qis)
    assert out["n_unique_claims"] == 1
    assert out["claim_precision"] == 0.0
    assert out["reidentification_rate"] == 0.0


def test_output_is_aggregate_only():
    prot, rm = _identity_release([0, 1, 2, 3, 4, 5, 6, 7])
    out = insider_attack(_original(), prot, rm, _identity(), date_col="arrival_ts", place_col="municipality",
                         record_key="visit_id", sensitive="icd10_primary")
    assert set(out) == set(AGGREGATE_KEYS)
    for k, v in out.items():
        assert v is None or isinstance(v, (bool, int, float)), k


def test_single_target_ladder_release_is_certain():
    orig = pd.DataFrame({"visit_id": ["v0"], "arrival_ts": ["2025-03-20T10:10:00"], "municipality": ["Kaarina"], "icd10_primary": ["J10.1"]})
    prot = pd.DataFrame({"arrival_ts": ["2025-03-01T10:00"], "municipality": ["other"], "icd10_primary": ["J10"]})
    rm = pd.DataFrame({"protected_row": ["0"], "original_record_id": ["v0"]})
    ident = pd.DataFrame({"record_id": ["v0"], "person_id": ["p0"]})
    adv = pd.DataFrame({"adv_row_id": ["a0"], "t": ["2025-03-20T10:10:00"], "p": ["Kaarina"]})
    atruth = pd.DataFrame({"adv_row_id": ["a0"], "person_id": ["p0"]})
    qis = [QI("time", ("t",), ("arrival_ts",), window=(1, 1)), QI("exact", ("p",), ("municipality",))]
    out = broker_attack(adv, atruth, prot, rm, ident, qis, original=orig, record_key="visit_id", sensitive="icd10_primary")
    assert out["reidentification_rate"] == 1.0 and out["attribute_inference_rate"] == 1.0  # truncated ICD is a prefix


@pytest.mark.parametrize("mutate", [
    lambda rm: rm.iloc[0:0],                                              # empty
    lambda rm: rm.iloc[:-1],                                              # incomplete
    lambda rm: pd.concat([rm, rm.iloc[:1]], ignore_index=True),           # duplicate protected row
    lambda rm: rm.assign(original_record_id=["v0"] * len(rm)),            # duplicate record ids
    lambda rm: rm.assign(original_record_id=["zz"] + list(rm.original_record_id[1:])),  # unknown record
    lambda rm: rm.assign(protected_row=["x"] + list(rm.protected_row[1:])),             # non-integer row
    lambda rm: rm.assign(protected_row=[str(i + 1) for i in range(len(rm))]),           # out of range
])
def test_bad_row_maps_are_refused(mutate):
    prot, rm = _identity_release([0, 1, 2, 3, 4, 5, 6, 7])
    with pytest.raises(MappingError):
        insider_attack(_original(), prot, mutate(rm), _identity(), date_col="arrival_ts", place_col="municipality",
                       record_key="visit_id", sensitive="icd10_primary")
    with pytest.raises(MappingError):
        broker_attack(_adv([]), pd.DataFrame({"adv_row_id": [], "person_id": []}), prot, mutate(rm), _identity(),
                      [QI("exact", ("profile_city",), ("municipality",))])


def test_row_map_missing_columns_or_identity_gaps_are_refused():
    prot, rm = _identity_release([0, 1, 2, 3, 4, 5, 6, 7])
    with pytest.raises(MappingError):
        insider_attack(_original(), prot, rm.rename(columns={"protected_row": "r"}), _identity(), date_col="arrival_ts",
                       place_col="municipality", record_key="visit_id")
    with pytest.raises(MappingError):
        insider_attack(_original(), prot, rm, _identity().iloc[:-1], date_col="arrival_ts", place_col="municipality",
                       record_key="visit_id")


def test_zero_targets_is_not_evaluated():
    prot, rm = _identity_release([0, 1, 2, 3, 4, 5, 6, 7])
    adv = _adv([("a0", "Nobody", "Turku", "2025-01-01T10:00:00")])
    atruth = pd.DataFrame({"adv_row_id": ["a0"], "person_id": ["pX"]})
    out = broker_attack(adv, atruth, prot, rm, _identity(), [QI("exact", ("profile_city",), ("municipality",))])
    assert out["evaluated"] is False and out["n_targets"] == 0

