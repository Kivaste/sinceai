"""The numeric-column table must cover every task the installed kit ships."""

from pets_eval.utility import all_tasks

from pets_release.kiteval.numeric_columns import NUMERIC_COLUMNS


def test_every_kit_task_has_an_entry():
    assert {t.id for t in all_tasks()} <= set(NUMERIC_COLUMNS)


def test_entries_are_table_column_pairs():
    for cols in NUMERIC_COLUMNS.values():
        assert all(isinstance(c, tuple) and len(c) == 2 for c in cols)


def test_cs_u4_measures_handle_time_only_among_its_categories():
    assert ("conversations", "handle_time_s") in NUMERIC_COLUMNS["CS-U4"]
    assert ("conversations", "intent") not in NUMERIC_COLUMNS["CS-U4"]
