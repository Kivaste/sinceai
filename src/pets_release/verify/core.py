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
    ASSERTION_EVIDENCE,
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
    # The manifest binds EVERY table of the scenario's dataset (withheld ones included): the sets must be equal.
    for table in sorted(set(have) - set(bound)):
        out.append(f"inputs: {table}: kit table not bound in manifest")
    for table in sorted(bound):
        if table not in have:
            out.append(f"inputs: {table}: missing from kit")
        elif not hmac.compare_digest(have[table], str(bound[table])):
            out.append(f"inputs: {table}: digest mismatch")
    return out, scenario, dataset


def _assertion_problems(manifest: dict, records, scopes: set) -> list[str]:
    """Every in-scope export assertion re-proved from its fresh record by the writer's own rule
    (``assertion_reason``): a ``pass`` with low-severity hits is not absence. Denominators are not compared with
    the attested evidence: some legitimately differ between gate and verify (e.g. ``release.row-maps`` counts the
    manifest file, which does not exist yet at gate time)."""
    from pets_release.writer.assemble import assertion_reason

    fresh = {r.check: r for r in records}
    out = []
    for name in sorted(manifest["exportAssertions"]):
        want = ASSERTION_EVIDENCE[name]
        if want["scope"] not in scopes:
            continue
        reason = assertion_reason(name, fresh.get(want["check"]))
        if reason is not None:
            out.append(f"{reason} (re-run of {want['check']})")
    return out


def _residual_problems(manifest: dict, records, scopes: set) -> list[str]:
    """Low-severity residual risks re-derived from the fresh records (writer's ``low_severity_risks``) must equal
    the signed ``gate_low_severity`` entries of every check in scope."""
    from pets_release.writer.assemble import LOW_SEVERITY_KIND, low_severity_risks

    attested_scope = {c["check"]: c["scope"] for c in manifest["gate"]["checks"]}
    fresh = {r["risk"]: r for r in low_severity_risks(r for r in records if r.scope in scopes)}
    signed = {}
    for r in manifest["residualRisks"]:
        if r["kind"] != LOW_SEVERITY_KIND:
            continue
        check = r["risk"].split(":")[1] if r["risk"].count(":") >= 2 else None
        if attested_scope.get(check, "release") in scopes:  # unknown check: in scope, so it must match
            signed[r["risk"]] = r
    return [f"residualRisks: {risk}: low-severity count differs from the re-run"
            for risk in sorted(set(fresh) | set(signed)) if fresh.get(risk) != signed.get(risk)]


def _released_tables(release: Path, manifest: dict) -> dict:
    import pandas as pd

    out = {}
    for name in sorted(manifest["contract"]["files"]):
        out[name[:-4]] = pd.read_csv(release / name, dtype=str, keep_default_na=False, na_filter=False,
                                     encoding="utf-8")
    return out


