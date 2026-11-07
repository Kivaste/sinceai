"""The pinned scenario policy constrains a release contract (#62). Schema names only; no row values.

A contract cannot set its own privacy target:

* the k target comes from the policy's ``k_anonymity`` privacy target;
* every released column must state its source (output provenance): a released field justification for it
  (``table`` + ``column`` -> ``outputColumn``) and/or the column's ``params.derived_from`` (``col`` or
  ``table.col``). No source -> ``no-provenance``; two different sources -> ``provenance-conflict``; a malformed
  reference or one naming a column outside the pinned source schema (the policy's columns) -> ``unknown-provenance``;
* the mandatory QI set is derived from that provenance: any released column whose source is a policy QI is a
  QI whatever its name (also a column named like a policy QI's derived or source name), and must be listed in
  ``contract.qi``.

The writer refuses on any problem before the gate, and manifest validation applies the same rule (every verify
tier, the dashboard). Names in problem codes are schema names; one the identifier detectors flag is masked.
"""
from __future__ import annotations

from collections.abc import Mapping

from pets_release.checks.cells._shape import safe_name


def _valid_k(k) -> bool:
    return isinstance(k, int) and not isinstance(k, bool) and k >= 2


def _n(name) -> str:
    return name if safe_name(name) else "<name>"


def k_target(policy) -> int | None:
    """The policy's k-anonymity target, or None when it has none. Raises ValueError on a malformed target."""
    targets = [t for t in policy.privacy_targets if t.get("kind") == "k_anonymity"]
    if not targets:
        return None
    if len(targets) > 1 or not _valid_k(targets[0].get("k")):
        raise ValueError("policy k_anonymity target is malformed")
    return targets[0]["k"]


def _columns(contract) -> list[tuple[str, str, Mapping]]:
    """(table stem, released column, column spec) for every contract column."""
    files = contract.get("files") if isinstance(contract, Mapping) else None
    out = []
    if isinstance(files, Mapping):
        for file, spec in files.items():
            cols = spec.get("columns") if isinstance(spec, Mapping) else None
            stem = file[:-4] if isinstance(file, str) and file.endswith(".csv") else str(file)
            if isinstance(cols, Mapping):
                out += [(stem, c, s if isinstance(s, Mapping) else {}) for c, s in cols.items()]
    return sorted(out, key=lambda x: (x[0], str(x[1])))


def provenance(contract, justifications, source_schema) -> tuple[dict, list[str]]:
    """``({(table, released column): (source table, source column)}, problems)``.

    ``source_schema`` is the pinned set of ``(table, column)`` source columns (the policy's columns). A reference
    that is malformed or names a column outside it is ``unknown-provenance`` and counts as no source at all, so it
    can never stand in for real provenance (round-3 review, #62)."""
    justified: dict = {}
    for fj in justifications or ():
        if isinstance(fj, Mapping) and fj.get("decision") == "released" and isinstance(fj.get("outputColumn"), str):
            justified.setdefault((fj.get("table"), fj["outputColumn"]), set()).add((fj.get("table"), fj.get("column")))
    out, problems = {}, []
    for stem, col, spec in _columns(contract):
        sources = set(justified.get((stem, col), ()))
        params = spec.get("params")
        df = params.get("derived_from") if isinstance(params, Mapping) else None
        if df is not None:
            if not isinstance(df, str) or not df:
                problems.append(f"contract.files: {_n(stem)}.{_n(col)}: provenance-conflict")
                continue
            t, _, c = df.rpartition(".")
            sources.add((t or stem, c))
        if sources - set(source_schema):
            problems.append(f"contract.files: {_n(stem)}.{_n(col)}: unknown-provenance")
            continue
        if not sources:
            problems.append(f"contract.files: {_n(stem)}.{_n(col)}: no-provenance")
        elif len(sources) > 1:
            problems.append(f"contract.files: {_n(stem)}.{_n(col)}: provenance-conflict")
        else:
            out[(stem, col)] = next(iter(sources))
    return out, problems


def released_policy_qis(policy, contract: Mapping, justifications=None) -> list[tuple[str, str]]:
    """(table, released column) of every released column that is a policy QI: by provenance (its source is a
    policy QI) or by name (it carries a policy QI's derived or source name)."""
    qi_src = {(q["table"], q["column"]) for q in policy.qi}
    by_name = {(q["table"], name) for q in policy.qi for name in (q["derived"], q["column"])}
    prov, _ = provenance(contract, justifications, policy.floors)
    out = set()
    for stem, col, _spec in _columns(contract):
        if (stem, col) in by_name or prov.get((stem, col)) in qi_src:
            out.add((stem, col))
    return sorted(out)


def contract_policy_problems(scenario: str, contract, justifications=None) -> list[str]:
    """Content-free problem codes (``<field>: <rule>``); ``[]`` means the contract honours the policy."""
    from pets_release.policy import get_policy

    try:
        policy = get_policy(scenario)
    except KeyError:
        return ["scenario: no-policy"]
    if not isinstance(contract, Mapping):
        return ["contract: unreadable"]
    out = []
    try:
        want = k_target(policy)
    except ValueError:
        return ["policy: malformed-k-target"]
    if want is None:
        if "k" in contract:
            out.append("contract.k: not-in-policy")
    elif "k" not in contract:
        out.append("contract.k: missing")
    elif not _valid_k(contract["k"]) or contract["k"] != want:
        out.append("contract.k: policy-mismatch")
    out += provenance(contract, justifications, policy.floors)[1]
    qi = contract.get("qi")
    listed = {(q.get("table"), q.get("column")) for q in qi if isinstance(q, Mapping)} if isinstance(qi, list) else set()
    for table, column in released_policy_qis(policy, contract, justifications):
        if (table, column) not in listed:
            out.append(f"contract.qi: {_n(table)}.{_n(column)}: missing-policy-qi")
    return sorted(set(out))
