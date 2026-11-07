"""Aggregate summary of ticket 11's per-person k, as privacy components (after only: the original has no
released form to take a k of, so `before` is null)."""

from __future__ import annotations

from pets_release.measure.errors import MeasureRejected


def person_k_components(result, *, k) -> list[dict]:
    """`result` is ticket 11's `PersonK` (per-person k values stay in memory; only aggregates leave).

    Unidentified units count as persons and as below k, as in the producer.person-k check."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 2:
        raise MeasureRejected("person_k")
    per_person = getattr(result, "per_person", None)
    unidentified = getattr(result, "unidentified", None)
    if not isinstance(per_person, dict) or isinstance(unidentified, bool) or not isinstance(unidentified, int):
        raise MeasureRejected("person_k")
    total = len(per_person) + unidentified
    if total <= 0 or unidentified < 0:
        raise MeasureRejected("person_k")
    below = sum(1 for v in per_person.values() if v < k) + unidentified
    lowest = min(per_person.values()) if per_person else 1
    comps = [("person_k.below_k_share", below / total), ("person_k.min", lowest), ("person_k.persons", total)]
    return sorted(({"component": c, "before": None, "after": float(v)} for c, v in comps),
                  key=lambda r: r["component"])
