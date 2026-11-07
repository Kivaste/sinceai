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

import contextlib
import multiprocessing
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

RESULT_TIMEOUT_S = 3600  # one candidate; far above any measured candidate
GIB = 1 << 30
RAM_PER_WORKER = 2 * GIB
WORKER_FAILED = "search worker failed: no plan is picked from partial results"
JOIN_S = 10  # bounded wait for each terminated worker
# A worker's whole environment (allow-list, as #152's sender): OS basics and the determinism settings. No secret
# (PETS_HMAC_KEY), no PETS_OFFLINE / PYTHONPATH hook: the worker installs the offline guard itself.
WORKER_ENV = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
              "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "HOMEDRIVE", "HOMEPATH", "NUMBER_OF_PROCESSORS",
              "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONUTF8", "PYTHONIOENCODING",
              "PYTHONHASHSEED", "PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE", "VIRTUAL_ENV")
SECRET_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSW|CREDENTIAL", re.IGNORECASE)

_W = None  # the worker's own _Search (built once per worker by the initializer)


class WorkerFailed(Exception):
    """A pool worker failed (raised, died, timed out). Content-free."""


def worker_env(source) -> dict:
    """The allow-listed environment a search worker starts with (names from ``WORKER_ENV`` only)."""
    return {k: source[k] for k in WORKER_ENV if k in source}


@contextlib.contextmanager
def _worker_environ():
    """While a worker may be spawned (inside ``submit``), this process's environment is the worker allow-list;
    restored right after. Spawned children inherit the process environment block."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(worker_env(saved))
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


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
    """``requested`` capped at min(cores, free RAM / 2 GiB), at least 1. Never recorded in any artefact. An
    unmeasured core count or free memory is never replaced by a guess: the pool cannot be sized (WorkerFailed)."""
    cores, ram = os.cpu_count(), _free_ram()
    if cores is None or ram is None:
        raise WorkerFailed("search workers: core count or free memory not measurable; run with --workers 1")
    return max(1, min(int(requested), cores, ram // RAM_PER_WORKER))


def _guard_active() -> bool:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return True
    s.close()
    return False


def _init_worker(payload: dict) -> None:
    """No key material in the environment (fail closed); the offline guard installed here (the worker's
    environment carries no inherited hook) and verified; then this worker's search state, in strict mode."""
    if any(SECRET_NAME.search(k) for k in os.environ):
        raise RuntimeError("a search worker started with a secret in its environment")
    from pets_release import offline

    offline.install()
    if not _guard_active():
        raise RuntimeError("offline guard not active in a search worker")
    from .search import _Search

    global _W
    _W = _Search(**payload)
    _W.strict = True


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
            with _worker_environ():  # submit may spawn a worker: it starts with the allow-listed environment
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
                self.terminate()
        if failed:
            raise WorkerFailed(WORKER_FAILED)

    def terminate(self) -> None:
        """Failure path: kill every worker first (a hung scorer included), wait for each (bounded), then shut down.
        shutdown() first would forget the processes and leave a hung worker running."""
        procs = list((getattr(self.ex, "_processes", None) or {}).values())
        kill = getattr(self.ex, "terminate_workers", None)
        if kill is not None:
            try:
                kill()
            except Exception:  # noqa: BLE001, S110 - already broken; the PIDs below are still killed
                pass
        for p in procs:
            try:
                if p.is_alive():
                    p.kill()
                p.join(JOIN_S)
            except Exception:  # noqa: BLE001, S110 - already gone
                pass
        self.ex.shutdown(wait=False, cancel_futures=True)
