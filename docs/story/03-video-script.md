# Demo video script (target 1:50, hard limit 2:00)

**FINAL at c52424c (merged to main cc66ac2)**.
Final numbers below belong to this release only, not the recorded demo pin
`5b260ec`. The existing video stays on that pin (D55): never relabel its captures
with these numbers. A new recording must use the matching final release and proof.
No video capture or refusal is certified by this text.
All agent-visible recordings and screenshots use hand-made synthetic fixtures.
The human may show protected real-kit rows only under D41 and #117; agents must
not read or screenshot that view. “Before” always means fields and value forms.

## 1. Data types and privacy risks (0:00–0:20)

Screen: HEALTH-S1 recipient and purpose, field inventory with column roles. Show
schema only: direct identifiers, quasi-identifiers, sensitive attributes, free text.
For a final-release capture use its measured dashboard. k figures are now final
and may be shown: minimum person-k 5 and below-k share 0 across 24,204 persons on
both declared QI sets. Persona linkage rates are measured; see 06 for their scope.

Narration: “A university research group needs crowding and revisit analyses, not
names or clinical notes. We identify the fields and the linkage risks first.”

## 2. PETs and why (0:20–0:40)

Screen: `fieldJustifications` and `pets`; name the purpose check for each shown
field. Withholding avoids unnecessary sharing; HMAC pseudonyms keep required joins;
generalisation and local suppression reduce quasi-identifier detail.

Narration: “Each field has a ladder floor, a chosen detail level and a reason tied
to the purpose. The manifest records the trade-off, not just the method's name.”

Do not add an unmeasured parallel-search speed claim.

## 3. Protected output (0:40–0:58)

Screen: field-level before-to-after map and the protected table schemas; read
exact rungs from the final manifest.

The recording remains pinned: do not describe a later lab-test-name decision as
part of that recording. Description/deck use the final manifest's actual rung:
lab_results.test_name withheld, los_minutes in 30-minute bins.

The human can instead show the first approximately ten protected
rows per table from the verified web view, with the mandatory label:
“Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient
sees this view.” Display-time limited verify and manifest-file digests must pass;
no raw rows, row maps or truth/. Agent screenshots still use synthetic fixtures.

Narration: “This is what the recipient receives. Before means the original field's
detail, never a display of a patient's raw record.”

## 4. Measured privacy and utility (0:58–1:27)

Screen for a final capture: privacy 0.1716 → 1.0; mean utility 1.0 → 0.9188;
scorecard linkage 0.5697 → 0 and below-k=5 row share 0.9557 → 0. Show the
renamed-age_band blind spot and person-k separately. H-U2 0.9195 is an accepted
30-minute-bin detail sacrifice, still above 0.90; H-U4 0.7952 is below the original
0.90 target, accepted at floor 0.6. H-U6/H-U7/H-U8: 0.9462/0.9827/0.9504.
Red-team unique re-identifications: 0 within the tested attack frames, not a
universal guarantee. Do not relabel old captures with these results.

Narration: “Privacy and usefulness are measured on the actual protected tables.
A sacrifice is not a full pass. Missing measurements stay labelled not measured.”

CS-S1 is out of the video (D46). Its strict-gate refusal belongs in Q&A, not a
fabricated CS release or an unsupported recall figure.

## 5. Sharing scenario and limitations, then proof (1:27–1:50)

Screen: recipient/trust level, `fitFor`, `notFitFor`, sacrifices and residual risks.
For the final release, disclose diagnosis-known below-k=5 person share 73.6%,
diagnosis inference lift 2.1351x (no bound), and los_minutes lift 1.6894x (bound
2.0x). These are population lifts, distinct from sampled attacker rates. Then show
that recorded build's actual gate totals and fresh CLI outputs of `verify` and
`verify --full`. A deliberate synthetic planted-card candidate must be refused by
the real CLI: show the failed check and count, never a value. If any proof step
fails, show that outcome; do not paste a success line. No verification result is
itself a manifest measurement. Final proof: 42/42 checks pass, 0 not applicable;
release and both verify tiers exit 0. A fresh planted-violation refusal is not
demonstrated by that measured proof; record it separately, never invent it.

Narration: “Pseudonymised data is still personal data. Recipient verification is
limited; full verification needs the controller's inputs and key. A failed check
refuses the candidate release. Share only what the purpose needs.”

Closing caption, within the same duration: “Self-hosted pipeline engine; the web
app is the approval and audit console. Publish only after exit 0 and successful
verification; either nonzero exit stops the pipeline.” Source rows and keys stay
in-house. REST API: future work. Evidence-pack export is available (#147);
legal basis and DPIA are controller-supplied, never inferred by the tool.
