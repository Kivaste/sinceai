"""Fill the story kit from a release manifest. Reads ONLY `<release>/privacy_manifest.json` (aggregates).

    python docs/story-kit/fill_numbers.py <release> <out_dir>

Writes `<out_dir>/numbers.csv` (template rows + `value`) and `<out_dir>/pitch-beats.md` (placeholders replaced).
A value is `—` when the manifest has the key but its value is null / `not_measured` / absent; the sentence
should then be dropped by the presenter. Numbers use one formatter: 4 decimals for scores, integers for counts.
Never types a number: every value is resolved from a manifest key path (grammar in README.md).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")
MISSING = "—"


def _find(rows, **kw):
    for r in rows:
        if all(r.get(k) == v for k, v in kw.items()):
            return r
    return None


def resolve(m: dict, path: str):
    """The raw value at `path`, or None when the key exists in the grammar but has no value."""
    s = path.split(".")
    head = s[0]
    if head == "release":
        return m["release"].get(s[1])
    if head == "sacrifices" and len(s) == 3:  # sacrifices.<check>.floor
        e = _find(m["sacrifices"], check=s[1])
        return None if e is None else e[s[2]]
    if head in ("inventory", "sacrifices"):
        return len(m[head])
    if head == "fieldJustifications":
        return sum(1 for e in m[head] if e["decision"] == s[1])
    if head == "gate":
        return sum(1 for c in m["gate"]["checks"] if c["scope"] == s[2])
    if head == "exportAssertions":
        return m[head].get(s[1])
    if head == "assertionEvidence":
        ev = m[head].get(s[1])
        if ev is None:
            return None
        return ev["hits"] if s[2:] == ["hits"] else ev["denominator"]["n"]
    if head == "measured":
        block = m["measured"][s[1]]
        if block.get("status") != "measured":
            return None
        if s[1] == "utility":
            t = _find(block["tasks"], task=s[3])
            return None if t is None or t["status"] != "ok" else t[s[2]]
        if s[1] == "privacy":
            c = _find(block["components"], component=".".join(s[3:]))
            return None if c is None else c[s[2]]
        if s[1] == "baselines":
            r = _find(block["rows"], baseline=s[2], metric=".".join(s[3:]))
            return None if r is None else r["value"]
    raise KeyError(path)


def fmt(v, unit: str) -> str:
    if v is None:
        return MISSING
    if isinstance(v, bool):
        return "true" if v is True else "false"
    if unit == "count":
        return str(int(v))
    if isinstance(v, (int, float)):
        return f"{v:.4f}"
    return str(v)


def fill(manifest: dict, template: Path = HERE / "numbers-template.csv", script: Path = HERE / "pitch-beats.md"):
    with template.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["value"] = fmt(resolve(manifest, r["manifest_key_path"]), r["unit"])
    values = {r["manifest_key_path"]: r["value"] for r in rows}
    text = PLACEHOLDER.sub(lambda mo: values[mo.group(1)], script.read_text(encoding="utf-8"))
    return rows, text


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: fill_numbers.py <release> <out_dir>", file=sys.stderr)
        return 2
    manifest = json.loads((Path(argv[0]) / "privacy_manifest.json").read_text(encoding="utf-8"))
    rows, text = fill(manifest)
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    with (out / "numbers.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["beat", "label", "manifest_key_path", "unit", "value"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (out / "pitch-beats.md").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} values, {sum(r['value'] == MISSING for r in rows)} empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
