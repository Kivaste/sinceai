# Prompt templates (orchestrator → subagents)

Binding since Sat 10:45 (D31). Copy each template into the subagent prompt and fill in the `<…>` fields. Give **pointers, not pasted code**. The **outputs** demonstrate that the skill steps happened; naming a skill in the prompt proves nothing.

---

## 1. Implementer / fixer

```
You implement <ticket NN / issue #N: title> in repo Kivaste/sinceai, unattended. Model: <model>.
Read: AGENTS.md (binding), GLOSSARY.md, the issue (`gh issue view <N> -R Kivaste/sinceai --comments`),
spec #1 › Testing Decisions (approved seams), docs/testing.md, C:\Users\kivas\AI\sinceai-notes\conventions.md.
Worktree: C:\Users\kivas\AI\sinceai-wt\<slug>  Branch: ticket/<slug>  Base: origin/integration/pets-release @ <base sha>
Never edit, test or commit in C:\Users\kivas\AI\sinceai-hackaton (the main checkout); use `git -C <your worktree>` only.

Process — call the Skill tool with `tdd` FIRST and follow it (also read its tests.md and mocking.md):
- Test only at the approved seams: the CLI (`pets-release run|verify|detect|dashboard|submission`), the redactor seam
  (turns in → spans/placeholders out) and the detector seam (table in → field inventory out). Name the seam for each test.
- One vertical slice at a time. For EACH behavioural change:
  1. Rule: <the rule the change adds or restores>   Failure case: <trigger → wrong result today>
  2. Write the regression test. RUN IT. It must FAIL for the intended reason (not an import/typo error).
  3. Make the smallest implementation change.
  4. Rerun that test (must pass), then: powershell -NoProfile -File C:\Users\kivas\AI\sinceai-hackaton\scripts\overnight\affected-tests.ps1 -Worktree <worktree> -Run
- Tests exercise the PRODUCTION checks/CLI; never replace a check with a passing stub; no tautological expectations.
- Never display kit rows or values; inspect schema/aggregate counts only; debug with hand-made synthetic rows.
- A defect class that recurs gets a deterministic regression test or guard in the same change.
- Never run the whole suite (the merger does). Commit small; merge the integration tip in before reporting; push the branch.

Report EXACTLY in the "Done-report" format of templates.md §4, with the real commands and outcomes as they happened.
If you never observed a red run for a rule, write "No red observed: <why>". Do not reconstruct evidence afterwards.
```

## 2. Reviewer, Standards axis (code-review skill)

```
READ-ONLY review, Standards axis only (code-review skill). Do not edit, commit or push.
Diff: git -C <worktree> diff <base sha>...<head sha>     Commits: git -C <worktree> log <base sha>..<head sha> --oneline
Pinned head: <head sha>. If `git rev-parse <head sha>` fails or the diff is empty, stop and say so.
Standards sources: AGENTS.md, GLOSSARY.md, docs/adr/*.md, docs/testing.md, docs/agents/*.md.
Smell baseline (Fowler, judgement calls only; a documented repo standard overrides it):
<paste the smell list from C:\Users\kivas\.config\opencode\skills\code-review\SKILL.md §3 in full>
Brief: Report, per file/hunk, (a) every violation of a documented standard (cite file + rule; may be hard),
(b) baseline smells (name it, quote the hunk; always a judgement call). Also check AGENTS.md test rules: red-before-green
evidence in the branch's tests, no vacuous or stubbed-out production checks, fail-closed paths, no row values.
Skip anything tooling enforces. Verdict line: `STANDARDS: APPROVE` or `STANDARDS: CHANGES REQUIRED` (block only on
documented-standard breaches of high severity: fail-open, value leak, vacuous test of a privacy check, broken determinism).
Under 400 words. Delta round <r>: check only that earlier blocking findings are fixed + the fix diff <prev head>..<head sha>.
```

## 3. Reviewer, Spec axis (code-review skill)

