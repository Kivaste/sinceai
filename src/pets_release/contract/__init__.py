"""Release contract generator (ticket 10).

``generate(policy, plan)`` builds the pinned contract. ``digest`` is the SHA-256
hex of its canonical JSON, the same bytes as ``pets_release.manifest.canonical_digest``
when that module is importable.

Policy and plan shapes, and the rung-form seam, are documented on ``generate``.
"""

from pets_release.contract.canonical import canonical_bytes
from pets_release.contract.forms import load_forms
from pets_release.contract.generate import ContractError, digest, generate

__all__ = [
    "ContractError",
    "canonical_bytes",
    "digest",
    "generate",
    "load_forms",
]
