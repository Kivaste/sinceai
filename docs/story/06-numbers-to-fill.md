# Final numbers, targets met / not met, and submission handoff

**FINAL at c52424c (merged to main cc66ac2)**.
The filename is retained for existing links. These measurements belong to the
final integration release, not the later docs commit. `PRE-FILL-SOURCES.md`
records the final source paths, selectors, commands and observed exits.
Never relabel the existing video on demo pin `5b260ec` with these results (D55).
k figures are final and may now be shown; the earlier blanket hiding rule is lifted.

## Source contract

Every selector below addresses the one HEALTH-S1 `privacy_manifest.json` in the
source ledger. An array selector such as `tasks[task=H-U2]` means the unique entry
with that ID. Zero or multiple matches are unresolved, not zero. These are manual
lookup conventions, not support promised by `docs/story-kit/fill_numbers.py`.
Missing, null, errored or `not_measured` values never become numbers or passes.
`not_applicable` remains separate from pass, with its reason.

CS-S1 is future work under D46. There is no CS-S1 manifest in this proof; never
resolve a CS selector against HEALTH-S1. Utility thresholds are policy, not
measurements. Presentation timings and character limits are editorial constraints.

## 1. Data types and privacy risks

Show column roles and schema-level evidence. A policy-derived release inventory
is not detector-accuracy evidence. Unseen export requires every column to have
`privacy_role` and `subtype`; full coverage is not an organiser accuracy score.

| Kit public scorecard diagnostic | Before | After | Interpretation |
|---|---|---|---|
| Privacy summary | 0.1716 | 1.0 | Named scorecard metric, not perfect privacy |
| Share of ROWS below k=5 | 0.9557 | 0 | Row-weighted over the tables scored for k, not a PERSON share |
| Linkage re-identification | 0.5697 | 0 | Scorecard component, not a substitute for attacker evaluation |
| Utility: mean of five tasks | 1.0 | 0.9188 | Arithmetic mean of H-U2/H-U4/H-U6/H-U7/H-U8, not an extra manifest summary key |

The kit scorecard does not recognise renamed `age_band` as a QI (D22). Its zero
linkage and below-k components do not establish absence of risk. Separate
producer k and attacker measurements below address different questions. A full
k histogram and an overall composite are not supplied; no claims are made for them.

## 2. PETs and why

Read actual `fieldJustifications` rungs, floors and reasons, not the old hand plan.
Withholding removes unnecessary fields; keyed pseudonyms preserve needed joins;
generalisation and local suppression reduce detail. Bounded search optimises
k and purpose-check utility, not attacker rates or global optimality. Attacker
evaluation is post-hoc; no parallel-search speed-up is measured by this proof.

The optional Mistral front end drafts validated policies for human review from
screened request text and allowlisted schema metadata, never row values. Feeding
those drafts into release search remains future work (D51); `run` uses packaged
scenario policies. This measured release proof is not a new network integration run.

## 3. Protected output

Field-level before-to-after only, never raw input rows:

| Source field | Released field | Actual rung | Ladder floor | Purpose / reason |
|---|---|---|---|---|
| ed_visits.date_of_birth | age_band | age.band10 | age.band5 | Coarser age bands to reach k; H-U6 |
| ed_visits.arrival_ts | arrival_ts | ts.hour_of_day | ts.exact | Coarser time to reach k; H-U8 |
| ed_visits.municipality | municipality | geo.topn | geo.full | Municipality grouping to reach k; H-U4 sacrifice |
| ed_visits.visit_id | visit_id | id.pseudonym | id.pseudonym | Necessary H-U7 join, same pseudonym in lab_results |
| ed_visits.los_minutes | los_minutes | num.bin | num.exact | 30-minute bins enforce the 2.0x inference-lift bound; H-U2 detail sacrifice |
| ed_visits.icd10_primary | icd10_primary | icd.3 | icd.full | Chapter-level coding rejected; H-U4 would be 0 |
| lab_results.test_name | withheld | withheld | lab.full | Search withholds this catalogued QI |
| lab_results.test_code | test_code | keep | keep | Exact test identity needed for H-U7; residual test-history linkage risk |

The `los_minutes` bin width is recorded in `sacrifices[check=H-U2].liftStep.toParams.width`.
`fieldJustifications` records its rung; the lift step explains the final width.
`test_name` is not retained at full detail or as CRP-versus-other. H-U7 is 0.9827
because `test_code` still supports that purpose check. Do not imply that withholding
the name removes all test-identity information.

