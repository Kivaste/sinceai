# Submission description draft

**PRE-FILL at df79ec20538e8f02b3256911fb01d549e5af0ebb** (#103, D61).
Body after the separator: no headings; limit 5,000 characters including spaces.
Not `docs/story/final/description.md`. Refresh measurements after the freeze;
sources and unavailable measurements are in `PRE-FILL-SOURCES.md` and 06.

---

Share data without over-sharing. sinceai's product is the engine: a library and CLI that runs as a self-hosted pipeline step in your infrastructure, from CI, Airflow or dbt. Starting from a sharing scenario, it releases only the fields and detail the purpose needs and attaches a signed privacy manifest. Exit 0 releases; publish only after successful verification. Exit 1 stops on refusal or a failed check; exit 2 stops on bad input/configuration or an unknown state. Source rows and keys stay in-house. The web app is the approval and audit console for one run; a self-hosted REST API is future work.

Data types and risks: HEALTH-S1 shares emergency-visit data with a university research group studying crowding and revisits, under controlled-research trust. The policy-derived field inventory distinguishes direct identifiers, quasi-identifiers, sensitive attributes and free text; it is not detector-accuracy evidence. Removing names leaves linkage through ages, places, times and joins. Original below-k row share is 0.9557179814438992. Attacker-persona rates: not measured (#138 pending at this revision). Search optimises k and utility, not attackers; attacker evaluation is post-hoc.

PETs and why: fields the purpose checks do not need are withheld; keyed pseudonyms preserve necessary joins; generalisation and local suppression reduce detail. Each field justification records its ladder floor, chosen rung and reason. Read the actual rung, not the floor, as the release's detail. Any bounded search result is evidence about the candidates tried, not a global optimum.

Protected output: compare fields and value forms, never raw source rows. Birth date becomes age_band, names and clinical_notes are withheld, and visit_id becomes a keyed pseudonym. Exact rungs and reasons come from field justifications. Protected real-kit row views are human-only, labelled “Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient sees this view.” Agents use hand-made synthetic fixtures.

Measured privacy and utility: producer-attested minimum person-k is 5.0, with below-k person share 0.0 on this manifest's QI set. Separate k on the scenario QIs and all kept catalogued QIs: not measured (#146). k with diagnosis known: not measured (#143). The scorecard misses renamed age_band; linkage zero means no shared QIs left to match on, not measured attack resistance. Overall scorecard utility and composite: not measured (no summary fields). H-U2 after protection is 0.9670714229957352 against 0.90. H-U4 is 0.7952457536539007, with sacrifice floor 0.6. Meeting that floor alone is not meeting 0.90. See 06's targets met / not met table for every purpose check, privacy floor and unavailable measurement; component scores are supporting diagnostics, not a perfect-protection headline.

Scenario and limitations: this release serves its named purpose checks, not individual care, profiling or arbitrary reuse. Pseudonymised data is still personal data; the controller retains the key. Recipient verify re-runs release-scope checks and reports limited verification; person-k remains a producer attestation. Only full verification with inputs and key re-runs producer-scope checks and validates the signature. Missing, errored or failed required checks stop publication. Gate totals and both verify exits are in PRE-FILL-SOURCES; final proof must also demonstrate a fresh refusal, not recycle a success line.

CS-S1 is future work: its strict-gate refusal is an honest limitation (D46), not a released scenario. The CS evaluation path uses typed, numbered placeholders and D37 masking, never realistic fake values: clear labels avoid accidental matches with the shared synthetic population. This is not a CS-S1 recall or release claim. D60's evidence pack is not generated at this revision (#147); its DPO/Findata-shaped purpose, method, risk, utility, residual-risk and reproducibility narrative comes only from the authenticated signed manifest. Legal basis and DPIA are to be supplied by the controller.

The unseen-field export requires full column coverage with both privacy_role and subtype; omission refuses the export. Coverage is not accuracy: no organiser privacy-role or subtype score is claimed from this HEALTH-S1 run.
