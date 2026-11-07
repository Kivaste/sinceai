# Four-minute finals pitch and 6-minute Q&A prep

Updated to the current build: hand plan for HEALTH-S1, two-tier verify, per-label assertions, signed manifest. Numbers are double-brace placeholders (see 06). Outside a conditional block everything is true today; `<!-- IF #n ... -->` blocks are enabled only after that ticket merges and the claim is verified (06 claims checklist). Say "pseudonymised" and "per-label", never "anonymised" or "no identifiers remain".

## Pitch beats

| Time | Beat | What is shown | Pattern |
|---|---|---|---|
| 0:00-0:30 | Problem. Removing names is not anonymisation, and nobody can re-check an "anonymised" claim. <!-- IF #23 measured numbers -->Blanket k-anonymity scores `{{measured.baselines.B2-k.utility}}` utility on HEALTH-S1; B0's worst re-identification risk is `{{measured.baselines.B0.worst_reid}}`.<!-- END IF --> | Problem slide | none |
| 0:30-1:00 | Origin and idea. Patterns from our classroom-recording product. Start from the data request: required analyses decide which fields are released and at what detail; the rest is withheld, each field with a reason. Today the levels come from a hand-written plan per scenario. <!-- IF #26 search merged -->A measured search picks the coarsest passing level.<!-- END IF --> | `detect` on `unseen`, then `run --scenario HEALTH-S1` | purpose first |
| 1:00-1:40 | Transform. `{{inventory.count}}` columns, `{{fieldJustifications.released.count}}` released with a reason, `{{fieldJustifications.withheld.count}}` withheld; 10-year age bands, hour of day. Identifiers are HMAC-SHA256 tokens under a secret key, so joins survive. <!-- IF #24 CS-S1 release -->CS-S1: `[PERSON_1]` stays consistent inside one conversation.<!-- END IF --> | Dashboard sections 1-3 | P1 |
| 1:40-2:20 | Gate. Plant a card number in a copy of the release: verify exits 1, names `rescan.payment-cards`, count, no value. "We do not trust our own output; we verify it." | Live terminal | P2 |
| 2:20-3:10 | Proof. `paymentCards` is `false` over `{{assertionEvidence.paymentCards.denominator.n}}` cells with `{{assertionEvidence.paymentCards.hits}}` hits; the format cannot express `true`. `verify` (limited: `{{gate.checks.release.count}}` release-checked, `{{gate.checks.producer.count}}` producer-attested), then `verify --full` with the key. Residual risks listed, "not measured" where true. <!-- IF #23 measured numbers -->Utility `{{measured.utility.after.H-U2}}` ... `{{measured.utility.after.H-U8}}` after release; privacy score `{{measured.privacy.before.summary.privacy}}` to `{{measured.privacy.after.summary.privacy}}`.<!-- END IF --><!-- IF #24 CS-S1 release --> Free text: exact-match recall NATIONAL_ID `{{measured.redaction.labels.NATIONAL_ID.recall}}`.<!-- END IF --> | Live `verify`, dashboard | P3 |
| 3:10-3:30 | Offline. Wi-Fi off, run again, same digests. "No data leaves the machine, not even to an AI model." | Terminal | P4 |
| 3:30-4:00 | Limits and close. Pseudonymised data is still personal data; the key holder can re-link; synthetic data; recipient digests catch accidents only. "Release only what the purpose needs, and prove it." | Limitations slide | all |

## Jury Q&A (6 minutes)

| Likely question | Answer |
|---|---|
| Isn't pseudonymised data still personal data? | Yes, and the manifest says so. We reduce and report risk; we do not claim anonymity. Key custody stays with the controller. |
| Why trust your manifest? | You do not have to. Each assertion names a check, version, denominator and hits. `verify <release>` re-runs the release-derivable checks. The format cannot express `true`; a failed high-severity check refuses the release; lower-severity hits are listed as residual risks. |
| What does limited verify not cover? | Producer-scope checks (original-value survival, key material, reversible hashes, per-person k) are reported as producer-attested. Signature and input digests need `verify --full` with the key. Digests alone detect accidents, not a determined editor. |
| Do you claim "no identifiers remain"? | No. Claims are per label (cards, national IDs, IBANs, emails ...), each with its own check and denominator. |
| How are detail levels chosen? | Today by a hand-written plan per scenario, with a reason per field in the manifest. <!-- IF #26 search merged -->A bounded measured search then picks the coarsest passing level; the manifest records candidates tried.<!-- END IF --> |
| What if the gate misses something? | Rescan validators are separate from the transform code. Anything outside the validated labels is a residual risk, listed with a rate or "not measured". |
| Did you optimise for the scorecard? | We use it, plus our own per-person k over every released quasi-identifier. <!-- IF #23 measured numbers -->Scorecard results appear only as manifest paths from a measured run.<!-- END IF --> |
| How do you know it generalises? | <!-- IF #24 CS-S1 release -->Free-text results are exact-match per label; the data is templated, so we also point to the organisers' hidden check. <!-- END IF -->For tables, the data is synthetic; we do not claim general attack resistance. |
| Why no LLM? | Sending data to a cloud model to protect it from an LLM vendor defeats the purpose. A future front end would see only the request text and the data dictionary, never values (ADR 0002). |
| Why not k-anonymity everywhere? | We apply per-person k over the released quasi-identifiers and list each sacrifice. <!-- IF #23 measured numbers -->B2-k scores `{{measured.baselines.B2-k.utility}}` utility on this scenario.<!-- END IF --> |
| Who holds the key? | The controller (`PETS_HMAC_KEY`, 32+ characters, never in output). One key per release today. <!-- IF #29 recipient keys -->Recipient-scoped keys stop two recipients joining their copies.<!-- END IF --> |
| Is it reproducible? | Same input, key, creation time and versions give a byte-identical release; the network is blocked at start-up. |
| What did you not finish? | Read it from the manifest: every `not_measured` field, plus stretch features (search, CS-S1, recipient keys, LLM front end) that are not merged. Never invent a number. |

