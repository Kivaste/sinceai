# Numbers to fill

Every number used in `02`-`05` is a double-brace placeholder holding the manifest path it must come from. Fill from a real release's `privacy_manifest.json` only (Part B of `docs/story-kit/README.md`); never type a number by hand. If the key is `not_measured` or absent, drop the sentence. Path grammar follows `docs/story-kit/README.md`.

| Placeholder path | Resolves to | Scenario | Used in |
|---|---|---|---|
| `release.scenario` | `release.scenario` (text) | both | 05 slide 3 |
| `release.recipient` | `release.recipient` (text) | both | 05 slide 3 |
| `inventory.count` | length of `inventory` | HEALTH-S1 | 02, 04, 05 |
| `fieldJustifications.released.count` | entries with `decision` = released | HEALTH-S1 | 02, 04, 05 |
| `fieldJustifications.withheld.count` | entries with `decision` = withheld | HEALTH-S1 | 02, 03, 04, 05 |
| `gate.checks.release.count` | `gate.checks` entries with `scope` = release | HEALTH-S1 | 03, 04, 05 |
| `gate.checks.producer.count` | `gate.checks` entries with `scope` = producer | HEALTH-S1 | 03, 04, 05 |
| `exportAssertions.paymentCards` | always `false` | HEALTH-S1 | 05 |
| `assertionEvidence.paymentCards.denominator.n` | cells scanned | HEALTH-S1 | 03, 04, 05 |
| `assertionEvidence.paymentCards.hits` | hits (0 in a published release) | HEALTH-S1 | 03, 04, 05 |
| `measured.utility.after.H-U2` | `measured.utility.tasks[task==H-U2].after` | HEALTH-S1 | 02, 03, 05 |
| `measured.utility.after.H-U4` | same, H-U4 | HEALTH-S1 | 02, 05 |
| `measured.utility.after.H-U6` | same, H-U6 | HEALTH-S1 | 02, 05 |
| `measured.utility.after.H-U7` | same, H-U7 | HEALTH-S1 | 02, 05 |
| `measured.utility.after.H-U8` | same, H-U8 | HEALTH-S1 | 02, 03, 05 |
| `measured.privacy.before.singling_out` | `measured.privacy.components[component==singling_out].before` | HEALTH-S1 | 02, 03, 04, 05 |
| `measured.privacy.after.singling_out` | same, `.after` | HEALTH-S1 | 02, 03, 04, 05 |
| `measured.privacy.before.k_below_5_share` | components entry `k_below_5_share`, `.before` | HEALTH-S1 | 02, 05 |
| `measured.privacy.after.k_below_5_share` | same, `.after` | HEALTH-S1 | 02, 05 |
| `measured.baselines.B0.singling_out` | `measured.baselines.rows[baseline==B0, metric==singling_out].value` | HEALTH-S1 | 04, 05 |
| `measured.baselines.B2-k.utility_mean` | rows[baseline==B2-k, metric==utility_mean].value | HEALTH-S1 | 02, 03, 04, 05 |
| `measured.redaction.labels.NATIONAL_ID.recall` | `measured.redaction.labels[label==NATIONAL_ID].recall` (exact match) | CS-S1 | 02, 04, 05 |
| `measured.redaction.labels.PAYMENT_CARD.recall` | same, PAYMENT_CARD | CS-S1 | 02, 05 |
| `measured.redaction.labels.IBAN.recall` | same, IBAN | CS-S1 | 02 |
| `measured.redaction.labels.SECRET.recall` | same, SECRET | CS-S1 | 02 |
| `measured.redaction.summary.leakage_before` | `measured.redaction.summary[metric==leakage_before].value` | CS-S1 | 02, 05 |
| `measured.redaction.summary.leakage_after` | `measured.redaction.summary[metric==leakage_after].value` | CS-S1 | 02, 05 |

## Assumptions to confirm before Part B

- The schema's `measured.redaction` has `labels[]` (precision, recall) and `summary[]` of `{metric, value}`, but no fixed metric ids. The two `leakage_*` ids are my assumption; if the CS-S1 writer uses other ids, change the paths here and in 02, 04, 05, and nothing else.
- `k_below_5_share` and `singling_out` are the component ids in the fixture manifest; `utility_mean` is the baseline metric id. Confirm against a real HEALTH-S1 release.
- The B0 singling-out value is only available if the baselines table carries a `singling_out` row for B0 (the story-kit CSV assumes it does).
- HEALTH-S1 utility "before" is 1.0 by definition and is not used in the prose; only "after" is quoted.
- `pets-release run --scenario CS-S1` was not enabled when this was drafted (README marks it skipped, pending turn_id ticket); drop the CS-S1 numbers and sentences if no CS-S1 release exists.
- The description limit is 5,000 characters; placeholders are longer than rendered numbers, so the rendered text is shorter than the count in `02`.
