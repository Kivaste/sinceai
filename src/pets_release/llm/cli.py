"""`pets-release draft-policy`: plain-language request -> DRAFT scenario policy for human approval.

    pets-release draft-policy --request TEXT --dataset NAME --allow-network [--endpoint URL --model NAME]
                              [--kit PATH] [--out FILE]
    pets-release draft-policy --align-with HEALTH-S1|CS-S1 --allow-network ...   (self-check)

Optional stretch (ADR 0002). The model sees the request text and the data dictionary only. The command never
runs a release. The offline guard stays on for this process; the one request is made by a child process
(`transport.subprocess_transport`), and only when `--allow-network` is given.
Exit 0 draft written; 1 the model output was refused, or with --align-with the draft misses a required
analysis (nothing written); 2 usage error, missing config or unknown state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pets_release.kit import Kit, KitError
from pets_release.llm import alignment
from pets_release.llm.client import LlmError, draft_policy, resolve_config, screen_request
from pets_release.llm.dictionary import DictionaryError, parse_dictionary
from pets_release.llm.draft import DraftRejected
from pets_release.llm.transport import subprocess_transport
from pets_release.llm.vocabulary import VocabularyError


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def _fail(msg: str, code: int = 2) -> int:
    print(f"pets-release draft-policy: {msg}", file=sys.stderr)
    return code


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def main(argv: list[str], *, transport=subprocess_transport) -> int:
    p = _Parser(prog="pets-release draft-policy", description=__doc__.splitlines()[0])
    p.add_argument("--request", help="plain-language data request (who wants what, for which purpose)")
    p.add_argument("--dataset", help="kit dataset name (e.g. health)")
    p.add_argument("--align-with", metavar="SCENARIO", help="self-check against a packaged scenario's required tasks")
    p.add_argument("--endpoint", help="OpenAI-compatible base URL (default: PETS_LLM_ENDPOINT)")
    p.add_argument("--model", help="model name (default: PETS_LLM_MODEL)")
    p.add_argument("--allow-network", action="store_true", help="permit the one LLM request (offline guard stays on)")
    p.add_argument("--kit")
    p.add_argument("--out", help="write the draft here instead of stdout")
    a = p.parse_args(argv)

    if not a.allow_network:
        return _fail("refused: this command sends the request text and data dictionary to the configured "
                     "endpoint; pass --allow-network to permit that one request")
    kit_path = a.kit or os.environ.get("PETS_KIT")
    if not kit_path:
        return _fail("no kit path: pass --kit or set PETS_KIT")
    try:
        kit = Kit(kit_path)
        request, dataset, required = a.request, a.dataset, None
        if a.align_with:
            scenario = kit.scenario(a.align_with)
            required = alignment.required_tasks(scenario)
            dataset = scenario["dataset"]
            request = request or f"{scenario['recipient']}. Purpose: {scenario['purpose']}"
        if not request or not dataset:
            return _fail("--request and --dataset are required (or use --align-with SCENARIO)")
        request = screen_request(request)
        dictionary = parse_dictionary(kit.data_dictionary(), dataset)
        config = resolve_config(a.endpoint, a.model, os.environ)
        draft = draft_policy(request, dictionary, config, transport)
    except (KitError, DictionaryError, VocabularyError, alignment.AlignmentError, LlmError) as e:
        return _fail(str(e))
    except DraftRejected as e:
        return _fail(f"draft refused, nothing written: {e}", 1)

    if required is not None:
        result = alignment.align(draft, required)
        print(f"alignment {a.align_with}: {result['summary']}", file=sys.stderr)
        if result["missing"]:
            return _fail("alignment incomplete: the draft misses required analyses; nothing written", 1)
    text = json.dumps(draft, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if a.out:
        _write_atomic(Path(a.out), text)
        print(f"pets-release draft-policy: DRAFT written to {a.out}; a human must approve it", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0
