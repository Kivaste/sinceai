# Numbers, real-run provenance and claims checklist

HEALTH-S1 numbers in `02`–`05` are filled from the story kit's real, post-suppression release. Only CS-S1 recall remains in double braces. Never substitute a missing measurement with zero. Conditional CS-S1 blocks must be omitted from submitted material until measured.

## Source and reproduction

- **R (fresh tip release, local-only):** `C:\Users\kivas\AI\sinceai-out\story-tip-e846512\health-s1\`; manifest `R/privacy_manifest.json`, scoring sidecar `...\story-tip-e846512\health-s1.scoring\`, scratch `...\health-s1.measure\`. Built by `python -m pets_release.measure.wire --scenario HEALTH-S1 --out R --created 2026-11-07T00:00:00Z --kit <K>` (exit 0, about 480 s) with the key from the local secret store (never recorded). These paths are outside the repo and are **local-only**: they cannot be reproduced from the repo alone (they need the kit and the key).
- **Bound source revision:** `e84651205174226c03477deacb40afe6be37b351` (`bindings.toolRevision`, the story branch after merging `origin/integration/pets-release`); `release.created` is `2026-11-07T00:00:00Z`, scenario HEALTH-S1, recipient default. Docs-only commits after it do not change the release, but a code change invalidates it.
- **Verify at that revision (real CLI, exit 0 both):** `pets-release verify R` printed `VERIFIED (limited): 36 release-checked, 4 producer-attested`; `pets-release verify --full --kit <K> R` printed `VERIFIED (full): 40 checks re-run (36 release, 4 producer); purpose checks re-run; signature, input digests and tool revision match`. Re-run both at recording time and quote only what they print.
- **F (fresh fill):** `C:\Users\kivas\AI\sinceai-out\story-tip-e846512\story-kit\` plus dashboard `...\story-tip-e846512\health-s1.dashboard.html` and `.csv` (local-only). `python docs/story-kit/fill_numbers.py R F`: exit 0, "wrote 42 values, 3 empty". All 42 values equal the committed `docs/story-kit/numbers.csv` (no number changed from the earlier release at `c3749d7`). The two overall privacy scores (component `privacy`) were read from R's `measured.privacy.components` and equal the earlier ones (0.1716 before, 1.0000 after).
- **Earlier provenance:** the prior release at `c3749d7` (`...\22\health-s1\`) and the story-kit merge `15b2a42` are superseded by R above; the earlier timed-out attempt at `936e583` supplied no numbers.
- **Sacrifices at the tip:** `sacrifices` lists three policy-enumerated entries, each with floor 0.6000: H-U4 (0.7952 after), H-U6 (0.9462) and H-U8 (0.9505). Only H-U4 is a visible loss; none is a full pass claim.
- Python runs use `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1`, `TZ=UTC`. CSVs are read as strings; no kit rows are displayed or sent to a service.

## Filled numbers

Paths use `docs/story-kit/README.md` grammar. For every F entry, find the row with the stated `manifest_key_path` in `F/numbers.csv`; all values resolve from R's manifest. Scores and shares are formatted to four decimals, not percentages. Count separators in prose do not change the value.

| Manifest key / resolver path | Value | Exact meaning | Output | Used in |
|---|---|---|---|---|
| `inventory.count` | 53 | length of inventory (columns) | F | 02, 04, 05 |
| `fieldJustifications.released.count` | 16 | decisions = released | F | 02, 04, 05 |
| `fieldJustifications.withheld.count` | 37 | decisions = withheld | F | 02, 03, 04, 05 |
| `gate.checks.release.count` | 36 | gate records scoped release | F | 03, 04, 05 |
| `gate.checks.producer.count` | 4 | gate records scoped producer; attested in limited verify | F | 03, 04, 05 |
| `exportAssertions.paymentCards` | false | assertion backed by its named check | F | 03, 04, 05 |
| `assertionEvidence.paymentCards.denominator.n` | 1106994 | cells scanned for payment cards, not persons | F | 03, 04, 05 |
| `assertionEvidence.paymentCards.hits` | 0 | payment-card hits in that check | F | 03, 04, 05 |
| `measured.utility.after.H-U2` | 0.9908 | post-suppression release task score | F | 02–05 |
| `measured.utility.after.H-U4` | 0.7952 | post-suppression release task score, policy-enumerated sacrifice | F | 02–05 |
| `measured.utility.after.H-U6` | 0.9462 | post-suppression release task score | F | 02–05 |
| `measured.utility.after.H-U7` | 0.9933 | post-suppression release task score | F | 02–05 |
| `measured.utility.after.H-U8` | 0.9505 | post-suppression release task score | F | 02–05 |
| `measured.privacy.before.privacy` | 0.1716 | components[component=privacy].before, original scorecard | P | 02, 04, 05 |
| `measured.privacy.after.privacy` | 1.0000 | components[component=privacy].after, suppressed-release scorecard | P | 02, 04, 05 |
| `measured.privacy.after.person_k.min` | 5 | our independent minimum per-person k | F | 02–05 |
| `measured.privacy.after.person_k.persons` | 24204 | persons counted by our per-person check | F | 02, 04, 05 |
| `measured.privacy.after.person_k.below_k_share` | 0.0000 | share of PERSONS below k=5 | F | 02, 04, 05 |
| `measured.privacy.before.k_below_5_share` | 0.9557 | scorecard share of ROWS below 5, row-weighted over tables scored for k | F | 04 Q&A |
| `measured.privacy.after.k_below_5_share` | 0.0000 | same ROW-weighted scorecard share after suppression | F | 04 Q&A |
| `measured.baselines.B0.worst_reid` | 0.0950 | published dataset-level worst re-identification, not scenario worst-table rate | F | 04, 05 |
| `measured.baselines.B2-k.utility_mean` | 0.3990 | published mean scenario utility; corrects obsolete draft key `.utility` | F | 02, 04, 05 |
| `measured.baselines.B2-k.task.H-U6` | null (—) | baseline cannot answer; not zero | F | 02, 04, 05 |
| `measured.baselines.B2-k.task.H-U7` | null (—) | baseline cannot answer; not zero | F | 02, 04, 05 |
| `measured.baselines.B2-k.task.H-U8` | null (—) | baseline cannot answer; not zero | F | 02, 04, 05 |
| `sacrifices.H-U4.floor` | 0.6000 | policy-enumerated H-U4 sacrifice floor | F | 04 Q&A |

The privacy score is **not proof of zero risk**. D22: the scorecard is blind to the renamed `age_band`; our per-person k check is authoritative. Before-k weights cover clinical_notes, ed_visits, lab_results and published_weekly_stats; after-k weights cover ed_visits only (the tables the scorecard scores for k), not all released rows. Person shares and row shares are never interchangeable. Linkage attackers and attribute-inference rates remain not measured; do not claim measured attack resistance from the overall privacy score. Every quoted utility score is the **suppressed release's**, never the pre-suppression hand plan's.

## Unfilled placeholders

| Placeholder | Why it remains | Where |
|---|---|---|
| `measured.redaction.labels.NATIONAL_ID.recall` | R is HEALTH-S1; `measured.redaction.status` is `not_measured`. No verified measured CS-S1 release is supplied by this story kit. | 02, 04; path reference in 05 |
| `measured.redaction.labels.PAYMENT_CARD.recall` | same; exact-match recall unavailable | 02; path reference in 05 |
| `measured.redaction.labels.IBAN.recall` | same; exact-match recall unavailable | 02 |
| `measured.redaction.labels.SECRET.recall` | same; exact-match recall unavailable | 02 |

Keep those placeholders in the working drafts, but omit their conditional sentences/slides from the submission. Neither baseline nulls nor missing attacker rates are zero measurements.

## Claims checklist

These drafts demonstrate R's hand plan. Other merged features are not implicitly demonstrated by that run. Enable a conditional block only after a suitable real run verifies it.

| Claim | Status / verification needed |
|---|---|
| Hand plan, age in 10-year bands, arrival as hour of day | R uses `age.band10` and `ts.hour_of_day`; read actual `fieldJustifications.rung`, not floor. |
| Required-task utility and privacy before/after | Filled above; story-kit release and outputs are the source. Keep H-U4 sacrifice and D22 caveat visible. |
| Measured search (#26 / ticket 25) | Not shown by R: `measured.search.status` = `not_measured`. Keep search blocks conditional. Do not promise every original floor passes when a policy sacrifice is used. |
| CS-S1 release and exact-match per-label recall (#24 / ticket 23) | Conditional; needs a real CS-S1 release and `measured.redaction.status` = `measured`. No transcript rows on screen. |
| Recipient-scoped keys (#29 / ticket 28, merged) | R uses recipient default; a separate recipient-scoped run is needed before enabling the optional demo claim. |
| Two-tier verification and signed manifest | Verified for this story: both tiers were run with the real CLI on the fresh tip release (exit 0, outputs recorded under Source). Re-run at recording time; if either fails, report the failure, not a success line. Limited verification catches accidents only. |
| Planted card refusal / byte-identical offline rerun | Still requires the actual recording-time planted-copy test / same-input rerun. This documentation update does not certify either as a new check pass. |

## Limits and presentation

- Taglines must remain <= 140 characters; description body <= 5,000 including conditional text and remaining placeholders. Count the body after the separator, not the editing notes.
- Video timeline is 1:50; optional CS-S1 aggregate insert adds at most 5 seconds (1:55). Narration word-count estimates are not a timed recording: rehearse and confirm the exported video is < 2:00.
- Tagline character counts (including spaces): T1 118, T2 124, T3 127, T4 117, T5 122. Name counts: N1 58, N2 56, N3 52. Video narration: 160 words (about 80 seconds at 120 words/minute, within the 110-second screen schedule).
- Description body: 4,731 characters including conditional markup and remaining placeholders; 4,554 with comment markers stripped. Its four CS-S1 placeholders stay in the editing draft only, never an unmeasured submission claim.
- Names, age-band width and timing markers are presentation/schema choices, not measured performance claims. No data values belong in screenshots, narration, manifests, logs or commits.

## Gate severity behaviour (source: integration code)

- A high-severity hit fails its check and refuses the release.
- A hit of any severity in a check bound to an export assertion prevents that assertion from being written false, so the writer refuses.
- A low-severity hit in another check does not refuse. It stays in `gate.checks[].hits` AND is written to `residualRisks` as kind `gate_low_severity` (`writer/assemble.py`), which `verify` re-derives (`verify/core.py`). Tip release: `text.health` (release scope) has 83 low-severity HEALTH hits over 512,166 turns scanned. Errors, missing checks and unknown outcomes never count as passes.
