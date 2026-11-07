"""Gate-check registry and runner: the one implementation shared by the gate and ``verify``.

Public API (everything else is internal)::

    from pets_release.checks import run_checks, all_checks, Check, Outcome, Violation, register

    result = run_checks(release_dir, contract, context, scope=None, checks=None)
    result.refused        # True unless every selected check has status "pass"
    result.records        # tuple[CheckRecord], sorted by check name
    result.to_dict()      # {"refused": bool, "records": [CheckRecord dict]} (canonical-JSON ready)

``contract`` is the release contract dict (spec "Contract" shape):
``{files: {<file.csv>: {required: [col], columns: {col: {form, params}}}}, qi: [...],
tokens: [{table, column, scope}]}``. ``table`` is the file stem (``visits`` for ``visits.csv``).
``form`` is either an anchored regex (``^...$``) or a validator ID: ``hex64``, ``text``,
``integer``, ``decimal``, ``enum`` (``params.values``). ``params.nullable: true`` allows "".

``context`` is a plain mapping. Keys used here:
  ``phase``: ``"gate"`` (before the manifest exists) or ``"verify"`` (default; manifest required).
Producer-scope checks (tickets 11, 23) may read further keys, e.g. ``source_tables``, ``hmac_key``,
``kit_root``; a check whose inputs are absent returns ``Outcome.not_run()``, which refuses.

``scope``: None runs every registered check (gate, ``verify --full``); ``"release"`` runs only
release-scope checks (recipient ``verify``).

CheckRecord (closed, exact keys): ``{check, version, scope, status, denominator: {unit, n}, hits,
violations: [Violation]}``. Violation: ``{check, label, severity, file, column, count, locations}``;
``count`` = number of cells (or files/columns) with a hit, ``locations`` = up to the first 100
0-based data-row indices, sorted. Never values.

``result.registry_error`` is set (module names only) when discovery failed; then nothing ran and
``refused`` is True.

Adding a check (sibling tickets): put a module anywhere under ``pets_release/checks/`` (e.g.
``checks/text/stitch.py``) and decorate a function::

    from pets_release.checks import register, Outcome, Violation

    @register(name="text.health", version="1.0.0", scope="release", unit="turns")
    def run(release, contract, context) -> Outcome:
        if context.get("source_tables") is None:      # producer checks: inputs unavailable
            return Outcome.not_run()                   # -> status not_run, refuses
        ...
        return Outcome(n=scanned, violations=(Violation(name, label, "high", file, column, count, rows),))

Names match ticket 02's ``checkName`` pattern ``^[a-z0-9][a-z0-9._-]{0,63}$`` (``contract.files``,
``rescan.payment-cards``, ``text.payment-cards``, ``producer.person-k``); versions are semver
``1.0.0``. ``register`` raises on anything else. ``ASSERTION_CHECKS`` maps each manifest
export-assertion key (camelCase) to the one check name that is its evidence.

The registry auto-imports every submodule on first ``all_checks()``; names must be unique. Discovery
fails closed: a non-package submodule not starting with ``_`` that registers zero checks, or fails
to import, raises ``RegistryError`` (the runner refuses). Put helpers in ``_``-prefixed modules; no
module-level ``CHECKS`` tuples.
``Outcome.not_applicable()`` is allowed only for a check registered with ``applies_to=(forms...)``
when the contract declares no column with any of those forms; the runner verifies this, records
``not_applicable`` with denominator 0 (does not refuse), and records ``error`` for any other use.
A run where nothing but not_applicable records exist refuses.
``applies_to`` selectors besides forms (ticket 23): ``contract:k`` (applies iff the contract carries
a top-level ``k``; for the k checks, CS-S1 has none) and ``column:<file>.csv/<column>`` (applies iff
the contract releases that column; e.g. ``turn-id-synthetic``). Unknown selectors are
rejected at registration; an unreadable contract counts as declaring the selector (error). Writer rules (16): see the
``runner`` docstring (not_applicable and low-severity hits can never back an export assertion).

Violation ``file``/``column`` name only contract-listed files and columns; any other
release-derived name is reported as ``unlisted-file#<i>`` / ``unlisted-column#<pos>``.

The runner, not the check, decides status: an exception -> ``error``; ``Outcome.not_run()`` ->
``not_run``; denominator 0 on a non-empty release -> ``error``; any high-severity violation ->
``fail``; otherwise ``pass`` (low-severity hits stay counted, as residual risk). Nothing outside
the release folder (and no pass file anywhere) is read to decide a status.

``release`` is a ``pets_release.checks.release.Release``: ``.entries`` (sorted names in the
folder), ``.csv_files``, ``.table(file)`` -> ``Table(header, frame)`` with every value a ``str``,
``.manifest()``, ``.path``, ``.sha256(name)``.

This package imports nothing from the detector, redactor or transforms (tested).
"""
from pets_release.checks.records import CheckRecord, Outcome, Violation
from pets_release.checks.registry import (
           ASSERTION_CHECKS,
           Check,
           RegistryError,
           all_checks,
           register,
)
from pets_release.checks.runner import GateResult, run_checks

__all__ = ["ASSERTION_CHECKS", "Check", "CheckRecord", "GateResult", "Outcome", "RegistryError", "Violation",
           "all_checks", "register", "run_checks"]
