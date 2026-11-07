"""Aggregate summary of ticket 11's per-person k, as measured privacy components."""

from __future__ import annotations

import pytest

from pets_release.checks.producer.kanon import PersonK
from pets_release.measure import MeasureRejected, measure, measured_errors, person_k_components

SCENARIO = "TEST-S1"


def _pk(values, unidentified=0):
    return PersonK({f"p{i}": v for i, v in enumerate(values)}, [], unidentified, [])


def test_components_are_aggregates_of_the_person_k_result():
    comps = person_k_components(_pk([1, 5, 7, 9]), k=5)
    by = {c["component"]: c for c in comps}
    assert by["person_k.min"] == {"component": "person_k.min", "before": None, "after": 1.0}
    assert by["person_k.below_k_share"]["after"] == 0.25
    assert by["person_k.persons"]["after"] == 4.0


def test_unidentified_units_count_as_below_k():
    by = {c["component"]: c for c in person_k_components(_pk([5, 5, 5], unidentified=1), k=5)}
    assert by["person_k.below_k_share"]["after"] == 0.25
    assert by["person_k.persons"]["after"] == 4.0


def test_no_persons_fails_closed():
    with pytest.raises(MeasureRejected) as caught:
        person_k_components(_pk([]), k=5)
    assert caught.value.reason == "person_k"


@pytest.mark.parametrize("k", [None, 1, True, "5"])
def test_bad_k_fails(k):
    with pytest.raises(MeasureRejected):
        person_k_components(_pk([5]), k=k)


def test_measure_merges_person_k_components_and_still_validates(args):
    block = measure(SCENARIO, person_k=person_k_components(_pk([5, 6]), k=5), **args)
    ids = [c["component"] for c in block["privacy"]["components"]]
    assert "person_k.min" in ids and ids == sorted(ids)
    assert measured_errors(block) == []
