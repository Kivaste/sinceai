"""Attacker rates for the measured release (#138), from separate attacker child processes.

This package never imports the attacker package and never reads the kit's identity files. This module starts
the attacker and its manifest bridge as offline children of this same source tree (``python -m`` with the
module names below), on the scratch release and its row map chosen by identity, and reads back the bridge's
aggregate ``residualRisks`` entries (names, rates, denominators). Static boundary scan: this file may name the
attacker only in the two module-name constants below (see the attacker package's boundary guard).

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


def _child(args: list, work: Path, log: Path) -> None:
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    env = child_env({**os.environ, "PYTHONPATH": os.pathsep.join([str(_SRC), *parts]), "PYTHONUTF8": "1",
                     "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"})
    try:
        proc = subprocess.run([sys.executable, "-m", *map(str, args)], env=env, cwd=str(work), capture_output=True,
                              check=False, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise AttackUnavailable(f"attacker run failed: {args[0]} timed out") from None
    except OSError:
        raise AttackUnavailable(f"attacker run failed: {args[0]} could not start") from None
    with log.open("ab") as f:  # the children print class names and our own short messages only
        f.write(proc.stdout + b"\n--- stderr ---\n" + proc.stderr + b"\n")
    if proc.returncode != 0:
        raise AttackUnavailable(f"attacker run failed: {args[0]} exit {proc.returncode}")


def _rungs(manifest: dict) -> dict:
    """``{table: {released column: rung}}`` from the release's own field justifications."""
    out: dict = {}
    for fj in manifest["fieldJustifications"]:
        if fj["decision"] == "released":
            out.setdefault(fj["table"], {})[fj["outputColumn"]] = fj["rung"]
    return out


def _checked(risks) -> list:
    if not isinstance(risks, list) or not all(isinstance(r, dict) and isinstance(r.get("risk"), str)
                                              and isinstance(r.get("rate"), dict) for r in risks):
        raise AttackUnavailable("attacker bridge output malformed")
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
    _child([ATTACKER_MODULE, "--kit", Path(kit_root).absolute(), "--release", release.absolute(), "--label",
            "measured", "--out", attack, "--rungs", rungs, "--rowmap", f"{TABLE}={Path(rowmaps[TABLE]).absolute()}"],
           work, log)
    _child([BRIDGE_MODULE, "--attack", attack, "--out", residual], work, log)
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
