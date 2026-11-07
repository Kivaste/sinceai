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

Adding a check (sibling tickets): put a module anywhere under ``pets_release/checks/`` (e.g.
``checks/text/stitch.py``) and decorate a function::

    from pets_release.checks.registry import register, Outcome, Violation

    @register(name="healthInText", version="1", scope="release", unit="turns")
    def run(release, contract, context) -> Outcome: ...

The registry auto-imports every submodule on first ``all_checks()``; names must be unique.
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
from pets_release.checks.registry import Check, all_checks, register
from pets_release.checks.runner import GateResult, run_checks

__all__ = ["Check", "CheckRecord", "GateResult", "Outcome", "Violation", "all_checks", "register", "run_checks"]
