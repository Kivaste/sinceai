"""Per-person k (producer scope) over every released QI, incl. hour and join-derived QIs."""

from __future__ import annotations

import pytest

from pets_release.checks import all_checks, run_checks


class _Via04:
    """Runs one registered check through ticket 04's runner; returns its CheckRecord dict."""

    def __init__(self, name):
        self.check = {c.name: c for c in all_checks()}[name]

    def run(self, release, contract, context):
        return run_checks(release, contract, context, checks=[self.check]).to_dict()["records"][0]


PERSON_K = _Via04("producer.person-k")


def _health_ctx(h, visits, persons, labs=None, lab_visits=None):
    source = {"ed_visits": h.frame({"visit_id": visits, "patient_hetu": persons})}
    rowmaps = {"ed_visits": h.rowmap(visits)}
    keys = {"ed_visits": "visit_id"}
    joins = []
    if labs is not None:
        source["lab_results"] = h.frame({"lab_id": labs, "visit_id": lab_visits})
        rowmaps["lab_results"] = h.rowmap(labs)
        keys["lab_results"] = "lab_id"
        joins = [
            {"table": "lab_results", "column": "visit_id", "ref_table": "ed_visits", "ref_column": "visit_id"}
        ]
    return {
        "k": 5,
        "source": source,
        "rowmaps": rowmaps,
        "record_keys": keys,
        "person": {"table": "ed_visits", "column": "patient_hetu"},
        "joins": joins,
    }


VISITS = [f"V{i:02d}" for i in range(10)]
PERSONS = [f"P{i:02d}" for i in range(10)]
WEEK = ["2030-W10"] * 10
HOUR = ["08"] * 5 + ["09"] * 3 + ["10"] * 2


def test_hour_alongside_week_lowers_person_k(h):
    rel = h.release({"ed_visits": {"visit_tok": VISITS, "arrival_week": WEEK, "arrival_hour": HOUR}})
    ctx = _health_ctx(h, VISITS, PERSONS)

    week_only = PERSON_K.run(rel, h.contract([("ed_visits", "arrival_week")]), ctx)
    week_hour = PERSON_K.run(
        rel, h.contract([("ed_visits", "arrival_week"), ("ed_visits", "arrival_hour")]), ctx
    )

    assert week_only["status"] == "pass"
    assert week_only["hits"] == 0
    assert week_only["denominator"] == {"unit": "persons", "n": 10}
    # classes of 5, 3 and 2 persons: the 3 + 2 persons fall below k=5
    assert week_hour["status"] == "fail"
    assert week_hour["hits"] == 5
    assert week_hour["scope"] == "producer"


LABS = [f"L{i:02d}" for i in range(20)]
LAB_VISITS = [VISITS[i // 2] for i in range(20)]  # two labs per visit
LAB_DAY = [f"2030-03-{(i // 2) + 1:02d}" for i in range(20)]  # one distinct day per visit


def test_lab_sampled_day_counts_as_qi_of_joined_visit(h):
    rel = h.release(
        {
            "ed_visits": {"visit_tok": VISITS, "sex": ["F"] * 10},
            "lab_results": {"visit_tok": LAB_VISITS, "sampled_day": LAB_DAY},
        }
    )
    ctx = _health_ctx(h, VISITS, PERSONS, LABS, LAB_VISITS)

    visit_only = PERSON_K.run(rel, h.contract([("ed_visits", "sex")]), ctx)
    with_lab = PERSON_K.run(
        rel, h.contract([("ed_visits", "sex"), ("lab_results", "sampled_day")]), ctx
    )

    assert visit_only["status"] == "pass"
    assert with_lab["status"] == "fail"
    assert with_lab["hits"] == 10  # every visit is unique once its lab day is attached
    assert with_lab["denominator"] == {"unit": "persons", "n": 10}
    (v,) = with_lab["violations"]
    assert v["label"] == "quasiIdentifiersBelowK"
    assert v["file"] == "ed_visits.csv"
    assert v["locations"] == list(range(10))


def test_released_person_token_links_visits_of_one_person(h):
    # 6 persons, 2 visits each: P00..P04 visit at 08 and 09, P05 twice at 08.
    # Per visit: hour 08 has 6 persons, 09 has 5 -> all pass.
    # Person token released: the visit pair is the unit; P05's (08, 08) is unique.
    visits = [f"V{i:02d}" for i in range(12)]
    persons = [f"P{i // 2:02d}" for i in range(12)]
    hour = ["08", "09"] * 5 + ["08", "08"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "person_tok": persons, "hour": hour}})
    ctx = _health_ctx(h, visits, persons)
    unlinked = PERSON_K.run(rel, h.contract([("ed_visits", "hour")]), ctx)
    linked = PERSON_K.run(
        rel, h.contract([("ed_visits", "hour")], tokens=[("ed_visits", "patient_hetu")]), ctx
    )
    assert unlinked["status"] == "pass"
    assert unlinked["denominator"]["n"] == 6
    assert linked["status"] == "fail"
    assert linked["hits"] == 1
    assert linked["violations"][0]["locations"] == [10, 11]


def _linked_fixture(h):
    visits = [f"V{i:02d}" for i in range(12)]
    persons = [f"P{i // 2:02d}" for i in range(12)]
    hour = ["08", "09"] * 5 + ["08", "08"]
    rel = h.release({"ed_visits": {"visit_tok": visits, "person_tok": persons, "hour": hour}})
    return rel, _health_ctx(h, visits, persons)


