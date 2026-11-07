"""Two-tier verify: re-run the registry on a release folder; never reuse a prior result."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from pathlib import Path

from pets_release.checks import RegistryError, all_checks, run_checks
from pets_release.checks.records import STATUSES
from pets_release.kit import Kit, KitError
from pets_release.manifest import (
    MANIFEST_FILENAME,
    compute_signature,
    loads_strict,
    validate_manifest_file,
)
from pets_release.verify.revision import current_tool_revision

# Statuses that count as a re-proved check. ``not_applicable`` (ticket 04 follow-up) is accepted only once the
# runner defines it; the runner alone decides when it applies. Everything else (fail, error, not_run, unknown)
# fails verify.
OK_STATUSES = frozenset({"pass"} | ({"not_applicable"} & set(STATUSES)))
SIGNATURE_ALG = "HMAC-SHA256"


class VerifyUsageError(Exception):
    """Exit-2 condition: missing release path, kit or key. Message is content-free."""


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    mode: str  # "limited" | "full"
    lines: tuple  # content-free: schema names, statuses and counts only; last line is the verdict
    records: tuple = ()  # CheckRecords from this run (never from the manifest)

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _digest_problems(release: Path, bound: dict, listed: set) -> list[str]:
    """Bound names come from the validated manifest (== contract files); any other release-derived name is
    reported as a content-free ``unlisted-file#<i>`` marker (same convention as ticket 04)."""
    out = []
    entries = sorted(p.name for p in release.iterdir())
    for i, name in enumerate(entries):
        if name != MANIFEST_FILENAME and name not in bound:
            shown = name if name in listed else f"unlisted-file#{i}"
            out.append(f"files: {shown}: not bound in manifest")
    for name in sorted(bound):
        p = release / name
        if not p.is_file():
            out.append(f"files: {name}: bound file missing")
        elif not hmac.compare_digest(_sha256(p), str(bound[name])):
            out.append(f"files: {name}: digest mismatch")
    return out


def _record_lines(rec) -> list[str]:
    head = (f"check {rec.check} [{rec.scope}] {rec.version}: {rec.status} "
            f"(hits={rec.hits}, n={rec.denominator['n']} {rec.denominator['unit']})")
    lines = [head]
    for v in rec.violations:
        where = v.file + (f":{v.column}" if v.column else "")
        lines.append(f"  {v.severity} {v.label} in {where}: count={v.count}")
    return lines


def _claim_problems(manifest: dict, registered: dict, scopes: set) -> list[str]:
    out = []
    for rec in manifest["gate"]["checks"]:
        name, chk = rec["check"], registered.get(rec["check"])
        if chk is None:
            if rec["scope"] in scopes:
                out.append(f"check {name} [{rec['scope']}]: unavailable (claimed by manifest, not registered)")
            continue
        if chk.scope != rec["scope"]:
            out.append(f"check {name}: scope mismatch (manifest {rec['scope']}, registry {chk.scope})")
        if chk.version != rec["version"]:
            out.append(f"check {name}: version mismatch (manifest {rec['version']}, registry {chk.version})")
    return out


def _signature_problems(manifest: dict, master_key) -> list[str]:
    from pets_release.pseudonym import manifest_signing_key

    sig = manifest["signature"]
    sk = manifest_signing_key(master_key)
    out = []
    if sig.get("alg") != SIGNATURE_ALG:
        out.append("signature: unsupported alg")
    if not hmac.compare_digest(str(sig.get("keyId", "")), sk.key_id()):
        out.append("signature: keyId does not match the key in PETS_HMAC_KEY")
    if not hmac.compare_digest(str(sig.get("value", "")), compute_signature(manifest, sk)):
        out.append("signature: mismatch")
    return out


def _input_problems(manifest: dict, kit: Kit) -> tuple[list[str], dict | None, dict | None]:
    try:
        scenario = kit.scenario(manifest["release"]["scenario"])
        dataset = scenario["dataset"]
        have = kit.input_digests(dataset)
    except (KitError, KeyError, TypeError):
        return ["inputs: scenario or dataset unavailable in kit"], None, None
    bound = manifest["bindings"]["inputs"]
    out = []
    if not bound:
        out.append("inputs: manifest binds no input digests")
    for table in sorted(bound):
        if table not in have:
            out.append(f"inputs: {table}: missing from kit")
        elif not hmac.compare_digest(have[table], str(bound[table])):
            out.append(f"inputs: {table}: digest mismatch")
    return out, scenario, dataset


