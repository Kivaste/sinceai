# AGENTS.md

**sinceai** — purpose-first PETs tool for the TrustED PETs Transformer challenge, Since AI Hackathon 2026.
**Deadline: Sun 8 Nov 10:00 EET.**

See `README.md` and `docs/` for the plan, spec and setup.

## Hard rules

- **Never commit** anything from `Briefs/` (the challenge kit), any `rowmap_*.csv`, anything under a `truth/` directory, or secrets (`.env`, HMAC keys, other key material). These are gitignored; don't force-add them.
- **Read every CSV with `dtype=str`** (e.g. `pd.read_csv(path, dtype=str)`). Never let pandas infer types — it mangles IDs, leading zeros and dates.
- **Run `pets-eval` with `PYTHONUTF8=1`** and `--root` pointing at the kit (`Briefs/TRUSTED_PETS_PROVING_GROUND_2026 (1)/TRUSTED_PETS_PROVING_GROUND_2026`).
- **Never send data values to any LLM or network service.** Schema/field names and aggregate metrics only; row values stay local.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `Kivaste/sinceai`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` plus `docs/adr/`. See `docs/agents/domain.md`.

## Engineering rules

These apply to every change. A skipped, missing or errored check is a fail, not a pass.

### Fail closed

- A check passes only on exit 0, and only after the named check actually ran. Exit 1 is a fail. Skipped, timeout, missing or errored is unknown, and unknown is a fail.
- Never mint evidence. Do not write a check result, a review file, or a manifest assertion for your own change.

### Export assertions

- An export assertion is the literal `false` only when its named check ran on this release and found 0 hits. Never coerce a missing or errored value to `false`. A manifest missing a required assertion is invalid.

### Paths

- Choose strict paths by identity (revision, input digest, check name), never by the presence of a file someone could plant. Each new guard gets a planted-file test.

### Evidence

- Bind evidence to the exact revision and inputs. A new commit invalidates it. `pets-release verify` re-runs checks and never reuses a prior pass. A green status line or a log is not evidence.
- Every ticket's done-report includes evidence from a real run: an actual release folder, gate output, or `pets-eval` scorecard. Unit tests alone are not enough.

### Closed records

- Manifests and check records have exact keys. Unknown keys fail. Digests are canonical JSON: sorted keys, fixed separators.

### Tests

- Privacy tests call the production checks, and the real CLI at least once. Never hand-build both the writer and the reader in a test. A test that would still pass with the check deleted is not evidence.
- TDD: write the rule the change adds, list the failure rows from trigger to result, and write a red test for each changed row before any code.
- A defect class found twice becomes an automated test or a gate check in the same change.

### Review

- Every ticket gets independent read-only reviews from model families other than the implementer's (how many and which is below, per `docs/decisions.md` D13b). No agent reviews its own change. The orchestrator records the reviews. A new head after fixes gets a fresh (delta) review pass.
- Every implementer is Claude (Opus or Sonnet), so reviewers are always non-Claude. Since Sat 05:35 (D13b): core (`model:opus`) tickets get two reviews (`xai/grok-4.7#medium` + `opencode-go/gpt-6-luna#medium`) and routine tickets get one (`xai/grok-4.7#medium`). Rounds 2 and later are delta reviews of the fix only. After round 3, only high-severity findings block. The final integration-branch `/code-review` uses `opencode-go/gemini-4-argon` + `opencode-go/gpt-6-luna`.
- Merge a ticket as soon as its required reviews pass and the full suite is green on the merged result. Then remove that ticket's worktree and delete its branch, locally and on origin (`scripts/overnight/resume-prompt.md` §2).

### Worktrees and commits

- Before pushing, run `git log origin/<base>..HEAD` and confirm every commit is yours.
- Remove only worktrees your own session created. Never remove worktrees by glob. Never kill another run's tests or temp dirs.
- Each ticket owns its files. If two tickets must edit the same file, the orchestrator sequences them.

### Determinism

- Run Python with `PYTHONUTF8=1` and `PYTHONDONTWRITEBYTECODE=1`, and set `TZ=UTC`. Sort rows before hashing or writing. Do not rely on set order or wall-clock time in outputs.
- The same input, key and versions must produce a byte-identical release.

### Content-free artefacts

- Commits, docs, logs, review briefs and manifests contain schema names and aggregate metrics only. Never row values.
- Test fixtures in git are small hand-made synthetic rows, never copied from the kit.

### Orchestration

- Keep `docs/decision-log.md` append-only: EET time, the decision, why, and an evidence pointer.
- After every event, write the heartbeat under `scripts/overnight/` (that script is being built now).
- Park anything that needs a human with the label `ready-for-human`. Do not block on it.
