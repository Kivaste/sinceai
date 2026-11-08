# Name, tagline and built-with

**FINAL at c52424c (merged to main cc66ac2)**.
Measurements refer to the final integration release, not this later docs commit.
Submission packaging and independent review remain separate from measurement.
See `06-numbers-to-fill.md` and `PRE-FILL-SOURCES.md`.

Recommended name (limit 80 characters):

> Purpose-First PETs

Recommended tagline (limit 140 characters):

> Share only what the purpose needs, with measured privacy, measured utility and checks the recipient can re-run.

Recommended first five built-with chips: Python, pandas, NumPy, jsonschema, Jinja2.
Evaluation uses pets-eval and scikit-learn; HMAC-SHA256 uses the standard library.
The optional Mistral front end drafts validated policies for human review; it is
not the release engine. Feeding those drafts into the search remains future work.

## Product positioning (D57)

sinceai's product is the engine: a library and CLI running as a self-hosted
pipeline step in the customer's infrastructure (CI, Airflow or dbt). Exit 0
releases; publish only after successful verification. Exit 1 stops on refusal or
a failed check; exit 2 stops on bad input/configuration or an unknown state.
The web app is the approval and audit console for one run. A self-hosted REST API
is future work. Source row values and keys stay in-house; only approved protected
tables and the content-free signed privacy manifest go to the intended recipient.

## Story order (D40)

1. Data types and privacy risks: field inventory and baseline risk.
2. PETs and why: detail ladders, purpose checks and field justifications.
3. Protected output: protected tables and field-level before-to-after changes.
4. Measured privacy and utility: targets met / not met, including unmet targets.
5. Sharing scenario and limitations: recipient, sacrifices, residual risks and proof.

Use “pseudonymised”, not a promise of anonymity. Recipient verification is limited;
producer-scope checks need the controller or auditor. A passed gate proves only its
named checks, not that every possible privacy risk is absent.
