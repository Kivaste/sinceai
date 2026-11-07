"""Free-text redactor: typed, numbered placeholders scoped per conversation.

Public seam: ``redact_conversation(conversation_id, turns, passes=None)``.
Pass interface for lexicon passes: see ``pets_release.redactor.passes``.
"""

from .labels import (
    LABELS,
    LEXICON_LABELS,
    PLACEHOLDER_TYPE,
    STRUCTURED_LABELS,
    parse_placeholder,
    placeholder,
)
from .passes import (
    PRIORITY_CUE,
    PRIORITY_LEXICON,
    PRIORITY_VALIDATED,
    Candidate,
    ConversationView,
    Pass,
    Turn,
)
from .pipeline import Redaction, default_passes, redact_conversation
from .structured import StructuredPass

__all__ = [
    "LABELS",
    "LEXICON_LABELS",
    "PLACEHOLDER_TYPE",
    "PRIORITY_CUE",
    "PRIORITY_LEXICON",
    "PRIORITY_VALIDATED",
    "STRUCTURED_LABELS",
    "Candidate",
    "ConversationView",
    "Pass",
    "Redaction",
    "StructuredPass",
    "Turn",
    "default_passes",
    "parse_placeholder",
    "placeholder",
    "redact_conversation",
]
