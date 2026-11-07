"""Attacker aggregate JSON -> manifest ``residualRisks`` entries.

Lives in pets_attacker so no pets_release module imports the attacker (boundary rule). The input is the
aggregate file written by ``python -m pets_attacker``; the output holds names, rates and counts only.

    python -m pets_attacker.bridge --attack attack.json --out residual.json

A persona that was not evaluated, or a missing rate, becomes ``not_measured``, never 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pets_release.manifest.canonical import loads_strict
from pets_release.offline import entry_point

from .personas import MAX_SAMPLE, SEED

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}$")
_METHODS = {
    "linkage": ("reidentification_rate", "linkage",
                "share of attacker targets re-identified to the right person (unique-candidate claim)"),
    "attribute-inference": ("attribute_inference_rate", "attribute_inference",
                            "share of attacker targets whose sensitive attribute is inferred correctly"),
}


class BridgeError(ValueError):
    """Attacker output is malformed; no entries are produced."""


_FRAMES = {  # sampling frame of each persona's targets (the denominator), content-free
    "insider": (f"targets: released visits, a seeded random sample (seed {SEED}) of at most {MAX_SAMPLE} when the "
                "release holds more; not a whole-release measurement when capped"),
    "broker": (f"targets: adversary records whose person is in the release; the adversary file is a seeded random "
               f"sample (seed {SEED}) of at most {MAX_SAMPLE} records when it holds more"),
}


def _entry(persona: str, method: str, agg: dict, source: str) -> dict:
    metric, kind, what = _METHODS[method]
    risk = f"{method}-{persona}"
    if not _ID.match(risk):
        raise BridgeError("persona name is not a valid risk id")
    rate = agg.get(metric) if isinstance(agg, dict) else None
    n = agg.get("n_targets") if isinstance(agg, dict) else None
    if not isinstance(agg, dict) or metric not in agg or "n_targets" not in agg:
        raise BridgeError("persona aggregate lacks required keys")
    if rate is not None and (isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 <= rate <= 1):
        raise BridgeError("rate outside [0, 1]")
    ok = agg.get("evaluated") is True and rate is not None and isinstance(n, int) and not isinstance(n, bool) and n >= 1
    if ok:
        r = {"status": "measured", "value": float(rate), "denominator": {"unit": "rows", "n": n}, "source": source}
    else:
        r = {"status": "not_measured", "reason": f"{source}: persona not evaluated or rate unavailable"[:500]}
    frame = _FRAMES["insider" if persona == "insider" else "broker"]
    return {"risk": risk, "kind": kind, "label": None, "rate": r, "description": f"{source}: {what}; {frame}"[:500]}


def residual_risks(attack: dict) -> list:
    """Manifest residualRisks entries (sorted by risk id) for both personas and the red team (#139)."""
    if not isinstance(attack, dict) or not isinstance(attack.get("broker"), dict) or not attack["broker"] \
            or not isinstance(attack.get("insider"), dict):
        raise BridgeError("attacker output needs broker and insider aggregates")
    out = []
    for method in _METHODS:
        for adv, agg in attack["broker"].items():
            out.append(_entry(f"broker-{adv}", method, agg,
                              f"pets_attacker.broker_attack[{adv}]/{_METHODS[method][0]}"))
        out.append(_entry("insider", method, attack["insider"], f"pets_attacker.insider_attack/{_METHODS[method][0]}"))
    out += red_team_risks(attack.get("red_team"))
    return sorted(out, key=lambda r: r["risk"])


# --- #139 red team -------------------------------------------------------------------------------------------------
_REASONS = {  # attacker reason code -> manifest text (the attacker's codes only; anything else is refused)
    "no-aux-table": "no auxiliary person table in the kit",
    "aux-table-malformed": "an auxiliary person table lacks its expected columns",
    "no-field-catalog": "no field catalog to name the sensitive attributes",
    "no-sensitive-released": "no released sensitive attribute",
    "no-target": "no attacker target in the release",
    "no-attack-spec": "no attack spec for the released table",
    "no-link-to-target-table": "the table shares no visit pseudonym with the released visits",
}
_ERROR = re.compile(r"^error:[A-Za-z][A-Za-z0-9_]{0,63}$")
_RED_FRAME = (f"targets: the adversary records of the scenario's attack specs whose person is in the release, each "
              f"source a seeded random sample (seed {SEED}) of at most {MAX_SAMPLE} records")
_AUX = ("auxiliary knowledge: the kit's other-domain person tables and sports rosters joined on full name (worst "
        "case: as if public)")
_LINK = {
    "cross_dataset": ("linkage-redteam-cross-dataset", f"cross-dataset enrichment ({_AUX}), then Fellegi-Sunter "
                                                       "scoring of interval overlaps"),
    "range_aware": ("linkage-redteam-range-aware", "Fellegi-Sunter scoring of interval overlaps (a disagreeing "
                                                   "field lowers a row's score instead of vetoing it)"),
}
_LINK_RATES = (("reidentification_rate", "", "share of targets whose single best-scoring row is theirs"),
               ("guess_rate", "-guess", "1-in-k guess success: expected share of targets found by guessing one of "
                                        "the best-scoring rows"))
_ATTR_FRAME = (f"targets: released visits with a value, a seeded random sample (seed {SEED}) of at most {MAX_SAMPLE}; "
               "the attacker knows each target's exact QIs")
_RED_ATTR = "attribute-inference-redteam"


def _reason(agg) -> str:
    code = agg.get("reason") if isinstance(agg, dict) else None
    if code in _REASONS:
        return _REASONS[code]
    if isinstance(code, str) and _ERROR.match(code):
        return f"attack failed ({code[6:]})"
    raise BridgeError("red team reason is not a known code")


def _red(risk: str, kind: str, agg: dict, metric: str, source: str, what: str) -> dict:
    if not _ID.match(risk):
        raise BridgeError("red team risk id is not valid")
    if not isinstance(agg, dict) or not isinstance(agg.get("evaluated"), bool):
        raise BridgeError("red team aggregate malformed")
    if agg["evaluated"]:
        rate, n = agg.get(metric), agg.get("n_targets")
        if (isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 <= rate <= 1
                or type(n) is not int or n < 1):
            raise BridgeError("red team aggregate malformed")
        r = {"status": "measured", "value": float(rate), "denominator": {"unit": "rows", "n": n}, "source": source}
    else:
        r = {"status": "not_measured", "reason": f"{source}: {_reason(agg)}"[:500]}
    return {"risk": risk, "kind": kind, "label": None, "rate": r, "description": f"{source}: {what}"[:500]}


def red_team_risks(red) -> list:
    """Entries for the red-team block; a missing block gives not_measured entries, never a rate."""
    if red is None:
        red = {name: {"evaluated": False, "reason": "error:RedTeamDidNotRun"} for name in _LINK}
        red["attribute_inference"] = {"evaluated": False, "reason": "error:RedTeamDidNotRun", "columns": {}}
    if not isinstance(red, dict) or set(red) != {*_LINK, "attribute_inference"}:
        raise BridgeError("red team block malformed")
    out = []
    for name, (risk, how) in _LINK.items():
        for metric, suffix, what in _LINK_RATES:
            out.append(_red(risk + suffix, "linkage", red[name], metric, f"pets_attacker.redteam.{name}/{metric}",
                            f"{what}; {how}; {_RED_FRAME}"))
    ai = red["attribute_inference"]
    if not isinstance(ai, dict) or not isinstance(ai.get("columns"), dict) or not isinstance(ai.get("evaluated"), bool):
        raise BridgeError("red team block malformed")
    if not ai["evaluated"] or not ai["columns"]:
        out.append(_red(_RED_ATTR, "attribute_inference", {"evaluated": False, "reason": ai.get("reason")},
                        "inference_rate", "pets_attacker.redteam.attribute_inference",
                        "attribute inference by an attacker who knows a target's QIs"))
        return out
    for col, agg in sorted(ai["columns"].items()):
        src = f"pets_attacker.redteam.attribute_inference[{col}]"
        out.append(_red(f"{_RED_ATTR}-{col}", "attribute_inference", agg, "inference_rate", src + "/inference_rate",
                        "share of targets whose released value the attacker infers right by majority over the "
                        f"best-scoring rows; compare the -baseline entry; {_ATTR_FRAME}"))
        out.append(_red(f"{_RED_ATTR}-{col}-baseline", "attribute_inference", agg, "baseline_rate",
                        src + "/baseline_rate", "population base rate: share of the same targets right by always "
                        f"guessing the release's most common value; {_ATTR_FRAME}"))
    return out


@entry_point
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pets_attacker.bridge")
    ap.add_argument("--attack", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        # #114: strict (duplicate keys, NaN/Infinity refuse): a dropped duplicate aggregate never reaches the manifest
        risks = residual_risks(loads_strict(a.attack.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError) as e:
        print(f"bridge: refused: {type(e).__name__}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"residualRisks": risks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
