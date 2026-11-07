"""Producer-scope value checks: original identifier survival, unkeyed hashes, key material.

Each scans every cell of every released CSV and every string and number (as its JSON text) in the\nmanifest; a non-finite constant or other unsupported scalar there is an error. Violation records name a\nfile or column only if the contract declares it, else a positional label (file#i, column#j).

Original-value survival is a hit when any of these holds for a cell:
  - whole-cell equality (case-folded, whitespace collapsed) with an original value, any length;
  - the original's alphanumeric-compact form (case-folded, separators removed) of at least
    SUBSTRING_MIN (8) characters occurs anywhere in the cell's compact form, with no token
    boundary required (in a cell that is a single 32+ hex digest, only originals of at least
    DIGEST_SUBSTRING_MIN (12) compact characters, to keep chance matches negligible);
  - a token n-gram equals an original of at least 4 normalised characters (or its compact form
    of at least 6 characters).
Shorter originals inside longer text are not hits; that floor is deliberate (false refusals).

Key material: every supplied key must be at least MIN_KEY_FORM (16) characters/bytes, so every
form (raw, hex, base64 std/url, padded or not) is scannable; a shorter key is an error.
Originals and hash sets are built in memory from the source data and never
leave this module; records carry only declared schema names, positional labels, counts and row indices.

Context:
  source:       {table: DataFrame (dtype=str)}
  identifiers:  [{table, column}] source columns whose values are identifiers
                (direct identifiers; hashing also covers technical identifiers listed here)
  keys:         [key object | str | bytes] key material (master and derived keys). A key object exposes
                ``scannable_forms() -> (exact, lowercase-hex)`` (pseudonym.keys.SecretKey); its raw bytes
                are never read outside the keys module (#84)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections import defaultdict

import pandas as pd

from pets_release.checks.records import Outcome
from pets_release.checks.registry import register

from ._common import CheckError, read_csv, release_dir, viol

ORIGINAL_VALUES = "producer.original-values"
UNKEYED_HASHES = "producer.unkeyed-hashes"
KEY_MATERIAL = "producer.key-material"

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
# A cell that is one hex digest/token is not substring-scanned for originals: the
# reversible-hash check covers it, and a digit run inside a keyed digest is chance.
_DIGEST = re.compile(r"[0-9a-fA-F]{32,}")
SUBSTRING_MIN = 8
DIGEST_SUBSTRING_MIN = 12


def _tokens(s: str) -> list[str]:
    return [t.strip(_EDGE) for t in _SPLIT.split(s.casefold()) if t.strip(_EDGE)]


def _norm(s: str) -> str:
    return " ".join(_tokens(s))


def _compact(s: str) -> str:
    return _NON_ALNUM.sub("", s.casefold())


def _whole(s: str) -> str:
    return " ".join(s.casefold().split())


def _declared(contract) -> dict[str, set]:
    """Contract-declared released file -> declared column names (schema names only)."""
    files = (contract or {}).get("files") if isinstance(contract, dict) else None
    out: dict[str, set] = {}
    if isinstance(files, dict):
        for name, spec in files.items():
            cols = spec.get("columns") if isinstance(spec, dict) else None
            out[str(name)] = {str(c) for c in cols} if isinstance(cols, dict) else set()
    return out


def _cells(release, contract):
    """Return (n, [(file label, column label, {text: [row indices]})]) over every released cell and manifest scalar.

    Records carry content-free labels only: a file or column name appears as itself only when the contract
    declares it (or it is the fixed manifest name); otherwise it is ``file#<i>`` (index in the sorted file
    list) or ``column#<j>`` (header position), so a value planted in a name never reaches a record.
    Unique values per column are listed once with all their row indices.
    """
    root = release_dir(release)
    files = sorted(p for p in root.iterdir() if p.is_file())
    if not files:
        raise CheckError("release folder is empty")
    declared = _declared(contract)
    n = 0
    out = []
    for fi, p in enumerate(files):
        flabel = p.name if (p.name in declared or p.name == MANIFEST) else f"file#{fi}"
        dcols = declared.get(p.name, set())
        if p.suffix.lower() == ".csv":
            df = read_csv(p)
            for j, col in enumerate(df.columns):
                n += len(df)
                rows = defaultdict(list)
                for i, v in enumerate(df[col].tolist()):
                    if v:
                        rows[v].append(i)
                out.append((flabel, col if col in dcols else f"column#{j}", rows))
            out.append((flabel, "<header>", {c: [] for c in df.columns}))
        elif p.name == MANIFEST:
            strings: dict[str, list] = defaultdict(list)
            _walk(_load_manifest(p), strings)
            n += sum(len(v) for v in strings.values())
            out.append((flabel, "", strings))
        else:
            # any other file is scanned as text; the gate refuses it elsewhere
            n += 1
            out.append((flabel, "", {p.read_text(encoding="utf-8", errors="replace"): [0]}))
    return n, out


def _load_manifest(p):
    """Parse the manifest strictly (#114: the shared loader; duplicate keys and NaN/Infinity are an error), keeping
    every number as its exact JSON text, so numbers are scanned as strings."""
    # lazy: manifest.schema imports pets_release.checks
    from pets_release.manifest.canonical import loads_strict

    try:
        return loads_strict(p.read_bytes(), numbers_as_text=True)
    except ValueError:
        raise CheckError("manifest is not strict JSON") from None


def _walk(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            acc[str(k)].append(0)
            _walk(v, acc)
    elif isinstance(node, list):
        for v in node:
            _walk(v, acc)
    elif isinstance(node, str):  # strings and (via _load_manifest) numbers
        acc[node].append(0)
    elif node is None or isinstance(node, bool):
        return  # no content to scan
    else:
        raise CheckError("manifest holds an unsupported scalar type")


def _source_values(context):
    source = context["source"]
    out = []
    for ident in sorted(context["identifiers"], key=lambda d: (d["table"], d["column"])):
        df = source.get(ident["table"])
        if df is None or ident["column"] not in df.columns:
            raise CheckError("identifier column missing from source")
        label = f"{ident['table']}.{ident['column']}"
        raw = df[ident["column"]].tolist()
        # an empty cell (None / NaN) is skipped; any other non-string value is an error
        if any(not isinstance(v, str) and v is not None and not pd.isna(v) for v in raw):
            raise CheckError("source identifier column holds non-string values")
        vals = {v for v in raw if isinstance(v, str) and v.strip()}
        out.append((label, vals))
    return out


def _scan(release, contract, check, match):
    """Run ``match(text) -> set[label]`` over every cell; build the record (content-free labels only)."""
    n, groups = _cells(release, contract)
    if n == 0:
        raise CheckError("nothing to scan")
    hits_by = defaultdict(list)
    for file, col, rows in groups:
        for text, locs in rows.items():
            for label in match(text):
                hits_by[(file, col, label)].extend(locs if locs else [0])
    # count = distinct rows hit in that file/column (manifest strings count as row 0)
    vs = [viol(check, label, file, col, len(set(locs)), locs) for (file, col, label), locs in sorted(hits_by.items())]
    return Outcome(n=n, violations=tuple(vs))


# --- original identifier survival -------------------------------------------------


@register(name=ORIGINAL_VALUES, version="1.0.0", scope="producer", unit="cells")
def run_original_values(release, contract, context) -> Outcome:
    context = context or {}
    if not context.get("source") or not context.get("identifiers"):
        return Outcome.not_run()
    norm: dict[str, set] = defaultdict(set)
    compact: dict[str, set] = defaultdict(set)
    whole_cell: dict[str, set] = defaultdict(set)
    prefix: dict[str, list] = defaultdict(list)  # first SUBSTRING_MIN compact chars -> [(compact, label)]
    max_gram = 1
    for label, vals in _source_values(context):
        for v in vals:
            whole_cell[_whole(v)].add(label)
            cv = _compact(v)
            if len(cv) >= SUBSTRING_MIN:
                prefix[cv[:SUBSTRING_MIN]].append((cv, label))
            nv = _norm(v)
            if len(nv) >= MIN_NORM:
                norm[nv].add(label)
                max_gram = max(max_gram, min(MAX_GRAM, nv.count(" ") + 1))
            cv = _compact(v)
            if len(cv) >= MIN_COMPACT:
                compact[cv].add(label)

    def match(text):
        found = set(whole_cell.get(_whole(text), ()))
        c = _compact(text)
        # a single hex digest cell is still substring-scanned, but only for originals long
        # enough (DIGEST_SUBSTRING_MIN) that a chance match inside a digest is negligible
        floor = DIGEST_SUBSTRING_MIN if _DIGEST.fullmatch(text.strip()) else SUBSTRING_MIN
        for i in range(len(c) - SUBSTRING_MIN + 1):
            cands = prefix.get(c[i : i + SUBSTRING_MIN])
            if cands:
                for cv, label in cands:
                    if len(cv) >= floor and c.startswith(cv, i):
                        found.add(label)
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

    return _scan(release, contract, ORIGINAL_VALUES, match)


# --- reversible (unkeyed) hashes of original values ---------------------------------


def _variants(v: str):
    s = v.strip()
    n = " ".join(s.split())
    c = re.sub(r"[\W_]+", "", s)
    return {v, s, n, n.casefold(), n.upper(), c, c.casefold(), c.upper()} - {""}


@register(name=UNKEYED_HASHES, version="1.0.0", scope="producer", unit="cells")
def run_unkeyed_hashes(release, contract, context) -> Outcome:
    context = context or {}
    if not context.get("source") or not context.get("identifiers"):
        return Outcome.not_run()
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

    return _scan(release, contract, UNKEYED_HASHES, match)


# --- key material ---------------------------------------------------------------------


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


@register(name=KEY_MATERIAL, version="1.0.0", scope="producer", unit="cells")
def run_key_material(release, contract, context) -> Outcome:
    keys = (context or {}).get("keys")
    if not keys:
        return Outcome.not_run()
    exact, lower = set(), set()
    for k in keys:
        forms = getattr(k, "scannable_forms", None)
        if callable(forms):  # an opaque key object (pseudonym.keys.SecretKey): its bytes are never read here
            try:
                e, lo = forms()
            except Exception as exc:  # noqa: BLE001 - content-free
                raise CheckError("key object cannot give its scannable forms") from exc
            e = {f for f in e if isinstance(f, str) and len(f) >= MIN_KEY_FORM}
            lo = {f.lower() for f in lo if isinstance(f, str) and len(f) >= MIN_KEY_FORM}
            if not e and not lo:
                raise CheckError("key material too short to scan in every form")
            exact |= e
            lower |= lo
            continue
        if not isinstance(k, (str, bytes, bytearray)) or not k or len(k) < MIN_KEY_FORM:
            raise CheckError("key material too short to scan in every form")
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

    return _scan(release, contract, KEY_MATERIAL, match)
