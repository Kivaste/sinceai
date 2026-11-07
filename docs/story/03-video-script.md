# Demo video script (target 1:50, hard limit 2:00)

English narration. All screen actions are real CLI or the dashboard rendered from the manifest. No row values on screen. HEALTH-S1 numbers are from the real story-kit release (sources in 06). Pre-record from that release; `<R>` = release folder.
Current-build rule: everything outside a conditional block is true today. `<!-- IF #n ... -->` blocks are used only after that ticket has merged and the claim is verified (06, claims checklist).
Setup: `PETS_KIT`, `PETS_HMAC_KEY` (throwaway), `SOURCE_DATE_EPOCH` set; large terminal font; Wi-Fi visibly off.

| Time | On screen | Narration |
|---|---|---|
| 0:00-0:08 | Terminal: `pets-release run --scenario HEALTH-S1 --out <R> --created <iso> --kit "$env:PETS_KIT"` finishes; gate passed, release written. | "A hospital must share emergency-visit data with a university team. One offline command builds the release and gates it." |
| 0:08-0:20 | `ls <R>`: protected tables and `privacy_manifest.json`, nothing else. `pets-release verify <R>`: `VERIFIED (limited): 36 release-checked, 4 producer-attested`. | "The recipient gets tables and a manifest and can re-run the checks. It says limited, because they do not hold the key." |
| 0:20-0:45 | Dashboard, sections 1-3: field inventory with a reason per column, PET per field, 37 fields withheld. | "We start from the purpose. Names and clinical notes never leave; age goes out in 10-year bands, arrival time as hour of day." |
| 0:45-1:00 | Dashboard after suppression: H-U2 0.9908, H-U4 0.7952, H-U6 0.9462, H-U7 0.9933, H-U8 0.9505; per-person k minimum 5. Do not present the scorecard privacy score without its age_band caveat. | "We measure the release after suppression. H-U4 loses utility; per-person k is at least five. Unmeasured risks stay labelled." |
| 1:00-1:20 | Terminal: plant a payment-card number in a copy of `<R>`; `pets-release verify <R>.planted` fails, naming check `rescan.payment-cards` and the count, exit 1. | "We do not trust our own output. Plant a card number and the check fails, reporting the check and count, never the value." |
| 1:20-1:38 | Manifest: `exportAssertions.paymentCards: false` beside `assertionEvidence.paymentCards` (check, 1,106,994 cells, 0 hits). | "Each assertion can only say false and names the check that proved it on this release. If a check fails, no manifest is written." |
| 1:38-1:50 | Limitations in the dashboard, then name and tagline card. | "Pseudonymised data is still personal data, and we say so. Release only what the purpose needs, and prove it." |

## Notes

- Do not say "anonymised", "no identifiers remain", or that a search picked the levels (a hand plan does today).
<!-- IF #26 search merged -->- With search merged, add: "A measured search picks the coarsest level that keeps every purpose check passing." Only if `measured.search.status` is measured.<!-- END IF -->
<!-- IF #24 CS-S1 release -->- With a CS-S1 release: add at most 5 s of aggregate per-label recall, never transcript rows.<!-- END IF -->
- Show `unseen` detection only if the output is column names and roles.
