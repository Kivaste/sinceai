# Demo video script (target 1:50, hard limit 2:00)

English narration. All screen actions are real CLI or the dashboard rendered from the manifest. No row values on screen: the tool prints counts, names and checks only. Numbers are `{{placeholders}}` (see 06). Pre-record from a real release; `<R>` = release folder.
Setup before recording: `PETS_KIT`, `PETS_HMAC_KEY` (throwaway), `SOURCE_DATE_EPOCH` set; terminal font large; Wi-Fi visibly off in the tray.

| Time | On screen | Narration |
|---|---|---|
| 0:00-0:08 | Terminal: `pets-release run --scenario HEALTH-S1 --out <R> ...` starts and finishes; last lines show gate passed, release written. | "A hospital must share emergency-visit data with a university team. This is one command, offline: it builds the release and gates it." |
| 0:08-0:20 | `ls <R>`: protected tables and `privacy_manifest.json`, nothing else. Then `pets-release verify <R>`: `VERIFIED (limited): {{gate.checks.release.count}} release-checked, {{gate.checks.producer.count}} producer-attested`. | "The recipient gets tables and a manifest. They can re-run the checks themselves. It says limited, because they cannot see the key." |
| 0:20-0:40 | Dashboard open, section 1-3: field inventory with a reason per column; PET per field; `{{fieldJustifications.withheld.count}}` fields withheld. | "We start from the purpose, not the data. Each field is released at the coarsest detail the research questions still allow. Names and clinical notes never leave." |
| 0:40-1:00 | Dashboard before/after: utility per purpose check (`{{measured.utility.after.H-U2}}` ... `{{measured.utility.after.H-U8}}`), singling-out `{{measured.privacy.before.singling_out}}` to `{{measured.privacy.after.singling_out}}`, baselines B0 / B2-k. | "Utility measured before and after. Singling-out drops, and the analyses still answer the same. Blanket k-anonymity would keep only `{{measured.baselines.B2-k.utility_mean}}`." |
| 1:00-1:20 | Terminal: plant a payment-card number in a copy of `<R>`; `pets-release verify <R>.planted` prints refusal naming check `rescan.payment-cards`, count 1, exit 1. | "We do not trust our own output. Plant a card number and the check fails. It reports the check and the count, never the value." |
| 1:20-1:38 | Manifest JSON, `exportAssertions.paymentCards: false` beside `assertionEvidence.paymentCards` (check, `{{assertionEvidence.paymentCards.denominator.n}}` cells, `{{assertionEvidence.paymentCards.hits}}` hits). | "Every assertion can only say false, and names the check that proved it on this release. If a check fails, no manifest is written." |
| 1:38-1:50 | Dashboard limitations section: residual risks, tamper limitation. Closing card with project name and tagline. | "Pseudonymised data is still personal data, and we say so. Release only what the purpose needs, and prove it." |

## Notes

- Cut line if over time: drop the 1:38 beat's JSON zoom, keep the dashboard section.
- CS-S1 (free text) is not in the video; mention it in the description and the pitch. If a CS-S1 release exists on recording day, add 5 s of the before/after placeholder view after 0:40 and cut the baseline shot.
- Do not show the unseen detection output unless it contains only column names and roles.
- Do not say "anonymised" or "no identifiers remain". Say "per-label checks".
