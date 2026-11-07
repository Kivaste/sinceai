"""Gate runner: runs the selected registry checks and decides every status itself (fail closed)."""
from __future__ import annotations

from dataclasses import dataclass

from pets_release.checks.records import SEVERITIES, CheckRecord, Outcome, Violation
from pets_release.checks.registry import Check, RegistryError, all_checks
from pets_release.checks.release import Release


@dataclass(frozen=True)
class GateResult:
    refused: bool
    records: tuple
    registry_error: str | None = None  # module/check names only; set when discovery failed

    def to_dict(self) -> dict:
        return {"refused": self.refused, "records": [r.to_dict() for r in self.records],
                "registryError": self.registry_error}

    def summary(self) -> dict:
        """Aggregate-only view: per check status, hits and denominator."""
        return {"refused": self.refused, "registryError": self.registry_error,
                "records": [{"check": r.check, "version": r.version, "scope": r.scope, "status": r.status,
                             "hits": r.hits, "denominator": dict(r.denominator),
                             "violations": [{k: v for k, v in x.to_dict().items() if k != "locations"}
                                            for x in r.violations]}
                            for r in self.records]}


def _record(chk: Check, status: str, n: int = 0, violations: tuple = ()) -> CheckRecord:
    return CheckRecord(check=chk.name, version=chk.version, scope=chk.scope, status=status,
                       denominator={"unit": chk.unit, "n": int(n)},
                       hits=sum(v.count for v in violations), violations=violations)


def _valid(out, chk: Check) -> bool:
    if not isinstance(out, Outcome) or type(out.n) is not int or out.n < 0:
        return False
    for v in out.violations:
        if not isinstance(v, Violation) or v.severity not in SEVERITIES or v.check != chk.name:
            return False
        if type(v.count) is not int or v.count < 1:
            return False
    return True


def _run_one(chk: Check, release, contract, context) -> CheckRecord:
    if release is None:
        return _record(chk, "error")
    try:
        out = chk.run(release, contract, context)
    except Exception:  # noqa: BLE001  (message may carry values; record the status only)
        return _record(chk, "error")
    if not _valid(out, chk):
        return _record(chk, "error")
    if out.skipped:
        return _record(chk, "not_run")
    viol = tuple(sorted(out.violations, key=lambda v: (v.file, v.column or "", v.label, v.severity)))
    if out.n == 0:  # nothing scanned: on a non-empty release that is an error; an empty one is never clean
        return _record(chk, "error", 0, viol)
    status = "fail" if any(v.severity == "high" for v in viol) else "pass"
    return _record(chk, status, out.n, viol)


def run_checks(release_dir, contract, context=None, *, scope: str | None = None, checks=None) -> GateResult:
    """Run the registry (or ``checks``) over ``release_dir``. See the package docstring."""
    context = dict(context or {})
    try:
        selected = tuple(all_checks() if checks is None else sorted(checks, key=lambda c: c.name))
    except RegistryError as e:  # an untrustworthy registry refuses; nothing runs
        return GateResult(refused=True, records=(), registry_error=str(e))
    if scope is not None:
        selected = tuple(c for c in selected if c.scope == scope)
    try:
        release = Release(release_dir)
    except Exception:  # noqa: BLE001
        release = None
    records = tuple(_run_one(c, release, contract, context) for c in selected)
    refused = (not records) or any(r.status != "pass" for r in records)
    return GateResult(refused=refused, records=records)
