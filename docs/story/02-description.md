# Submission description

Character count: 4836 of 5,000 (with {{placeholders}} unrendered; re-count after Part B fills the numbers, a rendered number is shorter than its placeholder, so the limit holds).
First two paragraphs are written to work alone for voters. Terms follow GLOSSARY.md. Numbers are {{manifest.key}} placeholders, see 06-numbers-to-fill.md.

---

Share data with a recipient without over-sharing: pets-release releases only what the stated purpose needs, then proves it with checks anyone can re-run offline.

Most "anonymised" data is a claim. Ours is a release plus a privacy manifest where every statement is a named check that ran on the actual files, with the number of cells scanned and the hits found.

## The problem

A data controller has to share data for a purpose: a hospital with a research group, a contact centre with an LLM vendor. Removing names is not enough. Blanket k-anonymity keeps only {{measured.baselines.B2-k.utility_mean}} of the mean utility on HEALTH-S1 and some analyses drop to zero.

## Purpose first

We start from the data request, not the data. The scenario's required analyses (the purpose checks) decide each field's level of detail: the coarsest level at which every purpose check still passes. Fields no purpose check needs are withheld. Each field has a stated reason in the manifest.

## Four patterns

1. Keyed pseudonyms. Identifiers become HMAC-SHA256 tokens under a secret key, so joins survive inside a release but the scorecard's hash-reversal attack recovers nothing. In free text, typed placeholders such as [PERSON_1] stay consistent within one conversation.
2. Fail-closed gate. Every scenario has a closed contract: allowed files, columns and value forms. An independent rescan, a check for surviving original values and a per-person k check run on the candidate release. Any high-severity hit, error or check that did not run means exit 1 and nothing is published. Refusal reports give counts and labels, never values.
3. Privacy manifest. The format can only hold the literal false for each assertion, for example paymentCards or nationalIds. Each assertion is bound to a named check, with its version, denominator and hit count. Claims are per label; we never claim "no identifiers remain". Risks that cannot be zero are listed as residual risks with rates. The manifest is HMAC-signed.
4. Fully offline. No network and no cloud model; sockets are blocked at start-up and the same input, key and creation time give a byte-identical release. We never send data to an AI service to protect it from one.

Verification has two tiers. `pets-release verify <release>` lets the recipient re-run every release-derivable check and always reports "VERIFIED (limited)". `verify --full` with the kit and key re-runs everything, including the signature; a check that cannot run is a failure.

## Two scenarios

HEALTH-S1 (lead): emergency-department visits to a university research group studying crowding and revisits. Names and clinical notes are withheld; age becomes a 5-year band, arrival time month and hour, the visit id a keyed pseudonym. {{inventory.count}} columns were classified, {{fieldJustifications.released.count}} released, {{fieldJustifications.withheld.count}} withheld. Required analyses keep their scores: H-U2 {{measured.utility.after.H-U2}}, H-U4 {{measured.utility.after.H-U4}}, H-U6 {{measured.utility.after.H-U6}}, H-U7 {{measured.utility.after.H-U7}}, H-U8 {{measured.utility.after.H-U8}} (1.0 = same answer as the original). Singling-out falls from {{measured.privacy.before.singling_out}} to {{measured.privacy.after.singling_out}}; the share of rows with k below 5 from {{measured.privacy.before.k_below_5_share}} to {{measured.privacy.after.k_below_5_share}}.

CS-S1: contact-centre transcripts going to an external LLM vendor. Spoken ID numbers, card numbers, secrets and health remarks are redacted; people become consistent placeholders. We report exact-match precision and recall per label (not the scorer's overlap match). Recall on NATIONAL_ID {{measured.redaction.labels.NATIONAL_ID.recall}}, PAYMENT_CARD {{measured.redaction.labels.PAYMENT_CARD.recall}}, IBAN {{measured.redaction.labels.IBAN.recall}}, SECRET {{measured.redaction.labels.SECRET.recall}}; free-text leakage {{measured.redaction.summary.leakage_after}} against {{measured.redaction.summary.leakage_before}} before.

## Honest limitations

Pseudonymised data is still personal data, and whoever holds the key can re-link it. We do not claim anonymity. The data is synthetic and templated; real speech is messier. Names outside our gazetteers and indirect health remarks can survive in text; PERSON, ADDRESS and LOCATION are residual risks with measured recall, not assertions. The gate checks the form of the output; attack resistance is measured against the kit's attackers, not proven in general. Recipient-mode digests catch accidents only; only `verify --full` checks the signature. Languages: Finnish, Swedish, English.

## What is next

An optional LLM front end that turns a data request into a needs spec, seeing only the request text and the data dictionary, never data values. More scenarios through the same gate and manifest.

