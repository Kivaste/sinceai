# LLM front end (optional stretch, ticket 31)

`pets-release draft-policy` turns a plain-language data request into a **DRAFT** scenario policy for a human
to approve. It never runs a release and is not on the `run` path. It ships only if the Sat 14:00 go/no-go passes
(ADR 0002).

```
pets-release draft-policy --request "A university group wants length of stay and revisit rates" \
    --dataset health --allow-network [--endpoint URL --model NAME] [--kit PATH] [--out draft.json]
pets-release draft-policy --align-with HEALTH-S1 --allow-network      # self-check, see below
```

## What the model sees

Only the request text, the data dictionary (table and column names, roles and subtypes from
`docs/DATA_DICTIONARY.md`; descriptions are not sent) and the fixed list of analysis types. The prompt builder takes a typed
`DataDictionary`; it has no parameter that can carry a table, and the `llm` package imports no table library
(both are tested). The request is also screened: emails, ID-shaped strings and long digit runs are refused.

## Provider (your choice)

Any OpenAI-compatible chat-completions endpoint. Configure with flags or environment:

| setting | flag | env |
|---|---|---|
| endpoint (base URL, `/chat/completions` is appended) | `--endpoint` | `PETS_LLM_ENDPOINT` |
| model | `--model` | `PETS_LLM_MODEL` |
| API key (optional for local servers) | none | `PETS_LLM_API_KEY` |

Suggested default: a local or self-hosted server (llama.cpp `llama-server`, Ollama's `/v1`), so even the
request text stays on your machine. Mistral's API is the second suggestion. The key is read from the
environment only, passed to the sender child through its environment (not argv), and never printed.

## Offline guard

The guard stays on. Without `--allow-network` the command exits 2 and sends nothing. With it, the single
request is made by a child process (`pets_release.llm.sender`, standard library only, no redirects) whose
environment lacks the offline flag; the parent process keeps its socket block, and no other subcommand is
affected.

## Output and validation

The model's answer must be one JSON object that passes a closed JSON Schema (unknown keys fail), then is
checked against the dictionary and the vocabulary: unknown tables, columns or analysis types are refused (exit 1,
nothing written, error text names a schema path or list index, never a value). Accepted drafts carry
`"status": "draft"`, the dataset, the model name and the SHA-256 of the request.

Fields: `recipient`, `trustLevel` (`public|contractual|controlled_research|internal`), `purposeChecks`
(`id` from the vocabulary: H-U2, H-U4, H-U6, H-U7, H-U8, CS-U1, CS-U3, CS-U4, CS-U5, each with a reason),
`fieldsNeeded` (`table`, `column`, `detail` from `exact|pseudonymised|generalised|redacted|aggregate`, `reason`).
The vocabulary is pinned by a test to the purpose checks of the packaged scenario policies.

## Alignment self-check

`--align-with HEALTH-S1|CS-S1` builds the request from the kit scenario's recipient and purpose and prints
`alignment <ID>: recovered N of M required analyses (K extra)` on stderr, comparing the drafted purpose checks
to the scenario's official required tasks. It is content-free. If any required analysis is missing the command exits 1 and writes nothing (stdout and
`--out` alike); it exits 0 and writes the draft only when every required analysis is recovered.

## Hardening (review round 2)

- **No free-text metadata is transmitted.** The dictionary's description column is ignored. Only identifier-shaped
  table and column names and closed-list roles and subtypes go out; `ColumnInfo` has no description field.
- **Call-site type enforcement.** `TableInfo` and `DataDictionary` require real `ColumnInfo` / `TableInfo` children, and
  `build_messages` re-validates a fresh copy built from real instances before anything is serialised.
- **Short API keys are refused** (fewer than 6 characters, exit 2, nothing sent); every other key is screened against
  the draft in raw, hex and base64 forms.
- **Not yet consumable by `run`:** the draft is a reviewable artefact. The pipeline loads packaged policies only
  (`pets_release.policy.get_policy`) and has no `search` command, so a draft cannot be run without changes outside
  `llm/`.

## Hardening (review round 1)

- **Dictionary metadata is allowlisted.** Table and column names must be plain identifiers; role and subtype must be in
  the closed lists in `llm/dictionary.py` (the kit taxonomy names). A name, role or subtype outside them fails closed
  (exit 2, nothing sent). Descriptions are not sent at all (round 2). These checks run when the typed objects are built, so no construction
  path bypasses them.
- **No credentials in a draft.** A draft containing the API key (raw, hex, base64) or a credential-shaped token
  (`sk-`, bearer, JWT, cloud and VCS tokens, private-key header, 40+ hex) is refused with exit 1 and nothing written,
  on stdout and `--out` alike.
- **Reply size caps.** The sender reads at most 256 KB (`PETS_LLM_MAX_RESPONSE`, bytes) before buffering; the client
  also rejects replies over 256 KB and model text over 64 K characters before JSON parsing.
