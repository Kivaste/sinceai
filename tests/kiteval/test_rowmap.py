"""Row maps must cover exactly the final protected rows and reference real source keys."""

import pandas as pd
import pytest

from pets_release.kiteval.rowmap import RowMapRejected, validate_row_map

KEYS = ["r1", "r2", "r3", "r4"]


def _map(rows):
    return pd.DataFrame(rows, columns=["protected_row", "original_record_id"], dtype=str)


def _check(rm, n=3):
    return validate_row_map(rm, protected_rows=n, source_keys=KEYS)


def test_exact_cover_is_accepted_even_when_source_rows_were_suppressed():
    _check(_map([("0", "r1"), ("1", "r3"), ("2", "r4")]))  # r2 suppressed


def test_missing_protected_row_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([("0", "r1"), ("2", "r4")]))
    assert caught.value.reason == "missing_row"


def test_extra_protected_row_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([("0", "r1"), ("1", "r2"), ("2", "r3"), ("3", "r4")]))
    assert caught.value.reason == "unknown_protected_row"


def test_duplicate_protected_row_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([("0", "r1"), ("1", "r2"), ("1", "r3"), ("2", "r4")]))
    assert caught.value.reason == "duplicate_row"


def test_duplicate_source_key_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([("0", "r1"), ("1", "r1"), ("2", "r4")]))
    assert caught.value.reason == "duplicate_source_key"


def test_nonexistent_source_key_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([("0", "r1"), ("1", "r2"), ("2", "zzz")]))
    assert caught.value.reason == "unknown_source_key"


def test_non_integer_row_index_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([("0", "r1"), ("1", "r2"), ("x", "r3")]))
    assert caught.value.reason == "bad_row_index"


def test_empty_map_for_nonempty_table_is_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(_map([]))
    assert caught.value.reason == "missing_row"


def test_empty_map_for_empty_table_is_accepted():
    _check(_map([]), n=0)


def test_missing_columns_are_rejected():
    with pytest.raises(RowMapRejected) as caught:
        _check(pd.DataFrame({"a": ["0"]}))
    assert caught.value.reason == "structure"


def test_path_input_is_read_as_strings(tmp_path):
    p = tmp_path / "rowmap_t.csv"
    p.write_text("protected_row,original_record_id\n0,r1\n1,r2\n2,r3\n", encoding="utf-8")
    validate_row_map(p, protected_rows=3, source_keys=KEYS)
