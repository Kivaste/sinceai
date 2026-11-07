"""Manifest assembly: evidence decision, field-justification tie, bindings, signature.

The only place an export assertion is created is ``evidence_for``, and the only value it can hold is the literal
``False``. It is emitted for a scenario only when *every* required assertion is backed by its ticket-04 check
(``ASSERTION_CHECKS``) with status ``pass``, ``hits == 0``, ``denominator.n >= 1`` and the scope/unit ticket 02
pins. Any other record (fail, error, not_run, not_applicable, missing, low-severity hits, wrong shape) withholds
the whole assertion set, which the writer turns into a refusal.
"""
from __future__ import annotations

import re

from pets_release.manifest import (
    ASSERTION_EVIDENCE,
    SCHEMA_VERSION,
    canonical_digest,
    compute_signature,
    release_scope_id,
    required_assertions,
)
from pets_release.manifest.schema import SPAN_LABELS

NARRATIVE_KEYS = ("fieldJustifications", "fitFor", "inventory", "measured", "notFitFor", "pets", "residualRisks",
                  "sacrifices")
TEMPORARY_STATE = {"buildDirRemoved": True, "mappingTablesPersisted": False, "rowMapsInRelease": False}


def gate_entry(record) -> dict:
    """The manifest's gate/evidence view of a CheckRecord (no violations, no locations)."""
    return {"check": record.check, "version": record.version, "scope": record.scope, "status": record.status,
            "denominator": {"unit": record.denominator["unit"], "n": record.denominator["n"]},
            "hits": record.hits}


def assertion_reason(name: str, rec) -> str | None:
    """The one assertion-evidence rule (writer and verify): None when ``rec`` (a CheckRecord or None) can back
    export assertion ``name``; otherwise a content-free reason code."""
    want = ASSERTION_EVIDENCE[name]
    if rec is None or rec.check != want["check"]:
        return f"assertion:{name}:missing"
    if rec.status != "pass":
        return f"assertion:{name}:status:{rec.status}"
    if rec.scope != want["scope"] or rec.denominator.get("unit") != want["unit"]:
        return f"assertion:{name}:shape"
    if type(rec.hits) is not int or rec.hits != 0 or rec.violations:
        return f"assertion:{name}:hits"
    n = rec.denominator.get("n")
    if type(n) is not int or n < 1:
        return f"assertion:{name}:denominator"
    return None


def evidence_for(records, scenario: str):
    """``(assertions, evidence, reasons)``. ``assertions``/``evidence`` are None unless ``reasons`` is empty."""
    by_check = {r.check: r for r in records}
    reasons: list[str] = []
    evidence: dict = {}
    for name in required_assertions(scenario):
        rec = by_check.get(ASSERTION_EVIDENCE[name]["check"])
        reason = assertion_reason(name, rec)
        if reason is not None:
            reasons.append(reason)
            continue
        evidence[name] = gate_entry(rec)
    if reasons:
        return None, None, sorted(reasons)
    return {name: False for name in sorted(evidence)}, evidence, []


LOW_SEVERITY_KIND = "gate_low_severity"


def low_severity_risks(records) -> list[dict]:
    """``residualRisks`` entries for low-severity gate hits: one per (check, label), with the hit count and the
    check's denominator. Counts and schema names only. Writer and verify both derive them with this function."""
    counts: dict = {}
    for r in records:
        for v in r.violations:
            if v.severity == "low":
                key = (r.check, v.label)
                counts[key] = (r, counts.get(key, (r, 0))[1] + v.count)
    out = []
    for (check, label), (r, count) in sorted(counts.items()):
        d = {"unit": r.denominator["unit"], "n": r.denominator["n"]}
        out.append({
            "risk": re.sub(r"[^A-Za-z0-9._:+-]", "-", f"gate:{check}:{label}")[:64], "kind": LOW_SEVERITY_KIND,
            "label": label if label in SPAN_LABELS else None,
            "rate": {"status": "counted", "count": count, "denominator": d,
                     "source": f"gate check {check} {r.version} ({r.scope} scope)"},
            "description": (f"{count} low-severity {label} hit(s) over {d['n']} {d['unit']} scanned by {check}; "
                            "below the refusal threshold, so released and disclosed here")[:500],
        })
    return out


def justification_reasons(contract: dict, field_justifications: list) -> list[str]:
    """Every released contract column has a released justification and vice versa (02 leaves this to 16)."""
    released = {(f.get("table"), f.get("outputColumn")) for f in field_justifications
                if f.get("decision") == "released"}
    columns = {(file[:-4], col) for file, spec in contract.get("files", {}).items() for col in spec.get("columns", {})}
    out = [f"justification:{t}.{c}:missing" for t, c in sorted(columns - released)]
    out += [f"justification:{t}.{c}:not-in-contract" for t, c in sorted(released - columns, key=str)]
    return out


def assemble_manifest(candidate, records, file_digests: dict, input_digests: dict, signing_key):
    """``(manifest, reasons)``; the manifest is None when any reason exists. Signed with ``signing_key``."""
    assertions, evidence, reasons = evidence_for(records, candidate.scenario)
    if reasons:
        return None, reasons
    # not_applicable records (04: n 0, hits 0) are listed for transparency; evidence_for never uses them.
    gate = [gate_entry(r) for r in sorted(records, key=lambda r: r.check) if r.status in ("pass", "not_applicable")]
    contract = candidate.contract
    m = {
        "schemaVersion": SCHEMA_VERSION,
        "release": {
            "scenario": candidate.scenario, "recipient": candidate.recipient, "created": candidate.created,
            "releaseScopeId": release_scope_id(scenario=candidate.scenario, recipient=candidate.recipient,
                                               inputs=dict(input_digests), tool_revision=candidate.tool_revision),
        },
        "bindings": {
            "files": dict(sorted(file_digests.items())),
            "inputs": dict(sorted(input_digests.items())),
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
    m["residualRisks"] = sorted([*m["residualRisks"], *low_severity_risks(records)], key=lambda r: r["risk"])
    m["signature"] = {"alg": "HMAC-SHA256", "keyId": signing_key.key_id(),
                      "value": compute_signature(m, signing_key)}
    return m, []
