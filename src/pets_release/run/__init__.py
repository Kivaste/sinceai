"""``pets-release run`` (ticket 21): the HEALTH-S1 walking skeleton.

    from pets_release.run import run_release, producer_context, verify_context

``producer_context`` builds the producer-check context for the gate; ``verify_context`` rebuilds the same
context for ``verify --full`` from kit + key + release folder (row maps by pseudonym inversion, never a file).
"""
from pets_release.run.context import DEFAULT_RECIPIENT, producer_context, verify_context
from pets_release.run.pipeline import RunError, RunRefused, run_release

__all__ = ["DEFAULT_RECIPIENT", "RunError", "RunRefused", "producer_context", "run_release", "verify_context"]
