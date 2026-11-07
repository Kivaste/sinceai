# Demo video script (target 1:50, hard limit 2:00)

English narration. All screen actions are real CLI or the dashboard rendered from the manifest. No row values on screen. Numbers are double-brace placeholders (see 06). Pre-record from a real release; `<R>` = release folder.
Current-build rule: everything outside a conditional block is true today. `<!-- IF #n ... -->` blocks are used only after that ticket has merged and the claim is verified (06, claims checklist).
Setup: `PETS_KIT`, `PETS_HMAC_KEY` (throwaway), `SOURCE_DATE_EPOCH` set; large terminal font; Wi-Fi visibly off.

| Time | On screen | Narration |
|---|---|---|
| 0:00-0:08 | Terminal: `pets-release run --scenario HEALTH-S1 --out <R> --created <iso> --kit "$env:PETS_KIT"` finishes; gate passed, release written. | "A hospital must share emergency-visit data with a university team. One offline command builds the release and gates it." |
| 0:08-0:20 | `ls <R>`: protected tables and `privacy_manifest.json`, nothing else. `pets-release verify <R>`: `VERIFIED (limited): {{gate.checks.release.count}} release-checked, {{gate.checks.producer.count}} producer-attested`. | "The recipient gets tables and a manifest and can re-run the checks. It says limited, because they do not hold the key." |
| 0:20-0:45 | Dashboard, sections 1-3: field inventory with a reason per column, PET per field, `{{fieldJustifications.withheld.count}}` fields withheld. | "We start from the purpose. Names and clinical notes never leave; age goes out in 10-year bands, arrival time as hour of day." |
| 0:45-1:00 | Dashboard residual-risk section: entries show their measured rate or read "not measured". | "Where we have not measured something, the manifest says so." |
<!-- IF #23 measured numbers --> 
| 0:45-1:00 (replaces row above) | Dashboard before/after: utility per purpose check (`{{measured.utility.after.H-U2}}` ... `{{measured.utility.after.H-U8}}`), privacy score `{{measured.privacy.before.summary.privacy}}` to `{{measured.privacy.after.summary.privacy}}`, B0 / B2-k baselines. | "Utility and risk measured before and after, against the published baselines." |
<!-- END IF -->
| 1:00-1:20 | Terminal: plant a payment-card number in a copy of `<R>`; `pets-release verify <R>.planted` fails, naming check `rescan.payment-cards` and the count, exit 1. | "We do not trust our own output. Plant a card number and the check fails, reporting the check and count, never the value." |
| 1:20-1:38 | Manifest: `exportAssertions.paymentCards: false` beside `assertionEvidence.paymentCards` (check, `{{assertionEvidence.paymentCards.denominator.n}}` cells, `{{assertionEvidence.paymentCards.hits}}` hits). | "Each assertion can only say false and names the check that proved it on this release. If a check fails, no manifest is written." |
| 1:38-1:50 | Limitations in the dashboard, then name and tagline card. | "Pseudonymised data is still personal data, and we say so. Release only what the purpose needs, and prove it." |

## Notes

- Do not say "anonymised", "no identifiers remain", or that a search picked the levels (a hand plan does today).
<!-- IF #26 search merged -->- With search merged, add: "A measured search picks the coarsest level that keeps every purpose check passing." Only if `measured.search.status` is measured.<!-- END IF -->
<!-- IF #24 CS-S1 release -->- With a CS-S1 release: add 5 s of the before/after transcript view (placeholders such as [PERSON_1] consistent within one conversation).<!-- END IF -->
- Show `unseen` detection only if the output is column names and roles.
