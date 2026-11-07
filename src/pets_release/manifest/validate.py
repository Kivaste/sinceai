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


def _flagged(part: str) -> bool:
    from pets_release.checks.cells._shape import flagged

    return flagged(part)


def _safe(part: str) -> str:
    """``part`` if it looks like a plain name, else ``<key>``: identifier-shaped names never reach a diagnostic."""
    # a key the identifier detectors flag is masked in every diagnostic (round-2 review, #61)
    ok = isinstance(part, str) and _SAFE_KEY.match(part) and not _DIGIT_RUN.search(part) and not _flagged(part)
    return part if ok else "<key>"


def _fmt(path) -> str:
    out = "$"
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else "." + _safe(part)
    return out


def _field(t: str, c: str) -> str:
    """Content-free ``$.fieldJustifications: <table>.<column>`` prefix (#109 round 2)."""
    return f"{_fmt(['fieldJustifications'])}: {_safe(t)}.{_safe(c)}"


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


# #132: anchored regexes proven (by inspection, under the ``fullmatch`` the contract.forms check applies) to
# accept only strings the validator ID already accepts. Regex inclusion is not checked in general: any regex
# not listed here must equal the rung's form exactly. ``text`` has no entry on purpose (#132 r2): the text
# checks scan only ``text``-form columns, so a regex substitute would hide the column from them.
_NARROWING_REGEXES: dict[str, frozenset[str]] = {
    "hex64": frozenset({"^[0-9a-f]{64}$"}),  # the hex64 validator's own pattern
    "decimal": frozenset({"^[0-9]+$"}),  # [0-9]+ is within -?\d+(?:\.\d+)?
}


def _narrows(form: str, validator: str) -> bool:
    """True only if ``form`` provably accepts no string the validator ID ``validator`` rejects and the swap
    leaves every check's scope unchanged."""
    return form in _NARROWING_REGEXES.get(validator, frozenset())


def _applied_rungs(m: dict, errs: list[str]) -> dict:
    """#109: ``{(table, source column): rung}`` as the bound contract applies it to each released field
    (``contract.files[<table>.csv].columns[<outputColumn>].params.rung``). Fail closed (no rung, no sacrifice
    decision): the contract rung must exist and equal the justification's, lie on the ladder the pinned policy
    gives that source column (its default family, or exactly its ``alt_floors`` rung), and the column's form must
    be the rung's form. A rung whose form is a validator ID may declare an anchored regex instead only if that
    regex provably narrows the validator (#132, ``_narrows``); every regex-form rung (all timestamp rungs) must
    carry exactly its own form. A contract column no released justification backs is an error too."""
    from pets_release.ladders import CONTRACT_FORMS, RUNG_KIND
    from pets_release.policy import get_policy

    try:
        policy = get_policy(m["release"]["scenario"])
    except KeyError:
        errs.append("$.release.scenario: no-policy")
        return {}
    floors, alt_floors = policy.floors, policy.alt_floors or {}
    files = m["contract"]["files"]
    applied, backed = {}, set()
    for f in m["fieldJustifications"]:
        if f["decision"] != "released":
            continue
        t, c, out = f["table"], f["column"], f["outputColumn"]
        backed.add((f"{t}.csv", out))
        col = files.get(f"{t}.csv", {}).get("columns", {}).get(out)
        rung = col["params"].get("rung") if col is not None else None
        where = _field(t, c)
        if not isinstance(rung, str):
            errs.append(f"{where}: rung-contract-missing")
            continue
        if rung != f["rung"]:
            errs.append(f"{where}: rung-contract-mismatch")
        floor = floors.get((t, c))
        # on the default family's ladder, or exactly the policy-enumerated alternative floor (CS-S1 turn_id)
        on_ladder = floor is not None and (RUNG_KIND.get(rung) == floor.family or alt_floors.get((t, c)) == rung)
        if not on_ladder:
            errs.append(f"{where}: rung-not-on-ladder")
        want = CONTRACT_FORMS.get(rung)
        if want is None or (col["form"] != want and not _narrows(col["form"], want)):
            errs.append(f"{where}: rung-form-mismatch")
        applied[(t, c)] = rung
    for file, spec in sorted(files.items()):
        for col in sorted(spec["columns"]):
            if (file, col) not in backed:
                errs.append(f"{_fmt(['contract', 'files', file, 'columns', col])}: rung-unjustified")
    return applied


