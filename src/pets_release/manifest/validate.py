"""Manifest validation (schema + cross-field rules), signature payload and the not-measured helper.

Error codes are ``"<json path>: <rule>"`` and never contain instance values. Map keys that do not look like
plain names are masked as ``<key>``.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pets_release.manifest.canonical import canonical_bytes, canonical_digest, loads_strict
from pets_release.manifest.schema import MANIFEST_SCHEMA

MANIFEST_FILENAME = "privacy_manifest.json"

_VALIDATOR = Draft202012Validator(MANIFEST_SCHEMA)
_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
_DIGIT_RUN = re.compile(r"[0-9]{3,}")


def not_measured(reason: str) -> dict:
    """The schema-valid value for a ``measured.*`` section or residual-risk ``rate`` not measured yet."""
    return {"status": "not_measured", "reason": reason}


def release_scope_id(*, scenario: str, recipient: str | None, inputs: dict, tool_revision: str) -> str:
    """First 16 hex of SHA-256(canonical {inputs, recipient, scenario, toolRevision}); same bytes as ticket 06."""
    payload = {"inputs": dict(inputs), "recipient": recipient, "scenario": scenario, "toolRevision": tool_revision}
    return canonical_digest(payload)[:16]


def signing_bytes(manifest: dict) -> bytes:
    """Canonical bytes of ``manifest`` without its ``signature`` key (the HMAC payload)."""
    return canonical_bytes({k: v for k, v in manifest.items() if k != "signature"})


def compute_signature(manifest: dict, signing_key: Any) -> str:
    """HMAC-SHA256 hex over ``signing_bytes(manifest)``.

    ``signing_key`` is either an opaque key object with ``hmac_sha256(data: bytes) -> bytes`` (ticket 06's
    ``manifest_signing_key(master)``; its bytes are never read) or raw ``bytes`` (test fixtures only).
    Anything else raises TypeError.
    """
    payload = signing_bytes(manifest)
    if isinstance(signing_key, (bytes, bytearray)):
        return hmac.new(bytes(signing_key), payload, hashlib.sha256).hexdigest()
    mac = getattr(signing_key, "hmac_sha256", None)
    if not callable(mac):
        raise TypeError("signing key must be bytes or expose hmac_sha256(data) -> bytes")
    digest = mac(payload)
    if not isinstance(digest, bytes) or len(digest) != 32:
        raise TypeError("hmac_sha256 must return 32 bytes")
    return digest.hex()


def _fmt(path) -> str:
    out = "$"
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        elif _SAFE_KEY.match(part) and not _DIGIT_RUN.search(part):
            out += "." + part
        else:
            out += ".<key>"
    return out


def _schema_errors(obj: Any) -> list[str]:
    errs = []
    for e in _VALIDATOR.iter_errors(obj):
        rule = "propertyNames" if "propertyNames" in e.schema_path else e.validator
        errs.append(f"{_fmt(e.absolute_path)}: {rule}")
    return errs


def _order(errs: list[str], path: str, items: list, key) -> None:
    keys = [key(i) for i in items]
    if any(a >= b for a, b in itertools.pairwise(keys)):
        errs.append(f"{path}: order")


def _cross_field_errors(m: dict) -> list[str]:
    errs: list[str] = []
    gate = {c["check"]: c for c in m["gate"]["checks"]}
    ev = m["assertionEvidence"]

    by_check: dict[str, list[str]] = {}
    for name, rec in ev.items():
        by_check.setdefault(rec["check"], []).append(name)
        g = gate.get(rec["check"])
        if g is None:
            errs.append(f"{_fmt(['assertionEvidence', name, 'check'])}: not-in-gate")
        elif g != rec:
            errs.append(f"{_fmt(['assertionEvidence', name])}: gate-mismatch")
    for names in by_check.values():
        if len(names) > 1:
            errs += [f"{_fmt(['assertionEvidence', n, 'check'])}: shared" for n in names]

    if m["bindings"]["checkVersions"] != {c: g["version"] for c, g in gate.items()}:
        errs.append("$.bindings.checkVersions: gate-mismatch")
    if set(m["bindings"]["files"]) != set(m["contract"]["files"]):
        errs.append("$.bindings.files: contract-mismatch")
    rel, b = m["release"], m["bindings"]
    if rel["releaseScopeId"] != release_scope_id(scenario=rel["scenario"], recipient=rel["recipient"],
                                                 inputs=b["inputs"], tool_revision=b["toolRevision"]):
        errs.append("$.release.releaseScopeId: mismatch")
    if m["bindings"]["contractDigest"] != canonical_digest(m["contract"]):
        errs.append("$.bindings.contractDigest: mismatch")

    def tk(*fields):
        return lambda r: tuple(r[f] for f in fields)

    _order(errs, "$.inventory", m["inventory"], tk("dataset", "table", "column"))
    for i, row in enumerate(m["inventory"]):
        _order(errs, f"$.inventory[{i}].evidence", row["evidence"], lambda s: s)
    _order(errs, "$.pets", m["pets"], tk("table", "column", "pet"))
    _order(errs, "$.fieldJustifications", m["fieldJustifications"], tk("table", "column"))
    _order(errs, "$.contract.qi", m["contract"]["qi"], tk("table", "column"))
    _order(errs, "$.contract.tokens", m["contract"]["tokens"], tk("table", "column"))
    for f, spec in m["contract"]["files"].items():
        _order(errs, f"{_fmt(['contract', 'files', f, 'required'])}", spec["required"], lambda s: s)
        if not set(spec["required"]) <= set(spec["columns"]):
            errs.append(f"{_fmt(['contract', 'files', f, 'required'])}: not-in-columns")
    _order(errs, "$.gate.checks", m["gate"]["checks"], tk("check"))
    _order(errs, "$.sacrifices", m["sacrifices"], tk("check"))
    _order(errs, "$.residualRisks", m["residualRisks"], tk("risk"))
    _order(errs, "$.fitFor", m["fitFor"], tk("scenario"))
    _order(errs, "$.notFitFor", m["notFitFor"], tk("scenario"))
    if {f["scenario"] for f in m["fitFor"]} & {f["scenario"] for f in m["notFitFor"]}:
        errs.append("$.notFitFor: overlaps-fitFor")
    if m["release"]["scenario"] not in {f["scenario"] for f in m["fitFor"]}:
        errs.append("$.fitFor: missing-release-scenario")

    meas = m["measured"]
    lists = {"utility": ("tasks", tk("task")), "privacy": ("components", tk("component")),
             "search": ("points", tk("step")), "baselines": ("rows", tk("baseline", "metric")),
             "redaction": ("labels", tk("label"))}
    for section, (field, key) in lists.items():
        if meas[section]["status"] == "measured":
            _order(errs, f"$.measured.{section}.{field}", meas[section][field], key)
    if meas["redaction"]["status"] == "measured":
        _order(errs, "$.measured.redaction.summary", meas["redaction"]["summary"], tk("metric"))
    return errs


def validate_manifest(obj: Any) -> list[str]:
    """Sorted, content-free error codes; ``[]`` means valid. Cross-field rules run only on a schema-valid object."""
    errs = _schema_errors(obj)
    if not errs:
        errs = _cross_field_errors(obj)
    return sorted(set(errs))


def validate_manifest_file(path: str | Path) -> list[str]:
    """Validate a manifest file (or a release folder's ``privacy_manifest.json``). Raises OSError if unreadable."""
    p = Path(path)
    if p.is_dir():
        p = p / MANIFEST_FILENAME
    raw = p.read_bytes()
    try:
        obj = loads_strict(raw)
    except (ValueError, UnicodeDecodeError):
        return ["$: not-json"]
    errs = validate_manifest(obj)
    try:
        if canonical_bytes(obj) != raw:
            errs = sorted(set(errs) | {"$: not-canonical"})
    except (TypeError, ValueError):
        errs = sorted(set(errs) | {"$: not-canonical"})
    return errs
