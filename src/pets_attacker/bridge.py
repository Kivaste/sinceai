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

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}$")
_METHODS = {
    "linkage": ("reidentification_rate", "linkage",
                "share of attacker targets re-identified to the right person (unique-candidate claim)"),
    "attribute-inference": ("attribute_inference_rate", "attribute_inference",
                            "share of attacker targets whose sensitive attribute is inferred correctly"),
}


class BridgeError(ValueError):
    """Attacker output is malformed; no entries are produced."""


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
    return {"risk": risk, "kind": kind, "label": None, "rate": r, "description": f"{source}: {what}"[:500]}


def residual_risks(attack: dict) -> list:
    """Manifest residualRisks entries (sorted by risk id) for both personas."""
    if not isinstance(attack, dict) or not isinstance(attack.get("broker"), dict) or not attack["broker"] \
            or not isinstance(attack.get("insider"), dict):
        raise BridgeError("attacker output needs broker and insider aggregates")
    out = []
    for method in _METHODS:
        for adv, agg in attack["broker"].items():
            out.append(_entry(f"broker-{adv}", method, agg,
                              f"pets_attacker.broker_attack[{adv}]/{_METHODS[method][0]}"))
        out.append(_entry("insider", method, attack["insider"], f"pets_attacker.insider_attack/{_METHODS[method][0]}"))
    return sorted(out, key=lambda r: r["risk"])


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
