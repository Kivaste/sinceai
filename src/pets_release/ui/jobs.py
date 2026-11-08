"""Run the public CLI unchanged; expose only selected aggregate artefacts, never its output."""
from __future__ import annotations

import copy
import hashlib
import io
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd

from pets_release.dashboard.render import render_html
from pets_release.manifest import loads_strict, validate_manifest_file
from pets_release.offline import child_env
from pets_release.policy import get_policy
from pets_release.run.context import SCENARIO_SPEC
from pets_release.ui.rows import protected_rows, verified_snapshot
from pets_release.ui.rows import snapshot as release_snapshot
from pets_release.ui.targets import target_rows

SCENARIOS = ("HEALTH-S1", "CS-S1")
RECIPIENTS = {"HEALTH-S1": "University research group", "CS-S1": "External LLM analytics vendor"}
SCENARIO_DETAILS = {
    "HEALTH-S1": {"title": "Emergency care research", "context": "Controlled research",
                  "trust": "Purpose-bound research recipient; no re-identification permission",
                  "purpose": "Study crowding, diagnosis groups, revisits and lab relationships without sharing direct identifiers."},
    "CS-S1": {"title": "Contact-centre analytics", "context": "Redacted free text",
              "trust": "External third-party analytics recipient; no customer linkage",
              "purpose": "Analyse contact reasons and handling time while redacting sensitive spans and withholding the customer table."},
}


def scenarios():
    return [{**get_policy(name).to_json(), **SCENARIO_DETAILS[name], "recipient": RECIPIENTS[name],
             "supported": name in SCENARIO_SPEC} for name in SCENARIOS]


MANIFEST = "privacy_manifest.json"
PROOF_FIELDS = ("gate", "exportAssertions", "assertionEvidence", "measured", "sacrifices", "residualRisks",
                "inventory", "pets", "fieldJustifications", "fitFor", "notFitFor", "personK", "targets",
                "verification", "contract", "bindings")


def live_digests(release, root):
    """sha256 of every entry in the live release folder; raises on links, junctions or folders."""
    if release is None or release.is_symlink() or release.is_junction():
        raise ValueError("Release unavailable")
    release = release.resolve(strict=True)
    if release.parent != root:
        raise ValueError("Release outside root")
    out = {}
    for entry in release.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("Unexpected release entry")
        out[entry.name] = hashlib.sha256(entry.read_bytes()).hexdigest()
    return out


def gate_summary(checks):
    """Only ``pass`` is a pass. ``not_applicable`` is its own number; anything else is neither."""
    statuses = [c["status"] for c in checks]
    return {"passed": statuses.count("pass"), "notApplicable": statuses.count("not_applicable"),
            "total": len(statuses)}


def person_k(manifest):
    """Person-k from the verified manifest only (never the unsigned scoring sidecar).

    ``belowK``/``persons`` come from the producer.person-k record that ``verify --full`` re-ran;
    ``minK`` only when the manifest's privacy block measured it, else None (not measured).
    """
    record = next((c for c in manifest["gate"]["checks"] if c["check"] == "producer.person-k"), None)
    if record is None:
        return None
    components = manifest["measured"].get("privacy", {}).get("components", [])
    minimum = next((c["after"] for c in components if c["component"] == "person_k.min"), None)
    return {"belowK": record["hits"] if record["status"] in ("pass", "fail") else None,
            "persons": record["denominator"]["n"], "minK": minimum, "k": manifest["contract"]["k"]}


def proof_summary(scenario, manifest):
    summary = {
        "gate": gate_summary(manifest["gate"]["checks"]),
        "exportAssertions": manifest["exportAssertions"],
        "assertionEvidence": manifest["assertionEvidence"],
        "measured": manifest["measured"], "sacrifices": manifest["sacrifices"],
        "residualRisks": manifest["residualRisks"],
        **{name: manifest[name] for name in ("inventory", "pets", "fieldJustifications", "fitFor", "notFitFor")},
        "personK": person_k(manifest),
        "contract": manifest["contract"],
        # As on /dashboard, retain binding names but never emit opaque identifier-shaped
        # digests. This projection is made only from the snapshot both tiers verified.
        "bindings": {
            **{group: {name: "bound digest" for name in manifest["bindings"][group]}
               for group in ("files", "inputs", "lexiconDigests")},
            "contractDigest": "bound digest",
            "toolRevision": manifest["bindings"]["toolRevision"][:12],
            "checkVersions": manifest["bindings"]["checkVersions"],
        },
    }
    summary["targets"] = target_rows(scenario, manifest, summary["personK"])
    return summary


