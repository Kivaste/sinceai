"""Submission-packager fixtures. Synthetic rows only (the shared health minikit plus tiny hand-made CS/unseen tables)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sub_helpers import build_kit, cli, coarse_qis, run_args

CS_TURNS = (
    "turn_id,conversation_id,seq,speaker,ts,text\n"
    "t1,c1,1,customer,2025-01-01T10:00:00Z,Hello my email is anna.testi@example.com please call\n"
    "t2,c1,2,agent,2025-01-01T10:01:00Z,Thanks for contacting us\n"
    "t3,c2,1,customer,2025-01-02T10:00:00Z,Router 192.168.1.1 is slow\n"
    "t4,c2,2,agent,2025-01-02T10:01:00Z,\n"
    "t5,c3,1,customer,2025-01-03T10:00:00Z,Train conversation text only\n"
)
CS_CONVS = (
    "conversation_id,customer_id,agent_id,agent_name,channel,language,started_ts,intent,sentiment,csat,resolved,"
    "handle_time_s,n_turns,split,agent_note\n"
    "c1,u1,a1,Agent,chat,en,2025-01-01T10:00:00Z,billing,neutral,4,1,300,2,eval,\n"
    "c2,u2,a1,Agent,chat,en,2025-01-02T10:00:00Z,refund,neutral,4,1,200,2,eval,\n"
    "c3,u3,a1,Agent,chat,en,2025-01-03T10:00:00Z,refund,neutral,4,1,100,1,train,\n"
)
UNSEEN = (
    "c01,c02,c03\n"
    "anna.testi@example.com,2024-01-03,Hoitaja\n"
    "pekka.testi@example.org,2023-02-11,Hoitaja\n"
    "liisa.testi@example.net,2022-05-30,Sairaanhoitaja\n"
    "mikko.testi@example.com,2021-06-21,Hoitaja\n"
)
CATALOG = (
    "dataset,table,column,privacy_role,data_kind,subtype\n"
    "health,ed_visits,visit_id,record_key,identifier,id\n"
    "health,lab_results,lab_id,record_key,identifier,id\n"
    "health,clinical_notes,note_id,record_key,identifier,id\n"
    "health,published_weekly_stats,stat_id,record_key,identifier,id\n"
)


def build_world(root: Path):
    """Synthetic kit with health + customer_service + unseen; returns (kit, release_dir)."""
    kit = build_kit(root / "kit", coarse_qis)
    cs = kit / "data" / "customer_service"
    cs.mkdir(parents=True)
    (cs / "turns.csv").write_text(CS_TURNS, encoding="utf-8", newline="")
    (cs / "conversations.csv").write_text(CS_CONVS, encoding="utf-8", newline="")
    un = kit / "data" / "unseen"
    un.mkdir(parents=True)
    (un / "export_2025_q4.csv").write_text(UNSEEN, encoding="utf-8", newline="")
    out = root / "rel" / "health"
    proc = cli(*run_args(kit, out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # record keys for the real out-of-process scorecard, so the real CLI can build a bundle on this kit
    (kit / "metadata" / "field_catalog.csv").write_text(CATALOG, encoding="utf-8", newline="")
    return kit, out


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    return build_world(tmp_path_factory.mktemp("sub"))


@pytest.fixture
def fresh(tmp_path, world):
    """A private copy of the release (+ scoring folder) that a test may damage."""
    kit, rel = world
    dst = tmp_path / "rel" / "health"
    shutil.copytree(rel, dst)
    shutil.copytree(rel.with_name(rel.name + ".scoring"), dst.with_name("health.scoring"))
    return kit, dst

