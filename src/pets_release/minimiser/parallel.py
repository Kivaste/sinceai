"""Parallel candidate scoring for the search (#127, D44): a spawn-context process pool, opt-in.

The pool only computes ``_Search.raw(candidate)``: a pure function of the candidate (purpose results for the
checks whose input digest the main process has not cached yet, the risk vector and PersonK). The main process
consumes raws in exactly the order the sequential search evaluates candidates and commits them to its own
cache and counters, so the log, the stats, the chosen plan and the release are byte-identical at every worker
count, and the worker count is never recorded. Candidates are scored speculatively ahead of the search; a
speculation that the search never asks for is discarded, never used.

Fail closed: the offline guard is installed and self-checked in every worker; a worker task that raises, a
worker that dies, a result that times out, or a speculative task that failed makes the search refuse
(``MinimiserRefused``, content-free reason). No plan is ever picked from partial results.
"""
from __future__ import annotations

import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor

RESULT_TIMEOUT_S = 3600  # one candidate; far above any measured candidate
GIB = 1 << 30
RAM_PER_WORKER = 2 * GIB
WORKER_FAILED = "search worker failed: no plan is picked from partial results"

_W = None  # the worker's own _Search (built once per worker by the initializer)


class WorkerFailed(Exception):
    """A pool worker failed (raised, died, timed out). Content-free."""


def _free_ram() -> int | None:
    """Available physical memory in bytes, or None if it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return None
            return int(ms.ullAvailPhys)
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        return None


def effective_workers(requested: int) -> int:
    """``requested`` capped at min(cores, free RAM / 2 GiB), at least 1. Never recorded in any artefact."""
    n = min(int(requested), os.cpu_count() or 1)
    ram = _free_ram()
    if ram is not None:
        n = min(n, ram // RAM_PER_WORKER)
    return max(1, n)


def _guard_active() -> bool:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return True
    s.close()
    return False


def _init_worker(payload: dict) -> None:
    """Offline guard first (before anything is unpacked or scored), verified; then this worker's search state."""
    from pets_release import offline

    offline.install()
    if not _guard_active():
        raise RuntimeError("offline guard not active in a search worker")
    from .search import _Search

    global _W
    _W = _Search(**payload)


class NoKeys:
    """The workers' key material: none. Key objects refuse serialisation by design, so every keyed column
    (``MAIN_ONLY_RUNGS``) is computed in the main process and shipped as a derived column; a worker that would
    still need a key fails, and the search refuses."""

    def token(self, value, label="RECORD_KEY"):
        raise RuntimeError("search workers hold no key material")


def _score(cand: dict, known: frozenset, columns: dict):
    """One candidate's raw evaluation. Any failure, including a BaseException, is reported, never swallowed."""
    try:
        return ("ok", _W.raw(cand, known, columns))
    except BaseException:  # noqa: BLE001 - the message could carry values; the main process refuses
        return ("failed", None)


class Pool:
    """The search's speculative scorer. ``ahead`` submits candidates in priority order; ``take`` returns the raw
    for one candidate (submitting it if needed). ``columns(cand)`` gives the main-process columns a candidate
    needs. Any failure raises ``WorkerFailed``."""

    def __init__(self, workers: int, payload: dict, columns):
        self.workers = workers
        self.columns = columns
        self.ex = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                      initializer=_init_worker, initargs=(payload,))
        self.fut: dict = {}

    @staticmethod
    def key(cand) -> tuple:
        return tuple(sorted(cand.items()))

    def ahead(self, cands, known, room: int) -> None:
        """Speculate on ``cands`` (priority order, at most ``room`` and 2 x workers); cancel queued speculation
        that is no longer wanted. Running tasks finish and are checked at ``close``. A candidate whose main-process
        columns cannot be built is not speculated on (``take`` then raises exactly as the sequential search)."""
        want, keys = [], set()
        for c in cands:
            if len(want) >= min(room, 2 * self.workers):
                break
            k = self.key(c)
            if k not in keys:
                keys.add(k)
                want.append((k, c))
        for k in [k for k in self.fut if k not in keys]:
            if self.fut[k].cancel():
                del self.fut[k]
        for k, c in want:
            if k not in self.fut:
                try:
                    cols = self.columns(c)
                except Exception:  # noqa: BLE001, S112 - surfaces at take, in search order
                    continue
                self._submit(k, c, known, cols)

    def _submit(self, k, cand, known, cols):
        try:
            self.fut[k] = self.ex.submit(_score, cand, frozenset(known), cols)
        except Exception:  # noqa: BLE001 - a broken pool
            raise WorkerFailed(WORKER_FAILED) from None

    def take(self, cand, known):
        k = self.key(cand)
        if k not in self.fut:
            self._submit(k, cand, known, self.columns(cand))
        fut = self.fut.pop(k)
        try:
            status, raw = fut.result(timeout=RESULT_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - broken pool, timeout, cancelled, unpicklable result
            raise WorkerFailed(WORKER_FAILED) from None
        if status != "ok":
            raise WorkerFailed(WORKER_FAILED)
        return raw

    def close(self, ok: bool) -> None:
        """Shut the pool down. On success every speculative task already running must also have succeeded."""
        pending = list(self.fut.values())
        self.fut.clear()
        failed = False
        try:
            if ok:
                for f in pending:
                    if f.cancel():
                        continue
                    try:
                        status, _ = f.result(timeout=RESULT_TIMEOUT_S)
                    except Exception:  # noqa: BLE001
                        failed = True
                        break
                    if status != "ok":
                        failed = True
                        break
        finally:
            if ok and not failed:
                self.ex.shutdown(wait=True, cancel_futures=True)
            else:
                self.ex.shutdown(wait=False, cancel_futures=True)
                kill = getattr(self.ex, "terminate_workers", None)
                if kill is not None:
                    try:
                        kill()
                    except Exception:  # noqa: BLE001, S110 - already broken
                        pass
        if failed:
            raise WorkerFailed(WORKER_FAILED)
