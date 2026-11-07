"""#114 (closed-record class): the attacker's own JSON records load strictly (``manifest.loads_strict``).

Rules (trigger -> result):
  [CLI ``python -m pets_attacker.bridge``] attack aggregate with a duplicate "insider" key (first value a high
      rate, last value benign) -> exit 2, no output (was: exit 0, the dropped rate never reached residualRisks)
  [same] duplicate key inside a broker aggregate                                -> exit 2
  [same] the unplanted aggregate                                                -> exit 0 (control)
  [module CLI ``pets_attacker.cli.main``] --rungs file with a duplicate table key (first value contradicts the
      cells, last value correct) -> refused, no output (was: exit 0)
All values are synthetic and hand-made.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pets_attacker.cli import main as attacker_main
from tests.pets_attacker.test_cli import RUNGS, _mini_kit

SRC = Path(__file__).resolve().parents[2] / "src"
INSIDER_OK = '{"reidentification_rate": 0.0, "attribute_inference_rate": 0.0, "n_targets": 30, "evaluated": true}'
INSIDER_HIGH = '{"reidentification_rate": 0.9, "attribute_inference_rate": 0.9, "n_targets": 30, "evaluated": true}'
BROKER_OK = '{"reidentification_rate": 0.0, "attribute_inference_rate": 0.0, "n_targets": 20, "evaluated": true}'


def _bridge(tmp_path, text):
    src, out = tmp_path / "attack.json", tmp_path / "residual.json"
    src.write_text(text, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-m", "pets_attacker.bridge", "--attack", str(src), "--out", str(out)],
                       check=False, capture_output=True, text=True, env=env)
    return p, out


def test_bridge_control_runs(tmp_path):
    p, out = _bridge(tmp_path, '{"label": "t", "broker": {"b": ' + BROKER_OK + '}, "insider": ' + INSIDER_OK + '}')
    assert p.returncode == 0 and out.exists(), p.stderr


@pytest.mark.parametrize("text", [
    '{"label": "t", "broker": {"b": ' + BROKER_OK + '}, "insider": ' + INSIDER_HIGH + ', "insider": ' + INSIDER_OK + '}',
    '{"label": "t", "broker": {"b": ' + BROKER_OK[:-1] + ', "n_targets": 1}}, "insider": ' + INSIDER_OK + '}',
], ids=["dup-insider", "dup-in-broker"])
def test_bridge_refuses_a_duplicate_key_aggregate(tmp_path, text):
    p, out = _bridge(tmp_path, text)
    assert p.returncode == 2, p.stdout + p.stderr
    assert not out.exists()


def test_attacker_refuses_a_duplicate_key_rungs_file(tmp_path):
    kit = _mini_kit(tmp_path)
    rungs = tmp_path / "rungs.json"
    wrong = json.dumps({"arrival_ts": "ts.day", "municipality": "keep"})  # contradicts the cells: refused alone
    rungs.write_text('{"ed_visits": ' + wrong + ', "ed_visits": ' + json.dumps(RUNGS["ed_visits"]) + '}',
                     encoding="utf-8")
    out = tmp_path / "o.json"
    rc = attacker_main(["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(out),
                        "--rungs", str(rungs)])
    assert rc != 0
    assert not out.exists()
