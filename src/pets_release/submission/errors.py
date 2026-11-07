"""Content-free refusal for the submission packager."""
from __future__ import annotations


class SubmissionRefused(Exception):
    """The submission was not built. ``code`` is a content-free reason code; nothing was written.
    ``missing`` names the absent target datasets (dataset names only) when ``code`` is ``incomplete``."""

    def __init__(self, code: str, missing=()):
        super().__init__(code)
        self.code = code
        self.missing = tuple(missing)
