"""Trivial predictors used to exercise the harness (not the product redactor)."""
from __future__ import annotations

import re

_IDENTIFYING_LABELS = ("PERSON", "NATIONAL_ID", "EMAIL", "PHONE", "ADDRESS", "IBAN", "PAYMENT_CARD",
                       "ACCOUNT_NUMBER", "IP_ADDRESS", "LICENSE_PLATE", "USERNAME", "SECRET",
                       "DEVICE_ID", "PROPERTY_ID", "URL")


def whole_turn_predictor(text: str) -> list:
    """Predicts the entire turn as every identifying label. Must score ~0 precision."""
    return [{"start": 0, "end": len(text), "label": lab} for lab in _IDENTIFYING_LABELS] if text else []


_REGEXES = (
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){3,6}(?: ?\d{1,4})?\b")),
    ("NATIONAL_ID", re.compile(r"\b\d{6}[-+A]\d{3}[0-9A-Y]\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("URL", re.compile(r"https?://\S+")),
    ("PHONE", re.compile(r"(?<!\d)\+?\d[\d ]{7,13}\d(?!\d)")),
)


def regex_predictor(text: str) -> list:
    out, taken = [], []
    for label, rx in _REGEXES:
        for m in rx.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            out.append({"start": m.start(), "end": m.end(), "label": label})
    return sorted(out, key=lambda s: s["start"])