def _rung_step_errors(m: dict) -> list[str]:
    """#89/#109: a sacrifice-only rung the contract applies needs exactly one sacrifice ``rungStep`` for that
    column and rung, whose measured k at ``from`` exceeds the budget and whose check still scores >= 0.9 (fail
    closed); every ``rungStep`` must match a released field at its ``to`` rung. Rungs are read from the bound
    contract, never from the justification alone."""
    from pets_release.ladders import SACRIFICE_ONLY_RUNGS
    from pets_release.run.purpose import THRESHOLD

    errs: list[str] = []
    steps = [(i, s) for i, s in enumerate(m["sacrifices"]) if "rungStep" in s]
    released = _applied_rungs(m, errs)
    for (t, c), rung in sorted(released.items()):
        if rung not in SACRIFICE_ONLY_RUNGS:
            continue
        match = [s for _, s in steps if (s["rungStep"]["table"], s["rungStep"]["column"], s["rungStep"]["to"])
                 == (t, c, rung)]
        if len(match) != 1:
            errs.append(f"{_field(t, c)}: rung-sacrifice-missing")
    for i, s in steps:
        st = s["rungStep"]
        at = st["atFrom"]
        if released.get((st["table"], st["column"])) != st["to"] or st["from"] == st["to"]:
            errs.append(f"{_fmt(['sacrifices', i, 'rungStep'])}: field-mismatch")
        if not at["share"] > at["maxShare"] or at["unitsSuppressed"] > at["unitsBefore"]:
            errs.append(f"{_fmt(['sacrifices', i, 'rungStep', 'atFrom'])}: budget-not-exceeded")
        if not isinstance(s["after"], (int, float)) or isinstance(s["after"], bool) or not s["after"] >= THRESHOLD:
            errs.append(f"{_fmt(['sacrifices', i, 'after'])}: rung-sacrifice-check-not-strict")
    errs += _lift_step_errors(m, released, THRESHOLD)
    return errs


def _lift_step_errors(m: dict, released: dict, threshold: float) -> list[str]:
    """#157 r3: a ``liftStep`` sacrifice entry records a purpose cost that stays above the strict floor; it can never
    lower a floor. Its floor must be exactly the strict threshold, its check must still score >= it, it carries no
    rungStep, its field must be released at its rung, and the lift must exceed the bound at ``from`` and hold it at
    ``to`` (fail closed)."""
    errs: list[str] = []
    for i, s in enumerate(m["sacrifices"]):
        st = s.get("liftStep")
        if st is None:
            continue
        p = ["sacrifices", i]
        after = s["after"]
        if isinstance(s["floor"], bool) or s["floor"] != threshold:
            errs.append(f"{_fmt([*p, 'floor'])}: lift-step-floor-not-strict")
        if not isinstance(after, (int, float)) or isinstance(after, bool) or not after >= threshold:
            errs.append(f"{_fmt([*p, 'after'])}: lift-step-check-not-strict")
        if "rungStep" in s:
            errs.append(f"{_fmt(p)}: lift-step-with-rung-step")
        if released.get((st["table"], st["column"])) != st["rung"] or st["fromParams"] == st["toParams"]:
            errs.append(f"{_fmt([*p, 'liftStep'])}: field-mismatch")
        if not st["atFrom"]["lift"] > st["maxLift"] >= st["atTo"]["lift"]:
            errs.append(f"{_fmt([*p, 'liftStep'])}: bound-not-shown")
    return errs


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
    errs += _rung_step_errors(m)
    _order(errs, "$.residualRisks", m["residualRisks"], tk("risk"))
    _order(errs, "$.fitFor", m["fitFor"], tk("scenario"))
    _order(errs, "$.notFitFor", m["notFitFor"], tk("scenario"))
    if {f["scenario"] for f in m["fitFor"]} & {f["scenario"] for f in m["notFitFor"]}:
        errs.append("$.notFitFor: overlaps-fitFor")
    if m["release"]["scenario"] not in {f["scenario"] for f in m["fitFor"]}:
        errs.append("$.fitFor: missing-release-scenario")

    # the pinned scenario policy fixes the k target and the released QI set (#62)
    from pets_release.policy import contract_policy_problems

    errs += [f"$.{p}" for p in contract_policy_problems(m["release"]["scenario"], m["contract"],
                                                                   m["fieldJustifications"])]

    # identifier-shaped text anywhere outside the pinned digest/signature metadata (#61)
    from pets_release.manifest.value_scan import identifier_shape_errors

    errs += identifier_shape_errors(m, _fmt)

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
