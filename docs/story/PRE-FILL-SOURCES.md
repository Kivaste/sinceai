# Final release sources and selector ledger

**FINAL at c52424c (merged to main cc66ac2)**.
The historical filename is retained for existing links. Measurements below bind
the final integration release, not the later documentation commit. This note
transcribes existing measured proof; it does not mint release evidence or review.

## Final measurement source

- Integration tool revision: `c52424cef75d64a791ff9e8d11b9292c92e68562`.
- Main merge: `cc66ac2`.
- Proof root: `C:\Users\kivas\AI\sinceai-out\proof-c52424c\`.
- HEALTH-S1 manifest: `C:\Users\kivas\AI\sinceai-out\proof-c52424c\health-s1-measured\privacy_manifest.json`.
- Aggregate dashboard: `C:\Users\kivas\AI\sinceai-out\proof-c52424c\health-s1-measured-dashboard.csv`.
- Recorded driver: `commands.ps1` under that proof root. Its `$Tip` and revision
  guard pin c52424c; its introductory comment still names an older tip and is stale.
- Actual exit record: `run.out.log`; individual output logs are listed below.
- The driver generates a throwaway key in process memory and removes it from the
  environment. The key is not printed or saved by that driver.
- No CS-S1 manifest in this proof. D46 makes CS-S1 releases future work.
- Only aggregate fields, descriptions, rates and schema names were used. No kit
  tables, protected rows, row maps, truth data or key material were opened.

## Recorded commands and outcomes

The driver uses the shared `.venv` Python with `PYTHONPATH` pointing at the pinned
worktree's `src`, `PYTHONUTF8=1`, `TZ=UTC` and an external `PYTHONPYCACHEPREFIX`.
For readability, `$R` below means the absolute measured-release folder above,
`$K` the local kit root and `$Dashboard` its sibling dashboard HTML path. These
are transcriptions of the driver's argument arrays, not commands newly run by
this documentation update.

| Step | Recorded command | Exit | Log |
|---|---|---|---|
| Measured release | `python -m pets_release.measure.wire --scenario HEALTH-S1 --out $R --created 2026-11-07T08:00:00Z --kit $K` | 0 | `e-measured-default.log` |
| Limited verification | `python -m pets_release verify $R` | 0 | `f-measured-verify-limited.log` |
| Full verification | `python -m pets_release verify --full --kit $K $R` | 0 | `g-measured-verify-full.log` |
| Dashboard | `python -m pets_release dashboard $R --out $Dashboard` | 0 | `h-measured-dashboard.log` |

Gate records: **42 checks, 42 pass, 0 not applicable, 0 non-passing**.
Scopes: 37 release, 5 producer. Actual recorded CLI lines:

```text
RELEASED: health-s1-measured (measured)
VERIFIED (limited): 37 release-checked, 5 producer-attested
VERIFIED (full): 42 checks re-run (37 release, 5 producer); purpose checks re-run; signature, input digests and tool revision match
```

Verification outcomes are CLI observations, not invented manifest fields. Input
digest and revision matching is attested by the recorded full-verifier output;
the old pre-fill input-digest/hash ledger is not carried forward as fresh evidence.
This proof does not record a fresh planted-violation refusal or an evidence-pack
export. Never claim those operations ran here because a feature exists.

## Final selector ledger

All selectors refer to the manifest above. `[key=value]` denotes a unique array
entry, not a literal JSON key or an implicit list index. The full presentation
table and caveats are in `06-numbers-to-fill.md`. Display scores rounded to four
decimals; compute means from full precision, not rounded intermediate results.

| Claim | Actual source / selector | Final rendering |
|---|---|---|
| Task utilities | `measured.utility.tasks[task=H-U2/H-U4/H-U6/H-U7/H-U8].{before,after,status}` | Before all 1.0; after 0.9195 / 0.7952 / 0.9462 / 0.9827 / 0.9504; all status ok |
| Mean utility | Arithmetic mean of those five before/after task values | 1.0 → 0.9188; full-precision after mean 0.9188106157491702 |
| Privacy score | `measured.privacy.components[component=privacy].{before,after}` | 0.1716 → 1.0 |
| Below-k=5 ROW share | `measured.privacy.components[component=k_below_5_share].{before,after}` | 0.9557 → 0 |
| Scorecard linkage | `measured.privacy.components[component=linkage_reid].{before,after}` | 0.5697 → 0 |
| Person-k summary | `measured.privacy.components[component=person_k.min/person_k.persons/person_k.below_k_share].after` | 5 / 24,204 / 0 |
| Scenario QI set | `measured.kSets.sets[set=scenario].released.{minK,belowK,belowKShare,persons}` | 5 / 0 / 0 / 24,204 |
| Kept-catalogued QI set | `measured.kSets.sets[set=keptCatalogued].released.{minK,belowK,belowKShare,persons}` | 5 / 0 / 0 / 24,204 |
| QI coverage and withheld reasons | `measured.kSets.sets[].qi`, `measured.kSets.withheld[]` | Both released sets: age_band, arrival_ts, municipality; withheld reasons present |
| Suppression share | Derive from `measured.kSets.sets[set=scenario].{beforeSuppression,released}.persons` | (26,876 − 24,204) / 26,876 = 0.09942 |
| Actual field detail | `fieldJustifications[table=...,column=...].{rung,floor,decision,outputColumn,reason}` | See 06; test_name withheld, floor lab.full |
| H-U2 trade-off | `sacrifices[check=H-U2].{floor,after,reason,liftStep}` | Floor 0.90 unchanged; los_minutes 30-minute bins; accepted detail sacrifice |
| H-U4 sacrifice | `sacrifices[check=H-U4].{floor,after,reason}` | 0.7952, accepted at 0.6, below original 0.90 target |
| H-U6/H-U8 sacrifices | `sacrifices[check=H-U6/H-U8].{floor,after,reason}` | Coarser age/time detail; both still meet 0.90 |
| Diagnosis-known risk | `residualRisks[risk=person-k-diagnosis-known].{description,rate}` | 0.7356222112047596; 73.6% (17,805 / 24,204 persons) below k=5 |
| Population attribute lifts | `residualRisks[risk=attribute-lift-bound].description` | icd10_primary 2.1351x, no bound; los_minutes 1.6894x, bound 2.0x |
| Lift marker caveat | Same risk's `rate.reason` | Lift is a ratio, not a rate in [0,1]; numeric lifts live in description |
| Scorecard blind spot | `residualRisks[risk=renamed-age-band-scorecard-blind-spot/scorecard-renamed-qi].description` | Kit scorecard misses renamed age_band; not absence of risk |
| Exact test identity risk | `residualRisks[risk=lab-test-code-identity].description` | test_code remains exact for H-U7; known test history could single people out |
| Free-text recall | `residualRisks[risk=free-text-recall].rate` | Not applicable: no free text released, not a recall pass |
| Gate | `gate.status`, counts of `gate.checks[].{status,scope}` | Pass; 42/42, 0 not applicable; 37 release, 5 producer |

`measured.redaction.status` is `not_measured`: redaction evaluation was not run.
No overall composite, full k histogram, before-persona attack rates, CS-S1 scores
or organiser unseen-detection accuracy are supplied by this proof. Keep those
unavailable rather than fabricating selectors or substituting baseline results.

### Attacker selectors and scopes

Values below use `residualRisks[risk=<ID>].rate.{value,denominator.n}`. Their
descriptions define the frame and sampling cap. All entries are measured.

| Risk ID | Value | Denominator |
|---|---|---|
| linkage-insider | 0 | 3,000 sampled visits |
| linkage-broker-public_directory | 0 | 700 adversary records |
| linkage-broker-social_posts_health | 0 | 796 adversary records |
| linkage-broker-news_clips_health | 0 | 166 adversary records |
| attribute-inference-insider | 0 | 3,000 sampled visits |
| attribute-inference-broker-public_directory | 0 | 700 adversary records |
| attribute-inference-broker-social_posts_health | 0 | 796 adversary records |
| attribute-inference-broker-news_clips_health | 0 | 166 adversary records |
| linkage-redteam-range-aware | 0 | 1,662 adversary records |
| linkage-redteam-cross-dataset | 0 | 1,662 adversary records |
| linkage-redteam-release-join | 0 | 2,734 register persons |
| linkage-redteam-release-join-lab_results | 0 | 13,522 linked lab rows |
| linkage-redteam-range-aware-guess | 0.0007 | 1,662 adversary records |
| linkage-redteam-cross-dataset-guess | 0.0009 | 1,662 adversary records |
| linkage-redteam-release-join-guess | 0.0024 | 2,734 register persons |
| attribute-inference-redteam-icd10_primary | 0.1752 | 2,991 targets |
| attribute-inference-redteam-icd10_primary-baseline | 0.0806 | 2,991 targets |
| attribute-inference-redteam-los_minutes | 0.1570 | 2,994 targets |
| attribute-inference-redteam-los_minutes-baseline | 0.0919 | 2,994 targets |

The sampled attacker accuracy/baseline ratios are not the population lifts used
for the D64 bound. Zero unique re-identification does not imply zero guessing,
zero inference or safety when diagnosis or test history is known.

## Shipped features and evidence boundaries

- #146: both QI-set reports are present in this manifest; no pending claim remains.
- #138/#139: measured persona and red-team rates are present, with denominators.
- #143: diagnosis-known person-k risk is measured and disclosed, not estimated.
- #157 / D64: los_minutes population lift is bounded at 2.0x; diagnosis lift is
  disclosed without a bound because chapter-level coding makes H-U4 0.
- #147 / D60: exporter exists. Existing real-kit pack paths:
  `C:\Users\kivas\AI\sinceai-out\fu147-df62286-realkit\evidence-pack.html` and
  `C:\Users\kivas\AI\sinceai-out\fu147-df62286-realkit\evidence-pack.md`.
  These are separate earlier feature artefacts, not a c52424c export. Legal basis
  and DPIA remain controller-supplied; a pack is not legal approval or verification.
- Mistral front end: draft policies for human review, never row values; not
  draft-to-search integration and not a new network proof from this measured run.
- D46: HEALTH-S1 only; CS-S1 releases remain future work. CS evaluation uses typed,
  numbered placeholders and D37 masking, never realistic fake identities.
- D55: video stays labelled demo pin `5b260ec` unless re-recorded with matching proof.
- D57: self-hosted engine, approval/audit console; REST API future work.
- Independent review and `docs/story/final/` submission packaging remain separate
  tasks. No final folder, review verdict or fresh refusal is minted by this update.
