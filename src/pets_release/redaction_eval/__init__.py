"""Redaction measurement harness (ticket 14).

The public names are resolved lazily (PEP 562), so importing a scorer submodule such as
``redaction_eval.frame`` does not run the package initialiser's imports of the harness/predictors,
which would reach ``pets_release.redactor``. #85 item 4.1 (scorer isolation).
"""
from importlib import import_module

_EXPORTS = {
    "Frame": "frame",
    "build_frame": "frame",
    "load_clinical_notes_frame": "frame",
    "load_cs_frame": "frame",
    "headline": "harness",
    "run_harness": "harness",
    "regex_predictor": "predictors",
    "whole_turn_predictor": "predictors",
    "CS_S1_TARGET_LABELS": "scoring",
    "check_precision_floor": "scoring",
    "person_twice": "scoring",
    "score_frame": "scoring",
    "HELD_OUT_FRACTION": "split",
    "Split": "split",
    "skeleton": "split",
    "split_by_skeleton": "split",
    "export_spot_check": "spotcheck",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    sub = _EXPORTS.get(name)
    if sub is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{sub}"), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
