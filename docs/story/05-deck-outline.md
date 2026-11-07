# Deck outline (10 slides)

One message per slide. HEALTH-S1 numbers are filled from the real story-kit release (see 06); CS-S1 numbers remain conditional placeholders. Keep text sparse; dashboard screenshots come from that release's manifest, never table rows.

| # | Title | Message | Visual | Shows |
|---|---|---|---|---|
| 1 | Title | Name, tagline, team, "offline, deterministic, proof attached" | Name + tagline on one clean slide | none |
| 2 | The problem | Removing names is not enough, and "anonymised" cannot be re-checked | B0 dataset-level worst re-identification 0.0950; B2-k mean scenario utility 0.3990 (H-U6/H-U7/H-U8 null, not zero) | `measured.baselines.B0.worst_reid`, `measured.baselines.B2-k.utility_mean` |
| 3 | Purpose first | The data request becomes purpose checks; a hand plan picks each field's level, with a reason. IF #26: a measured search picks the coarsest level that still passes every check | Flow: request -> purpose checks -> hand plan (IF #26: measured search) -> release | `release.scenario`, `release.recipient` |
| 4 | HEALTH-S1 field decisions | 53 columns: 16 released with a reason, 37 withheld | Dashboard field table (schema only) | `inventory.count`, `fieldJustifications.released.count`, `fieldJustifications.withheld.count` |
| 5 | Four patterns | Keyed pseudonyms, fail-closed gate, privacy manifest, fully offline | Four icons in a row, one line each | none |
| 6 | The gate refuses | A planted card number is refused with check, label and count, never the value | Terminal screenshot of the refusal | none (live demo) |
| 7 | The manifest proves | paymentCards false: 1,106,994 cells, 0 hits; 36 release checks, 4 producer-attested | Manifest excerpt: assertion next to evidence; two-tier verify line | `exportAssertions.paymentCards`, `assertionEvidence.paymentCards.denominator.n`, `assertionEvidence.paymentCards.hits`, `gate.checks.release.count`, `gate.checks.producer.count` |
| 8 | Measured, before and after | Post-suppression H-U2 0.9908, H-U4 0.7952, H-U6 0.9462, H-U7 0.9933, H-U8 0.9505; H-U4 is a policy sacrifice | Privacy 0.1716 to 1.0000 with age_band blind-spot warning beside it; independent per-person k min 5, 24,204 persons, 0.0000 share below 5 | `measured.utility.after.H-U2` ... `H-U8`, `measured.privacy.before.privacy`, `measured.privacy.after.privacy`, `measured.privacy.after.person_k.{min,persons,below_k_share}` |
| 9 | Honest limits (IF #24: plus CS-S1 free text) | What still can go wrong; IF #24: exact-match recall per label | Limitations list (pseudonymised is personal data, synthetic data, tamper limitation, "not measured" entries); IF #24: per-label recall bars | IF #24: `measured.redaction.labels.NATIONAL_ID.recall`, `measured.redaction.labels.PAYMENT_CARD.recall` |
| 10 | Close | Release only what the purpose needs, and prove it; what is next | Name, tagline, repository link | none |

Rule: slides marked IF are built only after the enabling ticket merges (see claims checklist in 06). If a key is `not_measured` in the manifest, drop that number and its sentence.





