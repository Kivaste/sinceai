# Questions for TrustED (Discord draft)

Paste from "Hi TrustED" down.

---

Hi TrustED team — a few questions, and one optional note.

**1. Company evaluators.** The published criteria are technical implementation, innovation, impact and presentation, with no weights. Do the company evaluators use any further criteria, or any weighting, beyond those four?

**2. Delivering `pets_submission/`.** The brief asks for outputs in `pets_submission/` in our repo, but row maps must never be published and our repo will be public at submission. Is a separate private repo, with organisers invited, acceptable for the protected tables, row maps, unseen labels and eval redactions? If so, which GitHub handles should we invite?

**3. Hidden checks.** What is the turnaround for the hidden-attacker, unseen-label and eval-redaction checks, and what is the latest time on Saturday we can request them?

**4. Scorecard note (only if useful).** While running `pets-eval` we noticed a few behaviours. Happy to send a short factual note — as help, not criticism:
- span scoring counts any overlap with a gold span as correct;
- row maps are not validated (an empty or partial map can report linkage risk 0);
- scenario IDs are not validated (a wrong ID can raise utility and lower risk);
- some errors exit 0 (a missing path writes an empty scorecard; `check` can exit 0 even when it finds hits);
- on Windows, piping the scorecard can crash on cp1252 (`PYTHONUTF8=1` avoids it).

Thank you — we will follow whatever process you prefer.

— sinceai