```
READ-ONLY review, Spec axis only (code-review skill). Do not edit, commit or push.
Diff: git -C <worktree> diff <base sha>...<head sha>     Commits: git -C <worktree> log <base sha>..<head sha> --oneline
Pinned head: <head sha>. Spec sources: the issue (`gh issue view <N> -R Kivaste/sinceai`) and spec #1 (sections: <…>),
docs/decisions.md entries <…>.
Brief: Report (a) requirements/acceptance criteria missing or partial, (b) behaviour not asked for (scope creep),
(c) requirements that look implemented but wrong. Quote the spec/issue line for each finding. Check the done-report's
evidence matches the head (same sha; red/green present; real-run artefact for this head).
Verdict line: `SPEC: APPROVE` or `SPEC: CHANGES REQUIRED` (block on an unmet acceptance criterion or wrong behaviour).
Under 400 words. Delta round <r>: earlier blocking findings + fix diff <prev head>..<head sha> only.
```

Reviewer assignment (D31, user decision A): Claude-written code → Standards = `xai/grok-4.7#medium`, Spec = `openai/gpt-6.1-sol#high`.
Sol-written code → Standards = `xai/grok-4.7#medium`, Spec = `claude-agent/sonnet`.
Core fail-closed tickets (gate, verify, writer, manifest, keys, measurer, the CS-S1 chain), **round 1 only**: all four, i.e. both
families × both axes. Delta rounds use the cross-map. Report findings under `## Standards` and `## Spec` separately; never merge or re-rank.

## 4. Done-report (implementer output, posted by the orchestrator as the issue comment)

```
## Done-report
- Issue: #<N>
- Branch: ticket/<slug>
- Head: <40-char sha>
- Base: <integration sha merged in last>
- Implementer: <model>
### TDD evidence
- Rule: <…>
  - Failure case: <…>
  - Seam: <CLI | redactor | detector>
  - Red: `<command>` → exit <code>; failing: <test id> — <one-line reason>     (or: No red observed: <why>)
  - Green: `<command>` → exit 0; <n> passed
### Affected tests
- `affected-tests.ps1 -Run` → exit <code>; <n> passed, <m> skipped; selection: <…>
### Real-run evidence
- Revision: <sha>
- Command: `<…>`
- Artefacts: <absolute path>
- Outcome: <gate x/y; verify (limited) exit c; verify --full exit c; scorecard …>     (docs/test-only tickets: N/A: <why>)
### Reviews
- Standards: <model> r<k> <APPROVE|CHANGES REQUIRED> @ <sha>
- Spec: <model> r<k> <APPROVE|CHANGES REQUIRED> @ <sha>
### Unknowns
- none      (or list every skipped / errored / not-run required check — these block the close)
```

## 5. Merger (merge train, D28/D30)

```
You are the merger. One merger at a time. Integration worktree: C:\Users\kivas\AI\sinceai-wt\integration.
Batch (Merge-after order): <ticket branches + head shas>. For each: verify the branch head equals the reviewed head sha.
Merge them in order; then on the EXACT merged sha run: fast tier `pytest -n 16 -m "not slow"`, and only if green,
`pytest -n 16 -m slow` (docs-only batch: tests/docs + tests/story_kit only). Env: PYTHONUTF8=1, TZ=UTC,
PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\sinceai-pycache. Red → bisect (reset to the last green tip, test halves), return the
culprit, merge the rest. Green → push. Report: merged sha, per-tier exit code + counts, the tickets merged, any culprit.
```

## 6. Closing a ticket (orchestrator)

1. Post the done-report as the issue comment.
2. Run `powershell -NoProfile -File scripts/overnight/check-done-report.ps1 -Issue <N>`. **Close only on exit 0.** Exit 1 lists what's missing. Fix that, or keep the ticket open; never close around it.
3. `gh issue close <N>`, then clean up (resume-prompt §2.8).
