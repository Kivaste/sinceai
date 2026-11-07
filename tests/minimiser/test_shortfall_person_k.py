"""Must-fix #118 at the minimiser seam (``pets_release.minimiser.search``). Synthetic rows only.

Rule: under a k target the search never reads an unmeasured PersonK as "no shortfall". Every candidate the search
scores carries a measured PersonK (ticket 11's production per-person k), even when the policy's risk vector has
no k component; the sacrifice-phase k shortfall is computed from it. A missing PersonK refuses the search
(``MinimiserRefused``, content-free ``PersonK missing``) at the first candidate; nothing is scored, logged or
released from it. A risk component missing from the final re-check refuses; it is never logged as 0.0.

Failure rows (trigger -> wrong result before the fix):
  S1 k target, risk vector without k components, k fails at the strict plan
       -> ``_shortfall`` read ``pk is None`` as 0.0: sacrifice phase skipped, search refused on the suppression
          budget although the enumerated sacrifice reaches k
  S2 same policy, per-person k yields no PersonK
       -> candidates scored and logged with no k measurement; the search only crashed (RuntimeError) in the
          final suppression, never a refusal
  S4 ``risk.person_k`` yields None at a search call site (evaluate / risk_vector / suppress)
       -> suppress broke out of its loop (0 of 0 persons suppressed, search went on to the final gate);
          evaluate and risk_vector scored on or crashed with an AttributeError instead of refusing
  S3 a risk component measured during the search but missing from the final re-check
       -> final log entry recorded it as 0.0 and the plan was released with it unmeasured

The minimiser has no CLI of its own, so these use its approved seam (``search``, ticket 24), as #112 did. The
missing result is planted by replacing ``risk.person_k_values`` (the boundary to ticket 11's check) with one
returning None; the missing final component by a ``risk_extra`` that omits it on the suppressed final data.
"""
from __future__ import annotations

import pytest

from pets_release.minimiser import MinimiserRefused, search

NO_K = ("join_derived_qi", "direct_identifier_leak", "attribute_inference")  # k target kept, no k component


def _no_k_policy(syn):
    pol = syn.policy()
    return type(pol)(**{**pol.__dict__, "risk_vector": NO_K})


def _run(syn, pol, **kw):
    return search(pol, syn.tables, syn.keys, purpose=syn.purpose, params=syn.params, kspec=syn.kspec, **kw)


def test_shortfall_measured_without_k_risk_components(syn):
    """S1: the k shortfall drives the sacrifice phase even when the risk vector has no k component."""
    res = _run(syn, _no_k_policy(syn))
    assert [s["check"] for s in res.sacrifices] == ["U-TOWN"]
    assert any(e["step"] != "final" and e["reason"].startswith("sacrifice:") for e in res.log)


def test_missing_person_k_refuses_before_any_score(syn, monkeypatch):
    """S2: a missing PersonK refuses at the first candidate; no candidate is logged with a score."""
    from pets_release.minimiser import risk

    monkeypatch.setattr(risk, "person_k_values", lambda *a, **kw: None)
    with pytest.raises(MinimiserRefused, match="PersonK missing") as ei:
        _run(syn, _no_k_policy(syn))
    assert ei.value.log == []


def _person_k_none_in(site):
    """A ``risk.person_k`` that returns no PersonK when called from ``site`` (the search method calling it) and the
    real result elsewhere: a fault plant at the boundary, to prove each call site refuses on its own."""
    import sys

    from pets_release.minimiser import risk

    real = risk.person_k

    def planted(*a, **kw):
        pk, contract = real(*a, **kw)
        return (None if sys._getframe(1).f_code.co_name == site else pk), contract
    return planted


@pytest.mark.parametrize("site", ["raw", "risk_vector", "suppress"])
def test_person_k_none_at_each_search_site_refuses(syn, monkeypatch, site):
    """S4: a PersonK of None, at the candidate evaluation (risk vector without k components: ``raw``, the scoring
    half of ``evaluate`` since #127; with
    them: ``risk_vector``) or in the local-suppression loop, refuses with ``PersonK missing``. Before the fix
    suppression broke out of its loop and reported 0 of 0 persons."""
    from pets_release.minimiser import risk

    monkeypatch.setattr(risk, "person_k", _person_k_none_in(site))
    with pytest.raises(MinimiserRefused, match="PersonK missing") as ei:
        _run(syn, syn.policy() if site == "risk_vector" else _no_k_policy(syn))
    if site != "suppress":
        assert ei.value.log == []  # refused at the first candidate, before any score is logged
    assert not any("0 of 0 persons" in e["reason"] for e in ei.value.log)


def test_final_risk_component_missing_refuses(syn):
    """S3: a risk component the final re-check cannot measure refuses; it is never logged as 0.0."""
    pol = syn.policy()
    pol = type(pol)(**{**pol.__dict__, "risk_vector": pol.risk_vector + ("x_extra",)})
    n_visits = len(syn.tables["visits"])

    def extra(plan, prot):  # measured on every unsuppressed candidate, missing on the suppressed final data
        return {"x_extra": 0.5} if len(prot["visits"]) == n_visits else {}

    with pytest.raises(MinimiserRefused, match="x_extra") as ei:
        _run(syn, pol, risk_extra=extra)
    last = ei.value.log[-1]
    assert last["step"] == "final" and last["accepted"] is False
    assert last["risk"]["x_extra"] is None