def test_person_token_released_under_another_name_links_via_released_as(h):
    rel, ctx = _linked_fixture(h)
    ctx["person"] = {**ctx["person"], "released_as": [{"table": "ed_visits", "column": "person_tok"}]}
    rec = PERSON_K.run(rel, h.contract([("ed_visits", "hour")], tokens=[("ed_visits", "person_tok")]), ctx)
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["locations"] == [10, 11]


@pytest.mark.parametrize("derived", ["patient_hetu", "ed_visits.patient_hetu"])
def test_person_token_links_via_token_derived_from(h, derived):
    rel, ctx = _linked_fixture(h)
    contract = h.contract([("ed_visits", "hour")], tokens=[("ed_visits", "person_tok")])
    contract["tokens"][0]["derived_from"] = derived
    rec = PERSON_K.run(rel, contract, ctx)
    assert rec["status"] == "fail" and rec["hits"] == 1


def test_unrelated_token_released_under_another_name_does_not_link(h):
    rel, ctx = _linked_fixture(h)
    contract = h.contract([("ed_visits", "hour")], tokens=[("ed_visits", "visit_tok")])
    contract["tokens"][0]["derived_from"] = "visit_id"
    assert PERSON_K.run(rel, contract, ctx)["status"] == "pass"


def test_unidentified_records_never_inflate_k_and_count_as_below_k(h):
    # 4 identified F persons + 3 F visits with no person ID (possibly one person).
    # If the unidentified visits counted as persons, the F class would reach k=7.
    visits = VISITS[:7]
    persons = ["P01", "P02", "P03", "P04", "", "", ""]
    rel = h.release({"ed_visits": {"visit_tok": visits, "sex": ["F"] * 7}})
    rec = PERSON_K.run(rel, h.contract([("ed_visits", "sex")]), _health_ctx(h, visits, persons))
    assert rec["status"] == "fail"
    assert rec["denominator"] == {"unit": "persons", "n": 7}  # 4 persons + 3 unidentified units
    assert rec["hits"] == 7
    by_label = {v["label"]: v for v in rec["violations"]}
    assert by_label["quasiIdentifiersBelowK"]["count"] == 4
    assert by_label["quasiIdentifiersBelowK"]["locations"] == [0, 1, 2, 3]
    assert by_label["unidentifiedPersonRecords"]["count"] == 3
    assert by_label["unidentifiedPersonRecords"]["locations"] == [4, 5, 6]


def test_unidentified_records_do_not_lower_others_and_suppressing_them_passes(h):
    visits = VISITS[:8]
    persons = ["P01", "P02", "P03", "P04", "P05", "", "", ""]
    rel = h.release({"ed_visits": {"visit_tok": visits, "sex": ["F"] * 8}})
    rec = PERSON_K.run(rel, h.contract([("ed_visits", "sex")]), _health_ctx(h, visits, persons))
    by_label = {v["label"]: v for v in rec["violations"]}
    assert set(by_label) == {"unidentifiedPersonRecords"}  # the 5 identified persons are k=5
    assert rec["hits"] == 3
    # local suppression of the unidentified visits makes the release pass
    kept = visits[:5]
    rel2 = h.release({"ed_visits": {"visit_tok": kept, "sex": ["F"] * 5}})
    ctx = _health_ctx(h, visits, persons)
    ctx["rowmaps"] = {"ed_visits": h.rowmap(kept)}
    assert PERSON_K.run(rel2, h.contract([("ed_visits", "sex")]), ctx)["status"] == "pass"


def test_not_run_without_source_or_k(h):
    rel = h.release({"ed_visits": {"visit_tok": VISITS, "sex": ["F"] * 10}})
    full = _health_ctx(h, VISITS, PERSONS)
    for missing in ("source", "rowmaps", "person", "record_keys"):
        ctx = {k: v for k, v in full.items() if k != missing}
        rec = PERSON_K.run(rel, h.contract([("ed_visits", "sex")]), ctx)
        assert rec["status"] == "not_run", missing
    assert PERSON_K.run(rel, h.contract([("ed_visits", "sex")]), None)["status"] == "not_run"
    # no contract k (CS-S1): not applicable, which the runner verifies against the contract (ticket 23)
    assert PERSON_K.run(rel, h.contract([("ed_visits", "sex")], k=None), full)["status"] == "not_applicable"


def test_fail_closed_on_bad_rowmap_or_missing_qi_column(h):
    rel = h.release({"ed_visits": {"visit_tok": VISITS, "sex": ["F"] * 10}})
    ctx = _health_ctx(h, VISITS, PERSONS)
    short = dict(ctx, rowmaps={"ed_visits": h.rowmap(VISITS[:9])})
    unknown = dict(ctx, rowmaps={"ed_visits": h.rowmap(VISITS[:9] + ["V99"])})
    dup = dict(ctx, rowmaps={"ed_visits": h.rowmap(VISITS[:9] + ["V00"])})
    for bad in (short, unknown, dup):
        assert PERSON_K.run(rel, h.contract([("ed_visits", "sex")]), bad)["status"] == "error"
    absent_col = PERSON_K.run(rel, h.contract([("ed_visits", "age_band")]), ctx)
    assert absent_col["status"] == "error"
    unjoined = PERSON_K.run(
        h.release({"ed_visits": {"sex": ["F"] * 10}, "lab_results": {"d": ["x"] * 10}}),
        h.contract([("lab_results", "d")]),
        ctx,
    )
    assert unjoined["status"] == "error"
