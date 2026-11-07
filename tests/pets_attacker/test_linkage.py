"""Linkage primitives on tiny hand-made synthetic tables.

Seam: Matcher over a protected DataFrame; no truth involved.
"""

from __future__ import annotations

import pandas as pd

from pets_attacker.linkage import QI, Matcher, edit_le1, parse_interval


def _prot():
    return pd.DataFrame(
        {
            "patient_name": ["Anna Virtanen", "Anna Virtanen", "Pekka Korhonen", ""],
            "municipality": ["Turku", "Raisio", "Turku", "Turku"],
            "arrival_ts": ["2025-03-01T10:30:00", "2025-03-01T11:00:00", "2025-03-09T08:00:00", ""],
            "date_of_birth": ["1980", "1980-05-04", "1950", ""],
            "sex": ["F", "F", "M", ""],
            "postcode": ["20***", "21***", "20***", ""],
        }
    )


def test_edit_le1():
    assert edit_le1("virtanen", "virtanen")
    assert edit_le1("virtanen", "virtanin")
    assert edit_le1("virtanen", "virtane")
    assert not edit_le1("virtanen", "virtonin")


def test_parse_interval_granularities():
    s, e = parse_interval(pd.Series(["2025-03-01T10:30:00", "2025-03-01", "2025-03", "2025", "2025-W10", "", "garbage"]))
    widths = [(b - a) / pd.Timedelta(hours=1) if pd.notna(a) else None for a, b in zip(s, e)]
    assert widths[0] == 0
    assert widths[1] == 24
    assert 24 * 28 <= widths[2] <= 24 * 31
    assert 24 * 365 <= widths[3] <= 24 * 366
    assert widths[4] == 24 * 7
    assert widths[5] is None and widths[6] is None


def test_exact_and_blank_wildcard():
    m = Matcher(_prot(), [QI("exact", ("place",), ("municipality",))])
    rows, used = m.candidates({"place": "turku"})
    assert sorted(rows) == [0, 2, 3] and used == 1


def test_time_window_overlap():
    m = Matcher(_prot(), [QI("time", ("t",), ("arrival_ts",), window=(2, 1))])
    rows, _ = m.candidates({"t": "2025-03-01T12:00:00"})
    assert sorted(rows) == [0, 1, 3]  # 10:30 within 2h before, 11:00 too; blank row is a wildcard
    rows, _ = m.candidates({"t": "2025-03-09"})
    assert sorted(rows) == [2, 3]  # date-only adversary time widens to the whole day


def test_fuzzy_name_and_wildcard_for_removed_names():
    m = Matcher(_prot(), [QI("name", ("n",), ("patient_name",))])
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
    m = Matcher(_prot(), qis)
    rows, used = m.candidates({"age": "45", "s": "female", "pc": "20100"})
    assert used == 3 and sorted(rows) == [0, 3]
    rows, _ = m.candidates({"age": "75", "s": "mies", "pc": "20100"})
    assert sorted(rows) == [2, 3]


def test_no_usable_qi_returns_everyone_with_used_zero():
    m = Matcher(_prot(), [QI("exact", ("place",), ("municipality",))])
    rows, used = m.candidates({"place": ""})
    assert used == 0 and len(rows) == 4
