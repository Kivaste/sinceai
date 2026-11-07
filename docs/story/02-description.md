# Submission description

Character count: 4933 of 5,000, counting the body below including all conditional blocks and unrendered placeholders. Rendered numbers are shorter than placeholders.
True for the current build when every conditional block is removed. A block is kept only once its enabling ticket has merged and the claim is verified (see the claims checklist in 06). Strip the HTML comment markers before submitting. The first two paragraphs work alone for voters.

---

Share data with a recipient without over-sharing: pets-release releases only the fields a stated purpose needs, then ships checks anyone can re-run offline.

Most "anonymised" data is a claim. Ours is a release plus a privacy manifest where every statement names a check that ran on the actual files, with the cells scanned and the hits found.

## The problem

A data controller must share data for a purpose: a hospital with a research group, a contact centre with an LLM vendor. Removing names is not enough, and an "anonymised" claim cannot be re-checked.
<!-- IF #23 measured numbers -->Blanket k-anonymity (B2-k) scores {{measured.baselines.B2-k.utility}} utility on HEALTH-S1.<!-- END IF -->

## Purpose first

We start from the data request. The scenario's required analyses (purpose checks) decide which fields are released and at what detail; fields no purpose check needs are withheld. Today a hand-written plan per scenario picks the levels, and the manifest records a reason for every field.
<!-- IF #26 search merged -->A measured search over detail ladders then picks the coarsest level at which every purpose check still passes.<!-- END IF -->

## Four patterns

1. Keyed pseudonyms. Identifiers become HMAC-SHA256 tokens under a secret key, so joins inside a release survive.
<!-- IF #29 recipient keys -->Keys can be scoped per recipient, so two recipients cannot join their copies.<!-- END IF -->
2. Fail-closed gate. A closed contract lists allowed files, columns and value forms. An independent rescan, a check for surviving original values and a per-person k check run on the candidate release. A hit, an error or a check that did not run means exit 1 and nothing is published. Refusal reports give counts and labels, never values.
3. Privacy manifest. Each assertion, for example paymentCards or nationalIds, can only hold the literal false and is bound to a named check with version, denominator and hits. Claims are per label; we never claim "no identifiers remain". Risks that cannot be zero are listed as residual risks. The manifest is HMAC-signed.
4. Fully offline. No network, no cloud model; sockets are blocked at start-up. The same input, key and creation time give a byte-identical release.

Verification has two tiers. `pets-release verify <release>` lets the recipient re-run the release-derivable checks and always says "VERIFIED (limited)". `verify --full` with the kit and key re-runs everything, including the signature; a check that cannot run is a failure.

## Scenario HEALTH-S1 (lead)

Emergency-department visits go to a university research group studying crowding and revisits. Patient names and clinical notes are withheld; age is released in 10-year bands, arrival time as hour of day, the visit id as a keyed pseudonym. {{inventory.count}} columns were classified: {{fieldJustifications.released.count}} released, {{fieldJustifications.withheld.count}} withheld. Per-person k is checked over every released quasi-identifier.
<!-- IF #23 measured numbers -->Required analyses after release (1.0 = same answer as the original): H-U2 {{measured.utility.after.H-U2}}, H-U4 {{measured.utility.after.H-U4}}, H-U6 {{measured.utility.after.H-U6}}, H-U7 {{measured.utility.after.H-U7}}, H-U8 {{measured.utility.after.H-U8}}. Scorecard privacy score {{measured.privacy.before.summary.privacy}} before, {{measured.privacy.after.summary.privacy}} after; share of persons below k {{measured.privacy.after.person_k.below_k_share}}.<!-- END IF -->

<!-- IF #24 CS-S1 release -->## Scenario CS-S1 (free text)

Contact-centre transcripts go to an external LLM vendor. Spoken ID numbers, cards, secrets and health remarks are redacted; people become consistent placeholders such as [PERSON_1] within one conversation. We report exact-match recall per label, not the scorer's overlap match: NATIONAL_ID {{measured.redaction.labels.NATIONAL_ID.recall}}, PAYMENT_CARD {{measured.redaction.labels.PAYMENT_CARD.recall}}, IBAN {{measured.redaction.labels.IBAN.recall}}, SECRET {{measured.redaction.labels.SECRET.recall}}.<!-- END IF -->

## Honest limitations

Pseudonymised data is still personal data, and whoever holds the key can re-link it. We do not claim anonymity. The data is synthetic and templated; real speech is messier. Recipient-mode digests catch accidents only; only `verify --full` checks the signature. The gate checks the form of the output; attack resistance is measured against the kit's attackers, not proven in general. A residual-risk entry reads "not measured" until a measurement exists.
<!-- IF #24 CS-S1 release -->Names outside our gazetteers and indirect health remarks can survive in text; PERSON, ADDRESS and LOCATION are residual risks, not assertions.<!-- END IF -->

## What is next

An optional LLM front end that turns a request into a needs spec, seeing only the request text and the data dictionary, never data values. More scenarios through the same gate and manifest.
