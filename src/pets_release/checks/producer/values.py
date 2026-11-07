"""Producer-scope value checks: original identifier survival, unkeyed hashes, key material.

Each scans every cell of every released CSV and every string in the manifest.
Originals and hash sets are built in memory from the source data and never
leave this module; records carry only schema names, counts and row indices.

Context:
  source:       {table: DataFrame (dtype=str)}
  identifiers:  [{table, column}] source columns whose values are identifiers
                (direct identifiers; hashing also covers technical identifiers listed here)
  keys:         [str | bytes] key material (master and derived keys)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections import defaultdict

from ._common import (
    Check,
    CheckError,
    guarded,
    not_run,
    read_csv,
    record,
    release_dir,
    violation,
)

MANIFEST = "privacy_manifest.json"
MIN_NORM = 4
MIN_COMPACT = 6
MAX_GRAM = 8
MIN_KEY_FORM = 16

_SPLIT = re.compile(r"[\s:;,=()\[\]{}<>\"'|/\\]+")
_EDGE = ".!?*"
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)
_HEX = re.compile(r"[0-9a-fA-F]{32,}")
_HEX_LENS = (32, 40, 64)


def _tokens(s: str) -> list[str]:
    return [t.strip(_EDGE) for t in _SPLIT.split(s.casefold()) if t.strip(_EDGE)]


def _norm(s: str) -> str:
    return " ".join(_tokens(s))


def _compact(s: str) -> str:
    return _NON_ALNUM.sub("", s.casefold())


def _cells(release):
    """Yield (file, column, location, text) for every released cell and manifest string.

    Unique values per column are yielded once with all their row indices.
    """
    root = release_dir(release)
    files = sorted(p for p in root.iterdir() if p.is_file())
    if not files:
        raise CheckError("release folder is empty")
    n = 0
    out = []
    for p in files:
        if p.suffix.lower() == ".csv":
            df = read_csv(p)
            for col in df.columns:
                n += len(df)
                rows = defaultdict(list)
                for i, v in enumerate(df[col].tolist()):
                    if v:
                        rows[v].append(i)
                out.append((p.name, col, rows))
            out.append((p.name, "<header>", {c: [] for c in df.columns}))
        elif p.name == MANIFEST:
            strings: dict[str, list] = defaultdict(list)
            _walk(json.loads(p.read_text(encoding="utf-8")), strings)
            n += sum(len(v) for v in strings.values())
            out.append((p.name, "", strings))
        else:
            # any other file is scanned as text; the gate refuses it elsewhere
            n += 1
            out.append((p.name, "", {p.read_text(encoding="utf-8", errors="replace"): [0]}))
    return n, out


def _walk(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            acc[str(k)].append(0)
            _walk(v, acc)
    elif isinstance(node, list):
        for v in node:
            _walk(v, acc)
    elif isinstance(node, str):
        acc[node].append(0)


def _source_values(context):
    source = context["source"]
    out = []
    for ident in sorted(context["identifiers"], key=lambda d: (d["table"], d["column"])):
        df = source.get(ident["table"])
        if df is None or ident["column"] not in df.columns:
            raise CheckError("identifier column missing from source")
        label = f"{ident['table']}.{ident['column']}"
        vals = {v for v in df[ident["column"]].tolist() if isinstance(v, str) and v.strip()}
        out.append((label, vals))
    return out


def _scan(release, check, unit, match):
    """Run ``match(text) -> set[label]`` over every cell; build the record."""
    n, groups = _cells(release)
    if n == 0:
        raise CheckError("nothing to scan")
    hits_by = defaultdict(list)
    for file, col, rows in groups:
        for text, locs in rows.items():
            for label in match(text):
                hits_by[(file, col, label)].extend(locs if locs else [0])
    vs = [violation(check.name, label, file, col, locs) for (file, col, label), locs in hits_by.items()]
    hits = sum(v["count"] for v in vs)
    return record(check, "fail" if hits else "pass", unit, n, hits, vs)


# --- original identifier survival -------------------------------------------------


def _originals():
    return ORIGINAL_VALUES


@guarded(_originals, "cells")
def _run_originals(release, contract, context):
    if not context.get("source") or not context.get("identifiers"):
        return not_run(ORIGINAL_VALUES, "cells")
    norm: dict[str, set] = defaultdict(set)
    compact: dict[str, set] = defaultdict(set)
    max_gram = 1
    for label, vals in _source_values(context):
        for v in vals:
            nv = _norm(v)
            if len(nv) >= MIN_NORM:
                norm[nv].add(label)
                max_gram = max(max_gram, min(MAX_GRAM, nv.count(" ") + 1))
            cv = _compact(v)
            if len(cv) >= MIN_COMPACT:
                compact[cv].add(label)

    def match(text):
        found = set()
        toks = _tokens(text)
        ctoks = [_compact(t) for t in toks]
        whole = _compact(text)
        if whole in compact:
            found |= compact[whole]
        for size in range(1, min(max_gram, len(toks)) + 1):
            for i in range(len(toks) - size + 1):
                gram = " ".join(toks[i : i + size])
                if gram in norm:
                    found |= norm[gram]
                cg = "".join(ctoks[i : i + size])
                if cg in compact:
                    found |= compact[cg]
        return found

    return _scan(release, ORIGINAL_VALUES, "cells", match)


ORIGINAL_VALUES = Check("original_values", "1", "producer", _run_originals)


# --- reversible (unkeyed) hashes of original values ---------------------------------


def _hashes():
    return REVERSIBLE_HASHES


def _variants(v: str):
    s = v.strip()
    n = " ".join(s.split())
    c = re.sub(r"[\W_]+", "", s)
    return {v, s, n, n.casefold(), n.upper(), c, c.casefold(), c.upper()} - {""}


@guarded(_hashes, "cells")
def _run_hashes(release, contract, context):
    if not context.get("source") or not context.get("identifiers"):
        return not_run(REVERSIBLE_HASHES, "cells")
    digests: dict[str, set] = defaultdict(set)
    for label, vals in _source_values(context):
        for v in vals:
            for var in _variants(v):
                b = var.encode("utf-8")
                for algo in ("md5", "sha1", "sha256"):
                    digests[hashlib.new(algo, b).hexdigest()].add(f"{algo}:{label}")

    def match(text):
        found = set()
        for m in _HEX.finditer(text):
            run = m.group(0).lower()
            for size in _HEX_LENS:
                if len(run) < size:
                    break
                windows = [run] if len(run) == size else (run[i : i + size] for i in range(len(run) - size + 1))
                for w in windows:
                    if w in digests:
                        found |= digests[w]
        return found

    return _scan(release, REVERSIBLE_HASHES, "cells", match)


REVERSIBLE_HASHES = Check("reversible_hashes", "1", "producer", _run_hashes)


# --- key material ---------------------------------------------------------------------


def _keys():
    return KEY_MATERIAL


def _key_forms(key) -> tuple[set, set]:
    """Return (case-sensitive forms, case-insensitive lowercase forms)."""
    raw = key.encode("utf-8") if isinstance(key, str) else bytes(key)
    exact = set()
    if isinstance(key, str):
        exact.add(key)
    for b in {raw, raw.strip()}:
        std = base64.b64encode(b).decode()
        url = base64.urlsafe_b64encode(b).decode()
        exact |= {std, std.rstrip("="), url, url.rstrip("=")}
        try:
            exact.add(b.decode("utf-8"))
        except UnicodeDecodeError:
            pass
    lower = {raw.hex(), binascii.hexlify(raw.strip()).decode()}
    # a key given as hex text: also look for its decoded bytes in base64
    if isinstance(key, str) and re.fullmatch(r"(?:[0-9a-fA-F]{2})+", key):
        b = bytes.fromhex(key)
        exact |= {base64.b64encode(b).decode().rstrip("="), base64.urlsafe_b64encode(b).decode().rstrip("=")}
    exact = {f for f in exact if len(f) >= MIN_KEY_FORM}
    lower = {f.lower() for f in lower if len(f) >= MIN_KEY_FORM}
    return exact, lower


@guarded(_keys, "cells")
def _run_keys(release, contract, context):
    keys = context.get("keys")
    if not keys:
        return not_run(KEY_MATERIAL, "cells")
    exact, lower = set(), set()
    for k in keys:
        if not k:
            raise CheckError("empty key material")
        e, lo = _key_forms(k)
        exact |= e
        lower |= lo
    if not exact and not lower:
        raise CheckError("key material too short to scan")

    def match(text):
        if any(f in text for f in exact):
            return {"keyMaterial"}
        tl = text.lower()
        if any(f in tl for f in lower):
            return {"keyMaterial"}
        return set()

    return _scan(release, KEY_MATERIAL, "cells", match)


KEY_MATERIAL = Check("key_material", "1", "producer", _run_keys)
