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


def killed(real, task_id, original, protected):
    if _in_worker():
        os._exit(13)
    return real(task_id, original, protected)
