"""Minimiser: deterministic bounded search producing a Plan (``source: "search"``) and a SearchLogEntry JSONL.

    from pets_release.minimiser import search, write_search_log, apply_suppression, MinimiserRefused
    res = search(policy, tables, keys, purpose=..., purpose_all=..., kspec=..., params=...)
    res.plan; res.log; res.suppressed; res.final; res.sacrifices; res.stats

Kit glue (purpose checks through ticket 08's adapter, HEALTH-S1 person/record keys, read sets) is in
``pets_release.minimiser.kit``. See ``search`` for phases, acceptance and the objective.
"""

from .readsets import KIT_READ_SETS
from .search import (
    DEFAULT_BUDGET,
    LOG_KEYS,
    MinimiserRefused,
    SearchResult,
    apply_suppression,
    rebuild_plan,
    search,
    write_search_log,
)

__all__ = [
    "DEFAULT_BUDGET",
    "KIT_READ_SETS",
    "LOG_KEYS",
    "MinimiserRefused",
    "SearchResult",
    "apply_suppression",
    "rebuild_plan",
    "search",
    "write_search_log",
]
