"""#62: the scenario policy, not the candidate contract, fixes the k target and the released QI set.

Rule: a HEALTH-S1 contract must carry exactly the policy's k target (5) and list every released policy QI
(by its derived output name, or its source name if released as such); otherwise the writer refuses and the
manifest is invalid (both verify tiers, dashboard). The producer context's ``k`` comes from the policy.

Failure rows (trigger -> result):
  contract k=2, matching context k=2, all classes >= 2 -> writer refused (policy:contract.k)
  contract k=6 (differs from policy)                    -> refused
  released policy QI (sex) omitted from contract.qi     -> refused (policy:contract.qi)
  HEALTH-S1 manifest with contract k=2                  -> validate_manifest error (schema minimum + policy rule)
  manifest omitting a released policy QI                -> validate_manifest error
  producer_context with contract k=2                    -> context k is the policy's 5
  unchanged fixture                                     -> released (no false refusal)
Synthetic fixture rows only.
"""
from __future__ import annotations

import copy

import pandas as pd
from writer_helpers import MASTER, make_candidate, make_kit, producer_context

from pets_release.manifest import loads_strict, validate_manifest
from pets_release.policy import get_policy
from pets_release.pseudonym import MasterKey
from pets_release.run.context import producer_context as run_producer_context
from pets_release.writer import write_release


def _write(tmp_path, contract, k_ctx=None):
    cand = make_candidate(contract=contract)
    kit = make_kit(tmp_path / "kit", cand)
    ctx = producer_context(cand)
    if k_ctx is not None:
        ctx["k"] = k_ctx
    return write_release(cand, tmp_path / "o" / "rel", MASTER, kit, context=ctx)


def _contract(**edit):
    c = copy.deepcopy(make_candidate().contract)
    c.update(edit)
    return c


def test_unchanged_fixture_releases(tmp_path):
    res = _write(tmp_path, _contract())
    assert res.status == "released", res.reasons


def test_weakened_k_with_matching_context_refuses(tmp_path):
    res = _write(tmp_path, _contract(k=2), k_ctx=2)
    assert res.status == "refused"
    assert "policy:contract.k: policy-mismatch" in res.reasons, res.reasons


def test_k_differing_from_policy_refuses(tmp_path):
    res = _write(tmp_path, _contract(k=6), k_ctx=6)
    assert res.status == "refused"
    assert "policy:contract.k: policy-mismatch" in res.reasons, res.reasons


def test_omitted_released_policy_qi_refuses(tmp_path):
    c = _contract()
    c["qi"] = [q for q in c["qi"] if q["column"] != "sex"]
    res = _write(tmp_path, c)
    assert res.status == "refused"
    assert "policy:contract.qi: ed_visits.sex: missing-policy-qi" in res.reasons, res.reasons


def _manifest(tmp_path):
    res = _write(tmp_path, _contract())
    assert res.status == "released", res.reasons
    return loads_strict((res.out / "privacy_manifest.json").read_bytes())


def _rebind(m):
    from pets_release.manifest import canonical_digest

    m["bindings"]["contractDigest"] = canonical_digest(m["contract"])
    return m


def test_manifest_with_weakened_k_is_invalid(tmp_path):
    m = _manifest(tmp_path)
    m["contract"]["k"] = 2
    errs = validate_manifest(_rebind(m))
    assert errs, "weakened k must not validate"
    assert any("contract.k" in e for e in errs), errs


def test_manifest_with_omitted_qi_is_invalid(tmp_path):
    m = _manifest(tmp_path)
    m["contract"]["qi"] = [q for q in m["contract"]["qi"] if q["column"] != "municipality"]
    errs = validate_manifest(_rebind(m))
    assert "$.contract.qi: ed_visits.municipality: missing-policy-qi" in errs, errs


def test_context_k_comes_from_policy_not_contract():
    src = {"ed_visits": pd.DataFrame({"visit_id": ["v1"], "patient_hetu": ["p1"]}, dtype=str)}
    ctx = run_producer_context(scenario_id="HEALTH-S1", policy=get_policy("HEALTH-S1"), source=src,
                               master=MasterKey.from_text("policy-target-test-only-key-not-a-secret-000"),
                               scope_id="0" * 16, recipient="default",
                               contract={"k": 2, "files": {}, "qi": [], "tokens": []}, released=None)
    assert ctx["k"] == 5


# --- renamed policy QI (round-1 review, DeepSeek): matched through the field justification's outputColumn ----

