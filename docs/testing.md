# Test tiers

Use the shared environment with `PYTHONUTF8=1`, `TZ=UTC`, `PYTHONPATH=src`, and
`PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\sinceai-pycache` (PowerShell:
`$env:PYTHONPYCACHEPREFIX = Join-Path $env:LOCALAPPDATA 'sinceai-pycache'`).
Do not set `PYTHONDONTWRITEBYTECODE` on the top-level command: D30 caches bytecode
outside the tree instead of recompiling on every run. Child processes may still
disable writes; they can read the shared cache. Commands below assume that
environment's Python. Agent test processes run at BelowNormal priority (D27).

- **Implementers/fixers/reviewers (D27):** run **only affected tests**, both
  while iterating and for the done-report, through
  `scripts/overnight/affected-tests.ps1 -Run`. The helper maps changed files to
  test paths and runs `pytest -n 2 -m "not slow"`; do not separately run the
  entire fast suite or full suite. Report the selection and actual result,
  never a claim that unselected tests passed. Shared test infrastructure changes
  (including this tier hook/config) deliberately map to the whole fast suite.
- **Merger only (D28/D30):** one merger batches up to four ready tickets in a
  merge train. On the exact merged revision run `python -m pytest -n 16 -m "not slow"`
  first, and **only if green**, `python -m pytest -n 16 -m slow`. Merger processes
  keep Normal priority. Bisect a red batch and return the culprit; merge the rest.
  Docs-only batches run only `tests/docs` and `tests/story_kit`. Missing kit,
  skips, errors, timeouts, or nonzero exits never count as a pass.

From a ticket worktree, invoke the helper in the main clone (where the shared
virtual environment lives) and explicitly select the worktree:

```powershell
powershell -NoProfile -File C:\Users\kivas\AI\sinceai-hackaton\scripts\overnight\affected-tests.ps1 -Worktree (Get-Location).Path -Run
```

Omit `-Run` to inspect its selection without executing tests. The helper is
maintained on `main`; do not copy or fork its policy in ticket branches.

The default pytest invocation still runs everything. Only an explicit
`-m "not slow"` deselects heavy tests. `tests/conftest.py` marks exact node IDs
from `tests/slow_tests.txt`, plus every test with the inherited `kit` marker or
the transitive `kit_root` fixture dependency. New real-kit fixtures must depend
on `kit_root`, or their tests must use `@pytest.mark.kit`. A synthetic fixture
called `kit`, `make_kit`, or `mini_kit`, and merely setting `PETS_KIT` to a
synthetic path, do not imply real-kit access.

Synthetic gate/verification modules stay fast even above the timing threshold:
`tests/run/`, `tests/verify/`, `tests/checks/test_runner.py`,
`tests/checks/test_review_r3.py`, and `tests/manifest/test_cli.py`. This module-level
rule retains every refusal, manifest-validation and limited/full verification
case, including shared synthetic fixture setup, not just three happy-path smoke
IDs. It changes selection only; existing test bodies/checks are untouched. Other
synthetic CLI modules (detector, offline, scaffold, etc.) remain timing-classified.
Real-kit markers or transitive `kit_root` dependencies always override the exemption.
The three `FAST_CLI_SMOKE` IDs remain explicit live-suite pins for gate refusal,
both verification tiers and determinism. `tests/test_tiers.py` collects the real
suite with `-m "not slow"` and checks those pins, the restored fail-closed cases,
and that every canonical slow-list ID exists and is actually marked slow.

## Refreshing the list

Refreshing is a merger/test-infrastructure maintenance operation, not an agent
iteration step. Profile once with low parallelism (this change's one profiling
run is the approved exception to D27); keep the raw log outside git:

```powershell
python -m pytest -n 2 -q -p no:cacheprovider --durations=0 --durations-min=0 *> C:\path\outside-repo\durations.log
if ($LASTEXITCODE -ne 0) { throw 'Profile failed; do not regenerate' }
python tools/list_slow_tests.py C:\path\outside-repo\durations.log
```