def verify_release(release_dir, *, full: bool = False, kit=None, master_key=None, checks=None,
                   context: dict | None = None) -> VerifyReport:
    """Verify ``release_dir``. Recipient mode by default; ``full=True`` needs ``kit`` and ``master_key``.

    ``checks`` replaces the registry (tests and run-context wiring only; the CLI never passes it).
    ``context`` adds producer run context under ``--full`` (ticket 21 wiring); recipient mode ignores it.
    """
    mode = "full" if full else "limited"
    release = Path(release_dir)
    if not release.is_dir():
        raise VerifyUsageError("release folder does not exist")
    if full:
        if kit is None:
            raise VerifyUsageError("--full needs the kit (--kit or PETS_KIT)")
        if master_key is None:
            raise VerifyUsageError("--full needs the key in PETS_HMAC_KEY")
        if not isinstance(kit, Kit):
            try:
                kit = Kit(kit)
            except KitError as e:
                raise VerifyUsageError("kit path is not a kit directory") from e

    def fail(problems, records=()):
        lines = [*problems, f"VERIFY FAILED ({mode}): {len(problems)} problem(s)"]
        return VerifyReport(False, mode, tuple(lines), tuple(records))

    # 1. Manifest: closed schema, cross-field rules, canonical bytes (ticket 02). Nothing else is trusted yet.
    if not (release / MANIFEST_FILENAME).is_file():
        return fail(["manifest: missing"])
    errors = validate_manifest_file(release)
    if errors:
        return fail([f"manifest: {e}" for e in errors])
    try:
        manifest = loads_strict((release / MANIFEST_FILENAME).read_bytes())
    except (OSError, ValueError):
        return fail(["manifest: unreadable"])

    problems: list[str] = []
    # 2. Every file digest, recomputed here.
    problems += _digest_problems(release, manifest["bindings"]["files"], set(manifest["contract"]["files"]))

    # 3. Registry, and the manifest's claims against it.
    try:
        registered_list = tuple(all_checks() if checks is None else checks)
    except RegistryError:
        return fail(problems + ["registry: discovery failed"])
    registered = {c.name: c for c in registered_list}
    scopes = {"release", "producer"} if full else {"release"}
    problems += _claim_problems(manifest, registered, scopes)

    # 4. Inputs (full only) and producer context.
    run_ctx: dict = {"phase": "verify"}
    if full:
        inp, scenario, dataset = _input_problems(manifest, kit)
        problems += inp
        rev = current_tool_revision()
        if rev is None:
            problems.append("toolRevision: unavailable (cannot read this checkout's revision)")
        elif not hmac.compare_digest(rev, str(manifest["bindings"]["toolRevision"])):
            problems.append("toolRevision: mismatch")
        problems += _signature_problems(manifest, master_key)
        run_ctx.update({"kit_root": str(kit.root), "hmac_key": master_key})
        if scenario is not None:
            run_ctx["scenario"] = scenario
            try:
                run_ctx["source"] = kit.load_dataset(dataset)
            except KitError:
                problems.append("inputs: dataset unreadable")
        run_ctx.update(dict(context or {}))
        run_ctx["phase"] = "verify"

    # 5. Re-run the checks (fresh records; the manifest's gate records are never consulted for a status).
    selected = tuple(c for c in registered_list if c.scope in scopes)
    result = run_checks(release, manifest["contract"], run_ctx, checks=selected)
    if result.registry_error is not None:
        problems.append("registry: discovery failed")
    if not any(r.status == "pass" for r in result.records):
        problems.append("checks: nothing ran")
    bad = [r for r in result.records if r.status not in OK_STATUSES]
    for r in bad:
        problems += _record_lines(r)
    if result.refused and not problems:  # the runner's own verdict is a floor, never overridden
        problems.append("checks: runner refused")

    if problems:
        return fail(problems, result.records)
    n_release = sum(1 for r in result.records if r.scope == "release")
    if full:
        n_producer = sum(1 for r in result.records if r.scope == "producer")
        verdict = (f"VERIFIED (full): {len(result.records)} checks re-run ({n_release} release, {n_producer} "
                   f"producer); signature, input digests and tool revision match")
    else:
        attested = sum(1 for c in manifest["gate"]["checks"] if c["scope"] == "producer")
        verdict = f"VERIFIED (limited): {n_release} release-checked, {attested} producer-attested"
    return VerifyReport(True, mode, (verdict,), result.records)
