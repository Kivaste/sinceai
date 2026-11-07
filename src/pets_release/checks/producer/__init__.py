"""Producer-scope gate checks (and the release-scope per-row k).

``CHECKS`` lists every check this submodule contributes to the registry.
"""

from __future__ import annotations

from .kanon import PERSON_K, ROW_K
from .values import KEY_MATERIAL, ORIGINAL_VALUES, REVERSIBLE_HASHES

CHECKS = (KEY_MATERIAL, ORIGINAL_VALUES, PERSON_K, REVERSIBLE_HASHES, ROW_K)

__all__ = ["CHECKS"]
