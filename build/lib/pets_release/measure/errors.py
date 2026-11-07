"""The measurer's single rejection type: a short content-free reason code."""

from __future__ import annotations


class MeasureRejected(ValueError):
    """A measurement is missing, errored or malformed. `reason` is a short code with no data values."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