D41's real-kit protected-row view is human-only: display-time limited verification
and manifest-file digests must pass. Mandatory label: “Synthetic kit data © Since
AI ry, CC BY 4.0. In a real deployment only the recipient sees this view.” No raw
input, row maps or `truth/`. Agents use hand-made synthetic fixtures only.

## 4. Measured privacy and utility: targets met / not met

### Per-person k on both QI sets (#146 / D58)

| Set | Minimum person-k | Persons below k=5 | Person share below k=5 | Persons | Verdict |
|---|---|---|---|---|---|
| Scenario QIs | 5 | 0 | 0 | 24,204 | Meets declared k target |
| All kept catalogued QIs | 5 | 0 | 0 | 24,204 | Meets declared k target |

Both released sets contain `age_band`, `arrival_ts` and `municipality`. Their
measurements and withheld-column justifications are in `measured.kSets`, not an
inference from a single contract-QI result. k is producer-attested to recipients;
only full verification with inputs and key recomputes producer checks.

The suppression share derived from `measured.kSets` person totals is
(26,876 − 24,204) / 26,876 = 0.09942, within the policy cap 0.10. This is not
the scorecard's row-weighted below-k share or the diagnosis-known risk share.
Free-text PERSON/PHONE/ADDRESS/NATIONAL_ID recall targets are not applicable:
no free text is released. That is not a recall pass. Redaction evaluation is
`not_measured` in this proof, not perfect recall.

### Purpose checks

Before means the source scored against itself; after is the actual protected
post-suppression release. The original threshold is 0.90. Policy sacrifice floors
do not rewrite that threshold. A missing, errored or below-floor task fails.

