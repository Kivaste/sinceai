# Pitch beats: HEALTH-S1 (Part A, no numbers yet)

Audience: the business teammate (deck, 2-minute video, tagline). Terms follow `GLOSSARY.md`.
Every number is a placeholder in double braces holding its manifest key path. Part B fills it from a real release (see `README.md`).
Do not type a number that has no placeholder. Each beat names the CLI command that shows it live.
`<R>` = the release folder, `<K>` = the kit root, `<S>` = HEALTH-S1.

## Beat 1: The problem (30 s)

- A hospital privacy officer must share ED visit data with a university research group studying crowding and revisits.
- "Remove the names" is not anonymisation: under the B0 baseline, people can still be singled out. (Qualitative here; the HEALTH-S1 singling-out figure appears in Beat 6. Do not quote a kit percentage from any other scenario.)
- Blanket k-anonymity (B2-k) keeps a scenario utility of only `{{measured.baselines.B2-k.utility_mean}}`, and it cannot answer H-U6 (`{{measured.baselines.B2-k.task.H-U6}}`), H-U7 (`{{measured.baselines.B2-k.task.H-U7}}`) or H-U8 (`{{measured.baselines.B2-k.task.H-U8}}`) at all (the kit publishes those as null; `—` below means null).
- The published B0 baseline (names removed only) has a dataset-level worst-case re-identification figure (maximum across tables) of `{{measured.baselines.B0.worst_reid}}`.
- Nobody can re-check an "anonymised" claim.
- Live: `pets-release detect unseen --format unseen` (opener: it labels an unlabelled export without hints).

## Beat 2: Purpose-first (30 s)

- We start from the data request, not the data: "researchers studying ED revisits" becomes five executable purpose checks (H-U2, H-U4, H-U6, H-U7, H-U8).
- For each field the tool finds the coarsest detail at which every purpose check still passes. Everything else is withheld. This is GDPR Art. 5(1)(b)-(c) as a measurement.
- Scenario: `{{release.scenario}}` for recipient `{{release.recipient}}`.
- Live: `pets-release run --scenario HEALTH-S1 --out <R> --created <iso-utc> --kit <K>`

## Beat 3: Withheld fields (30 s)

- `{{inventory.count}}` source columns were identified and given a role, with evidence.
- `{{fieldJustifications.released.count}}` fields are released, each with its rung and a stated reason.
- `{{fieldJustifications.withheld.count}}` fields are withheld, because no purpose check needs them. Names, phone numbers, addresses and the clinical notes never leave.
- Age is released as a band (`age_band`), not a birth date. Our own per-person k over every released QI is authoritative (D22).
- Live: `pets-release dashboard <R> --out <R>.dashboard.html` (sections 1-3: data types, PET per field, protected output).

## Beat 4: The gate refuses (live, 45 s)

- Plant a payment-card number into a copy of the release, then run the gate/verify on it. The tool refuses, names the check and label, gives counts and row locations, and never prints the value.
- The assertion we show instead of a universal claim: `exportAssertions.paymentCards` is `{{exportAssertions.paymentCards}}`, checked over `{{assertionEvidence.paymentCards.denominator.n}}` cells with `{{assertionEvidence.paymentCards.hits}}` hits.
- Same for `nationalIds`: `{{exportAssertions.nationalIds}}` over `{{assertionEvidence.nationalIds.denominator.n}}` cells.
- We make per-label claims only, each backed by its own named check. No "no identifiers remain".
- Live: `pets-release verify <R>.planted` exits 1 (plant by editing a copy of `<R>`; never the original).

## Beat 5: Limited vs full verify (30 s)

