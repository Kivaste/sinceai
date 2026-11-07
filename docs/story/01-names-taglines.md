# Name, tagline and built-with draft

PREP for #103, not final submission text. Finalisation waits for the final review
and fresh proof on the exact final SHA; see `06-numbers-to-fill.md`.

Recommended name (limit 80 characters):

> Purpose-First PETs

Recommended tagline (limit 140 characters):

> Share only what the purpose needs, with measured privacy, measured utility and checks the recipient can re-run.

Recommended first five built-with chips: Python, pandas, NumPy, jsonschema, Jinja2.
Evaluation uses pets-eval and scikit-learn; HMAC-SHA256 uses the standard library.
Do not list a model provider as a shipped dependency without #32 and final-SHA proof.

## Story order (D40)

1. Data types and privacy risks: field inventory and baseline risk.
2. PETs and why: detail ladders, purpose checks and field justifications.
3. Protected output: protected tables and field-level before-to-after changes.
4. Measured privacy and utility: targets met / not met, including unmet targets.
5. Sharing scenario and limitations: recipient, sacrifices, residual risks and proof.

Use “pseudonymised”, not a promise of anonymity. Recipient verification is limited;
producer-scope checks need the controller or auditor. A passed gate proves only its
named checks, not that every possible privacy risk is absent.
