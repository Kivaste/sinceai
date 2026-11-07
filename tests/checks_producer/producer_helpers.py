"""Helpers for producer-check tests (synthetic rows only)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from pets_release.detect.released import released_qis


def with_detected(release, contract, context):
    """``context`` plus ``detected_qi`` (#106) computed by the production detector helper over the release folder's
    tables and the context's source, as the producer context does. A context that already has one, or has no
    source, is returned unchanged (so tests of a missing item still see it missing)."""
    if not isinstance(context, dict) or "detected_qi" in context or not isinstance(context.get("source"), dict):
        return context
    folder = Path(getattr(release, "path", release))
    frames = {p.stem: pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
              for p in sorted(folder.glob("*.csv"))} if folder.is_dir() else {}
    return {**context, "detected_qi": released_qis(context["source"], frames, contract or {})}
