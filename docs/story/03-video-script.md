# Demo video draft (target 1:50, hard limit 2:00)

PREP: rehearse after final review and final-SHA proof, then fill from 06. No old
gate totals, measurements or verification lines are certified by this draft.
All agent-visible recordings and screenshots use hand-made synthetic fixtures.
The human may show protected real-kit rows only under D41 and #117; agents must
not read or screenshot that view. “Before” always means fields and value forms.

## 1. Data types and privacy risks (0:00–0:20)

Screen: HEALTH-S1 recipient and purpose, field inventory with column roles. Show
schema only: direct identifiers, quasi-identifiers, sensitive attributes, free text.
Show original scorecard privacy
{{manifest.measured.privacy.components[component=privacy].before}} and original
below-k row share {{manifest.measured.privacy.components[component=k_below_5_share].before}}.
If unavailable, display “not measured”. Separate attacker-persona rates: not
measured unless the final manifest contains their measured entries.

Narration: “A university research group needs crowding and revisit analyses, not
names or clinical notes. We identify the fields and the linkage risks first.”

## 2. PETs and why (0:20–0:40)

Screen: `fieldJustifications` and `pets`; name the purpose check for each shown
field. Withholding avoids unnecessary sharing; HMAC pseudonyms keep required joins;
generalisation and local suppression reduce quasi-identifier detail.

Narration: “Each field has a ladder floor, a chosen detail level and a reason tied
to the purpose. The manifest records the trade-off, not just the method's name.”

<!-- IF #127 -->Optional screen annotation, not extra running time: parallel scoring
is opt-in; compare byte digests from final-SHA runs at different worker counts.
Do not claim a speed-up without a timed measurement.<!-- END IF -->

## 3. Protected output (0:40–0:58)

Screen: field-level before-to-after map and the protected table schemas; read
exact rungs from the final manifest.

<!-- IF #106 -->Include the D33 lab test-name trade-off only as recorded in the
final field justifications and residual risks, with its measured H-U7 effect.<!-- END IF -->

<!-- IF #117 -->The human can instead show the first approximately ten protected
rows per table from the verified web view, with the mandatory label:
“Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient
sees this view.” Display-time limited verify and manifest-file digests must pass;
no raw rows, row maps or truth/. Agent screenshots still use synthetic fixtures.<!-- END IF -->

Narration: “This is what the recipient receives. Before means the original field's
detail, never a display of a patient's raw record.”

## 4. Measured privacy and utility (0:58–1:27)

Screen: 06's targets met / not met table, with final measurements and explicit
sacrifices. Show per-person minimum k
{{manifest.measured.privacy.components[component=person_k.min].after}} separately
from scorecard row shares. Mention the renamed-age-band blind spot. Overall
scorecard utility and composite: not measured unless final manifest keys exist.

Narration: “Privacy and usefulness are measured on the actual protected tables.
A sacrifice is not a full pass. Missing measurements stay labelled not measured.”

<!-- IF #24 -->Show the SECRET target note in place of part of this segment, not as
extra time: {{manifest.residualRisks[risk=target-recall-secret].description}}.
Narration: “SECRET recall missed its target. Later results are optimistic because
the held-out misses informed the change; the target stays at 0.98.”<!-- END IF -->

## 5. Sharing scenario and limitations, then proof (1:27–1:50)

Screen: recipient/trust level, `fitFor`, `notFitFor`, sacrifices and residual risks;
then actual final-SHA gate totals and fresh CLI outputs of `verify` and
`verify --full`. A deliberate synthetic planted-card candidate must be refused by
the real CLI: show the failed check and count, never a value. If any proof step
fails, show that outcome; do not paste a success line. No verification result is
itself a manifest measurement.

Narration: “Pseudonymised data is still personal data. Recipient verification is
limited; full verification needs the controller's inputs and key. A failed check
refuses the candidate release. Share only what the purpose needs.”

<!-- IF #32 -->Optional closing caption within the same duration: the needs-spec
front end receives request text and the data dictionary, never rows. Enable only
after D39 and final-SHA proof; otherwise list it as future work.<!-- END IF -->
