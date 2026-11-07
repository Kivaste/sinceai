# Deck outline (9 slides)

One message per slide. Numbers are double-brace placeholders (see 06). Keep text sparse; the dashboard screenshots come from a real release rendered from the manifest.

| # | Title | Message | Visual | Shows |
|---|---|---|---|---|
| 1 | Title | Name, tagline, team, "offline, deterministic, proof attached" | Name + tagline on one clean slide | none |
| 2 | The problem | Removing names is not enough, and "anonymised" cannot be re-checked | Three big numbers: B0 singling-out, B2-k utility, "0 ways to re-check" | `measured.baselines.B0.singling_out`, `measured.baselines.B2-k.utility_mean` |
| 3 | Purpose first | The data request becomes purpose checks; each field is released at the coarsest level that still passes | Flow: request -> purpose checks -> detail ladder -> release | `release.scenario`, `release.recipient` |
| 4 | HEALTH-S1 field decisions | Released fields have a reason; withheld fields were not needed | Dashboard field table (released vs withheld) | `inventory.count`, `fieldJustifications.released.count`, `fieldJustifications.withheld.count` |
| 5 | Four patterns | Keyed pseudonyms, fail-closed gate, privacy manifest, fully offline | Four icons in a row, one line each | none |
| 6 | The gate refuses | A planted card number is refused with check, label and count, never the value | Terminal screenshot of the refusal | none (live demo) |
| 7 | The manifest proves | Each assertion is `false` and bound to a named check with denominator and hits | Manifest excerpt: assertion next to evidence; two-tier verify line | `exportAssertions.paymentCards`, `assertionEvidence.paymentCards.denominator.n`, `assertionEvidence.paymentCards.hits`, `gate.checks.release.count`, `gate.checks.producer.count` |
| 8 | Measured, before and after | Required analyses keep their scores; risk falls | Bar pairs per purpose check; singling-out before/after; baseline comparison | `measured.utility.after.H-U2` ... `H-U8`, `measured.privacy.before.singling_out`, `measured.privacy.after.singling_out`, `measured.privacy.before.k_below_5_share`, `measured.privacy.after.k_below_5_share` |
| 9 | CS-S1 free text, and honest limits | Exact-match recall per label; what still can go wrong | Per-label recall bars; limitations list (pseudonymised is personal data, gazetteer gaps, synthetic data, tamper limitation) | `measured.redaction.labels.NATIONAL_ID.recall`, `measured.redaction.labels.PAYMENT_CARD.recall`, `measured.redaction.summary.leakage_before`, `measured.redaction.summary.leakage_after` |
| 10 | Close | Release only what the purpose needs, and prove it; what is next | Name, tagline, repository link | none |

Rule: if a key is `not_measured` in the manifest, drop that number and its sentence.

