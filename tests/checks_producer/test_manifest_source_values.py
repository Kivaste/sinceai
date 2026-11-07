"""#149 r2: ``producer.manifest-source-values`` through the production runner (``run_checks`` with the registered
check), on tiny hand-made release folders. Synthetic values only.

Rows (trigger -> result):
  a source cell changed IN PLACE between two runs on the same mapping -> the second run sees the new value
                                                     (was a stale cached index at 19870a2: 0 hits)
  a source value inside ``contract`` (verify phase: the manifest's; gate phase: the candidate's) -> fail
  a source value nested in lists of lists/maps -> fail
  enum item of column a that is a released value of a, at contract.files[t.csv].columns[a].params.values -> pass
  the same item under a column whose released cells do not hold it -> fail
  the same item at a's params.values while a's form is not ``enum`` -> fail (Grok r1; passed at 19870a2)
  the same item in another params list of column a (not ``values``) -> fail
  an item of a's enum that is a source value but not a released value of a -> fail
  a column name at a structural path (inventory[].column, contract key) -> pass
  the same column name (also a source value) as the whole fitFor[].reason or as an unrelated params key -> fail
  prefix index + occurs == naive substring scan, on fixed boundary cases and seeded random cases
"""
from __future__ import annotations

import json
import random

import pandas as pd
import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.checks.producer.manifest_values import CHECK, SCAN_MIN_LEN, fold, index, occurs

RELEASED = pd.DataFrame({"a": ["alpha_cat", "alpha_cat", "beta_catx"], "b": ["one", "two", "three"]})
NOTE = "synthetic hand-made remark"


def _check():
    return [c for c in all_checks() if c.name == CHECK]


def _rel(tmp_path, manifest: dict | None, released: pd.DataFrame = RELEASED):
    rel = tmp_path / "rel"
    rel.mkdir()
    released.to_csv(rel / "t.csv", index=False, lineterminator="\n")
    if manifest is not None:
        (rel / "privacy_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return rel


def _source(**extra):
    src = {"t": SOURCE_T.copy(), "notes": pd.DataFrame({"note_text": [NOTE, "short"]})}
    src.update(extra)
    return src


SOURCE_T = pd.DataFrame({"a": ["alpha_cat", "alpha_cat", "beta_catx"], "b": ["one", "two", "three"],
                               "chief_complaint": ["chief_complaint", "gamma_value", "delta_value"]})


def _status(rel, source, contract=None, phase="verify"):
    res = run_checks(rel, contract if contract is not None else {"files": {}}, {"source": source, "phase": phase},
                     checks=_check())
    (rec,) = res.records
    return rec.status, rec.hits


def test_in_place_source_change_is_seen_by_the_next_run(tmp_path):
    rel = _rel(tmp_path, {"fitFor": [{"reason": "the zebra crossing remark"}]})
    source = _source()
    assert _status(rel, source) == ("pass", 0)
    source["notes"].iat[1, 0] = "zebra crossing"  # same mapping, same frame object, same shape
    assert _status(rel, source) == ("fail", 1)


def test_source_value_in_manifest_contract_fails(tmp_path):
    m = {"contract": {"files": {"t.csv": {"columns": {"a": {"form": "text", "params": {"note": NOTE}}}}}}}
    assert _status(_rel(tmp_path, m), _source()) == ("fail", 1)


def test_source_value_in_candidate_contract_fails_at_gate(tmp_path):
    contract = {"files": {"t.csv": {"columns": {"a": {"form": "text", "params": {"note": NOTE.upper()}}}}}}
    assert _status(_rel(tmp_path, None), _source(), contract=contract, phase="gate") == ("fail", 1)


def test_source_value_nested_in_lists_fails(tmp_path):
    m = {"x": [["deep", {"k": [1, None, f"before {NOTE} after"]}]]}
    assert _status(_rel(tmp_path, m), _source()) == ("fail", 1)


def _enum(column: str, key: str, items: list, form: str = "enum") -> dict:
    return {"contract": {"files": {"t.csv": {"columns": {column: {"form": form, "params": {key: items}}}}}}}


def test_released_value_at_values_path_of_a_non_enum_column_fails(tmp_path):
    """Grok r1: the exemption also needs the column's form to be ``enum``."""
    assert _status(_rel(tmp_path, _enum("a", "values", ["alpha_cat"], form="text")), _source()) == ("fail", 1)


def test_enum_item_released_in_its_own_column_passes(tmp_path):
    assert _status(_rel(tmp_path, _enum("a", "values", ["alpha_cat", "beta_catx"])), _source()) == ("pass", 0)


def test_enum_item_under_a_different_column_fails(tmp_path):
    assert _status(_rel(tmp_path, _enum("b", "values", ["alpha_cat"])), _source()) == ("fail", 1)


def test_enum_item_outside_params_values_fails(tmp_path):
    assert _status(_rel(tmp_path, _enum("a", "labels", ["alpha_cat"])), _source()) == ("fail", 1)


def test_enum_item_that_is_not_released_in_its_column_fails(tmp_path):
    assert _status(_rel(tmp_path, _enum("a", "values", ["alpha_cat", "gamma_value"])), _source()) == ("fail", 1)


def test_column_name_at_structural_paths_passes(tmp_path):
    m = {"inventory": [{"table": "t", "column": "chief_complaint"}],
         "contract": {"files": {"t.csv": {"columns": {"chief_complaint": {"form": "text", "params": {}}}}}}}
    assert _status(_rel(tmp_path, m), _source()) == ("pass", 0)


@pytest.mark.parametrize("manifest", [
    {"fitFor": [{"scenario": "HEALTH-S1", "reason": "chief_complaint"}]},
    {"pets": [{"table": "t", "column": "a", "params": {"chief_complaint": 1}}]},
    {"inventory": [{"table": "t", "column": "a", "note": "chief_complaint"}]},
])
def test_column_name_that_is_a_source_value_elsewhere_fails(tmp_path, manifest):
    assert _status(_rel(tmp_path, manifest), _source()) == ("fail", 1)


def _naive(values: set, text: str) -> bool:
    return any(v in text for v in values)


BOUNDARY = [
    ({"abcdef"}, "abcdef"), ({"abcdef"}, "xabcdef"), ({"abcdef"}, "abcdefx"), ({"abcdef"}, "abcde"),
    ({"abcdef"}, "abcdeabcdef"), ({"abcdefgh", "abcdefxy"}, "..abcdefxy"), ({"abcdefgh"}, "abcdefg"),
    ({"aaaaaa"}, "aaaaaaa"), ({"aaaaaaab"}, "aaaaaaaaab"), ({"abcdef"}, ""), ({"abcdef", "bcdefg"}, "zbcdefg"),
]


@pytest.mark.parametrize(("values", "text"), BOUNDARY)
def test_prefix_index_matches_naive_scan_on_boundaries(values, text):
    assert occurs(index(values), text) is _naive(values, text)


def test_prefix_index_matches_naive_scan_on_random_cases():
    rng = random.Random(149)
    for _ in range(3000):
        values = {"".join(rng.choice("ab") for _ in range(rng.randint(SCAN_MIN_LEN, 9))) for _ in range(5)}
        text = "".join(rng.choice("ab ") for _ in range(rng.randint(0, 30)))
        assert occurs(index(values), text) is _naive(values, text), (values, text)


def test_fold_collapses_case_and_whitespace():
    assert fold("  Synthetic\tHAND-made \n remark ") == "synthetic hand-made remark"