def _rename_age_band(contract, narrative, new="ab"):
    c = copy.deepcopy(contract)
    cols = c["files"]["ed_visits.csv"]["columns"]
    cols[new] = cols.pop("age_band")
    req = c["files"]["ed_visits.csv"]["required"]
    c["files"]["ed_visits.csv"]["required"] = sorted(new if r == "age_band" else r for r in req)
    c["qi"] = [q for q in c["qi"] if q["column"] != "age_band"]  # the renamed QI is dropped from contract.qi
    n = copy.deepcopy(dict(narrative))
    for fj in n["fieldJustifications"]:
        if fj["outputColumn"] == "age_band":
            fj["outputColumn"] = new
    return c, n


def test_manifest_with_renamed_policy_qi_dropped_is_invalid(tmp_path):
    m = _manifest(tmp_path)
    c, n = _rename_age_band(m["contract"], {"fieldJustifications": m["fieldJustifications"]})
    m["contract"], m["fieldJustifications"] = c, n["fieldJustifications"]
    errs = validate_manifest(_rebind(m))
    assert "$.contract.qi: ed_visits.ab: missing-policy-qi" in errs, errs


def test_writer_refuses_renamed_policy_qi_dropped(tmp_path):
    from pets_release.writer import ProtectedTable

    base = make_candidate()
    c, n = _rename_age_band(base.contract, base.narrative)
    tables = tuple(ProtectedTable(name=t.name, frame=t.frame.rename(columns={"age_band": "ab"}), final=t.final,
                                  suppressed=t.suppressed) if t.name == "ed_visits.csv" else t for t in base.tables)
    cand = make_candidate(contract=c, narrative=n, tables=tables)
    kit = make_kit(tmp_path / "kit", cand)
    res = write_release(cand, tmp_path / "o" / "rel", MASTER, kit, context=producer_context(cand))
    assert res.status == "refused"
    assert "policy:contract.qi: ed_visits.ab: missing-policy-qi" in res.reasons, res.reasons


# --- output provenance (round-2 review, Sol): every released column states its source; a column derived from a
# policy QI is a QI whatever its name ---------------------------------------------------------------------------

def _with_extra_column(params, justification=None, name="at", src_col="arrival_ts"):
    from pets_release.writer import ProtectedTable

    base = make_candidate()
    c = copy.deepcopy(base.contract)
    cols = c["files"]["ed_visits.csv"]["columns"]
    cols[name] = {"form": cols[src_col]["form"], "params": params}
    n = copy.deepcopy(dict(base.narrative))
    if justification is not None:
        n["fieldJustifications"] = sorted([*n["fieldJustifications"], justification],
                                          key=lambda f: (f["table"], f["column"]))
    tables = tuple(ProtectedTable(name=t.name, frame=t.frame.assign(**{name: t.frame[src_col]}), final=t.final,
                                  suppressed=t.suppressed) if t.name == "ed_visits.csv" else t for t in base.tables)
    return make_candidate(contract=c, narrative=n, tables=tables)


def _write_cand(tmp_path, cand):
    kit = make_kit(tmp_path / "kit", cand)
    return write_release(cand, tmp_path / "o" / "rel", MASTER, kit, context=producer_context(cand))


def test_column_derived_from_policy_qi_must_be_a_qi(tmp_path):
    res = _write_cand(tmp_path, _with_extra_column({"derived_from": "arrival_ts"}))
    assert res.status == "refused"
    assert "policy:contract.qi: ed_visits.at: missing-policy-qi" in res.reasons, res.reasons


def test_column_without_provenance_refuses(tmp_path):
    res = _write_cand(tmp_path, _with_extra_column({}))
    assert res.status == "refused"
    assert "policy:contract.files: ed_visits.at: no-provenance" in res.reasons, res.reasons


def test_unresolvable_provenance_refuses(tmp_path):
    """Round-3 review (Sol): ``derived_from="."`` names no source column; it must not count as provenance."""
    res = _write_cand(tmp_path, _with_extra_column({"derived_from": "."}))
    assert res.status == "refused"
    assert "policy:contract.files: ed_visits.at: unknown-provenance" in res.reasons, res.reasons


def test_conflicting_provenance_refuses(tmp_path):
    fj = {"table": "ed_visits", "column": "triage", "outputColumn": "at", "decision": "released",
          "rung": "exact", "floor": "exact", "reason": "synthetic", "source": "hand"}
    res = _write_cand(tmp_path, _with_extra_column({"derived_from": "arrival_ts"}, justification=fj))
    assert res.status == "refused"
    assert "policy:contract.files: ed_visits.at: provenance-conflict" in res.reasons, res.reasons
