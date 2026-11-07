"""Scenario policies and hand-picked plans for HEALTH-S1 and CS-S1 (ticket 09)."""
from __future__ import annotations

from . import cs_s1, health_s1
from .model import LADDERS, FieldFloor, PlanError, PolicyError, ScenarioPolicy, validate_plan

_SCENARIOS = {"HEALTH-S1": health_s1, "CS-S1": cs_s1}


def get_policy(scenario_id: str) -> ScenarioPolicy:
    return _SCENARIOS[scenario_id].POLICY  # KeyError for any other scenario


def hand_plan(scenario_id: str) -> list:
    return _SCENARIOS[scenario_id].hand_plan()


__all__ = ["LADDERS", "FieldFloor", "PlanError", "PolicyError", "ScenarioPolicy", "get_policy", "hand_plan", "validate_plan"]
