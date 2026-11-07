"""Read content-free release evidence for the PowerShell close gate (stdlib only)."""

import json
import re
import sys
from collections import Counter
from pathlib import Path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    def invalid_constant(_):
        raise ValueError("non-finite JSON number")

    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object, parse_constant=invalid_constant)


def exact_keys(record, keys):
    if not isinstance(record, dict) or set(record) != set(keys.split()):
        raise ValueError("record keys")


def check_record(record, *, report=False):
    exact_keys(record, "check version scope status denominator hits" + (" violations" if report else ""))
    if not isinstance(record["check"], str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", record["check"]):
        raise ValueError("check name")
    if not isinstance(record["version"], str) or not record["version"]:
        raise ValueError("check version")
    if record["scope"] not in ("release", "producer"):
        raise ValueError("check scope")
    if record["status"] not in ("pass", "not_applicable", "fail", "error", "not_run"):
        raise ValueError("check status")
    exact_keys(record["denominator"], "n unit")
    if record["denominator"]["unit"] not in ("cells", "turns", "persons", "files", "rows"):
        raise ValueError("denominator unit")
    for number in (record["hits"], record["denominator"]["n"]):
        if type(number) is not int or number < 0:
            raise ValueError("check count")
    if report:
        if not isinstance(record["violations"], list):
            raise ValueError("violations")
        for violation in record["violations"]:
            # RunResult.aggregate() deliberately strips locations; both public
            # report shapes are closed, and neither needs cell values here.
            keys = "check label severity file column count"
            exact_keys(violation, keys + (" locations" if "locations" in violation else ""))


def gate_records(manifest, gate):
    exact_keys(gate, "records refused registryError")
    exact_keys(manifest["gate"], "checks status")
    records = gate["records"]
    checks = manifest["gate"]["checks"]
    if not isinstance(records, list) or not records or not isinstance(checks, list) or not checks:
        raise ValueError("missing checks")
    for record in records:
        check_record(record, report=True)
    for record in checks:
        check_record(record)
    counts = Counter(record["status"] for record in records)
    print("Gate records: " + " ".join(f"{status}={counts[status]}" for status in
                                      ("pass", "not_applicable", "fail", "error")))
    names = sorted(record["check"] for record in records if record["status"] == "not_applicable")
    print("Gate not_applicable checks: " + (", ".join(names) if names else "none"))
    if gate["refused"] is not False or gate["registryError"] is not None:
        raise ValueError("gate refusal or registry error")
    if any(record["status"] not in ("pass", "not_applicable") for record in records):
        raise ValueError("unsuccessful check")
    if manifest["gate"]["status"] != "pass":
        raise ValueError("manifest gate status")
    versions = manifest["bindings"]["checkVersions"]
    if not isinstance(versions, dict) or not versions:
        raise ValueError("check versions")
    for group in (records, checks):
        if len({record["check"] for record in group}) != len(group):
            raise ValueError("duplicate check")
        if {record["check"]: record["version"] for record in group} != versions:
            raise ValueError("missing or mismatched check")
    projected = [{key: value for key, value in record.items() if key != "violations"} for record in records]
    if sorted(projected, key=lambda r: r["check"]) != sorted(checks, key=lambda r: r["check"]):
        raise ValueError("manifest gate disagreement")


def verify_records(folder, release_name, head, outcome):
    claims = list(re.finditer(r"\bverify(?:\s*(--full|\(full\)|-full|full|\(limited\)|limited))?",
                              outcome, flags=re.IGNORECASE))
    if not claims:
        return []
    tiers = {"full" if match[1] and "full" in match[1].lower() else "limited" for match in claims}
    # Log identity follows the release, not whichever filename happens to exist.
    log_name = "run.log" if release_name == "release" else release_name.removeprefix("release-") + ".log"
    try:
        raw = (folder / log_name).read_bytes()
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        lines = text.splitlines()
    except (OSError, UnicodeError):
        return ["verify evidence log missing or unreadable"]
    revisions = [line for line in lines if line.startswith("revision=")]
    if revisions != [f"revision={head}"]:
        return ["verify evidence revision missing, ambiguous or not Head"]
    problems = []
    for tier in sorted(tiers):
        prefix = "verify-full exit=" if tier == "full" else "verify exit="
        exits = [line for line in lines if line.startswith(prefix)]
        if exits != [prefix + "0"] or lines.index(exits[0]) < lines.index(revisions[0]):
            problems.append(f"verify ({tier}) exit 0 record missing, ambiguous or unsuccessful")
    return problems


def check(folder, head, outcome):
    # One release identity, never a recursive search for a planted passing file.
    manifests = sorted(folder.glob("*/privacy_manifest.json"))
    if len(manifests) != 1:
        return ["exactly one release manifest required"]
    manifest = read_json(manifests[0])
    if manifest["bindings"]["toolRevision"] != head:
        return ["manifest revision does not equal Head"]
    gate_path = manifests[0].parent.with_name(manifests[0].parent.name + ".scoring") / "gate_report.json"
    try:
        gate_records(manifest, read_json(gate_path))
    except (OSError, ValueError, KeyError, TypeError):
        return ["gate report missing, unreadable, malformed or unsuccessful"]
    return verify_records(folder, manifests[0].parent.name, head, outcome)


if __name__ == "__main__":
    try:
        problems = check(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        # Never echo parser exceptions: they can contain data from the record.
        problems = ["machine records missing, unreadable or malformed"]
    for problem in problems:
        print(f"Real-run evidence: {problem}")
    sys.exit(1 if problems else 0)
