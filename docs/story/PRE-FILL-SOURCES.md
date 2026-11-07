# PRE-FILL sources and selector ledger

**PRE-FILL at df79ec20538e8f02b3256911fb01d549e5af0ebb** (#103, D61).

This is planning text, not final-SHA proof or submission readiness. The measured
release binds the revision below, not the later docs commit. Final review, a fresh
post-freeze run and a demonstrated refusal still gate finalisation. Keep
`docs/story/final/` absent until then; its named readiness skip is not a pass.

## One measurement source

- Tool revision: `df79ec20538e8f02b3256911fb01d549e5af0ebb`.
- HEALTH-S1 manifest: `C:\Users\kivas\AI\sinceai-out\story-prefill-df79ec2\health-s1-measured\privacy_manifest.json`.
- Manifest SHA-256: `25a51e1aa4ed91e03318b1bc857b4543ed0ddc324724d4bb85e08375243e66be`.
- Commands: `C:\Users\kivas\AI\sinceai-out\story-prefill-df79ec2\commands.ps1`.
- Recorded step outcomes: `C:\Users\kivas\AI\sinceai-out\story-prefill-df79ec2\steps.json`.
- The key was generated fresh in process memory and discarded; it was never printed or persisted.
- No CS-S1 manifest; D46 makes CS-S1 future work. No numbers come from another release.
- Aggregates and schema/field names only; no source/protected row values, row maps or keys were read for this fill.

### Input digests from bindings.inputs

| Input | SHA-256 |
|---|---|
| `clinical_notes` | `0f040c051454160561fea9de9e99606213f63699b734e40066e0157a9016db39` |
| `ed_visits` | `9d81dcc1badc186893097f57ff79356078edf83b4008770ebbcd28397bca9335` |
| `lab_results` | `8b66d848685da735e43eaa4dafaa55ce1200f15e859c322038a9160a69baffd4` |
| `published_weekly_stats` | `60ccc12e0fafa10f03268de9a46e8f642f541ab9841daf56d4df1d605b8e49b0` |

## Actual run and verification outcomes

Commands use the shared venv Python, `PYTHONPATH=<worktree>\src`, `PYTHONUTF8=1`,
`TZ=UTC` and the external `PYTHONPYCACHEPREFIX`. The driver records actual exits;
the following is a transcription, not newly minted check evidence.

| Step | Command | Exit |
|---|---|---|
| measure | `python -m pets_release.measure.wire --scenario HEALTH-S1 --out C:\Users\kivas\AI\sinceai-out\story-prefill-df79ec2\health-s1-measured --created 2026-11-07T08:00:00Z --kit "C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)\TRUSTED_PETS_PROVING_GROUND_2026"` | 0 |
| verify-limited | `python -m pets_release verify C:\Users\kivas\AI\sinceai-out\story-prefill-df79ec2\health-s1-measured` | 0 |
| verify-full | `python -m pets_release verify --full --kit "C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)\TRUSTED_PETS_PROVING_GROUND_2026" C:\Users\kivas\AI\sinceai-out\story-prefill-df79ec2\health-s1-measured` | 0 |

Gate records derived from `gate.checks`: **41/41 passing applicable checks;
0 not applicable; 0 non-passing**. Scopes: 37 release, 4 producer.

Actual CLI lines:

```text
RELEASED: health-s1-measured (measured)
VERIFIED (limited): 37 release-checked, 4 producer-attested
VERIFIED (full): 41 checks re-run (37 release, 4 producer); purpose checks re-run; signature, input digests and tool revision match
```

The verify results are CLI observations, not invented manifest fields.
Synthetic planted-violation refusal: not demonstrated by this run. The earlier
CS-S1 strict-gate refusal is a D46 limitation, not a fresh refusal observation.

### Named assertion records (copied from assertionEvidence)

| Assertion | Check | Version | Scope | Status | Hits | Scanned denominator |
|---|---|---|---|---|---|---|
| accountNumbers | `rescan.account-numbers` | 1.0.0 | release | pass | 0 | 834435 cells |
| deviceIds | `rescan.device-ids` | 1.0.0 | release | pass | 0 | 834435 cells |
| emails | `rescan.emails` | 1.0.0 | release | pass | 0 | 834435 cells |
| ibans | `rescan.ibans` | 1.0.0 | release | pass | 0 | 834435 cells |
| ipAddresses | `rescan.ip-addresses` | 1.0.0 | release | pass | 0 | 834435 cells |
| keyMaterial | `producer.key-material` | 1.0.0 | producer | pass | 0 | 834435 cells |
| nationalIds | `rescan.national-ids` | 1.0.0 | release | pass | 0 | 834435 cells |
| paymentCards | `rescan.payment-cards` | 1.0.0 | release | pass | 0 | 834435 cells |
| phones | `rescan.phones` | 1.0.0 | release | pass | 0 | 834435 cells |
| plates | `rescan.plates` | 1.0.0 | release | pass | 0 | 834435 cells |
| propertyIds | `rescan.property-ids` | 1.0.0 | release | pass | 0 | 834435 cells |
| quasiIdentifiersBelowK | `producer.person-k` | 1.0.0 | producer | pass | 0 | 24204 persons |
| rawTimestamps | `rescan.raw-timestamps` | 1.0.0 | release | pass | 0 | 834435 cells |
| reversibleHashes | `producer.unkeyed-hashes` | 1.0.0 | producer | pass | 0 | 834435 cells |
| rowMaps | `release.row-maps` | 1.0.0 | release | pass | 0 | 2 files |
| secrets | `rescan.secrets` | 1.0.0 | release | pass | 0 | 834435 cells |
| urlsWithTokens | `rescan.urls-with-tokens` | 1.0.0 | release | pass | 0 | 834435 cells |
| usernames | `rescan.usernames` | 1.0.0 | release | pass | 0 | 834435 cells |

## Selector ledger

All 83 original concrete selectors and 27 added concrete selectors are accounted
for below: **78 filled, 32 typed placeholders**. `manifest.<path>` was a grammar
illustration, not a concrete selector. Names are listed without row values.

The filled selectors resolve uniquely in the one manifest above. Utility requires
measured/ok status. Numbers retain manifest precision. `gate.checks` is rendered
as counts of its actual records, not a fabricated `.count` key. The free-text
status is `not_applicable` with reason “no free text released”, not a recall pass.
The numeric results and targets table are in `06-numbers-to-fill.md`.

### Filled selectors (names only)

- `manifest.assertionEvidence.accountNumbers.denominator.n`
- `manifest.assertionEvidence.accountNumbers.hits`
- `manifest.assertionEvidence.deviceIds.denominator.n`
- `manifest.assertionEvidence.deviceIds.hits`
- `manifest.assertionEvidence.emails.denominator.n`
- `manifest.assertionEvidence.emails.hits`
- `manifest.assertionEvidence.ibans.denominator.n`
- `manifest.assertionEvidence.ibans.hits`
- `manifest.assertionEvidence.ipAddresses.denominator.n`
- `manifest.assertionEvidence.ipAddresses.hits`
- `manifest.assertionEvidence.keyMaterial.denominator.n`
- `manifest.assertionEvidence.keyMaterial.hits`
- `manifest.assertionEvidence.nationalIds.denominator.n`
- `manifest.assertionEvidence.nationalIds.hits`
- `manifest.assertionEvidence.paymentCards.denominator.n`
- `manifest.assertionEvidence.paymentCards.hits`
- `manifest.assertionEvidence.phones.denominator.n`
- `manifest.assertionEvidence.phones.hits`
- `manifest.assertionEvidence.plates.denominator.n`
- `manifest.assertionEvidence.plates.hits`
- `manifest.assertionEvidence.propertyIds.denominator.n`
- `manifest.assertionEvidence.propertyIds.hits`
- `manifest.assertionEvidence.quasiIdentifiersBelowK.denominator.n`
- `manifest.assertionEvidence.quasiIdentifiersBelowK.hits`
- `manifest.assertionEvidence.rawTimestamps.denominator.n`
- `manifest.assertionEvidence.rawTimestamps.hits`
- `manifest.assertionEvidence.reversibleHashes.denominator.n`
- `manifest.assertionEvidence.reversibleHashes.hits`
- `manifest.assertionEvidence.rowMaps.denominator.n`
- `manifest.assertionEvidence.rowMaps.hits`
- `manifest.assertionEvidence.secrets.denominator.n`
- `manifest.assertionEvidence.secrets.hits`
- `manifest.assertionEvidence.urlsWithTokens.denominator.n`
- `manifest.assertionEvidence.urlsWithTokens.hits`
- `manifest.assertionEvidence.usernames.denominator.n`
- `manifest.assertionEvidence.usernames.hits`
- `manifest.fieldJustifications[table=ed_visits,column=arrival_ts].floor`
- `manifest.fieldJustifications[table=ed_visits,column=arrival_ts].reason`
- `manifest.fieldJustifications[table=ed_visits,column=arrival_ts].rung`
- `manifest.fieldJustifications[table=ed_visits,column=date_of_birth].floor`
- `manifest.fieldJustifications[table=ed_visits,column=date_of_birth].reason`
- `manifest.fieldJustifications[table=ed_visits,column=date_of_birth].rung`
- `manifest.fieldJustifications[table=ed_visits,column=municipality].floor`
- `manifest.fieldJustifications[table=ed_visits,column=municipality].reason`
- `manifest.fieldJustifications[table=ed_visits,column=municipality].rung`
- `manifest.fieldJustifications[table=ed_visits,column=visit_id].floor`
- `manifest.fieldJustifications[table=ed_visits,column=visit_id].reason`
- `manifest.fieldJustifications[table=ed_visits,column=visit_id].rung`
- `manifest.fieldJustifications[table=lab_results,column=test_name].floor`
- `manifest.fieldJustifications[table=lab_results,column=test_name].reason`
- `manifest.fieldJustifications[table=lab_results,column=test_name].rung`
- `manifest.gate.checks`
- `manifest.gate.status`
- `manifest.measured.privacy.components[component=k_below_5_share].after`
- `manifest.measured.privacy.components[component=k_below_5_share].before`
- `manifest.measured.privacy.components[component=linkage_reid].after`
- `manifest.measured.privacy.components[component=linkage_reid].before`
- `manifest.measured.privacy.components[component=person_k.below_k_share].after`
- `manifest.measured.privacy.components[component=person_k.min].after`
- `manifest.measured.privacy.components[component=person_k.persons].after`
- `manifest.measured.privacy.components[component=privacy].after`
- `manifest.measured.privacy.components[component=privacy].before`
- `manifest.measured.utility.tasks[task=H-U2].after`
- `manifest.measured.utility.tasks[task=H-U2].before`
- `manifest.measured.utility.tasks[task=H-U4].after`
- `manifest.measured.utility.tasks[task=H-U4].before`
- `manifest.measured.utility.tasks[task=H-U6].after`
- `manifest.measured.utility.tasks[task=H-U6].before`
- `manifest.measured.utility.tasks[task=H-U7].after`
- `manifest.measured.utility.tasks[task=H-U7].before`
- `manifest.measured.utility.tasks[task=H-U8].after`
- `manifest.measured.utility.tasks[task=H-U8].before`
- `manifest.pets[pet=local_suppression,table=ed_visits,column=patient_hetu].params.share`
- `manifest.residualRisks[risk=free-text-recall].rate.status`
- `manifest.residualRisks[risk=linkage-attackers].rate.reason`
- `manifest.sacrifices[check=H-U4].floor`
- `manifest.sacrifices[check=H-U6].floor`
- `manifest.sacrifices[check=H-U8].floor`

### Typed-placeholder selectors (names only)

The CS-S1 selectors below say “not measured (D46 / #24: CS-S1 future work; no
CS-S1 manifest in this run)”. Both existing attacker-risk status selectors say
“not measured (#138: per-persona attacker rates not present at this revision)”.
They never become zero or a target pass.

- `manifest.assertionEvidence.healthInText.denominator.n`
- `manifest.assertionEvidence.healthInText.hits`
- `manifest.fieldJustifications[table=conversations,column=started_ts].rung`
- `manifest.fieldJustifications[table=turns,column=ts].rung`
- `manifest.measured.utility.tasks[task=CS-U1].after`
- `manifest.measured.utility.tasks[task=CS-U1].before`
- `manifest.measured.utility.tasks[task=CS-U3].after`
- `manifest.measured.utility.tasks[task=CS-U3].before`
- `manifest.measured.utility.tasks[task=CS-U4].after`
- `manifest.measured.utility.tasks[task=CS-U4].before`
- `manifest.measured.utility.tasks[task=CS-U5].after`
- `manifest.measured.utility.tasks[task=CS-U5].before`
- `manifest.residualRisks[risk=attribute-inference].rate.status`
- `manifest.residualRisks[risk=attribute-inference-insider].rate.denominator.n`
- `manifest.residualRisks[risk=attribute-inference-insider].rate.value`
- `manifest.residualRisks[risk=linkage-attackers].rate.status`
- `manifest.residualRisks[risk=linkage-broker-news_clips_health].rate.denominator.n`
- `manifest.residualRisks[risk=linkage-broker-news_clips_health].rate.value`
- `manifest.residualRisks[risk=linkage-broker-public_directory].rate.denominator.n`
- `manifest.residualRisks[risk=linkage-broker-public_directory].rate.value`
- `manifest.residualRisks[risk=linkage-broker-social_posts_health].rate.denominator.n`
- `manifest.residualRisks[risk=linkage-broker-social_posts_health].rate.value`
- `manifest.residualRisks[risk=linkage-insider].rate.denominator.n`
- `manifest.residualRisks[risk=linkage-insider].rate.value`
- `manifest.residualRisks[risk=target-recall-iban].description`
- `manifest.residualRisks[risk=target-recall-iban].rate.value`
- `manifest.residualRisks[risk=target-recall-national-id].description`
- `manifest.residualRisks[risk=target-recall-national-id].rate.value`
- `manifest.residualRisks[risk=target-recall-payment-card].description`
- `manifest.residualRisks[risk=target-recall-payment-card].rate.value`
- `manifest.residualRisks[risk=target-recall-secret].description`
- `manifest.sacrifices[check=CS-U5].floor`

## Pending producer work (no invented selector paths)

- Merge-only update: #138's ten concrete per-persona value/denominator selectors are listed above and in 06, each absent from the unchanged df79ec2 manifest and typed “not measured (#138)”. Its generic fallback reason selector exists and is quoted from that same manifest in 06; no new release or measurement was used. The 3000-visit sample cap is #138 method documentation, not a PRE-FILL denominator.
- #146 / D58: not measured — separate k on the scenario QIs and all kept catalogued QIs, with withheld-column justifications.
- #138: not measured — per-persona attacker linkage and attribute-inference rates; the two existing risk-status selectors above stay unmeasured.
- #143: not measured — diagnosis-known k and risk share; no estimate is substituted.
- #147 / D60: not generated — evidence pack from the authenticated signed manifest; legal basis and DPIA to be supplied by the controller.

## Editorial and policy sources

- Editorial `origin/main` snapshot read for this fill: `1381010d7db2135753579d071dd64393249711e7`; the measured tool revision remains the separate integration pin above.
- origin/main docs/decisions.md: D46 (HEALTH-S1 cut, CS-S1 future work), D57 (pipeline engine and console), D58 (both QI sets), D60 (evidence pack), D61 (pre-fill now, refresh after freeze).
- #103 organiser clarification and #145 positioning/Q&A; #147 pointer. Typed, numbered placeholders and D37 masking are a CS evaluation choice, never fake realistic values or a CS-S1 release claim.
- src/pets_release/submission/unseen.py: full column coverage with role and subtype is an export prerequisite, not an organiser accuracy score or a fresh bundle observation.
- D40 / origin/main docs/challenge.md organiser clarifications: five demonstration items and honest targets met / not met.
- src/pets_release/policy/health_s1.py and run/purpose.py: original utility threshold 0.90, enumerated sacrifice floors, k target and suppression cap are policy, not new measurements.
- D55: the video remains on demo pin 5b260ec. These planning numbers must not relabel its captures.
- D22/D18: renamed age_band scorecard blind spot and producer-attested person-k. Recipient verification is limited; only the key holder re-verifies producer-scope checks.
- Search optimises k and utility, not attackers; attacker evaluation is post-hoc. Linkage zero means no shared QIs left to match on, not measured resistance.

After the freeze, refresh this ledger and the numeric renderings from one final
manifest. A newly available pending measurement also needs its real selector and
source binding; never turn an unavailable measurement into a guessed number.
