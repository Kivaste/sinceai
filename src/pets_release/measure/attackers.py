"""Attacker rates for the measured release (#138), from separate attacker child processes.

This package never imports the attacker package and never reads the kit's identity files. This module starts
the attacker and its manifest bridge as offline children of this same source tree (``python -m`` with the
module names below), on the scratch release and its row map chosen by identity, and reads back the bridge's
aggregate ``residualRisks`` entries (names, rates, denominators). Static boundary scan: this file may name the
attacker only in the two module-name constants below, used only in the approved child-launch form (see the
attacker package's boundary guard).

Fail closed: a child that fails, times out or writes a malformed result gives no rates; the caller keeps the
generic linkage and attribute-inference entries as ``not_measured`` with a current, content-free reason.
Never a rate without an attacker run behind it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pets_release.manifest import MANIFEST_FILENAME, loads_strict
from pets_release.offline import child_env

ATTACKER_MODULE = "pets_attacker"
BRIDGE_MODULE = "pets_attacker.bridge"
TABLE = "ed_visits"
GENERIC = ("linkage-attackers", "attribute-inference")  # the run's placeholders, replaced by per-persona entries
TIMEOUT_S = 3600
_SRC = Path(__file__).resolve().parents[2]  # this source tree: the attacker child runs the same revision


class AttackUnavailable(Exception):
    """No attacker rates for this release; the message is our own short, content-free reason."""


def _env() -> dict:
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    return child_env({**os.environ, "PYTHONPATH": os.pathsep.join([str(_SRC), *parts]), "PYTHONUTF8": "1",
                      "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"})


# The two launches below are the only uses of the module-name constants the boundary guard allows
# (``subprocess.run([sys.executable, "-m", <NAME>, ...])``); keep that exact form.
def _attacker(argv: list, work: Path):
    return subprocess.run([sys.executable, "-m", ATTACKER_MODULE, *map(str, argv)], env=_env(), cwd=str(work),
                          capture_output=True, check=False, timeout=TIMEOUT_S)


def _bridge(argv: list, work: Path):
    return subprocess.run([sys.executable, "-m", BRIDGE_MODULE, *map(str, argv)], env=_env(), cwd=str(work),
                          capture_output=True, check=False, timeout=TIMEOUT_S)


def _child(what: str, launch, argv: list, work: Path, log: Path) -> None:
    try:
        proc = launch(argv, work)
    except subprocess.TimeoutExpired:
        raise AttackUnavailable(f"attacker run failed: {what} timed out") from None
    except OSError:
        raise AttackUnavailable(f"attacker run failed: {what} could not start") from None
    with log.open("ab") as f:  # the children print class names and our own short messages only
        f.write(proc.stdout + b"\n--- stderr ---\n" + proc.stderr + b"\n")
    if proc.returncode != 0:
        raise AttackUnavailable(f"attacker run failed: {what} exit {proc.returncode}")


def _rungs(manifest: dict) -> dict:
    """``{table: {released column: rung}}`` from the release's own field justifications."""
    out: dict = {}
    for fj in manifest["fieldJustifications"]:
        if fj["decision"] == "released":
            out.setdefault(fj["table"], {})[fj["outputColumn"]] = fj["rung"]
    return out


_ENTRY_KEYS = {"risk", "kind", "label", "rate", "description"}
_RATE_KEYS = {"measured": {"status", "value", "denominator", "source"}, "not_measured": {"status", "reason"}}
_KINDS = {"linkage", "attribute_inference"}


def _entry(r) -> dict:
    """Closed record: exactly the aggregate keys (names, rate, denominator); any unknown key is refused."""
    if not isinstance(r, dict) or set(r) != _ENTRY_KEYS or r["kind"] not in _KINDS or r["label"] is not None:
        raise AttackUnavailable("attacker bridge output malformed")
    rate = r["rate"]
    if not isinstance(rate, dict) or set(rate) != _RATE_KEYS.get(rate.get("status"), set()):
        raise AttackUnavailable("attacker bridge output malformed")
    if rate["status"] == "measured":
        d, v = rate["denominator"], rate["value"]
        if (not isinstance(d, dict) or set(d) != {"unit", "n"} or d["unit"] != "rows" or type(d["n"]) is not int
                or d["n"] < 1 or type(v) is not float or not 0.0 <= v <= 1.0):
            raise AttackUnavailable("attacker bridge output malformed")
    if not all(isinstance(r[k], str) for k in ("risk", "description")):
        raise AttackUnavailable("attacker bridge output malformed")
    return {k: r[k] for k in sorted(_ENTRY_KEYS)}


def _checked(risks) -> list:
    if not isinstance(risks, list):
        raise AttackUnavailable("attacker bridge output malformed")
    risks = [_entry(r) for r in risks]
    ids = {r["risk"] for r in risks}
    if "linkage-insider" not in ids or not any(i.startswith("linkage-broker-") for i in ids):
        raise AttackUnavailable("attacker bridge output lacks a persona")
    if ids & set(GENERIC):
        raise AttackUnavailable("attacker bridge output malformed")
    return risks


def attacker_risks(*, kit_root, release: Path, rowmaps: dict, work: Path) -> list:
    """Per-persona residualRisks entries for ``release``. Raises AttackUnavailable (content-free reason)."""
    if TABLE not in rowmaps:
        raise AttackUnavailable(f"no attacker target: {TABLE} not released")
    work.mkdir(parents=True)
    log = work / "attacker.log"
    rungs = work / "rungs.json"
    rungs.write_text(json.dumps(_rungs(loads_strict((release / MANIFEST_FILENAME).read_bytes())), sort_keys=True),
                     encoding="utf-8")
    attack, residual = work / "attack.json", work / "residual.json"
    _child("attacker", _attacker, ["--kit", Path(kit_root).absolute(), "--release", release.absolute(), "--label",
                                   "measured", "--out", attack, "--rungs", rungs,
                                   "--rowmap", f"{TABLE}={Path(rowmaps[TABLE]).absolute()}"], work, log)
    _child("bridge", _bridge, ["--attack", attack, "--out", residual], work, log)
    try:
        doc = loads_strict(residual.read_bytes())
    except (OSError, ValueError):
        raise AttackUnavailable("attacker bridge output unreadable") from None
    return _checked(doc.get("residualRisks") if isinstance(doc, dict) else None)


def merge(risks: list, attack: list | None, reason: str | None) -> list:
    """The run's residualRisks with the generic attacker placeholders replaced by the per-persona entries, or,
    without them, kept as ``not_measured`` with the current ``reason``."""
    if attack is not None:
        return sorted([r for r in risks if r["risk"] not in GENERIC] + list(attack), key=lambda r: r["risk"])
    why = f"{reason}; rate unknown"[:500]
    return [dict(r, rate={"status": "not_measured", "reason": why}) if r["risk"] in GENERIC else r for r in risks]
