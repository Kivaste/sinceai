"""Planted purpose checks for the parallel-search tests (#127). Synthetic only; module-level so a spawned worker
can unpickle them. Each plant acts only inside a pool worker (a process with a parent) and otherwise defers to
the real purpose check, so the search's final re-check in the main process is unaffected."""
from __future__ import annotations

import multiprocessing
import os
import socket


class PlantedWorkerError(BaseException):
    """A BaseException escapes the search's per-check ``except Exception``: the worker's task itself raises."""


def _in_worker() -> bool:
    return multiprocessing.parent_process() is not None


def network(real, task_id, original, protected):
    """Open a socket inside the worker (no traffic); without the offline guard this succeeds silently."""
    if _in_worker():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.close()
    return real(task_id, original, protected)


def raises(real, task_id, original, protected):
    if _in_worker():
        raise PlantedWorkerError("planted")
    return real(task_id, original, protected)


LATER = ("ed_visits", "los_minutes")  # released at the start (floor exact); only later candidates withhold it


def _later(protected) -> bool:
    t = protected.get(LATER[0])
    return t is not None and LATER[1] not in t.columns


def network_later(real, task_id, original, protected):
    """A socket opened only while scoring a later candidate (never the start), in any process."""
    if _later(protected):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.close()
    return real(task_id, original, protected)


def raises_later(real, task_id, original, protected):
    """An ordinary exception, only inside a worker and only on a later candidate (never the start)."""
    if _in_worker() and _later(protected):
        raise RuntimeError("planted")
    return real(task_id, original, protected)


def _note_pid(d, extra=None):
    import json
    from pathlib import Path

    Path(d, f"{os.getpid()}.json").write_text(json.dumps(extra or {}), encoding="utf-8")


def env_probe(d, real, task_id, original, protected):
    """Record this worker's environment variable NAMES only (never values)."""
    if _in_worker():
        _note_pid(d, {"names": sorted(os.environ)})
    return real(task_id, original, protected)


def hangs(d, real, task_id, original, protected):
    """A scorer that never returns (inside a worker); records its PID first."""
    if _in_worker():
        import time

        _note_pid(d)
        time.sleep(600)
    return real(task_id, original, protected)


def jitter(real, task_id, original, protected):
    """Results complete out of submission order: a per-candidate delay (0-0.6 s) from the released columns."""
    if _in_worker():
        import hashlib
        import time

        cols = ",".join(f"{t}.{c}" for t in sorted(protected) for c in sorted(protected[t].columns))
        time.sleep(int(hashlib.sha256(cols.encode()).hexdigest()[:4], 16) % 7 / 10)
    return real(task_id, original, protected)


def killed(real, task_id, original, protected):
    if _in_worker():
        os._exit(13)
    return real(task_id, original, protected)