def _same_score(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(float(a) - float(b)) <= 1e-12


def purpose_problems(manifest: dict, release: Path, kit: Kit, source: dict, rowmaps: dict | None = None) -> list[str]:
    """Producer-scope fresh utility check (``--full``): re-run the run's own purpose evaluation
    (``run.purpose.evaluate``) on the release folder; it must accept, and the signed ``measured.utility`` and
    sacrifice scores must equal the re-run. Content-free lines (check IDs, reason codes). ``rowmaps``: the fresh
    producer row maps (``verify_context``, token inversion), the same lineage ``run`` scores through."""
    from pets_release.policy import get_policy
    from pets_release.run.purpose import evaluate

    try:
        policy = get_policy(manifest["release"]["scenario"])
        released = _released_tables(release, manifest)
    except Exception:  # noqa: BLE001 - unknown state fails closed, content-free
        return ["purpose [producer]: unavailable (policy or released tables unreadable)"]
    res = evaluate(policy, source, released, root=kit.root, rowmaps=rowmaps)
    out = [f"purpose [producer]: {r}" for r in res.reasons]
    util = manifest["measured"]["utility"]
    if util.get("status") != "measured":
        return out + ["measured.utility: not measured (full verify needs the signed purpose scores)"]
    signed = {t["task"]: t for t in util["tasks"]}
    fresh = {t["task"]: t for t in res.tasks}
    for tid in sorted(set(signed) | set(fresh)):
        s, f = signed.get(tid), fresh.get(tid)
        if s is None or f is None or s["status"] != f["status"] or not (
                _same_score(s["before"], f["before"]) and _same_score(s["after"], f["after"])):
            out.append(f"measured.utility: {tid}: re-run differs from the manifest")
    for sac in manifest["sacrifices"]:
        f = fresh.get(sac["check"])
        if f is None or not (_same_score(sac["before"], f["before"]) and _same_score(sac["after"], f["after"])):
            out.append(f"sacrifices: {sac['check']}: re-run differs from the manifest")
    return out


def rung_step_problems(manifest: dict, source: dict, master_key) -> list[str]:
    """Producer-scope re-measure (``--full``) of every recorded rung sacrifice (#89): rebuild the hand plan with the
    step's column at ``from`` and re-run the run's own ``protect``/``k_at_from``; the figures must equal the
    signed ``atFrom``. Unknown state fails closed. Content-free lines."""
    from pets_release.policy import get_policy, hand_plan
    from pets_release.run.pipeline import k_at_from, protect, search_step_at_from

    steps = [s for s in manifest["sacrifices"] if "rungStep" in s]
    if not steps:
        return []
    out = []
    try:
        scenario = manifest["release"]["scenario"]
        policy = get_policy(scenario)
        plan = hand_plan(scenario)
    except Exception:  # noqa: BLE001 - unknown state fails closed, content-free
        return ["rungStep: not reproducible (policy or hand plan unavailable)"]
    fj = {(f["table"], f["column"]): f for f in manifest["fieldJustifications"]}
    sources = {f["source"] for f in fj.values()}
    for s in steps:
        st = s["rungStep"]
        key = (st["table"], st["column"])
        rs = next((r for r in policy.rung_sacrifices if (r["check"], r["table"], r["column"], r["from"], r["to"])
                   == (s["check"], *key, st["from"], st["to"])), None)
        hand = {(e["table"], e["column"]): e for e in plan}
        by_hand = sources == {"hand"} and hand.get(key, {}).get("rung") == st["from"]
        # a search plan (ticket 25): every field from the search, the step's column released at `to`; the run's
        # own search_step_at_from rebuilds it from the manifest's rungs with the search's params
        by_search = sources == {"search"} and set(fj) == set(policy.floors) and fj.get(key, {}).get("rung") == st["to"]
        if rs is None or not (by_hand or by_search):
            out.append(f"rungStep: {s['check']}: not reproducible (not an enumerated step of the hand or search plan)")
            continue
        scope = {"source": source, "master": master_key, "scope_id": manifest["release"]["releaseScopeId"],
                 "recipient": manifest["release"]["recipient"]}
        try:
            if by_hand:
                *_, sup, _ = protect(plan, policy=policy, **scope)
                fresh = k_at_from(sup)
            else:
                fields = {k: (f["rung"], f["floor"]) for k, f in fj.items()}
                fresh = search_step_at_from(policy, fields, rs, **scope)
        except Exception:  # noqa: BLE001 - the message could carry values
            out.append(f"rungStep: {s['check']}: re-measure failed")
            continue
        if fresh != st["atFrom"]:
            out.append(f"rungStep: {s['check']}: re-measure differs from the manifest")
    return out


def verify_release(release_dir, *, full: bool = False, kit=None, master_key=None, checks=None,
                   context: dict | None = None, purpose=None) -> VerifyReport:
    """Verify ``release_dir``. Recipient mode by default; ``full=True`` needs ``kit`` and ``master_key``.

    ``checks`` replaces the registry (tests and run-context wiring only; the CLI never passes it).
    ``context`` adds producer run context under ``--full`` (ticket 21 wiring); recipient mode ignores it.
    ``purpose`` replaces ``purpose_problems`` under ``--full`` (in-process tests whose fixture rows are not a run
    of the kit; the CLI never passes it).
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
    # The re-run must reproduce what the manifest attests: a status that differs either way (pass vs
    # not_applicable, or any other) means the release no longer matches its gate record.
    attested = {c["check"]: c["status"] for c in manifest["gate"]["checks"]}
    for r in result.records:
        if r.check in attested and r.status != attested[r.check]:
            problems.append(f"check {r.check} [{r.scope}]: status mismatch "
                            f"(manifest {attested[r.check]}, re-run {r.status})")
    problems += _assertion_problems(manifest, result.records, scopes)
    problems += _residual_problems(manifest, result.records, scopes)
    # 6. Purpose checks (full only): fresh, on full data, against the signed scores.
    if full:
        if run_ctx.get("source") is None:
            problems.append("purpose [producer]: not_run (no source dataset)")
        else:
            problems += (purpose or purpose_problems)(manifest, release, kit, run_ctx["source"],
                                                      run_ctx.get("rowmaps"))
            problems += rung_step_problems(manifest, run_ctx["source"], master_key)
    if result.refused and not problems:  # the runner's own verdict is a floor, never overridden
        problems.append("checks: runner refused")

    if problems:
        return fail(problems, result.records)
    n_release = sum(1 for r in result.records if r.scope == "release")
    if full:
        n_producer = sum(1 for r in result.records if r.scope == "producer")
        verdict = (f"VERIFIED (full): {len(result.records)} checks re-run ({n_release} release, {n_producer} "
                   f"producer); purpose checks re-run; signature, input digests and tool revision match")
    else:
        attested = sum(1 for c in manifest["gate"]["checks"] if c["scope"] == "producer")
        verdict = f"VERIFIED (limited): {n_release} release-checked, {attested} producer-attested"
    return VerifyReport(True, mode, (verdict,), result.records)
