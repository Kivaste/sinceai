"""Follow-up 91: implausible protected ages and masked hour_of_day cells are refused (RungError)."""

from __future__ import annotations

import pandas as pd
import pytest

from pets_attacker.cli import main
from pets_attacker.linkage import QI, Matcher, RungError
from tests.pets_attacker.test_fu75 import _kit


def _age(rung: str, cell: str):
    return Matcher(pd.DataFrame({"c": [cell, ""]}), [QI("age", ("a",), ("c",))], {"c": rung})


@pytest.mark.parametrize("rung,cell", [
    ("age.years", "999"), ("age.years", "131"), ("age.band10", "200-209"), ("age.band5", "150-154"),
    ("dob.year", "1800"), ("dob.month", "1800-05"), ("dob.date", "1800-01-01"),
    ("dob.year", "2099"), ("dob.month", "2099-05"), ("dob.date", "2099-01-01"),
    ("dob.date", "9999-12-31"), ("dob.date", "0000-01-01"), ("dob.year", "0000"), ("dob.year", "9999"),
])
def test_implausible_protected_age_is_refused(rung, cell):
    with pytest.raises(RungError):
        _age(rung, cell)


@pytest.mark.parametrize("rung,cell", [
    ("age.years", "0"), ("age.years", "130"), ("age.band10", "0-9"), ("age.band10", "90+"),
    ("dob.year", "2025"), ("dob.date", "2025-12-31"), ("dob.date", "1900-01-01"), ("dob.year", "1895"),
])
def test_plausible_protected_age_still_indexes(rung, cell):
    _age(rung, cell)


@pytest.mark.parametrize("cell", ["**:00", "xx:00", "??", "ab:00", "25:00", "9:00"])
def test_bad_hour_of_day_cell_is_a_rung_error_not_valueerror(cell):
    with pytest.raises(RungError):
        Matcher(pd.DataFrame({"t": [cell, "09:00"]}), [QI("time", ("t",), ("t",))], {"t": "ts.hour_of_day"})


def test_blank_and_valid_hour_of_day_cells_still_index():
    Matcher(pd.DataFrame({"t": ["", "09:00", "23:00"]}), [QI("time", ("t",), ("t",))], {"t": "ts.hour_of_day"})


@pytest.mark.parametrize("dob_cell,ok", [("1990-01-01", True), ("1800-01-01", False), ("2099-01-01", False)])
def test_cli_refuses_implausible_age_cells(tmp_path, dob_cell, ok):
    kit, rel, rungs = _kit(tmp_path, dob_cell, "2025-01-01T09:00")
    out = tmp_path / "o.json"
    rc = main(["--kit", str(kit), "--release", str(rel), "--label", "t", "--out", str(out), "--rungs", str(rungs)])
    assert (rc == 0) is ok
    assert out.exists() is ok
