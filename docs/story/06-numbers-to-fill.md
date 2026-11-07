# Numbers to fill and claims checklist

Every number in `02`-`05` is a double-brace placeholder holding the manifest path it must come from. Fill from a real release's `privacy_manifest.json` only (Part B of `docs/story-kit/README.md`); never type a number by hand. If the key is `not_measured` or absent, drop the sentence. Path grammar follows `docs/story-kit/README.md`; where a component id contains dots (`summary.privacy`, `person_k.below_k_share`) it is the whole id after `before.` or `after.`.

Rule for the drafts: text outside a conditional block is true for the current build. A block `<!-- IF #n ... -->` is enabled only after its ticket has merged and the verify step below passes.

## Numbers

Source of each path: schema `src/pets_release/manifest/schema.py` (`_MEASURED`, `_FIELD_JUSTIFICATION`); writer `src/pets_release/measure/core.py` (`_utility` tasks, `_privacy` components `summary.composite|privacy|utility` and `risk.<key>`; `measure()` adds person-k components); `src/pets_release/measure/k.py` (`person_k.below_k_share`, `person_k.min`, `person_k.persons`, after only); `src/pets_release/measure/baselines.py` (baselines B0, B2, B2-k; metrics `privacy`, `utility`, `composite`, `worst_reid`, `residual_identifiers`, `task.<id>`).

| Placeholder path | Resolves to | Scenario | Enabled by | Used in |
|---|---|---|---|---|
| `inventory.count` | length of `inventory` | HEALTH-S1 | now | 02, 04, 05 |
| `fieldJustifications.released.count` | entries with `decision` = released | HEALTH-S1 | now | 02, 04 |
| `fieldJustifications.withheld.count` | entries with `decision` = withheld | HEALTH-S1 | now | 02, 03, 04 |
| `gate.checks.release.count` | `gate.checks` with `scope` = release | HEALTH-S1 | now | 03, 04 |
| `gate.checks.producer.count` | `gate.checks` with `scope` = producer | HEALTH-S1 | now | 03, 04 |
| `assertionEvidence.paymentCards.denominator.n` | cells scanned | HEALTH-S1 | now | 03, 04 |
| `assertionEvidence.paymentCards.hits` | hits (0 in a published release) | HEALTH-S1 | now | 03, 04 |
| `measured.utility.after.H-U2` ... `H-U8` | `measured.utility.tasks[task==H-U*].after` | HEALTH-S1 | #23 (ticket 22), #52 | 02, 03, 04, 05 |
| `measured.privacy.before.summary.privacy` | components[`summary.privacy`].before | HEALTH-S1 | #23, #52 | 02, 03, 04, 05 |
| `measured.privacy.after.summary.privacy` | components[`summary.privacy`].after | HEALTH-S1 | #23, #52 | 02, 03, 04, 05 |
| `measured.privacy.after.person_k.below_k_share` | components[`person_k.below_k_share`].after | HEALTH-S1 | #23 | 02, 05 |
| `measured.baselines.B0.worst_reid` | `baselines.rows[baseline==B0, metric==worst_reid].value` | HEALTH-S1 | #23 | 04, 05 |
| `measured.baselines.B2-k.utility` | rows[baseline==B2-k, metric==utility].value | HEALTH-S1 | #23 | 02, 04, 05 |
| `measured.redaction.labels.NATIONAL_ID.recall` | `redaction.labels[label==NATIONAL_ID].recall` (exact match) | CS-S1 | #24 (ticket 23) | 02, 04, 05 |
| `measured.redaction.labels.PAYMENT_CARD.recall`, `IBAN`, `SECRET` | same, other labels | CS-S1 | #24 | 02, 05 |

Dropped from the first draft (no source in the writer): `singling_out`, `k_below_5_share` before/after, `utility_mean`, `measured.redaction.summary.leakage_*`, and "some analyses drop to zero" (re-add only if a `task.<id>` baseline value is 0).

## Claims checklist

| Claim | File | Enabled by | How to verify |
|---|---|---|---|
| Detail levels chosen by a hand-written plan per scenario (true now) | 02 Purpose first, 04 beat 0:30, Q&A | now | `pets-release run --help` accepts only `--plan hand`; manifest `measured.search.status` = `not_measured` |
| A measured search picks the coarsest passing level | 02 Purpose first, 04 beat 0:30 and Q&A | #26 (ticket 25) | `measured.search.status` = `measured`, `measured.search.candidates` > 0 |
| Age in 10-year bands, hour of day (true for the hand plan) | 02 HEALTH-S1, 03 0:20, 04 1:00 | now | `fieldJustifications` entries for `date_of_birth` and `arrival_ts`: read `rung`, not `floor` (expect `age.band10`, `ts.hour_of_day`) |
| Identifiers are HMAC-SHA256 tokens under a secret key (true now); hash-reversal result is quoted only from a measured path | 02 pattern 1, 04 beat 1:00 | now | `exportAssertions.reversibleHashes` and its `producer.unkeyed-hashes` evidence under `verify --full --kit <K> <R>`; no scorecard claim without a measured manifest path |
| Utility and scorecard privacy before/after, baseline comparison | 02, 03 0:45, 04, 05 slide 8 | #23 (ticket 22), #52 | `measured.utility.status` and `measured.privacy.status` = `measured`; paths in the table above resolve |
| CS-S1 release and per-label recall | 02 CS-S1, 03 notes, 04 beats and Q&A, 05 slide 9 | #24 (ticket 23) | `pets-release run --scenario CS-S1 --out <R>` exits 0; `measured.redaction.status` = `measured` |
| Recipient-scoped keys | 02 pattern 1, 04 Q&A | #29 (ticket 28) | `pets-release run --recipient <id> ...` exits 0 (exits 2 in the current build); manifest `release.recipient` set |
| Two-tier verify, limited success line, signature only in `--full` (true now) | 02, 03, 04 | now | `pets-release verify <R>` prints `VERIFIED (limited)`; `verify --full --kit <K> <R>` exits 0 |
| Planted card number is refused (true now) | 03 1:00, 04 1:40 | now | `pets-release verify <R>.planted` exits 1 and names `rescan.payment-cards` |
| Byte-identical offline release (true now) | 02 pattern 4, 04 3:10 | now | run twice with the same `--created`, compare file digests |

## Assumptions

- Part B fills numbers from a real release; paths above must be re-checked against its manifest (the component ids come from the writer code, not from a release).
- The description limit is counted with the conditional text and unrendered placeholders included; rendered numbers are shorter.
