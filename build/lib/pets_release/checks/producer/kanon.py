"""k-anonymity checks: per-person k (producer scope) and per-row k (release scope).

Per-person k counts, for every person, the number of distinct persons who share
the same combination of released quasi-identifiers. Every contract QI counts,
in every released table: a QI of a table that joins to the person table (e.g. a
lab sampled date) is attached to the joined record, so join-derived information
lowers k exactly as it would for a recipient who joins on the released visit
pseudonym. Attachment uses the source join, which is conservative: it never
assumes a join is unavailable to the recipient.

If the person column itself is released as a token, a recipient can link all
of a person's records, so the unit becomes the person's full set of records.

Unidentified records (person ID empty in source): such a record (with its joined
rows) is one unidentified unit. It never adds to any class's person count, so it
cannot inflate anyone's k, and it is itself counted as below k: it is a hit under
the label ``unidentifiedPersonRecords`` (count = units, locations = person-table
release rows) and is in the denominator. Local suppression of those records
clears the hit, so the rule never makes a release impossible.

Context (producer scope; any missing item → ``not_run``):
  k:            optional; if given it must equal the contract's k (else error)

k itself comes from the release contract's top-level ``k`` (int >= 2), so recipient
verify needs only the release. No contract ``k`` -> both k checks return not_run.
  source:       {table: DataFrame (dtype=str)} original tables
  rowmaps:      {table: DataFrame[protected_row, original_record_id]} per released QI table
  record_keys:  {table: record-key column in source}
  person:       {table, column, normalise[, released_as]} the person identifier in source.
                ``normalise`` (str -> str) is the pseudonymiser's own normalisation for the person
                column's label, injected by the producer context (checks never import the
                pseudonymiser). Persons are keyed by it, so spellings that get one released token are
                one person; missing -> not_run. If a person token is released, token <-> canonical
                person must be one-to-one, else error (conflicting mapping).
  joins:        [{table, column, ref_table, ref_column}] source joins to the person table
"""

from __future__ import annotations

from collections import defaultdict
from typing import NamedTuple

from pets_release.checks.records import Outcome
from pets_release.checks.registry import register

from ._common import CheckError, qi_by_table, read_table, release_dir, viol

PERSON_K = "producer.person-k"
ROW_K = "producer.row-k"
ABSENT = "\x00absent"
LABEL = "quasiIdentifiersBelowK"
UNIDENTIFIED = "unidentifiedPersonRecords"


def _valid_k(k) -> bool:
    return isinstance(k, int) and not isinstance(k, bool) and k >= 2


def _k(contract, context):
    """k = contract["k"]. No contract k -> None (caller returns not_run; CS-S1 has no k target).

    A present but invalid contract k is an error; a context k, if given, must equal it.
    """
    if "k" not in (contract or {}):
        return None
    k = contract["k"]
    if not _valid_k(k):
        raise CheckError("contract k must be an integer >= 2")
    ck = (context or {}).get("k")
    if ck is not None and (not _valid_k(ck) or ck != k):
        raise CheckError("context k differs from contract k")
    return k


def _source_index(source, table, column):
    df = source.get(table)
    if df is None or column not in df.columns:
        raise CheckError("source table or column missing")
    return df


def _anchor_ids(table, release_n, context):
    """Release row index -> anchor id (person-table record key) for one released table."""
    source = context["source"]
    person_t = context["person"]["table"]
    rk = context["record_keys"].get(table)
    rm = context["rowmaps"].get(table)
    if rk is None or rm is None:
        raise CheckError("row map or record key missing for a QI table")
    if list(rm.columns[:2]) != ["protected_row", "original_record_id"] or len(rm) != release_n:
        raise CheckError("row map does not cover the released table")
    try:
        order = sorted(range(len(rm)), key=lambda i: int(rm["protected_row"].iat[i]))
    except ValueError as exc:
        raise CheckError("row map index is not an integer") from exc
    if [int(rm["protected_row"].iat[i]) for i in order] != list(range(release_n)):
        raise CheckError("row map index is not 0..n-1")
    orig = [rm["original_record_id"].iat[i] for i in order]

    src = _source_index(source, table, rk)
    if src[rk].duplicated().any():
        raise CheckError("source record key is not unique")
    if not set(orig) <= set(src[rk]):
        raise CheckError("row map references a missing source record")
    if len(set(orig)) != len(orig):
        raise CheckError("row map has duplicate source records")
    if table == person_t:
        return orig

    joins = [j for j in context.get("joins") or [] if j["table"] == table and j["ref_table"] == person_t]
    if len(joins) != 1:
        raise CheckError("QI table has no single join to the person table")
    j = joins[0]
    _source_index(source, table, j["column"])
    pt = _source_index(source, person_t, j["ref_column"])
    pk = context["record_keys"].get(person_t)
    if pk is None:
        raise CheckError("person table record key missing")
    _source_index(source, person_t, pk)
    if pt[j["ref_column"]].duplicated().any():
        raise CheckError("join target is not unique")
    ref_to_pk = dict(zip(pt[j["ref_column"]], pt[pk]))
    key_to_join = dict(zip(src[rk], src[j["column"]]))
    out = []
    for rid in orig:
        anchor = ref_to_pk.get(key_to_join[rid])
        if anchor is None:
            raise CheckError("joined record has no person-table record")
        out.append(anchor)
    return out


