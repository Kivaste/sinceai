"""Pass interface: how detectors plug into the redactor pipeline.

A *pass* looks at one conversation and proposes candidate spans. The pipeline
collects candidates from every pass, resolves overlaps (labels never overlap),
assigns placeholders and substitutes them. Passes never see other conversations.

Contract for lexicon passes (ticket 13, ``pets_release.redactor.lexicon``):

* the subpackage exposes ``passes() -> list[Pass]``; the pipeline calls it when
  building its default pass list (see ``pipeline.default_passes``);
* each pass has a unique ``name`` (used in reports and for deterministic
  ordering), a ``labels`` set it may emit, and ``run(view)`` returning
  ``Candidate`` objects;
* offsets are Python code points into the *untouched* ``Turn.text``, end
  exclusive, and must satisfy ``0 <= start < end <= len(text)``; the pipeline
  rejects (raises on) anything else rather than guessing;
* ``key`` is the value identity used for placeholder numbering inside the
  conversation; leave it ``None`` to use the pipeline's default normalisation of
  the covered text. Fragments of one value split across turns share a key;
* ``priority`` breaks overlaps: higher wins, then longer span, then earlier
  start, then pass name. Structured validator hits use ``PRIORITY_VALIDATED``;
  cue-only structured hits use ``PRIORITY_CUE``; lexicon passes should use
  ``PRIORITY_LEXICON`` unless they have a reason to outrank validators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

PRIORITY_VALIDATED = 300
PRIORITY_CUE = 200
PRIORITY_LEXICON = 100


@dataclass(frozen=True)
class Turn:
    """One utterance of a conversation, in conversation order."""

    turn_id: str
    text: str
    speaker: str = ""
    seq: str = ""


@dataclass(frozen=True)
class Candidate:
    """A proposed span in one turn of the conversation."""

    turn_index: int
    start: int
    end: int
    label: str
    priority: int = PRIORITY_LEXICON
    key: str | None = None
    source: str = ""


@dataclass(frozen=True)
class ConversationView:
    """What a pass sees: the turns of one conversation, in order."""

    conversation_id: str
    turns: tuple[Turn, ...]
    extras: dict = field(default_factory=dict, compare=False, hash=False)


@runtime_checkable
class Pass(Protocol):
    name: str
    labels: frozenset[str]

    def run(self, view: ConversationView) -> Iterable[Candidate]: ...
