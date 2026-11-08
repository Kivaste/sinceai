"""Does a short text (a name, key or path component) look like an identifier? For masking diagnostics only.

Uses the same independent detectors as the release rescans (``labels.LABEL_CHECKS``). Any high or low hit counts.
"""
from __future__ import annotations

import functools
import re

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$")
_DIGIT_RUN = re.compile(r"[0-9]{3,}")


@functools.lru_cache(maxsize=4096)
def flagged(text: str) -> bool:
    from pets_release.checks.cells.labels import LABEL_CHECKS

    return any(any(finder(text)) for _label, finder in LABEL_CHECKS.values())


def safe_name(text) -> bool:
    """True if ``text`` may appear verbatim in a diagnostic: plain name shape, no 3+ digit run, no detector hit."""
    return isinstance(text, str) and bool(_SAFE_NAME.match(text)) and not _DIGIT_RUN.search(text) and not flagged(text)