def _canonical(p, norm):
    """Canonical person identity: ``norm`` is the pseudonymiser's own normalisation for the person label.

    Two source spellings that pseudonymisation maps to one released token are one person. Empty
    (or empty after normalisation) -> None, an unidentified unit. Any normaliser error fails closed.
    """
    if not isinstance(p, str) or not p.strip():
        return None
    try:
        c = norm(p)
    except Exception as exc:  # noqa: BLE001 - any failure is a content-free error
        raise CheckError("person identifier cannot be normalised") from exc
    if not isinstance(c, str):
        raise CheckError("person normaliser returned a non-string")
    return c if c else None


def _person_tokens(contract, context, person_t, person_c) -> set[tuple[str, str]]:
    """Released (table, column) tokens that let a recipient link all records of one person.

    A contract token links the person when ANY of: it has the source person column's
    name (legacy), it carries ``derived_from`` naming the person column (``col`` or
    ``table.col``), or it is listed in ``context["person"]["released_as"]`` (the
    released output columns of the person column, from the plan's outputColumn).
    The token's released name need not match the source name.
    """
    tokens = (contract or {}).get("tokens", []) or []
    released_as = {
        (x["table"], x["column"]) for x in (context["person"].get("released_as") or [])
    }
    out = set()
    for x in tokens:
        key = (x["table"], x["column"])
        src = x.get("derived_from")
        if (
            key == (person_t, person_c)
            or key in released_as
            or (isinstance(src, str) and src in (person_c, f"{person_t}.{person_c}") and x["table"] == person_t)
        ):
            out.add(key)
    return out


def _check_token_mapping(pairs) -> None:
    """Released person token <-> canonical identity must be one-to-one (else refuse: conflicting mapping).

    ``pairs`` are (token, canonical person) per released row with a person ID. A canonical person under
    two tokens, or one token over two canonical persons, means the counting identity differs from what
    the recipient can link; the check cannot be trusted, so it errors.
    """
    tok_to_p: dict = {}
    p_to_tok: dict = {}
    for tok, p in pairs:
        if p is None:
            continue
        if tok_to_p.setdefault(tok, p) != p or p_to_tok.setdefault(p, tok) != tok:
            raise CheckError("person token and person identity do not map one-to-one")


class PersonK(NamedTuple):
    per_person: dict  # identified person -> k (in memory only; never exported)
    below_rows: list  # person-table release rows of identified persons below k
    unidentified: int  # count of unidentified units (records with no person ID)
    unidentified_rows: list  # person-table release rows of those units


