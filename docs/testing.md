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

## Checkout-write guard

`tests/conftest.py` identifies the running tests' checkout with Git, not the
process working directory or a planted marker. At session start and finish it
takes one `git status --porcelain -z --untracked-files=all` snapshot per checkout:
the tests' own checkout and the main checkout found through `--git-common-dir`.
With xdist, only the controller takes snapshots, bracketing all workers and
fixture teardowns. A new dirty path fails the session. Pre-existing untracked or
modified paths are baseline, so unrelated existing work is not reported.
Only pytest's actual temporary directory is exempt, not arbitrary temp-named
folders. Keep bytecode and generated outputs outside the checkout as above.

The same guard checks literal `ROOT`/`REPO`/`repo_root` and file-relative `root`
resolutions (including function-local ones), plus `Path(__file__).parents[n]`
references, against the tests' Git worktree identity. Fixture/import ancestors
inside `tests/` are allowed; repo-root assignments must equal the Git root.
It never evaluates test source. Regression tests run real nested pytest sessions
in temporary repositories and linked worktrees, never plant files in the real
main checkout.
Unrecognised uppercase `ROOT`/`REPO`/`REPO_ROOT` expressions fail closed; use
literal file-relative pathlib expressions rather than dynamic root discovery.

This is a boundary check, not a filesystem sandbox: writes outside a running
pytest session, ignored files, changes to already-dirty paths, or writes restored
before the final snapshot are not detected. Git errors fail closed. Independent
scripts and agents must still follow the worktree rules in `AGENTS.md`.
