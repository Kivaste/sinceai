"""Linkage primitives on tiny hand-made synthetic tables.

Seam: Matcher over a protected DataFrame plus explicit per-column rungs; no truth involved.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pets_attacker.linkage import QI, Matcher, RungError, edit_le1, parse_interval

RUNGS = {"municipality": "keep", "arrival_ts": "ts.exact", "date_of_birth": "dob.year"}


def _prot():
    return pd.DataFrame(
        {
            "patient_name": ["Anna Virtanen", "Anna Virtanen", "Pekka Korhonen", ""],
            "municipality": ["Turku", "Raisio", "Turku", "Turku"],
            "arrival_ts": ["2025-03-01T10:30:00", "2025-03-01T11:00:00", "2025-03-09T08:00:00", ""],
            "date_of_birth": ["1980", "1980", "1950", ""],
            "sex": ["F", "F", "M", ""],
            "postcode": ["20***", "21***", "20***", ""],
        }
    )


def test_edit_le1():
    assert edit_le1("virtanen", "virtanen")
    assert edit_le1("virtanen", "virtanin")
    assert edit_le1("virtanen", "virtane")
    assert not edit_le1("virtanen", "virtonin")


@pytest.mark.parametrize("rung,cell,hours", [
    ("ts.exact", "2025-03-01T10:30:00", 0), ("ts.hour", "2025-03-01 10:00", 1), ("ts.day", "2025-03-01", 24),
    ("ts.week", "2025-W10", 24 * 7), ("ts.month", "2025-03", 24 * 31),
])
def test_parse_interval_by_rung(rung, cell, hours):
    s, e = parse_interval(pd.Series([cell, ""]), rung)
    assert (e[0] - s[0]) / pd.Timedelta(hours=1) == hours
    assert pd.isna(s[1])


def test_cell_not_matching_its_declared_rung_is_refused():
    with pytest.raises(RungError):
        parse_interval(pd.Series(["2025-03"]), "ts.day")
    with pytest.raises(RungError):
        parse_interval(pd.Series(["2025-03-01"]), "no.such.rung")


def test_missing_rung_metadata_is_refused():
    with pytest.raises(RungError):
        Matcher(_prot(), [QI("time", ("t",), ("arrival_ts",))], {})
    with pytest.raises(RungError):
        Matcher(_prot(), [QI("exact", ("p",), ("municipality",))], {"arrival_ts": "ts.exact"})
    with pytest.raises(RungError):
        Matcher(_prot(), [QI("age", ("a",), ("date_of_birth",))], {})


def test_exact_and_blank_wildcard():
    m = Matcher(_prot(), [QI("exact", ("place",), ("municipality",))], RUNGS)
    rows, used = m.candidates({"place": "turku"})
    assert sorted(rows) == [0, 2, 3] and used == 1


def test_time_window_overlap():
    m = Matcher(_prot(), [QI("time", ("t",), ("arrival_ts",), window=(2, 1))], RUNGS)
    rows, _ = m.candidates({"t": "2025-03-01T12:00:00"})
    assert sorted(rows) == [0, 1, 3]  # 10:30 within 2h before, 11:00 too; blank row is a wildcard
    rows, _ = m.candidates({"t": "2025-03-09"})
    assert sorted(rows) == [2, 3]  # date-only adversary time widens to the whole day


def test_fuzzy_name_and_wildcard_for_removed_names():
    m = Matcher(_prot(), [QI("name", ("n",), ("patient_name",))], RUNGS)
    rows, _ = m.candidates({"n": "Anna Virtanin"})
    assert sorted(rows) == [0, 1, 3]
    rows, used = m.candidates({"n": ""})
    assert used == 0 and len(rows) == 4


def test_age_interval_and_sex_and_postcode():
    qis = [
        QI("age", ("age",), ("date_of_birth",), tol=1),
        QI("sex", ("s",), ("sex",)),
        QI("postcode", ("pc",), ("postcode",)),
    ]
    m = Matcher(_prot(), qis, RUNGS)
    rows, used = m.candidates({"age": "45", "s": "female", "pc": "20100"})
    assert used == 3 and sorted(rows) == [0, 3]
    rows, _ = m.candidates({"age": "75", "s": "mies", "pc": "20100"})
    assert sorted(rows) == [2, 3]


def test_no_usable_qi_returns_everyone_with_used_zero():
    m = Matcher(_prot(), [QI("exact", ("place",), ("municipality",))], RUNGS)
    rows, used = m.candidates({"place": ""})
    assert used == 0 and len(rows) == 4


def test_month_hour_rung_matches_month_and_hour_of_day():
    prot = pd.DataFrame({"arrival_ts": ["2025-03-01T10:00", "2025-03-01T15:00", "2025-04-01T10:00"]})
    m = Matcher(prot, [QI("time", ("t",), ("arrival_ts",), window=(2, 1))], {"arrival_ts": "ts.month_hour"})
    assert list(m.candidates({"t": "2025-03-17T10:30:00"})[0]) == [0]
    assert list(m.candidates({"t": "2025-04-30T09:15:00"})[0]) == [2]


def test_hour_rung_on_the_first_of_a_month_is_not_misread_as_month_hour():
    """Same cell shape as ts.month_hour; the declared rung decides."""
    prot = pd.DataFrame({"arrival_ts": ["2025-03-01T10:00", "2025-03-01T15:00"]})
    qi = [QI("time", ("t",), ("arrival_ts",), window=(0, 0))]
    hour = Matcher(prot, qi, {"arrival_ts": "ts.hour"})
    assert list(hour.candidates({"t": "2025-03-17T10:30:00"})[0]) == []
    assert list(hour.candidates({"t": "2025-03-01T10:20:00"})[0]) == [0]
    month_hour = Matcher(prot, qi, {"arrival_ts": "ts.month_hour"})
    assert list(month_hour.candidates({"t": "2025-03-17T10:30:00"})[0]) == [0]


def test_hour_form_is_an_hour_bucket():
    prot = pd.DataFrame({"arrival_ts": ["2025-03-17T10:00", "2025-03-17T11:00"]})
    m = Matcher(prot, [QI("time", ("t",), ("arrival_ts",), window=(0, 0))], {"arrival_ts": "ts.hour"})
    assert list(m.candidates({"t": "2025-03-17T10:40:00"})[0]) == [0]


def test_other_is_a_wildcard_only_under_geo_topn():
    prot = pd.DataFrame({"municipality": ["Turku", "Raisio", "other", "other"]})
    qi = [QI("exact", ("place",), ("municipality",))]
    topn = Matcher(prot, qi, {"municipality": "geo.topn"})
    assert sorted(topn.candidates({"place": "Naantali"})[0]) == [2, 3]
    assert sorted(topn.candidates({"place": "Turku"})[0]) == [0]
    literal = Matcher(prot, qi, {"municipality": "keep"})
    assert list(literal.candidates({"place": "Naantali"})[0]) == []
    assert sorted(literal.candidates({"place": "other"})[0]) == [2, 3]


def test_age_band_rung_is_an_interval():
    prot = pd.DataFrame({"age_band": ["20-24", "25-29", "90+"]})
    m = Matcher(prot, [QI("age", ("age",), ("age_band",), tol=0)], {"age_band": "age.band5"})
    assert list(m.candidates({"age": "22"})[0]) == [0]
    assert list(m.candidates({"age": "95"})[0]) == [2]


def test_single_target_release_in_ladder_forms_links_with_certainty():
    prot = pd.DataFrame({"arrival_ts": ["2025-03-01T10:00"], "municipality": ["other"], "age_band": ["30-34"], "sex": ["F"]})
    qis = [QI("time", ("t",), ("arrival_ts",), window=(0, 0)), QI("exact", ("p",), ("municipality",)),
           QI("age", ("a",), ("age_band",), tol=0), QI("sex", ("s",), ("sex",))]
    rungs = {"arrival_ts": "ts.month_hour", "municipality": "geo.topn", "age_band": "age.band5"}
    rows, used = Matcher(prot, qis, rungs).candidates({"t": "2025-03-20T10:10:00", "p": "Kaarina", "a": "32", "s": "F"})
    assert list(rows) == [0] and used == 4


def test_buckets_are_half_open_so_the_previous_day_does_not_match():
    prot = pd.DataFrame({"arrival_ts": ["2025-03-01", "2025-03-02", "2025-03-03"]})
    m = Matcher(prot, [QI("time", ("t",), ("arrival_ts",), window=(0, 0))], {"arrival_ts": "ts.day"})
    assert list(m.candidates({"t": "2025-03-02T09:00:00"})[0]) == [1]
    assert list(m.candidates({"t": "2025-03-02T00:00:00"})[0]) == [1]  # exclusive end of day 1 is not day 2
    assert list(m.candidates({"t": "2025-03-02"})[0]) == [1]  # date-only: the whole day, no neighbours


def test_hour_buckets_are_half_open_and_exact_instants_still_match_at_the_edge():
    hour = pd.DataFrame({"arrival_ts": ["2025-03-17T09:00", "2025-03-17T10:00"]})
    m = Matcher(hour, [QI("time", ("t",), ("arrival_ts",), window=(0, 0))], {"arrival_ts": "ts.hour"})
    assert list(m.candidates({"t": "2025-03-17T10:00:00"})[0]) == [1]
    exact = pd.DataFrame({"arrival_ts": ["2025-03-17T10:00:00", "2025-03-17T10:30:00"]})
    m = Matcher(exact, [QI("time", ("t",), ("arrival_ts",), window=(0, 1))], {"arrival_ts": "ts.exact"})
    assert list(m.candidates({"t": "2025-03-17T09:30:00"})[0]) == [0, 1]
    m = Matcher(exact, [QI("time", ("t",), ("arrival_ts",), window=(1, 0))], {"arrival_ts": "ts.exact"})
    assert list(m.candidates({"t": "2025-03-17T10:30:00"})[0]) == [0, 1]  # instant exactly at the window start matches


def test_hour_of_day_rung_matches_hour_of_day_any_date():
    prot = pd.DataFrame({"arrival_ts": ["10:00", "15:00", "", "23:00"]})
    qi = [QI("time", ("t",), ("arrival_ts",), window=(1, 1))]
    m = Matcher(prot, qi, {"arrival_ts": "ts.hour_of_day"})
    assert list(m.candidates({"t": "2025-07-09T10:30:00"})[0]) == [0, 2]  # 09:30..11:30 -> hours 09,10,11; blank = wildcard
    assert list(m.candidates({"t": "2025-01-01T00:10:00"})[0]) == [2, 3]  # window wraps past midnight
    wide = Matcher(prot, [QI("time", ("t",), ("arrival_ts",), window=(24, 24))], {"arrival_ts": "ts.hour_of_day"})
    assert list(wide.candidates({"t": "2025-07-09T10:30:00"})[0]) == [0, 1, 2, 3]


def test_hour_of_day_rung_refuses_a_cell_of_another_shape():
    prot = pd.DataFrame({"arrival_ts": ["2025-03-01T10:00"]})
    with pytest.raises(RungError):
        Matcher(prot, [QI("time", ("t",), ("arrival_ts",))], {"arrival_ts": "ts.hour_of_day"})
    with pytest.raises(RungError):
        parse_interval(pd.Series(["25:00x"]), "ts.hour_of_day")
