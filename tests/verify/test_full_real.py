"""#71: ``verify --full`` with the real registered producer checks (no stubs), on a real ``pets-release run`` release.

The bed is built by the real run CLI on the synthetic run minikit; the producer context is rebuilt exactly as the
CLI does (``run.context.verify_context``: row maps by pseudonym inversion, keys from the master key). Each plant
below is caught only by the named producer check's real implementation: with that check stubbed to a pass
(``Outcome(n=1)``) or deleted, its row's assertion fails.

Rows (trigger -> result):
  unchanged real release                      -> ok; every producer.* check re-runs to pass with n >= 1
  source person ID copied into a released cell -> producer.original-values fail
  unkeyed sha256 of a source person ID planted -> producer.unkeyed-hashes fail
  master key (test constant) planted           -> producer.key-material fail
  one person's released QI made unique         -> producer.person-k fail
  same original-value plant, real CLI          -> exit 1, producer.original-values fail line, value not echoed
"""
from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from pets_release.kit import Kit
from pets_release.pseudonym import MasterKey
from pets_release.run.context import verify_context

PRODUCER = ("producer.key-material", "producer.original-values", "producer.person-k", "producer.unkeyed-hashes")


def _full(real_bed):
    from pets_release.verify import verify_release

    master = MasterKey.from_text(real_bed.KEY)
    ctx = verify_context(Kit(real_bed.kit), master, real_bed.release)
    return verify_release(real_bed.release, full=True, kit=real_bed.kit, master_key=master, context=ctx)


def _source_person(real_bed) -> str:
    df = pd.read_csv(real_bed.kit / "data" / "health" / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    return sorted(v for v in df["patient_hetu"] if v)[0]


def _plant(real_bed, tb, value, column=None):
    """Write ``value`` into row 0 of a non-token ed_visits column, then re-bind digests and re-sign."""
    m = tb.load(real_bed.release)
    tokens = {t["column"] for t in m["contract"]["tokens"] if t["table"] == "ed_visits"}
    qi = {q["column"] for q in m["contract"]["qi"]}
    col = column or sorted(c for c in m["contract"]["files"]["ed_visits.csv"]["columns"]
                           if c not in tokens and c not in qi)[0]

    def edit(header, rows):
        rows[0][header.index(col)] = value
        return header, rows

    tb.edit_csv(real_bed.release, "ed_visits.csv", edit)
    real_bed.resign(m)


def _failed(rep, check):
    return any(x.startswith(f"check {check} [producer]") and ": fail " in x for x in rep.lines)


def test_unchanged_real_release_passes_with_real_producer_checks(real_bed):
    rep = _full(real_bed)
    assert rep.ok, rep.lines
    by = {r.check: r for r in rep.records}
    for name in PRODUCER:
        assert by[name].status == "pass" and by[name].denominator["n"] >= 1, name


def test_original_value_plant_fails_original_values(real_bed, tb):
    _plant(real_bed, tb, _source_person(real_bed))
    rep = _full(real_bed)
    assert not rep.ok
    assert _failed(rep, "producer.original-values"), rep.lines


def test_unkeyed_hash_plant_fails_unkeyed_hashes(real_bed, tb):
    _plant(real_bed, tb, hashlib.sha256(_source_person(real_bed).encode("utf-8")).hexdigest())
    rep = _full(real_bed)
    assert not rep.ok
    assert _failed(rep, "producer.unkeyed-hashes"), rep.lines


def test_key_material_plant_fails_key_material(real_bed, tb):
    _plant(real_bed, tb, real_bed.KEY.encode("utf-8").hex())  # published test-only key constant
    rep = _full(real_bed)
    assert not rep.ok
    assert _failed(rep, "producer.key-material"), rep.lines


def test_unique_qi_fails_person_k(real_bed, tb):
    m = tb.load(real_bed.release)
    col = sorted(q["column"] for q in m["contract"]["qi"] if q["table"] == "ed_visits")[0]
    df = pd.read_csv(real_bed.release / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    assert df[col].value_counts()[df[col].iat[0]] >= 5  # row 0 starts in a class of >= k

    def unique(header, rows):  # row 0 gets a QI value no other row has: its person is alone in its class
        rows[0][header.index(col)] += "x"
        return header, rows

    tb.edit_csv(real_bed.release, "ed_visits.csv", unique)
    real_bed.resign(m)
    rep = _full(real_bed)
    assert not rep.ok
    assert _failed(rep, "producer.person-k"), rep.lines


def test_real_cli_original_value_plant_fails(real_bed, tb, verify_cli):
    value = _source_person(real_bed)
    _plant(real_bed, tb, value)
    r = verify_cli("--full", "--kit", real_bed.kit, real_bed.release, env=real_bed.env())
    assert r.returncode == 1, r.stdout
    assert any(x.startswith("check producer.original-values [producer]") and ": fail " in x
               for x in r.stdout.splitlines()), r.stdout
    assert value not in r.stdout + r.stderr


PRODUCTION = {  # check name -> (module, function) of its production implementation, pinned by name (#115 item 6)
    "producer.key-material": ("pets_release.checks.producer.values", "run_key_material"),
    "producer.original-values": ("pets_release.checks.producer.values", "run_original_values"),
    "producer.person-k": ("pets_release.checks.producer.kanon", "run_person_k"),
    "producer.unkeyed-hashes": ("pets_release.checks.producer.values", "run_unkeyed_hashes"),
}


@pytest.mark.parametrize("name", PRODUCER)
def test_real_producer_check_is_the_registered_implementation(name):
    """No stub: the registry entry verify runs is exactly the pinned production function (identity, not a module
    prefix), so a deleted check or any other function registered under its name (even one defined inside
    checks.producer) fails here. A stub written into the production function's own body is caught by the plant
    rows above."""
    import importlib

    from pets_release.checks import all_checks

    module, fn = PRODUCTION[name]
    want = getattr(importlib.import_module(module), fn)
    got = [c for c in all_checks() if c.name == name]
    assert len(got) == 1, name
    assert got[0].run is want, (got[0].run.__module__, got[0].run.__qualname__)
