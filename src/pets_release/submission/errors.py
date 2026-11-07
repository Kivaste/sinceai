"""Content-free refusal for the submission packager."""
from __future__ import annotations


class SubmissionRefused(Exception):
    """The submission was not built. ``code`` is a content-free reason code; nothing was written."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
