# Decisions and open questions

Current snapshot of what's decided and what's still open. Updated as decisions are made.

The planning map lives on GitHub Issues (D17). The append-only execution log is [decision-log.md](decision-log.md). Hard-to-reverse trade-offs also have an ADR in [adr/](adr/).

## Decided

| # | Decision | Detail |
|---|---|---|
| D1 | **GitHub repo** | Private repo `Kivaste/sinceai`, branch `main`. History rewritten Fri 23:53 to remove the challenge kit. Goes public at submission. |
| D2 | **Purpose-first angle** | Start from the data request (business need), release only what's needed, at the coarsest detail that serves it. See [concept.md](concept.md). |
| D3 | **Tool architecture: option D (hybrid)** | LLM turns the request into a needs spec + purpose checks → measured search tightens each field to the minimum → verification. Build the search on the official tasks first (C), then put the LLM step in front (B). The LLM step is now a later stretch, not v1; see D9. See [tool-spec.md](tool-spec.md). |
| D4 | **Scope** | One tool; one lead dataset and scenario demonstrated in depth; nothing mandates using all datasets. |
| D5 | **Vocabulary** | [GLOSSARY.md](../GLOSSARY.md) is the source of the project's terms. |
| P1 | **Skeleton-first** | Accepted. Build order is skeleton-first; the loop lives inside the product, not as a dev-time process. See [build-plan.md](build-plan.md). |
| P2 | **Train / validation / test** | Accepted. Checks split into training (`pets-eval`), validation (our attacker), test (hidden organiser attackers). See [evaluation-strategy.md](evaluation-strategy.md). |
| D6 | **Team** | 3 people. Kivaste = main dev, drives orchestrator agents. Business teammate = video, deck, visuals, tagline, description. SuhtetarkKool (non-developer) = redaction spot-check (~200 turns), lexicon curation (fi/sv/en health terms + names), fresh-machine README test, demo rehearsal + jury Q&A. |
| D7 | **Plan merge** | [HACKATHON_PLAN.md](../HACKATHON_PLAN.md) + [PRIVACY_PATTERNS_PLAN.md](../PRIVACY_PATTERNS_PLAN.md) are the engine and proof (S1 compiler, S2 free-text redactor, P1 keyed pseudonyms, P2 fail-closed gate, P3 privacy manifest, P4 offline). Purpose-first ([concept.md](concept.md)) is the framing: the scenario's required tasks decide what is released and at which detail, everything else withheld, every field justified. See ADR 0001. |
| D8 | **Scenarios** | HEALTH-S1 lead (withhold `clinical_notes`; 20/29 `ed_visits` columns not needed). CS-S1 second (free-text redactor; withhold `agent_note` + `customers`; keep `split`). Live detection on `unseen` as the opener. |
| D9 | **LLM** | None in v1. Later stretch (go/no-go Sat 14:00): request → needs spec, seeing only request text + data dictionary, never data values. Provider is user-configurable via API key / endpoint; suggested default local/self-hosted (OpenAI-compatible endpoint), Mistral as second suggestion. See ADR 0002. |
| D10 | **Detail choice** | Small measured search over detail ladders (~3 levels/field, joint QI moves, local suppression last), inner loop on our own fast k/utility, `pets-eval` confirms; fallback to hand-picked levels if no valid release by Sat 12:00. |
| D11 | **Tech stack** | Python 3.14 existing `.venv`, pandas, stdlib `hmac`/`hashlib`, pytest + pytest-xdist, argparse CLI `pets-release run\|verify`, jinja2 static HTML dashboard rendered from the manifest, ruff. No ML deps in v1; stretch NER/LLM as optional extras. |
| D12 | **Process** | Matt Pocock skills. `/grill-with-docs` (done) → `/to-spec` → `/to-tickets` (GitHub Issues with blocking edges) → `/implement-spec` (parallel implementers in worktrees, `/tdd`, merger, `/code-review`) → `/retro`. Plus two rules borrowed from pstack: each ticket shows real-artefact evidence (an actual release folder / `pets-eval` run), and the orchestrator keeps [decision-log.md](decision-log.md). |
| D13 | **Model roster** | Orchestrator `claude-agent/opus`; core/hard tickets `claude-agent/opus`; routine tickets `xai/grok-4.7` (high); grunt `xai/grok-4.7` (medium); reviewers `claude-agent/sonnet` + `openai/gpt-6.1-sol` + `opencode-go/deepseek-v4.1-flash`, independent, reconciled by the orchestrator. |
| D14 | **Agent autonomy** | Fully automatic (no permission prompts). Project config: [opencode.json](../opencode.json). |
| D15 | **Row maps** | `pets_submission/` (incl. row maps) lives only in a separate private repo `Suhtetark-Kool/trusted-since-ai` with organisers invited; the public repo never contains row maps. Confirm delivery method with TrustED on Discord Sat morning. See ADR 0003. |
| D16 | **Checkpoints (EET)** | Spec+tickets Sat 01:30; first e2e HEALTH-S1 release + manifest + dashboard Sat 09:00 (story kit for business teammate: dashboard HTML, pitch-beat script, before/after numbers CSV); search/NER go-no-go + show TrustED Sat 12:00; LLM go/no-go Sat 14:00; `pets_submission` Sat 16:00; feature freeze Sat 20:00; submit Sun 08:00. Replaces P4. |
| D17 | **Tracker** | GitHub Issues on `Kivaste/sinceai`, default triage labels; [AGENTS.md](../AGENTS.md) is the steering file. |
| D13a | **Roster change (Sat 02:15)** | Grok 4.7 high was too slow (2–5 min per turn; no code after 12 min while Opus tickets committed). `model:grok` tickets and grunt work → `claude-agent/sonnet` (fallbacks: `openai/gpt-6.1-sol` — regular Sol, never `-fast` — then `xai/grok-4.7#medium`). In-flight Grok tickets without commits are re-dispatched on Sonnet. Reviewers for all (Claude-written) code: `openai/gpt-6.1-sol` + `opencode-go/deepseek-v4.1-flash`. Ready tickets merge immediately once the full suite is green on the merged result; then their worktree and branch are removed. Integration → `main` after #22 and after the final review. |
| D13b | **Lighter reviews (Sat 05:35)** | Measured: Grok 4.7 medium reviews median 10.8 min; DeepSeek flash 25+ min and throttled at 16 concurrent; GPT-6.1 Sol over quota. Core (`model:opus`) tickets: Grok 4.7 medium + GPT-6 Luna (opencode-go). Routine tickets: Grok only. Delta re-reviews from round 2; max 3 rounds, then high-severity-only blocking, the rest as follow-up issues. At most 8 concurrent reviews per provider. Final branch review: Gemini 4 Argon + GPT-6 Luna. DeepSeek out of ticket reviews. |
| D13c | **Quality recovery (Sat 05:50)** | To offset D13b: privacy/fail-closed follow-ups (#41, #42, #44, #45, #47, #50) are must-fix before 20:00, each delta-reviewed by Grok + Gemini 4 Argon. Numbers-producing tickets (18, 19, 22, 25, 29) get two reviewers; 18 and 19 get a retroactive Gemini review. Final review: GPT-6.1 Sol (if its quota reset by 11:00) or Luna, plus Gemini, plus an AGENTS.md rule audit. |
| D13d | **GPT-6.1 Sol switch-back** | A probe polls `openai/gpt-6.1-sol` every 5 min. On the first success it records the exact reset time and the orchestrator switches: Sol replaces Luna as second reviewer on core and numbers tickets; retroactive Sol review of 05, 11 and 02's final delta; final review Sol + Gemini. At most 4 concurrent Sol sessions; on a renewed limit, fall back to Luna. |
| D24 | **Extra parallel work (Sat 06:25)** | Waiting heads (26, 27, 30) reviewed immediately; rolling final review over merged code (delta passes after that); Sonnet story drafts in `docs/story/` for the business teammate; #31 LLM front end started early in isolation, shipping only on the 14:00 go. Orchestrator hand-over at >300k tokens (watchdog). |
| D25 | **One draft PR into main (Sat 06:40)** | After #22, one draft PR integration/pets-release → main, body per the /pr skill, updated at milestones; merged with a merge commit after the final review. Ticket merges stay direct into integration. Until the PR merges, testers use the integration branch. |
| D13e | **opencode-go exhausted (Sat 07:05)** | All `opencode-go/*` models (Gemini, Luna, DeepSeek) fail with a usage limit. Reviews: core = Grok 4.7 + GPT-6.1 Sol (at most 4 concurrent Sol); routine = Grok; must-fix deltas = Grok + Sol; rule audit = Grok high; final = Sol + Grok high. Sol fallback: free GLM 5.3 (Zhipu). A probe restores Gemini/Luna when the quota resets. Pass-1 Gemini review re-run on Grok high. |
| D13f | **GPT-6.1 Sol unlimited (Sat 07:20)** | ChatGPT subscription upgraded. Every ticket and every delta review: Grok 4.7 medium + GPT-6.1 Sol high. Rule audits: Sol high (+ Grok high). Final review: Sol high + Grok high. No Sol cap (sanity limit 12 concurrent). Overrides D13b tiering and the D13d/D13e Sol limits. |
| D13g | **Cap 28, Sol implements easier work (Sat 07:20)** | Worker cap 16 → 28. Opus keeps core tickets and must-fixes in gate/verify/writer/manifest/keys/measurer/minimiser. Routine tickets, medium/low follow-ups, docs and test work go to GPT-6.1 Sol as implementer (to avoid Anthropic rate limits), reviewed by Grok + Sonnet. On an Anthropic rate limit, more work moves to Sol and the Claude cap drops to 16. Sol is waiting on re-auth (#86). |
| D27 | **Affected tests only (Sat 09:58)** | Implementers, fixers and reviewers run only the tests affected by their change (`scripts/overnight/affected-tests.ps1 -Run`: changed files → test dirs, plus end-to-end consumers for core packages, `-n 2`, not slow). Only the merger runs the full suite, once per merge. All agent test processes run at BelowNormal priority so the desktop stays responsive. |
| D28 | **Faster merge gate (Sat 10:08)** | Merge train of up to 4 ready tickets per full-suite run, with bisection on red; the merger's full suite at `-n 16`; merger test processes keep Normal priority while agent tests stay BelowNormal (`deprioritize-tests.ps1` recognises the integration worktree). |
| D29 | **CS-S1 chain: one owner + 12:00 fallback (Sat 10:12)** | One Opus implementer owns #23 together with the redactor/secrets must-fixes (#53, #54, #56, #63, #92); no parallel fixers on those files. If CS-S1 still can't pass the gate at 12:00: just before the gate, turns in which the independent checker still finds a high-severity hit are withheld from the release. This is a recorded sacrifice (count, plus the effect on turn-level tasks), and the reduced independence of the checker for those turns is stated in residual risks. The gate itself stays strict. |
| D30 | **Inner loop and gate speed-ups (Sat 10:20)** | Bytecode cache moved outside the repo (`PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\sinceai-pycache`) instead of disabled; subprocesses still read it. The merge train fails fast (fast tier first, then slow) and runs only the docs tests for docs-only batches. The kit-data parse cache for tests is a Sol ticket (#97). Defender exclusion for `C:\Users\kivas\AI` is the human's action. |
| D31 | **Fidelity to the skills (Sat 10:50, user steering)** | Brief v3 states only the effective policies, with history kept here. Mandatory prompt templates (`scripts/overnight/templates.md`): observable TDD (rule, failure case, red then green with real commands, "No red observed" if so); two-axis code review in separate sub-agents, cross-mapped across families (Standards = Grok; Spec = Sol for Claude code, Sonnet for Sol code); core fail-closed round 1 gets all 4. Tickets close only when `check-done-report.ps1` passes (head-bound evidence, both axes, red/green, affected tests, real-run artefact, no unknowns). Finish with fresh proof on the exact final SHA, then `retro`. Evidence audit at 10:45: 0/57 closed tickets have complete red/green evidence, 0/15 sampled reviews separate the axes, and no run certifies the integration tip. |
| D18 | **Two-tier verify** | `verify <release>` (recipient): re-runs release-derivable checks, reports "VERIFIED (limited)", never full success. `verify --full --kit` (controller, key in env): re-runs every check; unavailable = fail. Evidence scope `release` or `producer`. From spec review (Sonnet, GPT-6.1 Sol). |
| D19 | **Per-label export assertions** | One assertion per validated identifier label, each with its own check and denominator. PERSON/ADDRESS/LOCATION/ORG/DATE/AGE in text are residual risks with measured recall. No universal "no identifiers" claim. |
| D20 | **Manifest integrity** | Per-file SHA-256, bound input digests, revision and check versions; HMAC signature with the key. Recipient verify is tamper-evident only; `--full` checks the signature. Limitation stated as a residual risk. |
| D21 | **CS-S1 turn_id** | Kept as-is only if a named check confirms it is a synthetic record key with no person/conversation info (official CS-U5 runs unmodified); otherwise row-map lineage adapter, both scores reported. |
| D22 | **HEALTH-S1 age** | Release `age_band`; our per-person k over every released QI is authoritative; the scorecard's blind spot for renamed columns is disclosed. |
| D23 | **Scope trims** | Hand-picked HEALTH-S1 plan is the walking skeleton; search replaces it. LLM front end only after both releases pass gate + verify. Zero-shot redaction: clinical_notes only. Search deterministic and bounded (≤~100 candidates/scenario, cached evaluations; scikit-learn allowed for evaluation). Both attacker personas stay; recipient keys stay (first cut). |

### Options considered for D3

| Option | Verdict |
|---|---|
| A. Fixed lookup of needs per scenario | Rejected: a config, not a tool |
| B. LLM reads the request | Kept as the front end of the hybrid; deferred out of v1 (D9) |
| C. Measured search over detail ladders | Kept as the engine and the fallback demo; this is v1 |
| **D. B → C hybrid** | **Chosen** as the end shape; v1 ships C, B is the Sat 14:00 stretch |

P4 (checkpoints: skeleton Fri 23:00, show TrustED Sat 12:00, freeze Sat 20:00, submit Sun 08:00) was accepted, then replaced by D16. Do not use the Fri 23:00 skeleton checkpoint.

## Proposed (awaiting confirmation)

| # | Proposal | Where |
|---|---|---|
| P3 | Scoreboard instead of "judge tooling"; mock judge as a 1-hour task | [evaluation-strategy.md](evaluation-strategy.md) |

## Answered

| # | Question | Answer |
|---|---|---|
| Q1 | **Destination of the planning map**: does it end at a build spec, with building outside the map? | Yes. The map ends at the spec and the tickets; building is `/implement-spec`, outside the map (D12). |
| Q3 | **Where the planning map lives**: GitHub Issues on `Kivaste/sinceai`? | Yes. Default triage labels; [AGENTS.md](../AGENTS.md) steers agents (D17). |
| Q4 | **Team**: how many people, which skills, everyone using an AI coding agent? | 3 people, roles in D6. Not everyone codes: CLI + static HTML dashboard (D11), not a web UI. |
| Q5 | **Lead dataset and scenario** | HEALTH-S1 lead, CS-S1 second, live detection on `unseen` as the opener (D8). |
| Q6 | **LLM**: which model and hosting; cost; offline fallback | None in v1. Later stretch only; user-configurable provider; suggested default local/self-hosted, Mistral second. Never sees data values (D9, ADR 0002). |
| Q9 | **Report/UI format** | argparse CLI `pets-release run\|verify` plus a jinja2 static HTML dashboard rendered from the manifest (D11). Business teammate owns video, deck and visuals (D6). |
| Q10 | **`unseen` dataset**: do we submit labels for the organiser check? | Yes. Live detection on `unseen` is the demo opener (D8), not deferred until after the skeleton. |

## Open questions

| # | Question | Recommendation |
|---|---|---|
| Q2 | **Attacker time budget**: about 25% of build time, one person, 2–3 attacker types fitted to the lead dataset? | Yes |
| Q7 | **Purpose-check representation**: generated code vs a fixed vocabulary of analysis types | Leaning towards the vocabulary (safer, easier to validate) |
| Q8 | **Acceptance threshold** for purpose checks (e.g. ≥ 0.9) | Not yet discussed |
| Q11 | **Questions for TrustED on Discord** (criteria and weighting, the hidden-check process) | Draft once the plan is confirmed. Delivery method for row maps is a Sat-morning question (D15); it does not close this item. |
