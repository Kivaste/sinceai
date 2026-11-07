"""Field justifications and ``measured.search`` from the search log (ticket 25).

Every field's reason names the search-log step it comes from, in the form ``search step <n>``:

* released or withheld by an adopted move: the last accepted (non-final) step whose moves set the field, plus,
  if a later step tried to move the field further and was rejected, that step too ("why not coarser");
* never moved: the last rejected step that tried to move it ("why not coarser / why not withheld"), or step 0
  (the start: every permitted field at its floor) when the search never tried it.

The log's ``reason`` texts and the policy reasons are schema names, rung IDs and check IDs only (never a row
value). ``justify`` fails closed: a field whose cited step is missing from the log, or whose adopting step set
a different rung than the plan's, raises ``JustificationError``.
"""
from __future__ import annotations

import math
import re

from pets_release.ladders import WITHHELD, output_column

MAX_REASON = 500


class JustificationError(Exception):
    """Content-free: the plan and the search log disagree."""


def _clip(text: str) -> str:
    return text if len(text) <= MAX_REASON else text[: MAX_REASON - 3] + "..."


def _why(entry: dict) -> str:
    """The log reason without its leading description (``<desc>: rejected (...)`` -> ``rejected (...)``)."""
    r = entry["reason"]
    for tag in ("rejected", "adopted"):
        i = r.find(f": {tag}")
        if i >= 0:
            return r[i + 2:]
    return r


def _describe(entry: dict, key) -> str:
    """The step's description of this field's move (schema names only)."""
    rung = next(m["rung"] for m in entry["moves"] if (m["table"], m["column"]) == key)
    return f"tried {rung}"


def justify(plan: list, log: list, policy) -> list[dict]:
    """Manifest ``fieldJustifications`` (02's shape) for every plan entry, each citing a log step."""
    steps = [e for e in log if e["step"] != "final"]
    if not steps or steps[0]["step"] != 0:
        raise JustificationError("search log has no start step")
    seen = {e["step"] for e in steps}
    out = []
    for e in sorted(plan, key=lambda x: (x["table"], x["column"])):
        key = (e["table"], e["column"])
        touching = [s for s in steps if any((m["table"], m["column"]) == key for m in s["moves"])]
        adopted = [s for s in touching if s["accepted"] and s["step"] != 0]  # step 0 = every field at its floor
        last_adopt = adopted[-1] if adopted else None
        if last_adopt is not None:
            rung = next(m["rung"] for m in last_adopt["moves"] if (m["table"], m["column"]) == key)
            if rung != e["rung"]:
                raise JustificationError(f"{key[0]}.{key[1]}: plan rung differs from its adopting log step")
            later = [s for s in touching if not s["accepted"] and s["step"] > last_adopt["step"]]
            text = f"search step {last_adopt['step']}: {e['rung']} adopted ({_why(last_adopt)})"
            if later:
                lr = later[-1]
                text += f"; search step {lr['step']}: {_describe(lr, key)}, {_why(lr)}"
        elif e["rung"] != e["floor"]:
            raise JustificationError(f"{key[0]}.{key[1]}: off its floor with no adopting log step")
        else:
            rejected = [s for s in touching if not s["accepted"]]
            floor_reason = policy.floors[key].reason
            if e["rung"] == WITHHELD and rejected:
                lr = rejected[-1]
                text = (f"search step {lr['step']}: withheld at the policy floor; {_describe(lr, key)}, "
                        f"{_why(lr)} ({floor_reason})")
            elif e["rung"] == WITHHELD:
                text = f"search step 0: withheld at the policy floor ({floor_reason})"
            elif rejected:
                lr = rejected[-1]
                text = (f"search step {lr['step']}: kept at floor {e['rung']}; {_describe(lr, key)}, {_why(lr)} "
                        f"({floor_reason})")
            else:
                text = f"search step 0: released at floor {e['rung']}; no coarser move tried ({floor_reason})"
        for n in _cited(text):
            if n not in seen:
                raise JustificationError(f"{key[0]}.{key[1]}: cites a step missing from the log")
        released = e["rung"] != WITHHELD
        out.append({"table": e["table"], "column": e["column"],
                    "outputColumn": output_column(e) if released else None,
                    "decision": "released" if released else "withheld",
                    "rung": e["rung"], "floor": e["floor"], "reason": _clip(text), "source": "search"})
    return out


def _cited(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"search step (\d+)", text)]


def _measured_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def search_summary(log: list, stats: dict) -> dict:
    """``measured.search``: one point per non-final candidate (risk = worst component, utility = mean score),
    the candidate count and the accepted count. Risk and utility are rounded to 6 decimals, like the manifest's
    other shares: a raw float's long digit run would read as an identifier to the manifest identifier-shape
    scan (#61).

    Fails closed (#133): an unknown figure is never published as a measured 0.0. A step with an empty or
    non-numeric risk map, with an empty score map, or accepted with a missing score, raises
    ``JustificationError``. A rejected candidate with a check the search could not score (not answerable or
    error) has an unknown utility: ``null``, never a stand-in 0.0."""
    steps = [e for e in log if e["step"] != "final"]
    points = []
    for e in steps:
        risk = list(e["risk"].values())
        if not risk or not all(_measured_number(v) for v in risk):
            raise JustificationError("measured.search: a search step has no measured risk")
        if not e["scores"]:
            raise JustificationError("measured.search: a search step has no purpose scores")
        if e["accepted"] and any(v is None for v in e["scores"].values()):
            raise JustificationError("measured.search: an accepted search step has a missing purpose score")
        scores = list(e["scores"].values())
        utility = None if any(v is None for v in scores) else round(sum(map(float, scores)) / len(scores), 6)
        points.append({"step": e["step"], "risk": round(float(max(risk)), 6),
                       "utility": utility, "accepted": bool(e["accepted"])})
    return {"status": "measured",
            "source": "search log in the scoring folder (search_log.jsonl): one candidate per point",
            "candidates": len(steps), "accepted": sum(1 for p in points if p["accepted"]),
            "boundReached": bool(stats.get("bound_reached", False)), "points": points}
