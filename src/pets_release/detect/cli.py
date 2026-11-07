"""`pets-release detect <dataset|csv> [--out FILE] [--format kit|unseen] [--kit PATH]`.

Prints aggregate counts to stderr and the labels to --out (or stdout). Never prints cell values.
Exit 0 success, 2 usage error or unknown state.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from pets_release.detect import inventory, serialise
from pets_release.kit import Kit, KitError, refuse_forbidden_path
from pets_release.offline import entry_point


# A header cell must look like a schema identifier, never a value: ASCII identifier, at most 64 chars, no
# run of 4+ digits (IDs, HETU, phone, dates). A headerless CSV's first row (names, emails, HETUs) fails this.
# Residual risk: a first row whose every cell is itself identifier-shaped (e.g. a bare code) passes.
_HEADER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_DIGIT_RUN_RE = re.compile(r"[0-9]{4}")


def bad_header_cells(columns) -> int:
    """Number of header cells that are not schema identifiers (count only; never the cells)."""
    return sum(1 for c in columns
               if not isinstance(c, str) or not _HEADER_RE.fullmatch(c) or _DIGIT_RUN_RE.search(c))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


@entry_point
def main(argv: list[str]) -> int:
    p = _Parser(prog="pets-release detect", description="detect column roles in a kit dataset or a CSV")
    p.add_argument("target", help="kit dataset name, or path to a CSV file")
    p.add_argument("--out")
    p.add_argument("--format", choices=["kit", "unseen"])
    p.add_argument("--kit")
    a = p.parse_args(argv)

    path = Path(a.target)
    try:
        if path.suffix.lower() == ".csv" and path.is_file():
            path = refuse_forbidden_path(path)
            tables = {path.stem: pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False,
                                             encoding="utf-8")}
            dataset = "csv"
            fmt = a.format or "unseen"
        else:
            kit_path = a.kit or os.environ.get("PETS_KIT")
            if not kit_path:
                print("pets-release detect: no kit path: pass --kit or set PETS_KIT", file=sys.stderr)
                return 2
            kit = Kit(kit_path)
            dataset = a.target
            tables = kit.load_dataset(dataset)
            if not tables:
                print(f"pets-release detect: dataset {dataset!r} has no tables", file=sys.stderr)
                return 2
            fmt = a.format or ("unseen" if dataset == "unseen" else "kit")
        bad = sum(bad_header_cells(df.columns) for df in tables.values())
        if bad:
            print(f"pets-release detect: refused: header-not-identifier cells={bad} "
                  "(the first row must be a header of schema identifiers)", file=sys.stderr)
            return 2
        inv = inventory.detect_dataset(dataset, tables)
        text = serialise.to_unseen_csv(inv) if fmt == "unseen" else serialise.to_kit_csv(inv)
    except KitError as e:  # our own messages: names and paths, never cell values
        print(f"pets-release detect: {e}", file=sys.stderr)
        return 2
    except (ValueError, OSError, UnicodeDecodeError, pd.errors.ParserError) as e:
        # foreign (pandas / codec / OS) text can quote input bytes or lines: class name only
        print(f"pets-release detect: refused: {type(e).__name__}", file=sys.stderr)
        return 2

    n_cols = sum(len(df.columns) for df in tables.values())
    if len(inv) != n_cols:
        print("pets-release detect: inventory does not cover every column", file=sys.stderr)
        return 2
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8", newline="")
    else:
        sys.stdout.write(text)
    counts = Counter(r["role"] for r in inv)
    print(f"detect: {dataset} tables={len(tables)} columns={len(inv)} format={fmt} "
          + " ".join(f"{k}={counts[k]}" for k in sorted(counts)), file=sys.stderr)
    return 0
