# Pitch beats: HEALTH-S1 (Part A, no numbers yet)

Audience: the business teammate (deck, 2-minute video, tagline). Terms follow `GLOSSARY.md`.
Every number is a placeholder in double braces holding its manifest key path. Part B fills it from a real release (see `README.md`).
Do not type a number that has no placeholder. Each beat names the CLI command that shows it live.
`<R>` = the release folder, `<K>` = the kit root, `<S>` = HEALTH-S1.

## Beat 1: The problem (30 s)

- A hospital privacy officer must share ED visit data with a university research group studying crowding and revisits.
- "Remove the names" is not anonymisation. In the challenge kit under B0, a receipt still singles out `{{measured.baselines.B0.singling_out}}` of targets.
- Blanket k-anonymity (B2-k) keeps only `{{measured.baselines.B2-k.utility_mean}}` of the mean utility, and some required analyses drop to 0.
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

Utility, per purpose check, before and after (1.0 = same answer as the original):

| Check | Before | After |
|---|---|---|
| H-U2 | `{{measured.utility.before.H-U2}}` | `{{measured.utility.after.H-U2}}` |
| H-U4 | `{{measured.utility.before.H-U4}}` | `{{measured.utility.after.H-U4}}` |
| H-U6 | `{{measured.utility.before.H-U6}}` | `{{measured.utility.after.H-U6}}` |
| H-U7 | `{{measured.utility.before.H-U7}}` | `{{measured.utility.after.H-U7}}` |
| H-U8 | `{{measured.utility.before.H-U8}}` | `{{measured.utility.after.H-U8}}` |

Risk, before and after:

- Share of rows with k below 5: `{{measured.privacy.before.k_below_5_share}}` before, `{{measured.privacy.after.k_below_5_share}}` after.
- Singling-out rate: `{{measured.privacy.before.singling_out}}` before, `{{measured.privacy.after.singling_out}}` after.

Against the published baselines (same scenario, mean utility and singling-out):

| Baseline | Mean utility | Singling-out |
|---|---|---|
| B0 | `{{measured.baselines.B0.utility_mean}}` | `{{measured.baselines.B0.singling_out}}` |
| B2 | `{{measured.baselines.B2.utility_mean}}` | `{{measured.baselines.B2.singling_out}}` |
| B2-k | `{{measured.baselines.B2-k.utility_mean}}` | `{{measured.baselines.B2-k.singling_out}}` |

- Sacrifices the scenario policy allowed: `{{sacrifices.count}}`, each listed with the check it affects.
- Close with the honest residual risks (linkage under two attacker personas, the tamper limitation) from `residualRisks`.
- Live: open `<R>.dashboard.html` (sections 4-5 and the baseline comparison).

## Rules for the presenter

- Quote only numbers rendered from a real release. If a placeholder is unfilled, drop the sentence.
- Say "per-label" and "limited", never "fully anonymised".
