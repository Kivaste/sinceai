"""Deterministic OS-boundary faults around an otherwise unmodified real smoke CLI.

Python audit events run immediately before the syscall: no sleeps, production
check stubs, or private smoke functions. Only the synthetic checkout is touched.
"""
import json
import os
import runpy
import shlex
import subprocess
import sys
from pathlib import Path


def main():
    fault = sys.argv.pop(1)
    sys.argv.pop(0)
    script = Path(sys.argv[0])
    checkout = script.parent.parent
    output = Path(sys.argv[sys.argv.index("--out-root") + 1])
    observation = output.parent / "fault-observation.json"
    state = {"fired": False}

    def audit(event, args):
        command = None
        if event == "subprocess.Popen":
            command = ([arg.strip('"') for arg in shlex.split(args[1], posix=False)]
                       if isinstance(args[1], str) else args[1])
        if fault == "interrupt-after-invalidation":
            if event == "os.rename" and Path(args[1]).name == "smoke.json":
                pending = Path(args[0]).read_bytes()
                previous = json.loads(Path(args[1]).read_bytes())
                record = json.loads(pending)
                observation.write_text(json.dumps({
                    "previousHealthPassed": previous["scenarios"]["HEALTH-S1"]["pass"],
                    "pendingPassed": record["pass"],
                    "pendingScenarioPasses": [s["pass"] for s in record["scenarios"].values()],
                    "canonical": pending == json.dumps(record, sort_keys=True, separators=(",", ":"),
                                                        ensure_ascii=False, allow_nan=False).encode("utf-8"),
                }), encoding="utf-8")
            if command and "show" in command:
                os._exit(86)  # Abrupt exit: no finally block or final evidence write.
        if state["fired"]:
            return
        if (fault == "existing-run-output" and command
                and "run" in command and "HEALTH-S1" in command):
            state["fired"] = True
            Path(command[command.index("--out") + 1]).mkdir(parents=True)
            observation.write_text("{}", encoding="utf-8")
        if (fault == "head-drift" and command
                and "run" in command and "CS-S1" in command):
            state["fired"] = True
            subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Smoke Test",
                            "-c", "user.email=smoke@example.invalid", "commit", "--allow-empty",
                            "-m", "synthetic concurrent revision"], check=True, capture_output=True)
            observation.write_text("{}", encoding="utf-8")
        if fault == "wrong-manifest-revision" and event == "open" and isinstance(args[0], str):
            path = Path(args[0])
            if (path.name == "privacy_manifest.json" and path.parent.name == "HEALTH-S1"
                    and path.parent.parent.name.startswith("attempt-")):
                state["fired"] = True  # Prevent recursion through the real filesystem calls below.
                manifest = json.loads(path.read_bytes())
                manifest["bindings"]["toolRevision"] = "0" * 40
                path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
                observation.write_text("{}", encoding="utf-8")

    sys.addaudithook(audit)
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
