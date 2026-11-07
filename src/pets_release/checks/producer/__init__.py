"""Producer-scope gate checks (and the release-scope per-row k), registered with 04's registry.

Checks: ``producer.person-k``, ``producer.row-k`` (release scope), ``producer.original-values``,
``producer.unkeyed-hashes``, ``producer.key-material``, ``producer.manifest-source-values`` (#149).
Importing this package registers them all.
"""

from __future__ import annotations

from . import kanon, manifest_values, values  # noqa: F401  (registration on import)
