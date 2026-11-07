"""Per-row k (release scope): a necessary condition computed from the release alone."""

from __future__ import annotations

from pets_release.checks import all_checks, run_checks


class _Via04:
    """Runs one registered check through ticket 04's runner; returns its CheckRecord dict."""

    def __init__(self, name):
        self.check = {c.name: c for c in all_checks()}[name]

    def run(self, release, contract, context):
        return run_checks(release, contract, context, checks=[self.check]).to_dict()["records"][0]


ROW_K = _Via04("producer.row-k")


def test_row_k_counts_rows_in_small_classes_per_table(h):
    rel = h.release(
        {
            "ed_visits": {"age_band": ["30-39"] * 6 + ["40-49"] * 2, "sex": ["F"] * 6 + ["M"] * 2},
            "lab_results": {"sampled_day": ["2030-03-01"] * 5},
        }
    )
    c = h.contract([("ed_visits", "age_band"), ("ed_visits", "sex"), ("lab_results", "sampled_day")])
    rec = ROW_K.run(rel, c, {"k": 5})
    assert rec["scope"] == "release"
    assert rec["status"] == "fail"
    assert rec["hits"] == 2
    assert rec["denominator"] == {"unit": "rows", "n": 13}
    (v,) = rec["violations"]
    assert (v["file"], v["column"], v["locations"]) == ("ed_visits.csv", "age_band+sex", [6, 7])

    ok = ROW_K.run(rel, h.contract([("ed_visits", "sex"), ("lab_results", "sampled_day")]), {"k": 2})
    assert ok["status"] == "pass"


def test_row_k_needs_only_release_but_not_run_without_k(h):
    rel = h.release({"ed_visits": {"sex": ["F"] * 6}})
    assert ROW_K.run(rel, h.contract([("ed_visits", "sex")]), {})["status"] == "not_run"
    assert ROW_K.run(rel, h.contract([("ed_visits", "sex")]), {"k": 5})["status"] == "pass"


def test_row_k_errors_on_missing_qi_column_or_no_qis(h):
    rel = h.release({"ed_visits": {"sex": ["F"] * 6}})
    assert ROW_K.run(rel, h.contract([("ed_visits", "age_band")]), {"k": 5})["status"] == "error"
    assert ROW_K.run(rel, h.contract([]), {"k": 5})["status"] == "error"
    assert ROW_K.run(rel.parent / "nope", h.contract([("ed_visits", "sex")]), {"k": 5})["status"] == "error"
