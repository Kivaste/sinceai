"""Canonical JSON: sorted keys, `,`/`:` separators, UTF-8, no NaN, byte-stable."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.manifest import canonical_bytes, canonical_digest, loads_strict

SRC = Path(__file__).resolve().parents[2] / "src"


def test_known_bytes_for_a_worked_example():
    obj = {"b": [1, 2.5, None, True], "a": {"y": "ä", "x": False}}
    assert canonical_bytes(obj) == '{"a":{"x":false,"y":"ä"},"b":[1,2.5,null,true]}'.encode()


def test_key_insertion_order_does_not_change_bytes():
    one = {"z": 1, "a": {"q": 1, "b": 2}}
    two = {"a": {"b": 2, "q": 1}, "z": 1}
    assert canonical_bytes(one) == canonical_bytes(two)
    assert canonical_digest(one) == canonical_digest(two)


def test_digest_is_sha256_hex_of_bytes():
    # sha256 of b'{}' (worked example, independent of the implementation)
    assert canonical_digest({}) == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"


def test_byte_stable_across_two_processes():
    code = (
        "import sys;from pets_release.manifest import canonical_bytes;"
        "sys.stdout.buffer.write(canonical_bytes({'k':[{'b':1,'a':0.1}],'é':'x'}))"
    )
    outs = []
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONHASHSEED=seed)
        run = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, check=True)
        outs.append(run.stdout)
    assert outs[0] == outs[1] and outs[0]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(bad):
    with pytest.raises(ValueError):
        canonical_bytes({"x": bad})


def test_non_string_keys_are_rejected():
    with pytest.raises(TypeError):
        canonical_bytes({1: "a"})


def test_loads_strict_rejects_duplicate_keys():
    with pytest.raises(ValueError):
        loads_strict(b'{"a":false,"a":true}')


@pytest.mark.parametrize("raw", [b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'])
def test_loads_strict_rejects_non_finite_constants(raw):
    with pytest.raises(ValueError):
        loads_strict(raw)


def test_loads_strict_round_trips_canonical_bytes():
    obj = {"a": [1, {"b": "c"}], "d": None}
    assert canonical_bytes(loads_strict(canonical_bytes(obj))) == canonical_bytes(obj)
