"""Build per-section view models from manifest keys and render them.

Each section reads only its mapped manifest keys (spec table). A key that is absent shows "missing"; a
``measured.*`` value with status ``not_measured`` shows "not yet measured" with its reason. Nothing is invented.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from jinja2 import Environment, StrictUndefined

from pets_release.dashboard.templates import PAGE

MISSING = object()


def _get(m: dict, *path: str) -> Any:
    node: Any = m
    for p in path:
        if not isinstance(node, dict) or p not in node:
            return MISSING
        node = node[p]
    return node


class Block:
    """One mapped manifest key: ``ok`` (data usable), ``missing`` (absent) or ``unmeasured`` (not_measured)."""

    def __init__(self, key: str, value: Any):
        self.key = key
        self.value = value
        self.reason = ""
        if value is MISSING:
            self.state = "missing"
        elif isinstance(value, dict) and value.get("status") == "not_measured":
            self.state = "unmeasured"
            self.reason = str(value.get("reason", ""))
        else:
            self.state = "ok"

    @property
    def ok(self) -> bool:
        return self.state == "ok"


def _params(p: Any) -> str:
    return ", ".join(f"{k}={p[k]}" for k in sorted(p)) if isinstance(p, dict) else ""


def _rate(r: Any) -> str:
    if not isinstance(r, dict):
        return ""
    if r.get("status") == "measured":
        d = r.get("denominator") or {}
        return f"{r.get('value')} (n={d.get('n')} {d.get('unit', '')})".strip()
    return f"{str(r.get('status', '')).replace('_', ' ')}: {r.get('reason', '')}"


def _status(blocks: list[Block]) -> str:
    states = {b.state for b in blocks}
    return "missing" if "missing" in states else "unmeasured" if "unmeasured" in states else "complete"


def _s1(m: dict) -> dict:
    b = Block("inventory", _get(m, "inventory"))
    rows, roles = [], {}
    if b.ok:
        rows = sorted(b.value, key=lambda r: (r["table"], r["column"]))
        for r in rows:
            roles[r["role"]] = roles.get(r["role"], 0) + 1
    return {"blocks": [b], "rows": rows, "roles": sorted(roles.items())}


def _s2(m: dict) -> dict:
    bp, bf, bc = Block("pets", _get(m, "pets")), Block("fieldJustifications", _get(m, "fieldJustifications")), \
        Block("contract", _get(m, "contract"))
    pets = {(p["table"], p["column"]): p for p in bp.value} if bp.ok else {}
    rows = []
    if bf.ok:
        for f in bf.value:
            p = pets.get((f["table"], f["column"]))
            form, cparams = "", ""
            if bc.ok and f.get("outputColumn"):
                col = bc.value.get("files", {}).get(f["table"] + ".csv", {}).get("columns", {}).get(f["outputColumn"])
                if col:
                    form, cparams = col["form"], _params(col.get("params"))
            rows.append({**f, "pet": p["pet"] if p else "", "petParams": _params(p.get("params")) if p else "",
                         "form": form, "formParams": cparams})
        rows.sort(key=lambda r: (r["table"], r["column"]))
    return {"blocks": [bp, bf, bc], "rows": rows}


def _s3(m: dict, files_base: str) -> dict:
    bc, bfiles = Block("contract", _get(m, "contract")), Block("bindings.files", _get(m, "bindings", "files"))
    bg, ba, be = Block("gate", _get(m, "gate")), Block("exportAssertions", _get(m, "exportAssertions")), \
        Block("assertionEvidence", _get(m, "assertionEvidence"))
    forms, files, checks, asserts = [], [], [], []
    if bc.ok:
        for fname in sorted(bc.value.get("files", {})):
            spec = bc.value["files"][fname]
            for col in sorted(spec["columns"]):
                c = spec["columns"][col]
                forms.append({"file": fname, "column": col, "form": c["form"], "params": _params(c.get("params")),
                              "required": col in spec.get("required", [])})
    if bfiles.ok:
        base = files_base.rstrip("/") or "."
        files = [{"name": n, "href": f"{base}/{n}", "sha256": bfiles.value[n]} for n in sorted(bfiles.value)]
    if bg.ok:
        checks = sorted(bg.value.get("checks", []), key=lambda c: c["check"])
    if ba.ok:
        ev = be.value if be.ok else {}
        for name in sorted(ba.value):
            e = ev.get(name)
            asserts.append({"name": name, "value": ba.value[name], "has_evidence": e is not None,
                            "scope": e["scope"] if e else "", "check": e["check"] if e else "",
                            "version": e["version"] if e else "", "hits": e["hits"] if e else "",
                            "n": e["denominator"]["n"] if e else "", "unit": e["denominator"]["unit"] if e else "",
                            "status": e["status"] if e else ""})
    return {"blocks": [bc, bfiles, bg, ba, be], "forms": forms, "files": files, "checks": checks,
            "gate_status": bg.value.get("status") if bg.ok else "", "asserts": asserts}


def _s4(m: dict) -> dict:
    bu, bs = Block("measured.utility", _get(m, "measured", "utility")), Block("sacrifices", _get(m, "sacrifices"))
    tasks = sorted(bu.value["tasks"], key=lambda t: t["task"]) if bu.ok else []
    sac = bs.value if bs.ok else []
    return {"blocks": [bu, bs], "tasks": tasks, "sacrifices": sac}


def _s5(m: dict) -> dict:
    br, bf, bn = Block("release", _get(m, "release")), Block("fitFor", _get(m, "fitFor")), \
        Block("notFitFor", _get(m, "notFitFor"))
    bk, bp = Block("residualRisks", _get(m, "residualRisks")), Block("measured.privacy", _get(m, "measured", "privacy"))
    risks = [{**r, "rate_text": _rate(r.get("rate"))} for r in bk.value] if bk.ok else []
    return {"blocks": [br, bf, bn, bk, bp], "release": br.value if br.ok else {}, "fit": bf.value if bf.ok else [],
            "notfit": bn.value if bn.ok else [], "risks": risks,
            "components": sorted(bp.value["components"], key=lambda c: c["component"]) if bp.ok else []}


def _baselines(m: dict) -> dict:
    b = Block("measured.baselines", _get(m, "measured", "baselines"))
    metrics: dict[str, dict[str, Any]] = {}
    if b.ok:
        for r in b.value["rows"]:
            metrics.setdefault(r["metric"], {})[r["baseline"]] = r["value"]
    names = sorted({n for v in metrics.values() for n in v}, key=lambda n: (n not in ("B0", "B2", "B2-k"), n))
    return {"blocks": [b], "names": names, "metrics": [(k, metrics[k]) for k in sorted(metrics)]}


def _chart(m: dict) -> dict:
    b = Block("measured.search", _get(m, "measured", "search"))
    out: dict[str, Any] = {"blocks": [b], "svg": None}
    if not b.ok or not b.value.get("points"):
        return out
    pts = sorted(b.value["points"], key=lambda p: p["step"])
    w, h, pad = 480, 300, 44
    xmax = max(max(p["risk"] for p in pts), 1e-9)
    ymax = max(max(p["utility"] for p in pts), 1e-9)

    def sx(v: float) -> float:
        return round(pad + (w - 2 * pad) * v / xmax, 1)

    def sy(v: float) -> float:
        return round(h - pad - (h - 2 * pad) * v / ymax, 1)

    out["svg"] = {"w": w, "h": h, "pad": pad, "xmax": xmax, "ymax": ymax,
                  "line": " ".join(f"{sx(p['risk'])},{sy(p['utility'])}" for p in pts),
                  "points": [{"x": sx(p["risk"]), "y": sy(p["utility"]), "accepted": p["accepted"],
                              "step": p["step"]} for p in pts]}
    out["summary"] = {k: b.value.get(k) for k in ("candidates", "accepted", "boundReached")}
    return out


_ENV = Environment(autoescape=True, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
_ENV.filters["fmt"] = lambda v: f"{v:.3g}" if isinstance(v, float) else str(v)
_TEMPLATE = _ENV.from_string(PAGE)


def render_html(manifest: dict, files_base: str = ".") -> str:
    secs = {1: _s1(manifest), 2: _s2(manifest), 3: _s3(manifest, files_base), 4: _s4(manifest), 5: _s5(manifest)}
    for s in secs.values():
        s["status"] = _status(s["blocks"])
    extra = {"baselines": _baselines(manifest), "chart": _chart(manifest)}
    for s in extra.values():
        s["status"] = _status(s["blocks"])
    release = _get(manifest, "release")
    return _TEMPLATE.render(secs=secs, extra=extra, release=release if release is not MISSING else {},
                            schema_version=_get(manifest, "schemaVersion") if _get(manifest, "schemaVersion")
                            is not MISSING else "")


def render_csv(manifest: dict) -> str:
    """Aggregate before/after numbers only: kind, name, before, after (baselines have no before)."""
    rows: list[list[str]] = []
    u = Block("u", _get(manifest, "measured", "utility"))
    if u.ok:
        rows += [["utility", t["task"], str(t["before"]), str(t["after"])]
                 for t in sorted(u.value["tasks"], key=lambda t: t["task"])]
    p = Block("p", _get(manifest, "measured", "privacy"))
    if p.ok:
        rows += [["privacy", c["component"], str(c["before"]), str(c["after"])]
                 for c in sorted(p.value["components"], key=lambda c: c["component"])]
    b = Block("b", _get(manifest, "measured", "baselines"))
    if b.ok:
        rows += [["baseline", f"{r['baseline']}/{r['metric']}", "", str(r["value"])]
                 for r in sorted(b.value["rows"], key=lambda r: (r["baseline"], r["metric"]))]
    s = Block("s", _get(manifest, "sacrifices"))
    if s.ok:
        rows += [["sacrifice", r["check"], str(r["before"]), str(r["after"])]
                 for r in sorted(s.value, key=lambda r: r["check"])]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["kind", "name", "before", "after"])
    w.writerows(rows)
    return buf.getvalue()
