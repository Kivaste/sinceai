"""The measure wiring's byte-identity guard, through the production ``run_measured`` / ``main`` on the minikit.

Only the measurer's scoring is stubbed (it needs the challenge kit); the two ``run_release`` passes, the guard and
the cleanup are production code. The second pass is wrapped to change, delete or add a table after it ran.

Rows (trigger -> result):
  second pass identical to the first   -> released, tables present
  a table changed / missing / extra    -> RunError, no release folder, no scoring folder
  cleanup fails after a mismatch       -> still an error (cleanup failure named), never a silent pass
  the CLI entry on a mismatch          -> exit 2, nothing published
"""
from __future__ import annotations

import pytest
from run_helpers import CREATED, TEST_KEY, SCENARIOS, build_kit, coarse_qis, run_args

from pets_release.measure import wire
from pets_release.run import pipeline
from pets_release.verify import current_tool_revision

BLOCK = {k: {"status": "not_measured", "reason": "stub"} for k in ("utility", "privacy", "baselines", "search", "redaction")}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=coarse_qis)
    monkeypatch.setattr(wire, "measure", lambda *a, **k: dict(BLOCK))
    monkeypatch.setattr(wire, "person_k_components", lambda *a, **k: [])
    monkeypatch.setattr(wire, "_person_k_from_release", lambda **k: None)
    return kit, tmp_path / "rel"


def _tamper(monkeypatch, how):
    real = pipeline.run_release
    calls = []

    def run_release(**kw):
        res = real(**kw)
        calls.append(kw["out"])
        if len(calls) == 2 and res.status == "released":
            files = sorted(res.out.glob("*.csv"))
            if how == "change":
                files[0].write_bytes(files[0].read_bytes() + b"x\n")
            elif how == "missing":
                files[0].unlink()
            elif how == "extra":
                (res.out / "extra_table.csv").write_bytes(b"a\n1\n")
        return res

    monkeypatch.setattr(pipeline, "run_release", run_release)


def _run(kit, out):
    from pets_release.cli import resolve_run_context

    ctx = resolve_run_context(run_args(kit, out)[1:])
    return ctx, wire.run_measured(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key,
                                  out=out, plan_name="hand", tool_revision=current_tool_revision())


def test_matching_passes_release(setup):
    kit, out = setup
    _, res = _run(kit, out)
    assert res.status == "released" and any(out.glob("*.csv"))


@pytest.mark.parametrize("how", ["change", "missing", "extra"])
def test_mismatch_refuses_and_publishes_nothing(setup, monkeypatch, how):
    kit, out = setup
    _tamper(monkeypatch, how)
    with pytest.raises(pipeline.RunError, match="differ"):
        _run(kit, out)
    assert not out.exists()
    assert not (out.parent / "rel.scoring").exists()


def test_cleanup_failure_is_an_error_not_a_pass(setup, monkeypatch):
    kit, out = setup
    _tamper(monkeypatch, "change")
    real = wire.shutil.rmtree

    def rmtree(path, *a, **k):
        if str(path).endswith(("rel", "rel.scoring")):
            raise PermissionError("locked")
        return real(path, *a, **k)

    monkeypatch.setattr(wire.shutil, "rmtree", rmtree)
    with pytest.raises(pipeline.RunError, match="cleanup failed"):
        _run(kit, out)


def test_cli_exit_2_on_mismatch(setup, monkeypatch, capsys):
    kit, out = setup
    _tamper(monkeypatch, "change")
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert not out.exists()
    assert "differ" in capsys.readouterr().err


def test_recipient_reaches_the_release_through_the_cli(setup, monkeypatch):
    """follow-up #94: --recipient must reach run_release (both passes) and the signed manifest."""
    from pets_release.manifest import MANIFEST_FILENAME, loads_strict

    kit, out = setup
    seen = []
    real = pipeline.run_release
    monkeypatch.setattr(pipeline, "run_release", lambda **kw: (seen.append(kw.get("recipient")), real(**kw))[1])
    assert wire.main(run_args(kit, out)[1:] + ["--recipient", "acme"]) == 0
    assert seen == ["acme", "acme"]
    assert loads_strict((out / MANIFEST_FILENAME).read_bytes())["release"]["recipient"] == "acme"


def test_invalid_recipient_is_refused_by_the_measure_cli(setup, capsys):
    kit, out = setup
    assert wire.main(run_args(kit, out)[1:] + ["--recipient", "bad id!"]) == 2
    assert not out.exists()
