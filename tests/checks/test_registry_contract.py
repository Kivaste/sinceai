"""Registry rules: naming (ticket 02 schema), assertion mapping, fail-closed discovery, producer-scope API."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pets_release.checks import ASSERTION_CHECKS, Check, Outcome, all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
SRC = Path(__file__).resolve().parents[2] / "src"
CHECK_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")  # ticket 02 schema: checkName
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")  # ticket 02 schema: version
# ticket 02 schema ALL_ASSERTIONS (union over CS-S1 and HEALTH-S1)
ASSERTIONS_02 = sorted([
    "accountNumbers", "deviceIds", "emails", "ibans", "ipAddresses", "nationalIds", "paymentCards", "phones",
    "plates", "propertyIds", "secrets", "urlsWithTokens", "usernames",
    "keyMaterial", "rawTimestamps", "reversibleHashes", "rowMaps", "healthInText", "quasiIdentifiersBelowK"])
OWNED_HERE = ["accountNumbers", "deviceIds", "emails", "ibans", "ipAddresses", "nationalIds", "paymentCards",
              "phones", "plates", "propertyIds", "secrets", "urlsWithTokens", "usernames", "rawTimestamps", "rowMaps"]


def test_every_registered_name_and_version_match_manifest_schema():
    checks = all_checks()
    assert checks
    assert [c.name for c in checks if not CHECK_NAME.match(c.name)] == []
    assert [c.name for c in checks if not SEMVER.match(c.version)] == []


def test_assertion_map_covers_exactly_the_manifest_assertions_with_valid_names():
    assert sorted(ASSERTION_CHECKS) == ASSERTIONS_02
    assert all(CHECK_NAME.match(v) for v in ASSERTION_CHECKS.values())
    assert len(set(ASSERTION_CHECKS.values())) == len(ASSERTION_CHECKS)


def test_assertions_owned_by_this_package_bind_to_registered_checks():
    names = {c.name for c in all_checks()}
    assert [a for a in OWNED_HERE if ASSERTION_CHECKS[a] not in names] == []


def _run_with_planted(tmp_path, files):
    plant = tmp_path / "plant"
    plant.mkdir()
    for name, body in files.items():
        (plant / name).write_text(body, encoding="utf-8")
    rel = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", rel)
    code = (
        "import json, sys, pets_release.checks as c\n"
        "c.__path__.append(sys.argv[1])\n"
        "r = c.run_checks(sys.argv[2], json.load(open(sys.argv[3], encoding='utf-8')), {'phase': 'gate'})\n"
        "print(json.dumps({'refused': r.refused, 'n': len(r.records), 'err': r.registry_error}))\n"
    )
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-c", code, str(plant), str(rel), str(FIX / "contract.json")],
                       check=False, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_planted_submodule_that_registers_nothing_refuses(tmp_path):
    body = ("from pets_release.checks import Check\n"
            "CHECKS = (Check('tuple-style', '1.0.0', 'producer', 'cells', lambda r, c, x: None),)\n")
    res = _run_with_planted(tmp_path, {"tuple_style.py": body})
    assert res["refused"] is True
    assert res["err"] is not None and "tuple_style" in res["err"]


def test_planted_submodule_that_fails_to_import_refuses(tmp_path):
    res = _run_with_planted(tmp_path, {"broken.py": "raise RuntimeError('x')\n"})
    assert res["refused"] is True and res["err"] is not None


def test_planted_submodule_that_registers_is_discovered_and_run(tmp_path):
    body = ("from pets_release.checks import register, Outcome\n"
            "@register(name='planted.ok', version='1.0.0', scope='release', unit='files')\n"
            "def run(release, contract, context):\n"
            "    return Outcome(n=len(release.entries))\n")
    res = _run_with_planted(tmp_path, {"planted_ok.py": body})
    assert res["err"] is None and res["refused"] is False
    assert res["n"] == len(all_checks()) + 1


def _producer(release, contract, context):
    src = context.get("source_tables")
    if src is None or context.get("hmac_key") is None:
        return Outcome.not_run()
    assert release.path.is_dir()
    return Outcome(n=len(src))


def test_producer_check_sees_path_and_context_and_can_say_not_run(tmp_path):
    rel = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", rel)
    chk = Check(name="producer.demo", version="1.0.0", scope="producer", unit="rows", run=_producer)
    missing = run_checks(rel, CONTRACT, {"phase": "gate"}, checks=[chk])
    assert (missing.records[0].status, missing.refused) == ("not_run", True)
    ok = run_checks(rel, CONTRACT, {"phase": "gate", "source_tables": {"a": 1}, "hmac_key": b"k" * 32}, checks=[chk])
    assert (ok.records[0].status, ok.refused) == ("pass", False)
