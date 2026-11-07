"""Release contract generator (ticket 10).

``generate(policy, plan)`` builds the contract from ticket 09's ``ScenarioPolicy`` and a final
Plan, with forms from ticket 07 and the digest from ticket 02. See ``generate`` for the shape.

    python -m pets_release.contract    # contracts for both hand plans (schema names and forms only)
"""

from pets_release.contract.generate import ContractError, digest, generate

__all__ = ["ContractError", "digest", "generate"]
