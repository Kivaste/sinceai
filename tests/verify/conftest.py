"""Test bed for verify: the ticket-02 fixture release, rebound to this checkout.

Synthetic rows only (the 02 fixture and the shared minikit). ``rebind`` aligns the fixture manifest with the
current registry (claimed release-scope checks = the registered ones), the minikit's input digests, this
checkout's tool revision and a test-only master key, then re-signs it. Mutation helpers edit a copy and
optionally re-bind digests, so a test can isolate exactly one failing rule.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "manifest" / "release"
MANIFEST = "privacy_manifest.json"
TEST_KEY = "verify-test-only-master-key-not-a-secret-000000"  # published test constant, signs nothing real

def load(release: Path) -> dict:
    return json.loads((release / MANIFEST).read_text(encoding="utf-8"))


def save(release: Path, m: dict) -> None:
    from pets_release.manifest import canonical_bytes

    (release / MANIFEST).write_bytes(canonical_bytes(m))


def sign(m: dict, key_text: str = TEST_KEY) -> dict:
    from pets_release.manifest import compute_signature
    from pets_release.pseudonym import MasterKey, manifest_signing_key

    sk = manifest_signing_key(MasterKey.from_text(key_text))
    m["signature"] = {"alg": "HMAC-SHA256", "keyId": sk.key_id(), "value": "0" * 64}
    m["signature"]["value"] = compute_signature(m, sk)
    return m


def rebind_files(release: Path, m: dict) -> dict:
    import hashlib

    m["bindings"]["files"] = {
        f: hashlib.sha256((release / f).read_bytes()).hexdigest() for f in sorted(m["bindings"]["files"])
    }
    return m


def rebind(release: Path, kit: Path, key_text: str = TEST_KEY, extra_checks=()) -> dict:
    """Align the copied fixture manifest with the registry, kit, revision and key; write it canonically."""
    from pets_release.checks import all_checks
    from pets_release.kit import Kit
    from pets_release.manifest import release_scope_id
    from pets_release.verify import current_tool_revision

    m = load(release)
    registered = {c.name: c for c in (*all_checks(), *extra_checks)}
    kept = []
    for rec in m["gate"]["checks"]:
        chk = registered.get(rec["check"])
        if rec["scope"] == "producer" or (chk is not None and chk.scope == "release"):
            kept.append(rec)
    names = {r["check"] for r in kept}
    for name, chk in sorted(registered.items()):  # registered checks the fixture does not list yet
        if name not in names:
            kept.append({"check": name, "version": chk.version, "scope": chk.scope, "status": "pass",
                         "denominator": {"unit": chk.unit, "n": 1}, "hits": 0})
    for rec in kept:
        chk = registered.get(rec["check"])
        if chk is not None:
            rec["version"] = chk.version
            rec["scope"] = chk.scope
            rec["denominator"]["unit"] = chk.unit
    # Attest the status the re-run will produce (verify fails on a mismatch): a release-scope check that is
    # inapplicable to this fixture contract (e.g. text.* with no free-text columns) is recorded not_applicable.
    from pets_release.checks import run_checks

    rerun = {r.check: r for r in run_checks(release, m["contract"], {"phase": "verify"},
                                            checks=tuple(c for c in registered.values()
                                                         if c.scope == "release")).records}
    for rec in kept:
        r = rerun.get(rec["check"])
        if r is not None and r.status == "not_applicable":
            rec["status"] = "not_applicable"
            rec["denominator"]["n"] = 0
            rec["hits"] = 0
    kept.sort(key=lambda r: r["check"])
    m["gate"]["checks"] = kept
    by = {r["check"]: r for r in kept}
    for name, ev in m["assertionEvidence"].items():
        m["assertionEvidence"][name] = dict(by[ev["check"]])
    m["bindings"]["checkVersions"] = {r["check"]: r["version"] for r in kept}
    k = Kit(kit)
    m["bindings"]["inputs"] = k.input_digests(k.scenario(m["release"]["scenario"])["dataset"])
    m["bindings"]["toolRevision"] = current_tool_revision()
    rel = m["release"]
    rel["releaseScopeId"] = release_scope_id(scenario=rel["scenario"], recipient=rel["recipient"],
                                             inputs=m["bindings"]["inputs"],
                                             tool_revision=m["bindings"]["toolRevision"])
    rebind_files(release, m)
    sign(m, key_text)
    save(release, m)
    return m


def edit_csv(release: Path, name: str, fn) -> None:
    """Apply ``fn(header, rows)`` -> (header, rows) to a release CSV (synthetic fixture rows only)."""
    text = (release / name).read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    header, body = fn(rows[0], rows[1:])
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    w.writerows(body)
    (release / name).write_bytes(out.getvalue().encode("utf-8"))


class _TB:
    """Helper namespace handed to tests as the ``tb`` fixture."""

    KEY = TEST_KEY
    FIXTURE = FIXTURE
    MANIFEST = MANIFEST
    load = staticmethod(load)
    save = staticmethod(save)
    sign = staticmethod(sign)
    rebind = staticmethod(rebind)
    rebind_files = staticmethod(rebind_files)
    edit_csv = staticmethod(edit_csv)


@pytest.fixture
def tb():
    return _TB


@pytest.fixture
def kit(make_kit) -> Path:
    return make_kit()


@pytest.fixture
def bed(tmp_path: Path, kit: Path) -> Path:
    """A verifiable release folder (fixture rows) bound to ``kit``, this revision and TEST_KEY."""
    rel = tmp_path / "release"
    shutil.copytree(FIXTURE, rel)
    rebind(rel, kit)
    return rel


@pytest.fixture
def verify_cli(cli):
    """The real CLI as a subprocess: ``pets-release verify ...`` (env does not inherit key or kit)."""

    def _run(*args, env: dict | None = None):
        return cli("verify", *[str(a) for a in args], env=env)

    return _run