The generator sums reported setup/call/teardown seconds for each exact node ID,
selects totals >=2 seconds, adds collected real-kit dependencies, removes the
synthetic gate/verification module exceptions, and sorts the output. It collects tests but
does not run them again. Prefer an unfiltered passing full run from this revision.
If the approved single profile failed or skipped tests, the explicit
`--allow-failed-profile` option uses its timings only and warns; it does **not**
turn that run into pass evidence. Report its actual failures/skips and use the
affected-tests helper on the finished revision rather than rerunning the full
suite as an agent.
With `--durations-min=1.0`, subsecond phases are unavailable and cannot be
included in totals; use zero on future refreshes. Relative ordering matters more
than absolute timings on a loaded machine. Review and commit the generated list;
never commit raw logs or kit data. New unprofiled synthetic tests remain fast
until the next refresh; real-kit tests are slow immediately.

## Release smoke (D34, issue #116)

The real-kit smoke is an **explicit script tier**, not a pytest test/marker. Neither
the default pytest invocation, `-m "not slow"`, nor `-m slow` executes it. Only its
small synthetic regression tests live under `tests/smoke/` and belong to the fast
tier. This uses D34's script alternative, keeping the product smoke out of both
existing tiers without changing the shared collection hooks or pytest config.

After the slow tier is green, the merger runs this from the exact, clean merged
checkout (docs-only batches remain exempt). Use the same UTF-8, UTC and external
bytecode-cache environment described above:

```powershell
$sha = git rev-parse HEAD
python scripts/release_smoke.py --sha $sha
```

`--kit` overrides `PETS_KIT`, otherwise the pinned kit path is used. A selected kit
without `results/benchmark.json` fails, with no fallback to another kit. The script
executes the production CLI, with a fresh in-memory HMAC key passed only through
`PETS_HMAC_KEY`. It never prints or saves child stdout/stderr. Protected tables and
private scoring artefacts stay outside the checkout, in a new attempt directory.

- HEALTH-S1 must release; both verify tiers and the dashboard then run.
- CS-S1 follows `tests/smoke/expectations.json` **read from Git at that SHA**, not
  from the working file or the presence of a release. It remains `refused` until
  #24's change commits `released`; a released expectation runs the same four steps.
- A release needs all expected CLI exits, explicit limited/full verify messages,
  passing applicable gate checks, person-k at the policy target (where applicable),
  every policy/catalogue purpose check at its threshold or enumerated sacrifice
  floor, and a nonempty dashboard. Registry `not_applicable` is recorded separately;
  error/not-run/missing checks never pass.
- An expected refusal needs exit 1, no published release, and actual gate failure
  names and positive hit counts. Exit 2 is unknown, **not** a valid refusal.
- Dirty checkouts, SHA mismatch, unavailable inputs, identity drift, missing steps,
  errors and timeouts fail. `--timeout` sets the total CLI budget (default 360 seconds).
  Expectations, tool revision and input digests never come from a planted pass file.

Each invocation atomically replaces
`C:\Users\kivas\AI\sinceai-out\smoke\<full SHA>\smoke.json`, initially with a failed
record and then with the observed result. It includes the revision, scenario-catalogue
digest, input-table digests, each step's exit/status/seconds, gate counts, failure
counts, k and purpose aggregates, dashboard presence and scenario/overall verdicts.
The writer validates exact record keys at every level and canonical JSON (sorted
keys, fixed separators). Dynamic maps contain only schema/check names and aggregates.
`--validate-record <path>` checks this format only; it **never** supplies fresh
merge evidence or replaces executing the smoke. `--out-root` is available for isolated
rehearsals/tests but must be outside the checkout.

A nonzero smoke is a red merge gate, even if earlier tiers passed. The planning
session owns adding this command to the merger template after this ticket lands.
