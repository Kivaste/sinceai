"""CS-S1 release glue (ticket 23). Ticket 21's ``run --scenario CS-S1`` calls ``prepare``.

    from pets_release.cs_s1 import prepare, restore_turn_ids

    prep = prepare(source, keys)       # source: {table: DataFrame dtype=str} of customer_service
    prep.plan                          # final Plan: hand plan, or the turn_id fallback plan
    prep.tables                        # {"conversations", "turns"}: released frames, source row order/index
    prep.spans                         # [Span]; record_id = source turn_id (submission / evaluation)
    prep.turn_id                       # TurnIdDecision: kept, assessment, justification
    prep.gate_context                  # {"source", "identifiers"} for producer-scope gate checks
    prep.gazetteer                     # controller gazetteer (in memory only; never written)

``keys``: ``pets_release.ladders.PseudonymKeys`` bound to the release scope (conversation_id is
one release-scope pseudonym in both tables, by the policy's linked group).

``restore_turn_ids(protected_turns, rowmap)``: the row-map-lineage adapter for CS-U5 when the
fallback pseudonymised ``turn_id`` (D21): report the adapted score and the unmodified kit score,
labelled separately.

Notes for 21 / 16: put ``prep.turn_id.justification`` into ``fieldJustifications`` (it replaces the
plan-derived entry for turns.turn_id); pass ``prep.gate_context`` merged into the gate context.
CS-S1 has no k target, so the contract carries no ``k`` and the k checks are not_applicable
(``applies_to=("contract:k",)``); the writer omits ``quasiIdentifiersBelowK`` (02's schema does not
require it for CS-S1).
"""
from .lineage import LineageError, restore_turn_ids
from .prepare import SCENARIO, TURN_ID_CHECK, Prepared, TurnIdDecision, build_gazetteer, identifiers, prepare

__all__ = ["SCENARIO", "TURN_ID_CHECK", "LineageError", "Prepared", "TurnIdDecision", "build_gazetteer",
           "identifiers", "prepare", "restore_turn_ids"]
