"""CheckRecord, Violation and Outcome value types (closed shapes; no values ever)."""
from __future__ import annotations

from dataclasses import dataclass, field

UNITS = ("cells", "turns", "persons", "files", "rows")
SCOPES = ("release", "producer")
STATUSES = ("pass", "fail", "error", "not_run", "not_applicable")
SEVERITIES = ("high", "low")
MAX_LOCATIONS = 100


@dataclass(frozen=True)
class Violation:
    check: str
    label: str
    severity: str
    file: str
    column: str | None
    count: int
    locations: tuple = ()

    def to_dict(self) -> dict:
        return {"check": self.check, "label": self.label, "severity": self.severity, "file": self.file,
                "column": self.column, "count": self.count, "locations": list(self.locations)}


@dataclass(frozen=True)
class Outcome:
    """What a check function returns; the runner turns it into a CheckRecord."""

    n: int
    violations: tuple = ()
    skipped: bool = False
    inapplicable: bool = False

    @staticmethod
    def not_run() -> Outcome:
        """Inputs unavailable (e.g. no source tables): recorded as not_run, which refuses."""
        return Outcome(n=0, violations=(), skipped=True)

    @staticmethod
    def not_applicable() -> Outcome:
        """The contract declares no column of this check's forms (``applies_to``). The runner
        verifies that claim; otherwise the record is an error."""
        return Outcome(n=0, violations=(), inapplicable=True)


@dataclass(frozen=True)
class CheckRecord:
    check: str
    version: str
    scope: str
    status: str
    denominator: dict
    hits: int
    violations: tuple = field(default=())

    def to_dict(self) -> dict:
        return {"check": self.check, "version": self.version, "scope": self.scope, "status": self.status,
                "denominator": dict(self.denominator), "hits": self.hits,
                "violations": [v.to_dict() for v in self.violations]}


def locations(rows) -> tuple:
    """Sorted, de-duplicated, capped row indices."""
    return tuple(sorted({int(r) for r in rows})[:MAX_LOCATIONS])