def person_k_values(release, contract, context) -> PersonK:
    """Per-person k over every released QI. See the module docstring for the rules.

    Raises CheckError on any fail-closed condition. Values stay in memory only.
    """
    k = _k(contract, context)
    person_t = context["person"]["table"]
    person_c = context["person"]["column"]
    pk = context["record_keys"].get(person_t)
    if pk is None:
        raise CheckError("person table record key missing")
    psrc = _source_index(context["source"], person_t, person_c)
    _source_index(context["source"], person_t, pk)
    # persons are keyed by their canonical identity (see _canonical); a record with no person ID maps
    # to None: an unidentified unit (see module docstring)
    norm = context["person"].get("normalise")
    if not callable(norm):
        raise CheckError("person identity normaliser missing")
    anchor_person = {a: _canonical(p, norm) for a, p in zip(psrc[pk], psrc[person_c])}

    qis = qi_by_table(contract)
    tables = sorted(set(qis) | ({person_t} if (release_dir(release) / f"{person_t}.csv").is_file() else set()))
    if not tables:
        raise CheckError("nothing released to evaluate")

    person_tokens = _person_tokens(contract, context, person_t, person_c)
    # anchor -> {table: [row tuples]}
    parts: dict[str, dict[str, list[tuple]]] = defaultdict(lambda: defaultdict(list))
    person_rows: dict[str, list[int]] = defaultdict(list)
    token_pairs = []
    for t in tables:
        df = read_table(release, t)
        cols = qis.get(t, [])
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise CheckError("contract QI column missing from released table")
        anchors = _anchor_ids(t, len(df), context)
        for tt, tc in sorted(person_tokens):
            # a declared token column absent from the file has nothing to map (linking stays assumed)
            if tt == t and tc in df.columns:
                token_pairs.extend((tok, anchor_person.get(a)) for tok, a in zip(df[tc].tolist(), anchors))
        values = list(zip(*(df[c].tolist() for c in cols))) if cols else [()] * len(df)
        for i, (a, v) in enumerate(zip(anchors, values)):
            parts[a][t].append(tuple(v))
            if t == person_t:
                person_rows[a].append(i)

    def anchor_sig(a):
        p = parts[a]
        sig = []
        for t in tables:
            rows = p.get(t)
            if t == person_t:
                sig.append(rows[0] if rows else (ABSENT,))
            else:
                sig.append(tuple(sorted(rows)) if rows else ())
        return tuple(sig)

    person_linked = bool(person_tokens)
    _check_token_mapping(token_pairs)

    identified = [a for a in parts if anchor_person[a] is not None]
    unidentified = sorted(a for a in parts if anchor_person[a] is None)

    units: dict[str, list[tuple]] = defaultdict(list)  # person -> unit signatures
    if person_linked:
        by_person = defaultdict(list)
        for a in identified:
            by_person[anchor_person[a]].append(anchor_sig(a))
        for p, sigs in by_person.items():
            units[p].append(tuple(sorted(sigs)))
    else:
        for a in identified:
            units[anchor_person[a]].append(anchor_sig(a))

    class_persons: dict[tuple, set] = defaultdict(set)
    for p, sigs in units.items():
        for s in sigs:
            class_persons[s].add(p)
    per_person = {p: min(len(class_persons[s]) for s in sigs) for p, sigs in units.items()}

    below_rows = []
    if k is not None:
        below = {p for p, v in per_person.items() if v < k}
        for a in identified:
            if anchor_person[a] in below:
                below_rows.extend(person_rows.get(a, ()))
    unid_rows = sorted(i for a in unidentified for i in person_rows.get(a, ()))
    return PersonK(per_person, sorted(below_rows), len(unidentified), unid_rows)


@register(name=PERSON_K, version="1.0.0", scope="producer", unit="persons")
def run_person_k(release, contract, context) -> Outcome:
    context = context or {}
    k = _k(contract, context)
    needed = ("source", "rowmaps", "record_keys", "person")
    if k is None or any(context.get(n) is None for n in needed):
        return Outcome.not_run()
    if context["person"].get("normalise") is None:  # identity canonicaliser not supplied
        return Outcome.not_run()
    res = person_k_values(release, contract, context)
    n = len(res.per_person) + res.unidentified
    if n == 0:
        raise CheckError("no persons in release")
    below = sum(1 for v in res.per_person.values() if v < k)
    pt = context["person"]["table"]
    cols = "+".join(qi_by_table(contract).get(pt, [])) or "*"
    vs = []
    if below:  # count = persons below k
        vs.append(viol(PERSON_K, LABEL, f"{pt}.csv", cols, below, res.below_rows))
    if res.unidentified:  # count = unidentified units
        vs.append(viol(PERSON_K, UNIDENTIFIED, f"{pt}.csv", cols, res.unidentified, res.unidentified_rows))
    return Outcome(n=n, violations=tuple(vs))


@register(name=ROW_K, version="1.0.0", scope="release", unit="rows")
def run_row_k(release, contract, context) -> Outcome:
    """Rows of each table whose QI combination occurs fewer than k times (release only)."""
    k = _k(contract, context)
    if k is None:
        return Outcome.not_run()
    release_dir(release)
    qis = qi_by_table(contract)
    if not qis:
        raise CheckError("no QIs declared while k is required")
    n = 0
    vs = []
    for t, cols in qis.items():
        df = read_table(release, t)
        if any(c not in df.columns for c in cols):
            raise CheckError("contract QI column missing from released table")
        n += len(df)
        sizes = df.groupby(cols, sort=False, dropna=False)[cols[0]].transform("size")
        rows = [int(i) for i in (sizes < k).to_numpy().nonzero()[0]]
        if rows:
            vs.append(viol(ROW_K, LABEL, f"{t}.csv", "+".join(cols), len(rows), rows))
    if n == 0:
        raise CheckError("no released rows under QIs")
    return Outcome(n=n, violations=tuple(vs))
