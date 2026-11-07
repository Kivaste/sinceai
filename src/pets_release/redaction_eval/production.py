"""The shipped redactor as an evaluation predictor (follow-up #67).

The evaluator calls ``pets_release.redactor.redact_conversation`` once per conversation, turns in
``seq`` order, so cross-turn behaviour (split values, speaker-aware cues, lexicon passes) is measured.
Lexicon fitting is explicit and development-only: ``dev_gazetteer`` reads gold PERSON spans of the
development frame it is given and nothing else.
"""
from __future__ import annotations

from pathlib import Path

from pets_release.redactor import StructuredPass, Turn, default_passes, redact_conversation

ENTRY_POINT = "pets_release.redactor.redact_conversation"


class ConversationPredictor:
    """Conversation-level predictor: ``predict(conversation_id, turns) -> {turn_id: spans}``."""

    conversation_level = True

    def __init__(self, passes):
        self.passes = list(passes)

    @property
    def pass_names(self) -> list:
        return [p.name for p in self.passes]

    def predict(self, conversation_id: str, turns) -> dict:
        red = redact_conversation(conversation_id, turns, passes=self.passes)
        out = {t.turn_id: [] for t in turns}
        for s in red.spans:
            out[s["record_id"]].append({"start": s["start"], "end": s["end"], "label": s["label"]})
        return out


def shipped_passes(gazetteer=None) -> list:
    """The shipped pass list (``default_passes(require_lexicon=True)``); with a gazetteer, the same passes
    with the gazetteer handed to the lexicon passes."""
    if gazetteer is None:
        return default_passes(require_lexicon=True)
    from pets_release.redactor import lexicon

    return [StructuredPass(), *lexicon.passes(gazetteer)]


def dev_gazetteer(dev_frame):
    """Names learned from development gold PERSON spans only."""
    from pets_release.redactor.lexicon import Gazetteer

    names = sorted({dev_frame.texts[t][s["start"]:s["end"]]
                    for t in sorted(dev_frame.gold) for s in dev_frame.gold[t] if s["label"] == "PERSON"})
    return Gazetteer.from_tables(full_names=names)


def controller_gazetteer(kit_root):
    """The controller's own source tables (customers, agents), as the release would see them."""
    import pandas as pd

    from pets_release.redactor.lexicon import Gazetteer

    root = Path(kit_root)
    cust = pd.read_csv(root / "data/customer_service/customers.csv", dtype=str, keep_default_na=False)
    convs = pd.read_csv(root / "data/customer_service/conversations.csv", dtype=str, keep_default_na=False)
    name_of = dict(zip(cust["customer_id"], cust["full_name"]))
    parties = {}
    for cid, cu, ag in zip(convs["conversation_id"], convs["customer_id"], convs["agent_name"]):
        parties[cid] = [n for n in (name_of.get(cu, ""), ag) if n]
    return Gazetteer.from_tables(
        full_names=sorted(set(cust["full_name"]) | set(convs["agent_name"])),
        cities=sorted(set(cust["city"])), streets=sorted(set(cust["street_address"])), parties=parties)


def production_factory(dev_frame):
    """Default evaluator: the shipped passes with a gazetteer fitted on development names only."""
    return ConversationPredictor(shipped_passes(dev_gazetteer(dev_frame)))


def person_variants(kit_root):
    """The two named PERSON variants the spec asks for."""
    return {
        "controller_gazetteer": lambda dev: ConversationPredictor(shipped_passes(controller_gazetteer(kit_root))),
        "dev_lexicon": production_factory,
    }


def as_turns(frame, ids):
    """Turns of the given ids in conversation order (seq, then turn id)."""
    return [Turn(t, frame.texts[t], speaker=frame.meta(t)[1], seq=frame.meta(t)[0])
            for t in sorted(ids, key=frame.order_key)]