- Recipient mode re-runs what the recipient can: `pets-release verify <R>` prints `VERIFIED (limited): {{gate.checks.release.count}} release-checked, {{gate.checks.producer.count}} producer-attested`.
- It never claims full success. The controller or auditor runs `pets-release verify --full --kit <K> <R>` with the key in `PETS_HMAC_KEY`. It re-runs every check, the signature and the input digests; a check it cannot run is a failure.
- Honest limit: recipient-mode digests catch accidents, not a determined editor. Only `--full` checks the signature.
- Live: `pets-release verify <R>` then `pets-release verify --full --kit <K> <R>`.

## Beat 6: Numbers against B0 / B2 / B2-k (45 s)

Utility, per purpose check, before and after (a score of 1 = same answer as the original):

| Check | Before | After |
|---|---|---|
| H-U2 | `{{measured.utility.before.H-U2}}` | `{{measured.utility.after.H-U2}}` |
| H-U4 | `{{measured.utility.before.H-U4}}` | `{{measured.utility.after.H-U4}}` |
| H-U6 | `{{measured.utility.before.H-U6}}` | `{{measured.utility.after.H-U6}}` |
| H-U7 | `{{measured.utility.before.H-U7}}` | `{{measured.utility.after.H-U7}}` |
| H-U8 | `{{measured.utility.before.H-U8}}` | `{{measured.utility.after.H-U8}}` |

Risk, before and after. Mind the denominators: they differ.

- Our per-person k (authoritative, D22), over every released quasi-identifier: `{{measured.privacy.after.person_k.persons}}` persons counted, minimum k `{{measured.privacy.after.person_k.min}}`, share of PERSONS with k below 5: `{{measured.privacy.after.person_k.below_k_share}}`. There is no "before" for this: the original has no released form to take a k of.
- Kit scorecard, share of ROWS with k below 5, row-weighted across all tables: `{{measured.privacy.before.k_below_5_share}}` before, `{{measured.privacy.after.k_below_5_share}}` after. Rows, not persons, and see the disclosure below.
- Kit scorecard, linkage re-identification, worst table: `{{measured.privacy.before.linkage_reid}}` before, `{{measured.privacy.after.linkage_reid}}` after.

Against the published baselines (scenario utility, and the published dataset-level worst re-identification, the maximum across tables; not the HEALTH-S1 scenario figure):

| Baseline | Scenario utility | Worst re-identification (dataset level, max across tables) |
|---|---|---|
| B0 | `{{measured.baselines.B0.utility_mean}}` | `{{measured.baselines.B0.worst_reid}}` |
| B2 | `{{measured.baselines.B2.utility_mean}}` | `{{measured.baselines.B2.worst_reid}}` |
| B2-k | `{{measured.baselines.B2-k.utility_mean}}` | `{{measured.baselines.B2-k.worst_reid}}` |

- Disclosure (D22, residual risk `scorecard-renamed-qi`): we release age as `age_band`. The kit scorecard does not count a renamed column as a quasi-identifier, so its "rows with k below 5" figure is blind to `age_band`. Our per-person k over every released quasi-identifier is the authoritative figure; the scorecard figure is shown only for completeness. Do not present the scorecard figure as proof of k-anonymity.
- "After" is the score of the release the recipient actually gets, after local suppression of below-k persons, not the pre-suppression plan.
- Sacrifices the scenario policy allowed: `{{sacrifices.count}}`, each listed with the check it affects. H-U4 is the visible one: it falls to `{{measured.utility.after.H-U4}}` because the plan coarsens geography to municipality and suppresses below-k persons, which the scenario policy enumerates as a sacrifice with a floor of `{{sacrifices.H-U4.floor}}` (H-U6: floor `{{sacrifices.H-U6.floor}}`, H-U8: floor `{{sacrifices.H-U8.floor}}`). Say so; do not hide it.
- Close with the honest residual risks (linkage under two attacker personas, the tamper limitation) from `residualRisks`.
- Live: open `<R>.dashboard.html` (sections 4-5 and the baseline comparison).

## Rules for the presenter

- Quote only numbers rendered from a real release. If a placeholder is unfilled, drop the sentence.
- Say "per-label" and "limited", never "fully anonymised".