| Task | Original threshold | Applicable floor | Before | After | Verdict |
|---|---|---|---|---|---|
| H-U2 | 0.90 | 0.90 unchanged | 1.0 | 0.9195 | Meets original target; accepted detail sacrifice from 30-minute los_minutes bins (#157) |
| H-U4 | 0.90 | 0.60 | 1.0 | 0.7952 | Misses original target; accepted sacrifice at floor 0.6 |
| H-U6 | 0.90 | 0.60 | 1.0 | 0.9462 | Meets original target; coarser-age sacrifice disclosed |
| H-U7 | 0.90 | 0.90 | 1.0 | 0.9827 | Meets original target |
| H-U8 | 0.90 | 0.60 | 1.0 | 0.9504 | Meets original target; coarser-time sacrifice disclosed |

The mean computed from full-precision `measured.utility.tasks[].after` is
0.9188106157491702, presented as 0.9188. Do not substitute kit baseline utility
or composite scores. H-U2's detail loss is not a waiver of its 0.90 floor.

### Attacker measurements (#138, #139)

All listed values are measured after protection; no paired before-persona run is
supplied. Zero is an observed rate in the named frame, never universal safety.

| Persona / attack | Unique re-identification rate | Denominator / frame |
|---|---|---|
| Municipal insider | 0 | 3,000 sampled released visits |
| Broker: public directory | 0 | 700 adversary records with a person in the release |
| Broker: health social posts | 0 | 796 adversary records with a person in the release |
| Broker: health news clips | 0 | 166 adversary records with a person in the release |
| Red team: range-aware linkage | 0 | 1,662 adversary records |
| Red team: cross-dataset enrichment | 0 | 1,662 adversary records |
| Red team: release join | 0 | 2,734 sampled register persons with a released visit |
| Red team: linked lab_results rows | 0 | 13,522 linked rows in that attack frame |

The insider uses a seeded sample capped at 3,000 visits, not the whole release.
Broker and red-team sources also use seeded per-source samples capped at 3,000
where needed. Persona attribute-inference rates are 0 for those same four
insider/broker frames; the stronger red-team attribute attacks are separate.
The red-team 1-in-k guess-success rates are nonzero: range-aware 0.0007,
cross-dataset 0.0009 and release-join 0.0024. Zero unique matches does not mean
zero guess success or zero attribute inference.

### Inference lift and diagnosis-known risk (#143, #157 / D64)

| Risk / bound | Final measurement | Meaning / verdict |
|---|---|---|
| Population lift for icd10_primary | 2.1351x | No bound; disclosed residual risk. Chapter-level coarsening makes H-U4 0 |
| Population lift for los_minutes ≤ 2.0x | 1.6894x | Meets enforced bound through 30-minute bins; H-U2 0.9195 |
| Persons below k=5 when diagnosis is additionally known | 73.6% (17,805 / 24,204; exact share 0.7356222112047596) | Substantial disclosed residual risk, outside the declared-QI pass |

The population lifts are the exact-QI-class producer estimator across all released
rows. They are recorded in `residualRisks[risk=attribute-lift-bound].description`;
its `rate` is deliberately not a ratio field, since lift can exceed 1. Do not turn
its `not_measured` rate marker into a claim that the described lifts are missing.

Sampled red-team inference is different: `icd10_primary` accuracy 0.1752 versus
baseline 0.0806 over 2,991 targets; `los_minutes` accuracy 0.1570 versus baseline
0.0919 over 2,994 targets. Those sampled ratios are not the population lift-bound
measurement. The manifest also discloses lab-value, revisit, temperature and triage
inference; zero linkage does not erase these risks.

### Gate and zero-hit checks

Final gate: **42 checks, 42 pass, 0 not applicable, 0 non-passing**. The logs report
37 release checks and 5 producer attestations in limited mode; full mode re-runs
all 42. The gate's 0 not-applicable count is distinct from vacuous text-recall
targets and structural risk notes marked not applicable.

Named identifier rescans, reversible-hash and key-material checks each report
0 hits over 834,435 cells; row-map exclusion reports 0 over 2 files; person-k
reports 0 below-k hits over 24,204 persons. These are scoped gate records, not
recall fractions or a new validation of every export-assertion field. An export
assertion is literal false only when its own required production check ran with
0 hits. Missing evidence remains invalid, not absence proven.

## 5. Sharing scenario, limitations and proof

HEALTH-S1 serves controlled research on crowding and revisits, not individual
care, profiling or arbitrary reuse. Pseudonymised data is still personal data;
the controller retains the key. Templated synthetic data does not establish real
speech performance. Per-label checks and disclosed risks are not universal anonymity.

The final measured release, limited verification and full verification all exit
0; exact recorded commands and CLI lines are in the source ledger. Limited mode
cannot authenticate the HMAC signature: an editor can recompute file digests.
Full verification needs the controller's inputs and key and re-runs producer checks.
Missing, errored or failed required checks block publication. A new docs commit
does not relabel existing release evidence as a fresh run on that docs revision.

A fresh planted-violation refusal is not demonstrated by this measured proof.
Record it separately through the real CLI on hand-made synthetic input if shown
in the final demonstration; report check names and counts only, never fabricate it.

CS-S1 remains future work under D46, not a successful released scenario. Its
historical strict-gate refusal is a limitation. CS-U1/U3/U4/U5, CS text recall
and CS health-in-text target results are not measured by this HEALTH-S1 run.
The CS evaluation path uses typed, numbered placeholders and D37 masking, never
realistic fake values. Historical held-out-miss-informed fixes are optimistic,
not untouched recall proof; no historical recall count is imported here.

The DPO/Findata evidence-pack exporter exists (#147), with a separately generated
real-kit HTML/Markdown pack. It derives purpose, legal-basis/DPIA placeholders,
methods, measured risk, utility, residual risks and reproducibility from the
authenticated signed manifest only. It is technical evidence, not a permit or a
DPIA. Legal basis and DPIA remain “to be supplied by the controller”. No pack
export is recorded in the `proof-c52424c` measured-run command list.

## Submission packaging handoff

Name/tagline and built-with chips are in 01; description in 02; video and pitch
in 03/04; deck in 05. Keep the existing video labelled `5b260ec` unless re-recorded
with matching final-release proof. Optional Mistral drafting is for human review;
REST API, draft-to-search integration and CS-S1 releases remain future work.

`docs/story/final/` is a separate submission package, not automatically created by
updating these source files. Its required files are `name.txt`, `tagline.txt`,
`description.md`, `built-with.txt`, `pitch-4min.md`, `video-script.md` and `SOURCES.md`.
The limits are 80 characters for name, 140 for tagline, and 5,000 for description
including whitespace; description has no headings or editorial notes. Keep
independent Standards/Spec review separate from this documentation update.

Run `python docs/story/check_final.py` to check packaging. Missing files/folder,
unresolved placeholders, claim/comment markers and over-limit text fail. The check
does not certify claim truth, proof freshness or submission readiness. Its logic
is unchanged. A missing-final-folder result is a blocker, not a passing skip.
