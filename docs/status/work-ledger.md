# Work ledger — Kivaste/sinceai

Generated **Sat 12:22 EET (UTC+2)**, 7 Nov 2026; issue/remote-history snapshot **Sat 12:18**. Integration tip: **`10c2ba7fd4efe2a54f5ac44ac8fe1f61fbe06cee`** (`origin/integration/pets-release`). Process history: `origin/main` through `678fbd9`.

**Issues: 114 total, 67 closed, 47 open.** [#1](https://github.com/Kivaste/sinceai/issues/1) is the parent specification, excluded from tasks: **113 task issues = 67 done / 46 open**. Every task issue appears exactly once below. Unissued commit groups are additional tasks, excluded from issue counts.

| Category | Task issues | Done (closed) | Open | Sum of done durations |
|---|---:|---:|---:|---:|
| A. Foundation & kit access | 12 | 9 | 3 | 11:25 |
| B. Detect | 5 | 4 | 1 | 2:07 |
| C. Policy & selection | 17 | 7 | 10 | 16:06 |
| D. Transform | 10 | 6 | 4 | 10:27 |
| E. Gate & checks | 11 | 6 | 5 | 15:10 |
| F. Proof | 10 | 8 | 2 | 7:06 |
| G. Measure & show | 19 | 16 | 3 | 10:06 |
| H. End-to-end releases | 6 | 1 | 5 | 0:41 |
| I. Submission & presentation | 11 | 2 | 9 | 6:26 |
| J. Process, orchestration, CI & test infrastructure | 12 | 8 | 4 | 32:27 |
| **Total** | **113** | **67** | **46** | **112:01** |

**Totals:** issue-bound done windows **83:31**, story drafts **3:04**, unissued process groups **25:26** = **112:01**. Work ran in parallel, so sums exceed wall-clock. Shared merge-batch windows are counted for each issue; these are elapsed windows including review/waiting, not person-hours or unique active effort. There are **85 done rows** (67 issues + 18 unissued groups) and **48 to-do rows** (46 issues + final review/proof and README finalisation).

## Reading this ledger

- **Done** means GitHub `CLOSED`, or committed/merged for an unissued group. It does **not** certify present-day privacy, review completion, or fresh proof. An open issue stays to do even if some code has merged: notably #62, #71 and #84.
- Product time = earliest author date in each merge's `M^1..M^2` to merge commit date, on the integration first-parent merge history. Multiple batches use earliest start through latest merge. Explicit `#N` references take precedence; `ticket NN`, `ticket/NN-…` and `fuNN` use the local ticket/issue map. A closed issue with no mapped merge uses created→closed, explicitly marked.
- Process groups use first→last commit dates from the requested `origin/main` path-filtered log. The slow-split branch uses its first→last implementation commits. Planning is the requested single **Fri 23:40→Sat 02:01** task. Single-commit groups have **0:00** observed span, not zero actual effort. Durations are floored to minutes before summing; displayed start/finish times omit seconds.
- Open branch starts use the earliest author date among commits on matching origin ticket/follow-up branches not yet in the pinned integration tip. Inherited dependency commits can predate an issue's own fix; those cases are identified. Shared branches are named when no dedicated branch exists. No matching commit means no inferred start time.
- Follow-ups belong to the code phase they repair; mixed issues are kept whole under their primary module. Cross-cutting test/audit infrastructure goes in J; human issues #33–#39 stay in I.
- **P0:** privacy/fail-closed must-fix or release critical path. **P1:** submission requirement. **P2:** medium follow-up. **P3:** low batch/stretch/enhancement. Estimates are remaining wall-clock including independent two-axis review and merge for code tasks. Human estimates are execution time, not code-review time. The CS-S1 chain's **1.5–2.5 h is one shared budget**, not additive across its issues.
- Sources are GitHub issue titles/bodies/status/labels, metadata-only issue comments/assignees/dependencies, the local ticket map, and Git metadata. No kit rows, release contents, keys or private row maps were read for this ledger. This file creates no check evidence or assertion.

### A. Foundation & kit access

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#2](https://github.com/Kivaste/sinceai/issues/2) | Scaffold, CLI, kit access, offline guard | Establish a deterministic offline command entry point. | String-only kit loading, strict scenarios/digests and inherited socket blocking; `83efaa0`. | 0:21 (from Sat 02:19) | Sat 02:40 |
| [#4](https://github.com/Kivaste/sinceai/issues/4) | Synthetic fixture generator | Make realistic-sized, reproducible local test inputs. | Generate health/CS schemas and enough synthetic records for required utility tasks; `244e278`. | 3:09 (from Sat 02:20) | Sat 05:30 |
| [#9](https://github.com/Kivaste/sinceai/issues/9) | Kit-eval adapter | Turn evaluator output into strict purpose/risk results. | Disposable dtype conversions, subprocess scorecard, explicit lineage and validated aggregate exports; `6422758`. | 3:13 (from Sat 02:22) | Sat 05:35 |
| [#41](https://github.com/Kivaste/sinceai/issues/41) | Offline/package follow-up | Preserve offline execution and ship required resources. | Child-env helper, non-vacuous open-spy coverage and nested package-data globs; `f23ece7`. | 0:07 (from Sat 05:40) | Sat 05:47 |
| [#46](https://github.com/Kivaste/sinceai/issues/46) | Fixture phrase/format follow-up | Make fixtures detect utility loss and follow kit formats. | Split phrase variants and repair synthetic field formatting; `a5af05f`. | 0:09 (from Sat 05:44) | Sat 05:53 |
| [#48](https://github.com/Kivaste/sinceai/issues/48) | Adapter/policy follow-up | Reject unknown metrics and canonicalise policy metadata. | NaN/l-diversity checks, evaluated-denominator rules and canonical timestamp rung; `06a0d79`. | 0:18 (from Sat 06:20) | Sat 06:38 |
| [#64](https://github.com/Kivaste/sinceai/issues/64) | Released-table scorecard checks | Stop released tables silently being treated as withheld. | Compare reported table statuses/sections with expected released columns; `5ae4f9c`. | 0:52 (from Sat 07:11) | Sat 08:04 |
| [#78](https://github.com/Kivaste/sinceai/issues/78) | Refusal/manifest fixture provenance | Make committed fixture provenance reproducible. | Extend deterministic fixture generation to refusal/manifest fixtures; `4ab170b`. | 2:24 (from Sat 08:45) | Sat 11:09 |
| [#82](https://github.com/Kivaste/sinceai/issues/82) | Offline coverage on every entry point | Block network access beyond the main CLI path. | Cover evaluator children and module/auxiliary entry points with inherited guard; `5ae4f9c`. | 0:52 (from Sat 07:11) | Sat 08:04 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#81](https://github.com/Kivaste/sinceai/issues/81) | Enforce string-preserving CSV reads everywhere | P2 | 30–60 min | In progress since Sat 09:03 on `origin/ticket/fu81-csv-determinism`; round-2 fixer also owns #83/#94; source/test alias and NA-policy guards added, review/merge remain. |
| [#83](https://github.com/Kivaste/sinceai/issues/83) | Sort aggregate exports and force LF CSV output | P2 | 30–60 min, shared #81 batch | In progress since Sat 09:03 on shared `origin/ticket/fu81-csv-determinism`; no dedicated branch. Round 2; sequence overlapping measurement changes with #26/#94. |
| [#110](https://github.com/Kivaste/sinceai/issues/110) | Refuse silently skipped scorecard k evaluation | P0 | 45–60 min | Pass-2 Spec finding; derive expected QI/k components from inputs, not mutually consistent omissions. Fresh HEALTH-S1 run/full verify required. No matching origin branch observed. |

### B. Detect

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#21](https://github.com/Kivaste/sinceai/issues/21) | Detector and unseen labels | Inventory every field with a role and supporting signals. | Validators, names/cardinality/FK/range signals and exact kit/unseen serializers; `d0b0386`. | 0:16 (from Sat 05:10) | Sat 05:27 |
| [#45](https://github.com/Kivaste/sinceai/issues/45) | Detector guard/signal follow-up | Close direct-CSV boundary bypasses and strengthen signals. | Forbidden-path guard, explicit vocabulary errors and signal/scaling cleanup; `b67da90`. | 0:12 (from Sat 05:42) | Sat 05:54 |
| [#70](https://github.com/Kivaste/sinceai/issues/70) | Non-vacuous detector access test | Prove detect never reads truth/catalog answer material. | Actual subprocess audit-hook access tracing rather than string-only assertions; `6f6bae6`. | 0:18 (from Sat 07:09) | Sat 07:28 |
| [#79](https://github.com/Kivaste/sinceai/issues/79) | Content-free detect errors | Prevent parser exceptions from exposing input values. | Replace raw exception printing and guard emitted metadata; `9f3aba3`. | 1:21 (from Sat 08:03) | Sat 09:25 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#87](https://github.com/Kivaste/sinceai/issues/87) | Decide detector no-signal default | P2 | 30–60 min after decision | Human owner: Kivaste (decision pending). In progress since Sat 08:42 on `origin/ticket/fu87-detector`; blanket QI-default change reduced detection quality and was parked. Detector labels do not set release policy; retain that distinction. |

### C. Policy & selection

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#8](https://github.com/Kivaste/sinceai/issues/8) | Detail ladders and pure transforms | Represent each allowed precision level deterministically. | Timestamp/age/geo/ICD/numeric/token/withheld rungs and pure plan application; `910a80a`, later `c411162`. | 3:13 (from Sat 02:16) | Sat 05:30 |
| [#10](https://github.com/Kivaste/sinceai/issues/10) | Scenario policies and hand plans | Pin purpose checks, privacy floors and allowed sacrifices. | Closed records for HEALTH-S1/CS-S1 with per-column floors and joint QI moves; `4c69eb1`. | 3:14 (from Sat 02:22) | Sat 05:36 |
| [#11](https://github.com/Kivaste/sinceai/issues/11) | Contract generator | Bind the selected plan to an independently checkable release. | Generate files/columns/forms, derived QIs and token scopes with canonical digest; `c26c9ed`. | 3:15 (from Sat 02:23) | Sat 05:38 |
| [#25](https://github.com/Kivaste/sinceai/issues/25) | Deterministic bounded minimiser | Choose the coarsest purpose-preserving release plan. | Withhold/coarsen/joint moves, digest cache, bounded evaluations and post-suppression checks; `faa726c`. | 2:26 (from Sat 05:25) | Sat 07:51 |
| [#43](https://github.com/Kivaste/sinceai/issues/43) | Ladder alignment/numeric follow-up | Avoid row misalignment and misleading derived-column names. | Validate redactor indices, protect age output names and handle numeric/type edges; `93d61a6`. | 0:29 (from Sat 05:40) | Sat 06:10 |
| [#89](https://github.com/Kivaste/sinceai/issues/89) | Timestamp-rung ordering | Stop hour-only output pretending to preserve calendar detail. | Require purpose/privacy justification and correct coarseness ordering; `1a2c045`. | 2:52 (from Sat 08:39) | Sat 11:31 |
| [#90](https://github.com/Kivaste/sinceai/issues/90) | Low-severity policy/recipient batch | Avoid unnecessary released fields and clarify recipient separation. | Purpose-driven withholding plus recipient wiring/disclosure regressions; `31ffa5c`. | 0:37 (from Sat 10:44) | Sat 11:22 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#32](https://github.com/Kivaste/sinceai/issues/32) | LLM draft-policy front end (stretch) | P3 | ~45 min, only if go | #24/#26 plus Sat 14:00 go/no-go and both releases passing gate/verify. In progress since Sat 06:45 on `origin/ticket/31-llm`; exact-type/value-free transport fixes and reviews already underway. |
| [#63](https://github.com/Kivaste/sinceai/issues/63) | Bind generated conversational text contracts | P0 | 30–60 min; shared CS chain 1.5–2.5 h | Approved but blocked by #24 because branch carries CS commits. In progress since Sat 05:25 on `origin/ticket/fu63-cs-contract` (inherited dependencies; own binding fix Sat 07:29). |
| [#65](https://github.com/Kivaste/sinceai/issues/65) | Make mandatory CS health enforcement representable | P0 | 30–60 min | #24/#63. In progress since Sat 05:25 on `origin/ticket/fu65-cs-health` (inherited; own fix Sat 10:54); closed contract must require scenario-derived health enforcement. |
| [#66](https://github.com/Kivaste/sinceai/issues/66) | Execute raw turn-ID prerequisite | P0 | 30–60 min | #24/#63. In progress since Sat 05:25 on `origin/ticket/fu66-turnid-prereq` (inherited; own fix Sat 10:54); absent/failed check must force pseudonym/lineage fallback. |
| [#69](https://github.com/Kivaste/sinceai/issues/69) | Bind operative numeric transform parameters | P2 | 30–60 min | #24/#63. In progress since Sat 05:25 on `origin/ticket/fu69-contract-params` (inherited; own fix Sat 11:00); carry units/bin widths/origins and reject off-grid values. |
| [#99](https://github.com/Kivaste/sinceai/issues/99) | Purpose-driven timestamp alternatives | P3 | 2–3 h | Enhancement, not release-critical; define approved temporal goals/representations without releasing complementary date-reconstructing views. No matching origin branch observed. |
| [#100](https://github.com/Kivaste/sinceai/issues/100) | Selective cell protection before person removal | P3 | 3–5 h | Enhancement; threat model/checking semantics first, then bounded deterministic local protection and full rechecks. No matching origin branch observed. |
| [#109](https://github.com/Kivaste/sinceai/issues/109) | Enforce sacrifices against actual contract rungs | P0 | 45–60 min | Pass-2 Spec finding; align justification/source/output/rung mappings and remeasure actual sacrifice triggers. Fresh HEALTH-S1 proof invalid until fixed. No matching origin branch observed. |
| [#112](https://github.com/Kivaste/sinceai/issues/112) | Refuse missing PersonK in minimiser risk | P0 | 30–60 min | Pass-2 fail-closed must-fix; missing measurement must raise, never become perfect privacy. No matching origin branch observed. |
| [#115](https://github.com/Kivaste/sinceai/issues/115) | Pass-2 low-severity minimiser/test batch | P3 | 30–60 min | Reuse policy k-target validation and strengthen/remove name-only verification assertions. No matching origin branch observed. |

### D. Transform

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#7](https://github.com/Kivaste/sinceai/issues/7) | Pseudonymiser and key derivation | Preserve intended joins without reversible identifier hashes. | Domain-separated HMAC, HKDF, deterministic scope IDs and multilingual normalisation; `6f58567`. | 0:46 (from Sat 02:06) | Sat 02:53 |
| [#13](https://github.com/Kivaste/sinceai/issues/13) | Redactor core | Replace structured identifiers with stable typed placeholders. | Conversation normalisation, validators, original-offset projection and scoped substitution; `e1222fd`. | 3:33 (from Sat 02:10) | Sat 05:43 |
| [#14](https://github.com/Kivaste/sinceai/issues/14) | Lexicon labels and boundary rules | Cover names, places, dates, ages and health phrases. | Editable general-knowledge lexicons, runtime gazetteer, per-label boundary/deny rules; `5fae780`. | 3:26 (from Sat 02:17) | Sat 05:44 |
| [#29](https://github.com/Kivaste/sinceai/issues/29) | Recipient-scoped key wiring | Stop separate recipients joining pseudonym tokens. | Forward recipient identity into HKDF/token scope and manifest while preserving within-release joins; `dee7d18`. | 2:12 (from Sat 05:25) | Sat 07:38 |
| [#42](https://github.com/Kivaste/sinceai/issues/42) | Pseudonym normalisation follow-up | Avoid wrong name links and absorbed phone extensions. | Tighten surname suffix rules, strip extensions and improve canonical/error hygiene; `db4f353`. | 0:23 (from Sat 05:41) | Sat 06:04 |
| [#50](https://github.com/Kivaste/sinceai/issues/50) | Redactor/lexicon follow-up | Restore intended matching and strict lexicon parsing. | International phone forms, repaired Unicode lexicons, boundary validation and fixture claims; `f9c3589`. | 0:07 (from Sat 05:58) | Sat 06:05 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#54](https://github.com/Kivaste/sinceai/issues/54) | Catch remaining CS secrets/usernames/phones | P0 | Shared CS chain 1.5–2.5 h | Single D29 CS owner, not a separate fixer. In progress since Sat 06:17 on `origin/ticket/fu54-redactor`, continued on `origin/ticket/23-cs-s1`; round-5 fixes recorded. Fresh gate/recall evidence and delta review remain. |
| [#84](https://github.com/Kivaste/sinceai/issues/84) | Scan derived recipient keys without exposing private bytes | P0 | 30–60 min | Partial wave merged at `8e93dcf` Sat 11:47, issue remains open. Shared `origin/ticket/fu61-producer-wave` has no unmerged commits; closure/evidence must be checked, not inferred from merge. |
| [#88](https://github.com/Kivaste/sinceai/issues/88) | Validator precedence and spoken-form coverage | P0 | 45–60 min | Blocked by #54 and shared redactor ownership/#92; validators must beat amount/version denylists and keep validated email labels. No matching origin branch observed. |
| [#92](https://github.com/Kivaste/sinceai/issues/92) | Redact identifiers split across turns | P0 | Shared CS chain 1.5–2.5 h | Sequence after #54/#63; single CS owner. In progress since Sat 06:17 on `origin/ticket/fu92-split-secrets` (inherited; own WIP Sat 10:13), continued on CS branch; reuse stitching and remeasure. |

### E. Gate & checks

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#5](https://github.com/Kivaste/sinceai/issues/5) | Registry, cell checks and gate runner | Refuse every high hit or unavailable required check. | One independent registry, contract/file/form checks and per-label cell validators; `6dcb187`. | 3:19 (from Sat 02:12) | Sat 05:31 |
| [#6](https://github.com/Kivaste/sinceai/issues/6) | Independent conversational text checks | Catch spoken/split identifiers the redactor misses. | Separate multilingual normalisation, conversation joins and versioned health lexicon; `b148908`. | 3:12 (from Sat 02:21) | Sat 05:34 |
| [#12](https://github.com/Kivaste/sinceai/issues/12) | Producer-scope checks | Recheck person-k and surviving identifiers, hashes and keys. | Source/lineage-aware joined QIs, per-person k and raw/encoded material scans; `b48ec2d`. | 3:24 (from Sat 02:10) | Sat 05:34 |
| [#47](https://github.com/Kivaste/sinceai/issues/47) | Text/producer edge-case follow-up | Close matcher, applicability and source-linking gaps. | Phone/plate/secret edge rules plus producer join and scan-limit handling; `69fcd87`. | 0:10 (from Sat 05:43) | Sat 05:53 |
| [#57](https://github.com/Kivaste/sinceai/issues/57) | Person identity and content-free producer violations | Stop identity spelling inflating k or labels leaking values. | Canonical person linking, safe violation labels and manifest numeric handling; `e84b265`. | 0:31 (from Sat 06:42) | Sat 07:14 |
| [#61](https://github.com/Kivaste/sinceai/issues/61) | Registered manifest-value scanner | Scan proof metadata during publication and verification. | Registry-backed identifier-shape scan over manifest values, shared by writer/verify; `8e93dcf`. | 4:34 (from Sat 07:12) | Sat 11:47 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#53](https://github.com/Kivaste/sinceai/issues/53) | Correct secret/username cue false positives without fail-opens | P0 | Shared CS chain 1.5–2.5 h | Single D29 CS owner. In progress since Sat 06:35 on `origin/ticket/fu53-secrets`, continued on CS branch through round 5; review found additional cue/placeholder fail-opens. |
| [#56](https://github.com/Kivaste/sinceai/issues/56) | Close text health/phone/applicability/URL fail-opens | P0 | 30–60 min; within shared CS chain | Blocked by #53/file ownership. No dedicated origin branch; shared CS chain since Sat 05:25, own fix `b3872ed` Sat 10:18. Must prove joins, short cells and URL fragments refuse correctly. |
| [#62](https://github.com/Kivaste/sinceai/issues/62) | Bind scenario k and independently derive released QIs | P0 | 45–60 min + human #106 decision | Partial wave merged `8e93dcf` Sat 11:47; pass-2 Spec found trusted-provenance QI escape, so still open. Shared producer-wave branch has no unmerged commits. Reconstruct allowed derivations and refresh proof. |
| [#106](https://github.com/Kivaste/sinceai/issues/106) | Decide detector-derived QIs versus contract policy | P0 | 15–30 min decision, then 30–60 min implementation | Human owner: Kivaste (unassigned decision). Decide explicit policy treatment of `lab_results.test_name`, replan, or document deferral; affects whether HEALTH-S1 can meet k/suppression bounds. No branch fix committed. |
| [#114](https://github.com/Kivaste/sinceai/issues/114) | Reject duplicate keys in manifest-value check | P0 | 30–60 min | Pass-2 must-fix; named production check must use strict JSON loading and fail on parse errors independently of writer/verify prevalidation. No matching origin branch observed. |

### F. Proof

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#3](https://github.com/Kivaste/sinceai/issues/3) | Manifest schema and canonical JSON | Make privacy claims closed, typed and byte-stable. | Reject unknown keys/missing assertions; bind named positive-denominator evidence; `9914409`. | 3:27 (from Sat 02:09) | Sat 05:36 |
| [#17](https://github.com/Kivaste/sinceai/issues/17) | Atomic release writer and signature | Publish only a complete gated, signed release. | Temporary build, bound digests, HMAC manifest, self-scan and atomic rename; `afd62da`. | 0:35 (from Sat 05:13) | Sat 05:49 |
| [#18](https://github.com/Kivaste/sinceai/issues/18) | Two-tier verification | Distinguish recipient checks from controller re-proof. | Fresh registry reruns; limited recipient result; full signature/input/revision checks; `5caec51`. | 0:27 (from Sat 05:19) | Sat 05:47 |
| [#55](https://github.com/Kivaste/sinceai/issues/55) | Verify status-mismatch refusal | Detect drift between attested and rerun applicability. | Refuse pass↔not-applicable mismatches against fresh check records; `7afa590`. | 0:16 (from Sat 06:20) | Sat 06:37 |
| [#58](https://github.com/Kivaste/sinceai/issues/58) | Surface low-severity gate hits | Keep residual-risk claims aligned with observed gate results. | Derive residual-risk entries with label/hits/denominator from gate records; `6533ac6`. | 0:39 (from Sat 07:20) | Sat 07:59 |
| [#59](https://github.com/Kivaste/sinceai/issues/59) | Reapply absence-assertion rules in verify | Prevent fresh hits supporting a false export assertion. | Require zero hits, no violations and positive denominator on rerun evidence; `6533ac6`. | 0:39 (from Sat 07:20) | Sat 07:59 |
| [#60](https://github.com/Kivaste/sinceai/issues/60) | Run/full-verify purpose-check enforcement | Stop publishing or fully verifying unknown utility. | Execute required purpose checks, enforce allowed sacrifices and recheck after suppression; `6533ac6`. | 0:39 (from Sat 07:20) | Sat 07:59 |
| [#72](https://github.com/Kivaste/sinceai/issues/72) | Real producer checks in writer-assembly tests | Make writer assertion tests fail when producer checks break. | Replace blanket passing stubs with a synthetic source/key/lineage context; `5966fb8`. | 0:24 (from Sat 08:04) | Sat 08:28 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#71](https://github.com/Kivaste/sinceai/issues/71) | Remove vacuous full-verify producer stubs | P0 | 30–60 min | Partial producer-wave merged `8e93dcf` Sat 11:47; issue remains open with deletion/stub mutation-red evidence gap. Shared origin producer-wave branch has no unmerged commits; do not count merge as closure. |
| [#80](https://github.com/Kivaste/sinceai/issues/80) | Include withheld source values in manifest self-scan | P0 | 30–60 min | #24 remains open; #61 closed. Extend source-side scan coverage while keeping output content-free; own files overlap CS writer work. No matching origin branch observed. |

### G. Measure & show

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#15](https://github.com/Kivaste/sinceai/issues/15) | Redaction evaluation harness | Measure exact spans without overlap-based score inflation. | Full-turn evaluation frame, exact matching, held-out skeletons and local-only spot checks; `0008cdc`. | 0:17 (from Sat 02:21) | Sat 02:39 |
| [#16](https://github.com/Kivaste/sinceai/issues/16) | Broker/municipal attacker package | Independently validate linkage and attribute inference. | Isolated attacker-only truth access, two personas and aggregate output; `900dd8b`. | 0:35 (from Sat 02:23) | Sat 02:58 |
| [#19](https://github.com/Kivaste/sinceai/issues/19) | Manifest-only dashboard | Show all five demo items without displaying row values. | Static offline HTML, assertion scopes, baseline/search chart and aggregate CSV; `65e4e37`. | 0:21 (from Sat 05:15) | Sat 05:37 |
| [#20](https://github.com/Kivaste/sinceai/issues/20) | Measurer | Populate comparable before/after privacy and utility. | Strict adapter scorecards, independent person-k summaries and published baselines; `4da22de`. | 0:24 (from Sat 05:12) | Sat 05:37 |
| [#27](https://github.com/Kivaste/sinceai/issues/27) | Attack our HEALTH-S1 release | Put both independent attacker rates into residual risks. | Attacker-to-manifest bridge at release milestones; `7c8ecdb`. | 0:49 (from Sat 05:39) | Sat 06:29 |
| [#40](https://github.com/Kivaste/sinceai/issues/40) | Harness precision/determinism follow-up | Stop absent thresholds or weak tests appearing successful. | Fail-closed floor, explicit overlap guard, aggregate/determinism coverage and counts; `abf7ad9`. | 0:04 (from Sat 05:40) | Sat 05:44 |
| [#44](https://github.com/Kivaste/sinceai/issues/44) | Attacker parse/QI follow-up | Avoid understating attacks on unsupported or malformed QIs. | Refuse parse failures/unknown kinds and tighten wildcard/time matching; `223b23a`. | 0:08 (from Sat 05:43) | Sat 05:52 |
| [#49](https://github.com/Kivaste/sinceai/issues/49) | Dashboard/measurer edge follow-up | Keep displayed schemas and measurements faithful. | QI/token rendering, formatting/path edges and before-set/person-k corrections; `b45168b`. | 1:54 (from Sat 09:27) | Sat 11:21 |
| [#51](https://github.com/Kivaste/sinceai/issues/51) | Dashboard PET/chart/number fixes | Avoid misleading judge-facing presentation. | Derived-column PET lookup, accepted-point chart ordering and consistent number strings; `dc3385a`. | 0:07 (from Sat 05:55) | Sat 06:02 |
| [#52](https://github.com/Kivaste/sinceai/issues/52) | Measurer original-set/baseline/k fixes | Make before/after numbers actually comparable. | Full original table set, baseline field corrections, row-weighted k and metric IDs; `d902df0`. | 1:12 (from Sat 06:12) | Sat 07:25 |
| [#67](https://github.com/Kivaste/sinceai/issues/67) | Evaluate the shipped redactor | Stop baseline-only evaluation certifying product quality. | Wire the production redactor and named PERSON variants into evaluation CLI; `a48ef2e`. | 0:43 (from Sat 08:06) | Sat 08:50 |
| [#68](https://github.com/Kivaste/sinceai/issues/68) | Whole-conversation held-out evaluation | Keep conversation identity/context out of both split sides. | Conversation-level skeleton hold-out with explicit disjointness checks; `a48ef2e`. | 0:43 (from Sat 08:06) | Sat 08:50 |
| [#75](https://github.com/Kivaste/sinceai/issues/75) | Refuse invalid attacker birth dates | Prevent malformed dates silently reducing linkage risk. | Explicit date/age validation instead of NaT/nonmatch fall-through; `6559731`. | 0:18 (from Sat 07:14) | Sat 07:32 |
| [#76](https://github.com/Kivaste/sinceai/issues/76) | Validate attacker month/hour ranges | Reject impossible timestamp representations. | Range-aware parsing before month/hour key construction; `6559731`. | 0:18 (from Sat 07:14) | Sat 07:32 |
| [#77](https://github.com/Kivaste/sinceai/issues/77) | Fail-closed attacker boundary audit | Stop audit-hook errors silently losing access violations. | Record/refuse path-resolution failures rather than swallowing exceptions; `9f3aba3`. | 1:21 (from Sat 08:03) | Sat 09:25 |
| [#91](https://github.com/Kivaste/sinceai/issues/91) | Refuse implausible protected ages | Keep protected-side age handling as strict as adversary input. | Enforce plausible ranges and consistent attacker exception types; `8cec414`. | 0:52 (from Sat 08:33) | Sat 09:25 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#94](https://github.com/Kivaste/sinceai/issues/94) | Forward measurement recipient option | P2 | 30–60 min, shared #81 batch | In progress since Sat 09:03 on shared `origin/ticket/fu81-csv-determinism`; round 2. Sequence `measure/wire.py` overlap with #26; prove parsed recipient reaches production measurement. |
| [#101](https://github.com/Kivaste/sinceai/issues/101) | Compare privacy, utility and retention strategies | P3 | 2–3 h after strategies exist | Consumes #99/#100 strategy outputs; distinguish people, rows, cells and detail loss without inventing metrics. No matching origin branch observed. |
| [#113](https://github.com/Kivaste/sinceai/issues/113) | Choose measurement row-map inputs by identity | P0 | 30–60 min | Pass-2 must-fix; derive exact stems from lineage/contract and reject planted extras through measure CLI. Sequence measurement file ownership with #26/#94. No matching origin branch observed. |

### H. End-to-end releases

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#22](https://github.com/Kivaste/sinceai/issues/22) | HEALTH-S1 walking skeleton | Connect the mandatory tracer into a real release path. | Hand plan → transform/tokenise → contract/gate → signed atomic release → both verify tiers; `5ddf33c`. | 0:41 (from Sat 05:27) | Sat 06:09 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#24](https://github.com/Kivaste/sinceai/issues/24) | CS-S1 end-to-end release | P0 | 1.5–2.5 h for shared chain | In progress since Sat 05:25 on `origin/ticket/23-cs-s1`; one owner also handles #53/#54/#56/#63/#92. Sat 12:00 fallback triggered: withhold still-flagged turns, record sacrifice/counts and reduced checker independence; gate remains strict. Must produce real release and both verify outputs. |
| [#26](https://github.com/Kivaste/sinceai/issues/26) | Replace HEALTH-S1 hand plan with search | P1 | ~45 min | In progress since Sat 06:17 on `origin/ticket/25-search`; round-1 entry-point/privacy fixes recorded. Original issue names both scenarios; CS portion split to #96. Native #24 blocker still open; reconcile split before closing. |
| [#93](https://github.com/Kivaste/sinceai/issues/93) | Purpose-check follow-up edge cases | P2 | 30–60 min | #24/shared purpose-file ownership; fix stale suppression status, unknown before-scores and risk-ID handling. No matching origin branch observed. |
| [#96](https://github.com/Kivaste/sinceai/issues/96) | Search-chosen CS-S1 release | P1 | 45–60 min | #24/#26; explicit CS search follow-up, separate from HEALTH search merge. Real-kit gate, both verify tiers and dashboard required. No matching origin branch observed. |
| [#111](https://github.com/Kivaste/sinceai/issues/111) | Refuse absent/nonboolean suppression withinBound | P0 | 30–60 min | Pass-2 must-fix; no default-to-success sentinel in run pipeline. Real CLI regression/evidence required. No matching origin branch observed. |

### I. Submission & presentation

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#23](https://github.com/Kivaste/sinceai/issues/23) | Story kit | Give the business teammate a traceable demo package. | Measurer/dashboard wiring, manifest-backed aggregate numbers and pitch beats; `5f17654`, `15b2a42`. | 2:17 (from Sat 05:26) | Sat 07:44 |
| [#31](https://github.com/Kivaste/sinceai/issues/31) | README/reproducibility baseline | Make the workflow reproducible on Windows. | `python` commands, environment/creation-time setup and clear verification tiers; `297356b`. | 1:05 (from Sat 05:26) | Sat 06:32 |
| — | Story drafts | Prepare conditional submission and presentation copy. | Names/taglines `0d540a1`, description `35de63d`, video/pitch `30c98a7`, deck `d900b82`, claim gates `8b8f474`, wording `56b02b4`/`ee59bbd`/`8dac61b`, number updates `fb053b3`/`0386e6b`; merged `de380a5`. | 3:04 (from Sat 06:44) | Sat 09:49 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#30](https://github.com/Kivaste/sinceai/issues/30) | Submission packager | P1 | 1–1.5 h | #24/#26. In progress since Sat 06:25 on `origin/ticket/29-packager`; both reviewers approved per issue comment. Need final release inputs, external/private output, validated row maps and running README submission check at merge. |
| [#33](https://github.com/Kivaste/sinceai/issues/33) | Post TrustED Discord questions and log answers | P1 | 15–30 min | Human owner: **Kivaste**. Scheduled Sat 09:00; still open, so posting/answers not assumed. Organiser handles/delivery answer feed #34. |
| [#34](https://github.com/Kivaste/sinceai/issues/34) | Private submission repo and organiser invites | P1 | 15–30 min | Human owner: **SuhtetarkKool**. Invites need #33's handles; confirm private visibility and log completion. |
| [#35](https://github.com/Kivaste/sinceai/issues/35) | Curate fi/sv/en lexicons | P1 | 45–60 min | Human owner: **SuhtetarkKool**. #14 merged; use general knowledge only, validate CSV shape and remeasure aggregate label changes. |
| [#36](https://github.com/Kivaste/sinceai/issues/36) | Local redaction spot-check sheet | P1 | 45–60 min | Human owner: **SuhtetarkKool**. Blocked by #24; mark misses/over-redactions locally and report only aggregates. |
| [#37](https://github.com/Kivaste/sinceai/issues/37) | Fresh-machine README test | P1 | 45–60 min | Human owner: **SuhtetarkKool**. #31 closed, but final README changes need retesting; file each failure, do not assume setup success. |
| [#38](https://github.com/Kivaste/sinceai/issues/38) | Demo rehearsal and jury Q&A | P1 | 1 h | Human owner: **SuhtetarkKool**. #24 open; #23 closed. Rehearse unseen detection, HEALTH/CS, live refusal and limited/full verification. |
| [#39](https://github.com/Kivaste/sinceai/issues/39) | Video, deck, tagline and description | P1 | Video 2–3 h; deck 1–2 h | Human owner: **business teammate**. #23 closed; drafts exist, but use #103's final-SHA claims/numbers. Submission assets required by Sat 20:00 freeze. |
| [#103](https://github.com/Kivaste/sinceai/issues/103) | Finalise submission story for verified revision | P1 | ~45 min | #24/#26/#30 plus final review and fresh final-SHA proof. Resolve conditional claims, fill manifest-backed numbers, enforce field limits and two-axis claim review. No matching origin branch observed. |
| — | Final whole-product review + fresh proof | P1 | 1–1.5 h after fixes merge | First resolve P0 findings, especially #62/#109–#114 and CS chain. Pin exact final SHA, run Standards plus independent Spec axes, then fresh real-kit releases/verify/scorecards. Existing historical passes are not proof for the final head. |
| — | README finalisation | P1 | 30–45 min | After #24/#26/#30: replace pending/skip blocks with executable final commands and accurate search/CS/submission instructions; coordinate #37 clean-machine test. #31 closure covers baseline, not these final updates. |

### J. Process, orchestration, CI & test infrastructure

**Done**

| Issue | Task | Goal (1 line) | Approach (1 line, from the issue body / commit subjects) | Time | Finished |
|---|---|---|---|---|---|
| [#28](https://github.com/Kivaste/sinceai/issues/28) | End-to-end determinism/offline pattern tests | Catch cross-module nondeterminism and network escape. | Real CLI repeated releases and planted subprocess-network checks; `8451969`. | 1:04 (from Sat 05:26) | Sat 06:31 |
| [#73](https://github.com/Kivaste/sinceai/issues/73) | Required kit tests fail rather than silently skip | Treat absent configured inputs as unknown/failure. | Pinned kit resolution and explicit failure for required kit coverage; `5966fb8`. | 0:24 (from Sat 08:04) | Sat 08:28 |
| [#74](https://github.com/Kivaste/sinceai/issues/74) | Remove required-dependency importorskip | Stop broken/missing production modules counting as skipped success. | Normal imports and explicit dependency requirements in ladder/scaffold tests; `5966fb8`. | 0:24 (from Sat 08:04) | Sat 08:28 |
| [#85](https://github.com/Kivaste/sinceai/issues/85) | Low-severity rule-audit infrastructure batch | Strengthen test/data-boundary and output hygiene. | Synthetic key-test counterpart, strict exit codes, opt-in spot-check output and forbidden metadata/import guards; `e19a1d9`. | 1:50 (from Sat 09:53) | Sat 11:44 |
| [#86](https://github.com/Kivaste/sinceai/issues/86) | Restore OpenAI provider authentication | Restore the intended independent reviewer family. | Human provider re-authentication after expired-token failures; no mapped integration merge. | 1:03 (Sat 07:05→Sat 08:09; created→closed) | Sat 08:09 |
| [#98](https://github.com/Kivaste/sinceai/issues/98) | Repair affected-tests execution | Make D27 actually collect/run selected tests. | Diagnose Windows argument/environment handling and propagate real pytest status; `10c2ba7`. | 1:26 (from Sat 10:34) | Sat 12:01 |
| [#102](https://github.com/Kivaste/sinceai/issues/102) | Decode done-report GitHub output as UTF-8 | Make remote/local report checks agree. | Correct PowerShell gh-output decoding and exercise arrow-bearing reports; `d177288`. | 0:39 (from Sat 11:16) | Sat 11:56 |
| [#104](https://github.com/Kivaste/sinceai/issues/104) | Pin revision per test session | Avoid moving HEAD invalidating session-scoped release fixtures. | Session revision pin plus guard against HEAD drift; `6b43d2b`. | 0:11 (from Sat 11:26) | Sat 11:38 |
| — | Planning: grilling, spec, three-model review, 38 tickets | Establish scope, architecture and executable issue plan. | Requested planning window; `32a1eb5`, `c9a8f59`, `122fb1e`, `db026b5`, `5a5b988`, `4a6c58e`, `3ffddfd` cover setup/ADRs/review decisions/dispatch. | 2:21 (from Fri 23:40) | Sat 02:01 |
| — | Watchdog: build + fixes | Keep orchestration alive through crashes/server restarts. | Heartbeat/liveness/resume `f54e2af`, launcher/concurrency `2540b09`, PS JSON crash `59ae0f6`, WMI helper restarts `eb8f45f`. | 4:53 (from Sat 01:06) | Sat 05:59 |
| — | Keep-awake + power | Prevent suspend from silently stopping unattended work. | Power request, watchdog restart and post-suspend grace cycle; `2d6a548`. | 0:00 (from Sat 05:13) | Sat 05:13 |
| — | Utilization monitor | Nudge dispatch when ready work has idle capacity. | Independent monitor `deb7fb1`, single-query native blockers and GitHub retry/skip `d02a688`. | 0:22 (from Sat 06:48) | Sat 07:11 |
| — | One-screen status helper | Make unattended run state easy to inspect. | Content-free operational status command; `40e4bac`. | 0:00 (from Sat 05:20) | Sat 05:20 |
| — | Auto hand-over | Replace context-heavy orchestrators without losing inherited work. | Context threshold/retirement/polling `a101ac7`, real hand-over test and watchdog parameters/stderr fix `a8690ce`. | 0:41 (from Sat 06:15) | Sat 06:57 |
| — | Quota probes and reviewer switch-back | Restore preferred models when capacity returns. | Sol probe `416825d`, generic provider probe/fallback routing `770427d`. | 1:02 (from Sat 05:57) | Sat 06:59 |
| — | Review/dispatch governance | Adapt model families, review depth and release integration rules. | `c309db6`, `aa5cf71`, `cbf0cd3`, `c8bb930`, `6022af6`, `75719d1`, `80909a0`, `ec13af9`, `144344d`, `fa7abc4`, `678fbd9`: roster/encoding/caps, final reviews, single CS owner/fallback. | 9:15 (from Sat 02:14) | Sat 11:30 |
| — | Append-only operational decision diary | Record outages, review decisions and dependency deviations. | `7dc3dc5`, `ab1caa4`, `4efe5a8`, `94d5682`, `c038fb6`, `2d067b0`, `73505d9`, `6675731`, `60e3cdd`, `9eb5dc5`, `953a3c6`, `74e97e1`, `5bf6b81`, `caddcbd`, `6e8208f`. | 4:50 (from Sat 02:17) | Sat 07:08 |
| — | README command/submission-path guards | Stop stale pending commands and accidental submission tracking. | Executable-command/skip allowlist and ignored submission-directory test; `b204ba2`. | 0:00 (from Sat 05:46) | Sat 05:46 |
| — | Test-priority helper | Keep the developer desktop usable during parallel runs. | BelowNormal agent test priority with watchdog supervision; `031eb81`. | 0:00 (from Sat 09:54) | Sat 09:54 |
| — | Affected-tests helper (D27) | Keep implementer iteration scoped to changed code. | File→test selection, two workers and non-slow tier; `25a4363` (execution repair separately #98). | 0:00 (from Sat 09:58) | Sat 09:58 |
| — | Merge train (D28/D30) | Amortise full-suite gates without weakening failure handling. | Four-ticket batches/bisection `602ad13`; external bytecode cache, fail-fast and docs-only path `c5cf8dd`. | 0:11 (from Sat 10:07) | Sat 10:18 |
| — | Close gate + brief v3/templates (D31) | Require observable TDD, separate review axes and head-bound evidence. | Effective-policy brief/templates/done-report gate `b85d1d0`; final story ordering `c6457e9`; worktree isolation warning `6bad0b8`. | 0:44 (from Sat 10:36) | Sat 11:21 |
| — | Privacy deny policies | Prevent tools displaying kit rows to agents. | Hard read/shell deny patterns in project permissions; `135eeb9`. | 0:00 (from Sat 10:36) | Sat 10:36 |
| — | Human submission wizards | Guide dashboard-only human submission steps safely. | Saturday/Sunday wizards `13d3d50`; final-story loading and marker/size blockers `95988af`. | 0:16 (from Sat 11:11) | Sat 11:27 |
| — | Slow-split test tiering (D30) | Keep fast privacy/CLI coverage while isolating expensive tests. | Collection markers `5e4b289`, profiled heavy-test classification `82f395e`, retained synthetic gate/verify fast coverage `e694598`; merged `04773f8` Sat 11:09. | 0:51 (from Sat 10:01) | Sat 10:53 |

**To do**

| Issue | Task | Priority | Estimate | Blocked by / note |
|---|---|---|---|---|
| [#97](https://github.com/Kivaste/sinceai/issues/97) | Authenticated test-only kit parse cache | P2 | 30–60 min | In progress since Sat 10:34 on `origin/ticket/fu97-kit-cache`; hashed input/version/options, atomic external cache, production isolation and before/after timings required. Slow-split merged; sequence with #107. |
| [#105](https://github.com/Kivaste/sinceai/issues/105) | Main-checkout/worktree isolation guards | P2 | 30–45 min | In progress since Sat 11:32 on `origin/ticket/fu105-main-guard`; #98/#102 closed. Real scripts must refuse main by Git identity and require ticket worktrees in done reports; separate cross-checkout write guard is #107. |
| [#107](https://github.com/Kivaste/sinceai/issues/107) | Prevent tests writing into another checkout | P2 | 45–60 min | Merge after #97 and #104 (#104 closed). Real nested pytest planted-write test plus Git-identity ROOT checks; do not delete existing stray files of unknown ownership. No matching origin branch observed. |
| [#108](https://github.com/Kivaste/sinceai/issues/108) | Deterministic cold-import kiteval probe | P2 | 30–60 min | Intermittent control-case import-time subprocess under load; guarded privacy case unaffected. Find side effect and assert cold import records zero subprocess calls. No matching origin branch observed. |

## Placement, timing and outstanding-proof caveats

- **Unplaced task issues: none.** Issue #1 is deliberately the spec, not a task. Issue #95 is absent from the issue-list result; GitHub's shared issue/PR numbering is not a missing-task assumption.
- **Closed issues without a mapped merge:** only #86; its 1:03 uses created→closed. All other closed task issues have a mapped integration merge. Unissued story drafts and slow-split are included explicitly; main→integration synchronization merges are not separate implementation tasks.
- **Open issues without a dedicated matching origin branch:** #33–#39, #56, #62, #71, #80, #83, #84, #88, #93, #94, #96, #99–#101, #103, #106–#115. Shared-branch starts are shown where observed (#56/#83/#94); partial producer-wave merges are identified (#62/#71/#84). Others have no defensible branch start in this snapshot.
- **Unmeasurable active effort:** commit-span timing cannot recover pre-first-commit research, exact review labour, or human progress not recorded in issue metadata. Single-commit process tasks therefore retain 0:00 rather than invented durations. Planned remaining estimates are explicitly not measured work.
- **Fresh proof remains outstanding:** an old closed issue or merged batch does not establish that the pinned integration tip or final submission revision passes. The open pass-2 findings, CS-S1 chain, final multi-family review, final-SHA real runs and story finalisation remain visible above.
