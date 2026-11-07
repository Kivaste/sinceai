"""`pets-release detect <dataset|csv> [--out FILE] [--format kit|unseen] [--kit PATH]`.

Prints aggregate counts to stderr and the labels to --out (or stdout). Never prints cell values.
Exit 0 success, 2 usage error or unknown state.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from pets_release.detect import inventory, serialise
from pets_release.kit import Kit, KitError, refuse_forbidden_path
from pets_release.offline import entry_point


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
        inv = inventory.detect_dataset(dataset, tables)
        text = serialise.to_unseen_csv(inv) if fmt == "unseen" else serialise.to_kit_csv(inv)
    except (KitError, ValueError, OSError, UnicodeDecodeError, pd.errors.ParserError) as e:
        print(f"pets-release detect: {e}", file=sys.stderr)
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
