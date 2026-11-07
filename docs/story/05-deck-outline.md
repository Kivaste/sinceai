# Deck outline (9 slides)

One message per slide. Numbers are double-brace placeholders (see 06). Keep text sparse; the dashboard screenshots come from a real release rendered from the manifest.

| # | Title | Message | Visual | Shows |
|---|---|---|---|---|
| 1 | Title | Name, tagline, team, "offline, deterministic, proof attached" | Name + tagline on one clean slide | none |
| 2 | The problem | Removing names is not enough, and "anonymised" cannot be re-checked | Text only; add B0 worst re-identification and B2-k utility after #23 merges | IF #23: `measured.baselines.B0.worst_reid`, `measured.baselines.B2-k.utility` |
| 3 | Purpose first | The data request becomes purpose checks; each field is released at the coarsest level that still passes | Flow: request -> purpose checks -> hand plan (IF #26: measured search) -> release | `release.scenario`, `release.recipient` |
| 4 | HEALTH-S1 field decisions | Released fields have a reason; withheld fields were not needed | Dashboard field table (released vs withheld) | `inventory.count`, `fieldJustifications.released.count`, `fieldJustifications.withheld.count` |
| 5 | Four patterns | Keyed pseudonyms, fail-closed gate, privacy manifest, fully offline | Four icons in a row, one line each | none |
| 6 | The gate refuses | A planted card number is refused with check, label and count, never the value | Terminal screenshot of the refusal | none (live demo) |
| 7 | The manifest proves | Each assertion is `false` and bound to a named check with denominator and hits | Manifest excerpt: assertion next to evidence; two-tier verify line | `exportAssertions.paymentCards`, `assertionEvidence.paymentCards.denominator.n`, `assertionEvidence.paymentCards.hits`, `gate.checks.release.count`, `gate.checks.producer.count` |
| 8 | Measured, before and after | Required analyses keep their scores; scorecard privacy score improves | Bar pairs per purpose check; privacy score before/after; baseline comparison | IF #23: `measured.utility.after.H-U2` ... `H-U8`, `measured.privacy.before.summary.privacy`, `measured.privacy.after.summary.privacy`, `measured.privacy.after.person_k.below_k_share` |
| 9 | Honest limits (IF #24: plus CS-S1 free text) | What still can go wrong; IF #24: exact-match recall per label | Limitations list (pseudonymised is personal data, synthetic data, tamper limitation, "not measured" entries); IF #24: per-label recall bars | IF #24: `measured.redaction.labels.NATIONAL_ID.recall`, `measured.redaction.labels.PAYMENT_CARD.recall` |
| 10 | Close | Release only what the purpose needs, and prove it; what is next | Name, tagline, repository link | none |

Rule: slides marked IF are built only after the enabling ticket merges (see claims checklist in 06). If a key is `not_measured` in the manifest, drop that number and its sentence.