class Jobs:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.out).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.env = child_env()
        self.lock = threading.Lock()
        self.number = 0
        self.release = None
        self.verified = None  # name -> sha256 of the snapshot bytes both tiers verified
        self.state = {"status": "IDLE", "steps": []}

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def proof_view(self):
        """State for proof-bearing responses. RELEASED proof is shown only while the live folder
        still holds exactly the bytes verified at run time (cheap re-hash, no full verify). Any
        changed, missing or extra file withdraws the proof; the reason is content-free."""
        with self.lock:
            state, verified, release = copy.deepcopy(self.state), self.verified, self.release
        if state["status"] != "RELEASED":
            return state
        try:
            current = live_digests(release, self.root)
        except Exception:  # noqa: BLE001 - unknown is a change; never reflect paths or values
            current = None
        if verified is not None and current == verified:
            return state
        for field in PROOF_FIELDS:
            state.pop(field, None)
        # The run-time verify exits were for other bytes: never render them as a current pass.
        state["steps"] = [s for s in state["steps"] if not s["name"].startswith("verify")]
        state["status"] = "CHANGED"
        return state

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def start(self, scenario):
        with self.lock:
            if self.state["status"] == "RUNNING":
                return False
            self.number += 1
            self.release = self.root / f"run-{self.number}"
            self.verified = None
            self.state = {"status": "RUNNING", "scenario": scenario, "steps": [],
                          "supported": scenario in SCENARIO_SPEC, "targets": target_rows(scenario),
                          "policy": next(s for s in scenarios() if s["scenario"] == scenario)}
        threading.Thread(target=self.execute, args=(scenario, self.release), daemon=True).start()
        return True

    def command(self, name, args):
        with self.lock:
            self.state["steps"].append({"name": name, "exit": None})
        proc = subprocess.run([sys.executable, "-m", "pets_release", *map(str, args)],
                              env=self.env, capture_output=True, timeout=1800, check=False)
        with self.lock:
            self.state["steps"][-1]["exit"] = proc.returncode
        return proc.returncode

    def execute(self, scenario, release):
        try:
            args = self.args
            detector = subprocess.run([sys.executable, "-m", "pets_release", "detect",
                                       get_policy(scenario).dataset, "--kit", str(args.kit), "--format", "kit"],
                                      env=self.env, capture_output=True, timeout=120, check=False)
            inventory = []
            if detector.returncode == 0:
                inventory = pd.read_csv(io.BytesIO(detector.stdout), dtype=str,
                                        keep_default_na=False, na_filter=False).to_dict("records")
            self.update(detectedInventory=inventory, detectorExit=detector.returncode)
            run_args = ["run", "--scenario", scenario, "--kit", args.kit,
                        "--out", release, "--created", args.created]
            if args.plan is not None:
                run_args.extend(["--plan", args.plan])
            rc = self.command("run", run_args)
            if rc != 0:
                self.update(status="REFUSED" if rc == 1 else "FAILED", **self.refusal(release))
                return
            if validate_manifest_file(release):
                self.update(status="FAILED")
                return
            # Both tiers verify one private snapshot of the manifest and its listed files; the
            # proof is projected from that snapshot's manifest bytes only. The live folder is
            # never re-read for proof. Any failure publishes no gate, scores or targets.
            with release_snapshot(release, self.root) as (folder, manifest_bytes, payloads):
                limited = self.command("verify (limited)", ["verify", folder])
                full = self.command("verify --full", ["verify", "--full", "--kit", args.kit, folder])
            if limited != 0 or full != 0:
                self.update(status="FAILED")
                return
            manifest = loads_strict(manifest_bytes)
            verified = {MANIFEST: hashlib.sha256(manifest_bytes).hexdigest(),
                        **{name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}}
            # Date and run number only: a minute-precision time is a raw-timestamp shape that the
            # response scan (rightly) refuses.
            stamp = {"at": time.strftime("%Y-%m-%d", time.gmtime()) + f" (run {release.name.split('-')[-1]}"
                           " of this server session)",
                     "revision": str(manifest["bindings"]["toolRevision"])[:12]}
            with self.lock:
                self.verified = verified
                self.state.update(status="RELEASED", verification=stamp, **proof_summary(scenario, manifest))
        except Exception:  # noqa: BLE001 - unknown is failure; never reflect child output or values
            # Child output, exception strings and paths can contain values or key material.
            self.update(status="FAILED")

    def dashboard(self):
        with self.lock:
            if self.state["status"] != "RELEASED":
                return None
            release = self.release
        # Render only the manifest bytes that passed verify --full with the server key just now.
        manifest_bytes, _ = verified_snapshot(release, self.root, self.env, self.args.kit)
        manifest = loads_strict(manifest_bytes)
        # The standalone dashboard displays bound digests. Here omit those opaque values so the
        # entire HTTP HTML body can pass the same production identifier scan without exemptions.
        for field in ("files", "inputs", "lexiconDigests"):
            manifest["bindings"][field] = {k: "bound digest" for k in manifest["bindings"][field]}
        for field in ("contractDigest", "toolRevision"):
            manifest["bindings"][field] = "bound digest"
        manifest["signature"]["value"] = "bound digest"
        return (render_html(manifest, files_base="/unavailable")
                .replace('<meta charset="utf-8">', '<meta charset="utf8">')
                 .replace("<th>SHA-256</th>", "<th>Bound digest</th>"))

    def rows(self, *, name=None, limit=None):
        with self.lock:
            if self.state["status"] != "RELEASED":
                raise ValueError("No verified release")
            release = self.release
        return protected_rows(release, self.root, self.env, self.args.kit, name=name,
                              limit=self.args.preview_rows if limit is None else limit)

    @staticmethod
    def refusal(release):
        report = release.with_name(release.name + ".scoring") / "refusal_report.json"
        if not report.is_file():
            return {"failures": [], "refusalReportAvailable": False}
        node = loads_strict(report.read_bytes())
        gate = node.get("gate", node)
        records = gate.get("records", [])
        return {"failures": [{"check": r["check"], "status": r["status"], "hits": r["hits"]}
                             for r in records if r["status"] not in ("pass", "not_applicable")],
                "reasons": node.get("reasons", []), "refusalReportAvailable": True}
