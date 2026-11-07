# Four-minute finals pitch and 6-minute Q&A prep

Based on PRIVACY_PATTERNS_PLAN section 10, updated to what is built: two-tier verify, per-label assertions, signed manifest, search over detail ladders. Numbers are double-brace placeholders (see 06). Say "pseudonymised" and "per-label", never "anonymised" or "no identifiers remain".

## Pitch beats

| Time | Beat | What is shown | Pattern |
|---|---|---|---|
| 0:00-0:30 | Problem. Removing names is not anonymisation. Under the published B0 baseline people can still be singled out (`{{measured.baselines.B0.singling_out}}` on HEALTH-S1); blanket k-anonymity keeps `{{measured.baselines.B2-k.utility_mean}}` of utility. Nobody can re-check an "anonymised" claim. | Slide with the three numbers | none |
| 0:30-1:00 | Origin and idea. Patterns from our classroom-recording product, applied here. Start from the data request: the research questions become executable purpose checks; each field goes to the coarsest detail that still passes. | `detect` on `unseen` (column roles with reasons), then `run --scenario HEALTH-S1` | purpose first |
| 1:00-1:40 | Transform. `{{inventory.count}}` columns, `{{fieldJustifications.released.count}}` released with a reason, `{{fieldJustifications.withheld.count}}` withheld. Keyed tokens: a join across tables still works, hash reversal recovers nothing. CS-S1: `[PERSON_1]` stays consistent inside one conversation. | Dashboard sections 1-3 | P1 |
| 1:40-2:20 | Gate. Plant a card number in a copy of the release: verify exits 1, names `rescan.payment-cards`, one hit, no value printed. "We do not trust our own redactor; we verify it." | Live terminal | P2 |
| 2:20-3:10 | Proof. Manifest: `paymentCards` is `false`, `{{assertionEvidence.paymentCards.denominator.n}}` cells, `{{assertionEvidence.paymentCards.hits}}` hits; the format cannot express `true`. Run `verify` (limited: `{{gate.checks.release.count}}` release-checked, `{{gate.checks.producer.count}}` producer-attested), then `verify --full` with the key. Utility before/after per purpose check, singling-out `{{measured.privacy.before.singling_out}}` to `{{measured.privacy.after.singling_out}}`, sacrifices, residual risks. Free text (CS-S1): exact-match recall per label, e.g. NATIONAL_ID `{{measured.redaction.labels.NATIONAL_ID.recall}}`. | Live `verify`, dashboard | P3 |
| 3:10-3:30 | Offline. Wi-Fi off, run again, same bytes. "No data leaves the machine, not even to an AI model." | Terminal, byte-identical digest | P4 |
| 3:30-4:00 | Limits and close. Pseudonymised data is still personal data; the key holder can re-link; synthetic data; recipient digests catch accidents only. "Release only what the purpose needs, and prove it." | Limitations slide | all |

## Jury Q&A (6 minutes)

| Likely question | Answer (updated to what is built) |
|---|---|
| Isn't pseudonymised data still personal data? | Yes, and the manifest says so. We reduce and measure risk; we do not claim anonymity. Key custody stays with the controller. |
| Why trust your manifest? | You do not have to. Each assertion names a check, its version, its denominator and hits. `verify <release>` re-runs the release-derivable checks. The format cannot express `true`; a failed check refuses the release. |
| What does limited verify not cover? | Producer-scope checks (original-value survival, key material, reversible hashes, per-person k) are reported as producer-attested. The signature and input digests need `verify --full` with the key. Digests alone detect accidents, not a determined editor. |
| Do you claim "no identifiers remain"? | No. Claims are per label (cards, national IDs, IBANs, emails ...), each with its own check and denominator. PERSON, ADDRESS, LOCATION in text are residual risks with measured recall. |
| What if the gate misses something? | Rescan validators are separate from the detector. Known gap: names outside the gazetteers and indirect health remarks; reported as residual risk with a rate. |
| Did you optimise for the scorecard? | We use it, plus our own per-person k (the scorecard misses renamed columns) and exact-match span metrics (the scorer counts any overlap). Defects found are listed in the manifest as scorecard defects. |
| How do you know the redactor generalises, given templated data? | Headline numbers use a template-held-out split; the organisers' hidden check is the independent test. Real speech would be messier. |
| Why no LLM? | Sending data to a cloud model to protect it from an LLM vendor defeats the purpose. Any LLM front end would see only the request text and the data dictionary, never values (ADR 0002), and it is a stretch. |
| Why not k-anonymity everywhere? | Blanket k keeps `{{measured.baselines.B2-k.utility_mean}}` of utility. We apply k per person where the scenario targets it and list each sacrifice. |
| Who holds the key? | The controller (`PETS_HMAC_KEY`, 32+ characters, never in output). Recipient-scoped keys stop two recipients joining their copies. |
| Is the output reproducible? | Same input, key, creation time and versions give a byte-identical release; the network is blocked at start-up. |
| What did you not finish? | State from the manifest: any `not_measured` field and the stretch features (LLM front end). Never invent a number. |

