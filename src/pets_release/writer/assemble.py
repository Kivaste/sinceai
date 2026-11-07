"""Manifest assembly: evidence decision, field-justification tie, bindings, signature.

The only place an export assertion is created is ``evidence_for``, and the only value it can hold is the literal
``False``. It is emitted for a scenario only when *every* required assertion is backed by its ticket-04 check
(``ASSERTION_CHECKS``) with status ``pass``, ``hits == 0``, ``denominator.n >= 1`` and the scope/unit ticket 02
pins. Any other record (fail, error, not_run, not_applicable, missing, low-severity hits, wrong shape) withholds
the whole assertion set, which the writer turns into a refusal.
"""
from __future__ import annotations

from pets_release.manifest import (
    ASSERTION_EVIDENCE,
    SCHEMA_VERSION,
    canonical_digest,
    compute_signature,
    release_scope_id,
    required_assertions,
)

NARRATIVE_KEYS = ("fieldJustifications", "fitFor", "inventory", "measured", "notFitFor", "pets", "residualRisks",
                  "sacrifices")
TEMPORARY_STATE = {"buildDirRemoved": True, "mappingTablesPersisted": False, "rowMapsInRelease": False}


def gate_entry(record) -> dict:
    """The manifest's gate/evidence view of a CheckRecord (no violations, no locations)."""
    return {"check": record.check, "version": record.version, "scope": record.scope, "status": record.status,
            "denominator": {"unit": record.denominator["unit"], "n": record.denominator["n"]},
            "hits": record.hits}


def evidence_for(records, scenario: str):
    """``(assertions, evidence, reasons)``. ``assertions``/``evidence`` are None unless ``reasons`` is empty."""
    by_check = {r.check: r for r in records}
    reasons: list[str] = []
    evidence: dict = {}
    for name in required_assertions(scenario):
        want = ASSERTION_EVIDENCE[name]
        rec = by_check.get(want["check"])
        if rec is None:
            reasons.append(f"assertion:{name}:missing")
            continue
        if rec.status != "pass":
            reasons.append(f"assertion:{name}:status:{rec.status}")
            continue
        if rec.scope != want["scope"] or rec.denominator.get("unit") != want["unit"]:
            reasons.append(f"assertion:{name}:shape")
            continue
        if type(rec.hits) is not int or rec.hits != 0 or rec.violations:
            reasons.append(f"assertion:{name}:hits")
            continue
        n = rec.denominator.get("n")
        if type(n) is not int or n < 1:
            reasons.append(f"assertion:{name}:denominator")
            continue
        evidence[name] = gate_entry(rec)
    if reasons:
        return None, None, sorted(reasons)
    return {name: False for name in sorted(evidence)}, evidence, []


def justification_reasons(contract: dict, field_justifications: list) -> list[str]:
    """Every released contract column has a released justification and vice versa (02 leaves this to 16)."""
    released = {(f.get("table"), f.get("outputColumn")) for f in field_justifications
                if f.get("decision") == "released"}
    columns = {(file[:-4], col) for file, spec in contract.get("files", {}).items() for col in spec.get("columns", {})}
    out = [f"justification:{t}.{c}:missing" for t, c in sorted(columns - released)]
    out += [f"justification:{t}.{c}:not-in-contract" for t, c in sorted(released - columns, key=str)]
    return out


def assemble_manifest(candidate, records, file_digests: dict, signing_key):
    """``(manifest, reasons)``; the manifest is None when any reason exists. Signed with ``signing_key``."""
    assertions, evidence, reasons = evidence_for(records, candidate.scenario)
    if reasons:
        return None, reasons
    gate = [gate_entry(r) for r in sorted(records, key=lambda r: r.check) if r.status == "pass"]
    contract = candidate.contract
    m = {
        "schemaVersion": SCHEMA_VERSION,
        "release": {
            "scenario": candidate.scenario, "recipient": candidate.recipient, "created": candidate.created,
            "releaseScopeId": release_scope_id(scenario=candidate.scenario, recipient=candidate.recipient,
                                               inputs=dict(candidate.inputs), tool_revision=candidate.tool_revision),
        },
        "bindings": {
            "files": dict(sorted(file_digests.items())),
            "inputs": dict(sorted(candidate.inputs.items())),
            "toolRevision": candidate.tool_revision,
            "checkVersions": {g["check"]: g["version"] for g in gate},
            "lexiconDigests": dict(sorted(candidate.lexicon_digests.items())),
            "contractDigest": canonical_digest(contract),
        },
        "contract": contract,
        "exportAssertions": assertions,
        "assertionEvidence": evidence,
        "gate": {"status": "pass", "checks": gate},
        "temporaryState": dict(TEMPORARY_STATE),
        **{k: candidate.narrative[k] for k in NARRATIVE_KEYS},
    }
    m["signature"] = {"alg": "HMAC-SHA256", "keyId": signing_key.key_id(),
                      "value": compute_signature(m, signing_key)}
    return m, []
