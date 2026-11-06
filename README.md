# sinceai: purpose-first PETs

Team project for the **TrustED PETs Transformer** challenge at Since AI Hackathon 2026 (Turku, 6–8 Nov 2026).
**Submission deadline: Sunday 8 Nov, 10:00 EET (fixed), on sinceai.app.**

> Release only what the purpose needs, at the coarsest detail that still serves it, and prove both the privacy and the utility.

## Documentation

| Doc | What's in it |
|---|---|
| [docs/challenge.md](docs/challenge.md) | The challenge, the data package, deadlines, how judging works |
| [docs/concept.md](docs/concept.md) | Our angle: purpose-first data minimisation, and why it differentiates |
| [docs/tool-spec.md](docs/tool-spec.md) | The tool: pipeline, components, inputs and outputs |
| [docs/evaluation-strategy.md](docs/evaluation-strategy.md) | How we measure ourselves without overfitting: scoreboard, own attacker, hidden checks |
| [docs/build-plan.md](docs/build-plan.md) | Sequencing, checkpoints, workstreams, risks |
| [docs/decisions.md](docs/decisions.md) | What's decided, what's proposed, what's still open |
| [docs/setup.md](docs/setup.md) | Local environment, `pets-eval` toolkit, repo hygiene |
| [GLOSSARY.md](GLOSSARY.md) | Shared vocabulary. Use these terms in code, docs and the demo. |

## Repo layout (current)

```
Briefs/                 challenge briefs + the data package (NOT to be committed; see docs/setup.md)
docs/                   planning and specs
GLOSSARY.md             project vocabulary
.venv/                  local Python env with pets-eval installed (not committed)
```
