# PRE-FILL sources, targets met / not met, and finalisation handoff

**PRE-FILL at df79ec20538e8f02b3256911fb01d549e5af0ebb** (#103, D61).
These are build-bound planning measurements, not the final submission or proof
for the later docs commit. `PRE-FILL-SOURCES.md` binds the one measured HEALTH-S1
manifest, its input digests, commands, actual exits and selector ledger. After the
freeze, refresh numbers from the final manifest and obtain final review/proof.
Never relabel the video on demo pin `5b260ec` with these measurements (D55).

## Source contract: actual manifest keys, not guessed paths

All `manifest.selector` references address a single scenario's
`privacy_manifest.json`. The default is HEALTH-S1. CS-S1 rows below are explicitly
unmeasured: no CS-S1 manifest exists in this run, and D46 makes that scenario
future work. Never resolve a CS selector against HEALTH-S1. This namespace is an
editing convention, not a field named `manifest` in the JSON.

Use direct keys with explicit array selectors: `tasks[task=H-U2].after` means the
unique `tasks` entry whose `task` equals `H-U2`; `components[component=person_k.min]`
matches the entire component ID, including the dot. Multiple selectors, separated
by commas, must all match one entry. Zero or multiple matches are unresolved, never
zero. No implicit list index, guessed alias, list `.count` field, or interpolation
from a different scenario. This is a manual finalisation contract, **not supported
by the older `docs/story-kit/fill_numbers.py` resolver**.

Schema/producer references for the pinned PRE-FILL build:

| Source | Actual keys / meaning |
|---|---|
| `src/pets_release/manifest/schema.py`, `_MEASURED` | `measured.utility.tasks[].{task,status,before,after}`, `measured.privacy.components[].{component,before,after}`, `measured.redaction.labels[].{label,tp,fp,fn,support,precision,recall}` |
| Same schema, top-level records | `inventory`, `pets[].{table,column,pet,params}`, `fieldJustifications[].{table,column,outputColumn,decision,rung,floor,reason,source}`, `contract.k`, `contract.files`, `bindings.files`, `bindings.toolRevision` |
| Same schema, evidence and risks | `assertionEvidence.<name>.{check,version,scope,status,denominator,hits}`, `gate.{status,checks}`, `residualRisks[].{risk,kind,label,rate,description}`, `sacrifices[].{check,floor,before,after,reason}` |
| `src/pets_release/writer/assemble.py` | `assemble_manifest` copies the narrative, derives assertions only from their required checks, copies gate records and binds `bindings.toolRevision` and inputs; it does not invent measurement fields |
| `src/pets_release/run/narrative.py` | Writes local suppression under `pets[pet=local_suppression].params.{k,maxShare,unitsSuppressed,share}`; sacrifice floors; risk IDs `free-text-recall`, `linkage-attackers`, `attribute-inference`. #138 replaces the generic attacker placeholders with `linkage-<persona>` / `attribute-inference-<persona>` from `src/pets_release/measure/attackers.py`; those per-persona records are absent from this pinned manifest. |
| `src/pets_release/measure/ids.py`, `core.py`, `k.py` | Actual component IDs `privacy`, `k_below_5_share`, `linkage_reid`, `person_k.min`, `person_k.persons`, `person_k.below_k_share`; utility/composite overall scores are deliberately not privacy components |
| `src/pets_release/run/purpose.py`, `policy/health_s1.py`, `policy/cs_s1.py` | Normal utility threshold 0.90; enumerated sacrifice floors 0.60 (H-U4/H-U6/H-U8), 0.80 (CS-U5); k=5, suppression cap 0.10; CS label recall 0.98 and timestamp floor `ts.hour` |

CS target-note selectors remain listed for completeness, not as shipped CS-S1
measurements. D46 supersedes the earlier #24 release condition. The CS evaluation
path uses typed, numbered placeholders and D37 masking, never realistic fake
values: the organisers prefer explicit types to accidental population matches.

No absent/null/errored/`not_measured` measurement becomes a number, `false`, or a
pass. Render **“not measured”** and its reason. Distinguish `not_applicable` with
the actual reason; do not count it as a passed target. Verdicts here apply only
to the pinned PRE-FILL manifest. Compare only after `status=measured`
(utility tasks also require `status=ok`).

## 1. Data types and privacy risks

Show detector column roles and evidence through the detector seam when actually
demonstrated. The release's `inventory` may be policy-derived; do not call it a
detector accuracy result. Use schema names and aggregate metrics only.

| HEALTH-S1 baseline / before | Measured value | Interpretation |
|---|---|---|
| Scorecard privacy | 0.1716 | measured diagnostic; not a privacy target verdict |
| Scorecard share of ROWS below k=5 | 0.9557179814438992 | measured diagnostic; not a privacy target verdict |
| Scorecard linkage component (not the two attacker personas) | 0.5697 | measured diagnostic; not a privacy target verdict |
| Full k distribution / histogram | not measured: no histogram field in this manifest | not measured |
| Both attacker-persona linkage and attribute inference before protection | not measured: no bound before/after persona pair supplied | not measured |

## 2. PETs and why

For each presented field read `pets`, `fieldJustifications` and `contract` together.
The ladder floor is the most detailed permitted rung; the actual `rung` is what
was released. Tie `reason` to the purpose check. No old band widths, timestamp
detail or column counts are carried forward. Search is bounded; it does not prove
global optimality or excuse utility failures without an enumerated sacrifice.

D33: show the exact `lab_results.test_name` rung and H-U7 effect.
If the adopted rung is the CRP-versus-other distinction, say so as a schema-level
choice. If the release instead uses a justified non-QI exception, show its threat
model and residual risk. Do not silently describe either as a full-detail k pass.

## 3. Protected output

Field-level before-to-after, never raw input rows: full birth date → chosen age
band; raw join key → keyed pseudonym; unneeded field → withheld. Present all shown
fields' actual justifications. Keep protected table schemas visible even
without the optional web app.

| Source field | Released field | Actual rung | Ladder floor | Reason |
|---|---|---|---|---|
| ed_visits.date_of_birth | age_band | age.band10 | age.band5 | search step 32: age.band10 adopted (adopted) |
| ed_visits.arrival_ts | arrival_ts | ts.hour_of_day | ts.exact | search step 42: ts.hour_of_day adopted (adopted) |
| ed_visits.municipality | municipality | geo.topn | geo.full | search step 37: geo.topn adopted (adopted) |
| ed_visits.visit_id | visit_id | id.pseudonym | id.pseudonym | search step 0: released at floor id.pseudonym; no coarser move tried (release-scope pseudonym, identical in lab_results (H-U7 join)) |
| lab_results.test_name | withheld | withheld | keep | search step 26: withheld adopted (adopted) |

These are schema-level transformations and generated reasons, never row examples.
`lab_results.test_name` is withheld in this release, not retained at full detail
or coarsened to CRP-versus-other. H-U7's actual score is below. This does not
establish D58's separate scenario-QI and all-kept-catalogued-QI measurements.

D41's web row view is human-only for real-kit material. Show the
first approximately ten protected rows per table only after display-time limited
verify and matching manifest-file digests; only manifest-listed files. No raw
input, row maps or truth/. Mandatory label: “Synthetic kit data © Since AI ry,
CC BY 4.0. In a real deployment only the recipient sees this view.” Agents never
read or screenshot this real-kit view. Agent tests/screenshots use hand-made
synthetic fixtures.

## 4. Measured privacy and utility: targets met / not met

### HEALTH-S1 privacy floors

| Privacy target / floor | Measured value from HEALTH-S1 | Targets met / not met |
|---|---|---|
| Person-k ≥ 5 on this manifest's contract.qi, including its joined relations | 5.0 | met on contract.qi only |
| Share of retained PERSONS below k=5 = 0 | 0.0 | met on contract.qi only |
| Last-step local suppression share ≤ 0.10 | 0.09942 | met |
| PERSON text recall ≥ 0.95 | not applicable (no free text released) | not applicable (no free text released; not a recall pass) |
| PHONE text recall ≥ 0.95 | not applicable (no free text released) | not applicable (no free text released; not a recall pass) |
| ADDRESS text recall ≥ 0.95 | not applicable (no free text released) | not applicable (no free text released; not a recall pass) |
| NATIONAL_ID text recall ≥ 0.95 | not applicable (no free text released) | not applicable (no free text released; not a recall pass) |

Person-k is producer-attested to the recipient; only the key holder can recompute
it with full verification. This is not yet D58's two-set report:

| Pending measurement | Typed placeholder |
|---|---|
| k on scenario's four QIs and on all kept catalogued QIs; justification for every withheld catalogued QI | not measured (#146; no separate two-set measurements at this revision) |
| k with diagnosis known, and diagnosis-known risk share | not measured (#143; no diagnosis-known measurement at this revision) |
| Per-persona linkage and attribute-inference rates | not measured (#138; no per-persona measured entries at this revision) |
| DPO/Findata evidence pack | not generated (#147; exporter not present at this revision) |

Do not invent selector paths for pending producer fields. Search optimises k and
purpose-check utility, not attackers; attacker measurements are post-hoc.

Report number of persons alongside k:
24204.0.
The scorecard's after ROW share is
0.0; it is
not a PERSON share. Its privacy score
1.0 is not a proof
of zero risk: renamed `age_band` is a disclosed scorecard blind spot (D22).

| Supporting scorecard component | Before | After | Interpretation |
|---|---|---|---|
| Privacy summary (not an absence guarantee) | 0.1716 | 1.0 | Other unmeasured components remain unknown |
| Row-weighted share below k=5 | 0.9557179814438992 | 0.0 | Scorecard misses renamed age_band; not a person share |
| Linkage component | 0.5697 | 0.0 | Zero with no shared QIs means nothing left to match on, not measured resistance |
| Both attacker personas | not measured (#138) | not measured (#138) | No per-persona entries at this revision |
| Diagnosis-known risk | not measured (#143) | not measured (#143) | Never replace with an estimated share |

### Required zero-hit checks / export assertions (each demonstrated scenario)

These are HEALTH-S1 only. CS-S1 remains future work under D46.
Each cell is hits/scanned denominator, **not a recall fraction**.
Confirm `exportAssertions.<name>` is literal false AND that its own required
`assertionEvidence` check ran with status pass, correct scope, zero hits and a
positive denominator. Missing evidence is invalid, not “absence proven”.

| Named assertion: zero-hit floor | Measured hits / denominator | Targets met / not met |
|---|---|---|
| nationalIds | 0 / 834435 cells | met (this named check only) |
| paymentCards | 0 / 834435 cells | met (this named check only) |
| ibans | 0 / 834435 cells | met (this named check only) |
| accountNumbers | 0 / 834435 cells | met (this named check only) |
| emails | 0 / 834435 cells | met (this named check only) |
| phones | 0 / 834435 cells | met (this named check only) |
| ipAddresses | 0 / 834435 cells | met (this named check only) |
| deviceIds | 0 / 834435 cells | met (this named check only) |
| usernames | 0 / 834435 cells | met (this named check only) |
| propertyIds | 0 / 834435 cells | met (this named check only) |
| plates | 0 / 834435 cells | met (this named check only) |
| secrets | 0 / 834435 cells | met (this named check only) |
| urlsWithTokens | 0 / 834435 cells | met (this named check only) |
| rawTimestamps | 0 / 834435 cells | met (this named check only) |
| reversibleHashes | 0 / 834435 cells | met (this named check only) |
| keyMaterial | 0 / 834435 cells | met (this named check only) |
| rowMaps | 0 / 2 files | met (this named check only) |
| quasiIdentifiersBelowK (HEALTH-S1 only) | 0 / 24204 persons | met (this named check only) |

### HEALTH-S1 purpose-check thresholds

The original threshold remains 0.90. An enumerated sacrifice can permit a lower
score at its fixed floor; label it **accepted sacrifice**, not original target met.
A score below either applicable floor, a null, or an errored task fails. Before
means source scored against itself; After is the actual post-suppression release,
not an intermediate candidate. Before is not a pre-suppression utility score.

| Purpose check | Original threshold | Enumerated sacrifice floor | Before | After | Targets met / not met |
|---|---|---|---|---|---|
| H-U2 | ≥ 0.90 | none | 1.0 | 0.9670714229957352 | met original target |
| H-U4 | ≥ 0.90 | 0.6 (policy 0.60) | 1.0 | 0.7952457536539007 | not met original target; accepted sacrifice |
| H-U6 | ≥ 0.90 | 0.6 (policy 0.60) | 1.0 | 0.9462019606198547 | met original target |
| H-U7 | ≥ 0.90 | none | 1.0 | 0.9826848768683396 | met original target |
| H-U8 | ≥ 0.90 | 0.6 (policy 0.60) | 1.0 | 0.9504018267977822 | met original target |

Overall pets-eval utility and composite before/after: **not measured in the current
manifest**. The current measurer writes task scores and privacy components, not
these summary fields. Do not invent `measured.privacy.components[component=utility]`
or use `measured.baselines` as this release's result. If a final producer adds
summary keys, document the real keys and bind them before quoting their numbers.

### CS-S1: not measured, future work under D46

No CS release was attempted by this HEALTH-S1 measurement. Its historical strict-
gate refusal is a limitation, not a successful release. The rows below preserve
typed placeholders for the unavailable CS selectors, never HEALTH-S1 substitutes.

| Privacy target / floor | Measured value from CS-S1 | Targets met / not met |
|---|---|---|
| NATIONAL_ID exact-match recall ≥ 0.98 | not measured (D46 / #24: CS-S1 future work; no CS-S1 manifest in this run) | not measured |
| PAYMENT_CARD exact-match recall ≥ 0.98 | not measured (D46 / #24: CS-S1 future work; no CS-S1 manifest in this run) | not measured |
| IBAN exact-match recall ≥ 0.98 | not measured (D46 / #24: CS-S1 future work; no CS-S1 manifest in this run) | not measured |
| SECRET exact-match recall ≥ 0.98 | not measured (D46 / #24: CS-S1 future work; no CS-S1 manifest in this run) | not measured in this run; historical unmet target under D45 is not re-measured |
| No HEALTH in released text; healthInText hits = 0 | not measured (D46 / #24: no CS-S1 manifest; neither hits nor denominator supplied) | not measured |
| conversations.started_ts at hour or coarser | not measured (D46 / #24: no CS-S1 manifest) | not measured |
| turns.ts at hour or coarser | not measured (D46 / #24: no CS-S1 manifest) | not measured |

| Purpose check | Original threshold | Enumerated sacrifice floor | Before | After | Targets met / not met |
|---|---|---|---|---|---|
| CS-U1 | ≥ 0.90 | none | not measured (D46 / #24: no CS-S1 manifest) | not measured (D46 / #24: no CS-S1 manifest) | not measured |
| CS-U3 | ≥ 0.90 | none | not measured (D46 / #24: no CS-S1 manifest) | not measured (D46 / #24: no CS-S1 manifest) | not measured |
| CS-U4 | ≥ 0.90 | none | not measured (D46 / #24: no CS-S1 manifest) | not measured (D46 / #24: no CS-S1 manifest) | not measured |
| CS-U5 | ≥ 0.90 | not measured (D46 / #24: no CS-S1 manifest; policy floor 0.80) | not measured (D46 / #24: no CS-S1 manifest) | not measured (D46 / #24: no CS-S1 manifest) | not measured |

**D45 source note unavailable in this run:**
not measured (D46 / #24: CS-S1 future work; no CS-S1 manifest in this run)

No historical recall count is imported from another run. The absent CS target
note cannot be replaced with current HEALTH-S1 measurements or invented counts.
If CS-S1 resumes, preserve the historical unmet-target and contamination warning:
later results informed by held-out misses are optimistic, not untouched proof.

The later result is **optimistic** because held-out misses informed the rule.
The target is not lowered or described as met on untouched data. State exact match,
evaluation frame and the accepted turn-level template-held-out split. Gate zero
hits protects only within the independent check's coverage; it is not recall proof.
If this target note is absent, keep “not measured” for its values and block final
CS-S1 claim approval until the manifest carries D45; do not silently omit D45.

D29 fallback: only claim strict/no-withholding or fallback after reading the final
manifest and proof. If turns were withheld, quote the real sacrifice note/count,
CS-U1/CS-U5 effects and reduced checker independence. No invented fallback count key.

## 5. Sharing scenario and limitations, then proof

For each release show recipient, purpose and trust level; `fitFor`, `notFitFor`,
`sacrifices`, `residualRisks`. Pseudonymised data is still personal data; the
controller retains the key. Synthetic templated data does not establish general
speech performance. Recipient digests catch accidental changes, not a determined
editor; only full verify checks the HMAC signature.

Attacker linkage after protection (per persona; value over denominator n):
the #138 selectors below are retained for finalisation, but neither their values
nor their denominators exist in the `df79ec2` manifest. All remain typed
placeholders; no later release supplies a number to this PRE-FILL.

| #138 measurement | Value selector | Denominator selector | PRE-FILL result |
|---|---|---|---|
| Municipal insider linkage | `manifest.residualRisks[risk=linkage-insider].rate.value` | `manifest.residualRisks[risk=linkage-insider].rate.denominator.n` | not measured (#138: both selectors absent from df79ec2 manifest) |
| Data broker: public directory linkage | `manifest.residualRisks[risk=linkage-broker-public_directory].rate.value` | `manifest.residualRisks[risk=linkage-broker-public_directory].rate.denominator.n` | not measured (#138: both selectors absent from df79ec2 manifest) |
| Data broker: health social posts linkage | `manifest.residualRisks[risk=linkage-broker-social_posts_health].rate.value` | `manifest.residualRisks[risk=linkage-broker-social_posts_health].rate.denominator.n` | not measured (#138: both selectors absent from df79ec2 manifest) |
| Data broker: health news clips linkage | `manifest.residualRisks[risk=linkage-broker-news_clips_health].rate.value` | `manifest.residualRisks[risk=linkage-broker-news_clips_health].rate.denominator.n` | not measured (#138: both selectors absent from df79ec2 manifest) |
| Municipal insider attribute inference | `manifest.residualRisks[risk=attribute-inference-insider].rate.value` | `manifest.residualRisks[risk=attribute-inference-insider].rate.denominator.n` | not measured (#138: both selectors absent from df79ec2 manifest) |

#138's municipal-insider method uses a seeded sample capped at 3000 released
visits (a method cap, not a measured denominator here); never call that sample
the whole release when capped. Broker denominators count adversary records.
Attribute-inference records use the same persona IDs with the
`attribute-inference-` prefix; the insider example is listed explicitly above.
The fallback selector `manifest.residualRisks[risk=linkage-attackers].rate.reason`
does exist in this manifest: “not measured yet: the measurer is wired in the
story-kit ticket”. This is the pinned producer's unmeasured reason, not evidence
that the later #138 attacker ran on this release. Generic linkage and attribute-
inference status remain not measured (#138: per-persona rates absent).

If any status is `not_measured`, write “not measured”, never zero. To claim both personas, require
actual per-persona measured risk entries bound to the final inputs and document
their IDs; a generic note or scorecard linkage number is insufficient. Linkage zero
means no shared QIs left to match on, not measured attack resistance. Show scorecard
components separately; do not headline summary privacy as perfect protection.

Gate status: pass. Read actual `gate.checks` entries; derive
pass N / required applicable N and separately count declared not-applicable checks.
Never count a missing/error/not-run result as a pass or invent `.count` JSON keys.
Run the real CLI for limited verify and full verify on that same release and SHA;
record the actual outputs, exits and check totals in PRE-FILL-SOURCES. No verify outcome
field exists in the manifest. Demonstrate a refusal on hand-made synthetic input
with the real CLI and report check/count only. That fresh refusal remains pending;
this run records release and both verify tiers, not a synthetic refusal.

D57 integration: self-hosted library/CLI pipeline step, with the web app as the
approval and audit console. Exit 0 releases; publish only after successful
verification. Exit 1 stops on refusal/check failure; exit 2 stops on bad input or
unknown state. Source rows and keys stay local. Self-hosted REST API: future work.
D60's evidence pack must derive purpose, method/parameters, attacker risk, utility,
residual risks and reproducibility from the authenticated signed manifest only.
Legal basis and DPIA are “to be supplied by the controller”; no legal approval is
implied. The pack is not generated at this revision (#147).

## Claim gates and finalisation handoff

Only retain an optional claim when issue #n's work is
merged **and** the particular claim is verified on the final SHA. Otherwise drop
the whole claim. A closed issue alone is not merge or measurement evidence. This
PRE-FILL introduces no optional-feature integration proof and does not promote a
pending feature to shipped.

| Enabling issue | Finalisation condition |
|---|---|
| #24 | Future work under D46; no CS-S1 released-scenario claim |
| #32 | D47's HEALTH-S1 gate + verify condition replaces D39's two-release gate; front end merged and verified on the final SHA. Describe a validated draft policy for human review; feeding the draft into the search is future work (D51). Disclose the optional Mistral API sender and that row values never leave; unmerged/unverified becomes future work only |
| #117 | Web app merged; final-SHA evidence for display-time verification, manifest-listed file/digest binding and D41 label; real-kit row view never read by agents |
| #127 | Parallel search merged; final-SHA determinism across worker counts, offline workers and fail-closed worker error; no timed speed claim without measurement |
| #106 | D33 rung or disclosed threat-model exception actually merged and present in final release; H-U7 effect measured |

Finaliser creates `docs/story/final/` only after review + fresh proof. Required:
`name.txt` (≤80 characters), `tagline.txt` (≤140), `description.md` (≤5,000; no
headings/editorial notes), `built-with.txt` (first five chips in 01),
`pitch-4min.md`, `video-script.md`, `SOURCES.md`.

SOURCES is a plain Markdown note, **no HTML comments**. Record exact final SHA,
absolute HEALTH-S1 and eligible CS-S1 manifest paths, input digests, each retained
claim/number's scenario + actual key/selector, and real gate/verify/refusal commands
and exits. Fixed policy thresholds and presentation timings cite their spec/code,
not a fabricated measurement. Resolve all placeholders; keep “not measured” with
reason where unavailable. Have independent Spec review check claims against those
exact manifests and Standards review check vocabulary and content freedom.

Readiness CLI: `python docs/story/check_final.py` (defaults to this checkout's
`docs/story/final/`; explicit folder argument is for synthetic fixtures). It fails
on missing/empty deliverables, unresolved placeholders, comment/claim markers,
common editorial notes, description headings and over-limit text. It does not
certify claim truth, proof freshness or absence of all possible editorial wording.
Count actual final text including whitespace/newlines, not just visible prose.

`tests/story_kit/test_final_story.py` exercises that CLI on planted
`docs/story/final/` fixtures. The real-folder readiness test has the named skip
`story-finalisation-awaits-final-review-and-final-sha-proof` only while the folder
is absent. That skip is **not a pass** and blocks closing #103; once any real
final folder exists, missing files/markers/limits fail normally. No final content
or release evidence is minted by this preparation.
