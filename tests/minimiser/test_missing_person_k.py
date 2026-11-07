"""Must-fix #112 at the minimiser seam (``pets_release.minimiser.search``). Synthetic rows only.

Rule: the minimiser never scores a missing PersonK as perfect privacy. When the production per-person k
(``person_k_values``) yields no result, the risk computation raises (content-free ``PersonK missing``); no
``qi_k_shortfall`` / ``qi_unique_rate`` of 0.0 is recorded and no plan is returned.

Failure row (trigger -> wrong result before the fix):
  P1 per-person k yields no PersonK -> qi_k_shortfall = qi_unique_rate = 0.0 (perfect) and the search goes on

``person_k_values`` raises on every fail-closed condition today, so the missing result is planted by
replacing it (the boundary to ticket 11's check) with one that returns None, as test_k_recheck_error_refuses
does for the k gate.
"""
from __future__ import annotations

import pytest

from pets_release.minimiser import MinimiserRefused, search


def test_missing_person_k_raises_never_perfect(syn, monkeypatch):
    from pets_release.minimiser import risk

    monkeypatch.setattr(risk, "person_k_values", lambda *a, **kw: None)
    # since #118 the search turns the raise into a refusal at the first candidate, before anything is logged
    with pytest.raises(MinimiserRefused, match="PersonK missing") as ei:
        search(syn.policy(), syn.tables, syn.keys, purpose=syn.purpose, params=syn.params, kspec=syn.kspec)
    assert ei.value.log == []
