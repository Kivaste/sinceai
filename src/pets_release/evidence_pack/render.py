"""One section model, shared by the offline HTML and Markdown renderers."""
from __future__ import annotations

import json
from html import escape

from pets_release.run.purpose import THRESHOLD

HEADINGS = (
    "Purpose and recipient", "Legal basis and DPIA", "Method and parameters",
    "Measured re-identification risk against stated attackers", "Utility justification",
    "Residual risks", "Reproducibility and integrity",
)
CONTROLLER = "To be supplied by the data controller"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _measurement(value):
    if value.get("status") == "not_measured":
        return "not measured: " + value["reason"]
    return _json(value)


def _score(value, reason):
    return str(value) if value is not None else "not measured: " + reason


def _digest(value):
    # Explicitly grouped metadata, not a row token. Rejoin the slash-separated groups to reproduce the digest.
    return " / ".join(value[i:i + 4] for i in range(0, len(value), 4))


def sections(m):
    """Only manifest fields are evidence; product threshold is explicitly labelled."""
    release, measured = m["release"], m["measured"]
    purpose = [("Scenario", release["scenario"]), ("Recipient", release["recipient"]),
               ("Trust level", "not measured: not recorded in the signed manifest")]
    for key in ("fitFor", "notFitFor"):
        purpose += [(key, _json(m[key]))]
    method = [("k target", str(m["contract"].get("k", "not measured: no k target in the signed manifest"))),
              ("ε", "no differential privacy used")]
    for f in m["fieldJustifications"]:
        method.append((f'{f["table"]}.{f["column"]}', _json(f)))
    for pet in m["pets"]:
        method.append((f'{pet["table"]}.{pet["column"]}: {pet["pet"]}', _json(pet["params"])))
    method += [("Keyed pseudonym scopes", _json(m["contract"]["tokens"]))]
    method += [("Local suppression", _json([p for p in m["pets"] if p["pet"] == "local_suppression"])
                or "not measured")]
    privacy = measured["privacy"]
    risk = [("Privacy measurements", _measurement(privacy))]
    missing_reason = privacy.get("reason", "not recorded in the signed manifest")
    for label in ("k on scenario QIs", "k on all kept catalogued QIs"):
        risk.append((label, "not measured: " + missing_reason))
    if privacy["status"] == "measured":
        for c in privacy["components"]:
            risk.append((c["component"], f'before={_score(c["before"], missing_reason)}; '
                         f'after={_score(c["after"], missing_reason)}; source={privacy["source"]}'))
    for r in m["residualRisks"]:
        if r["kind"] in ("linkage", "attribute_inference"):
            risk.append((r["risk"], r["description"] + "; " + _measurement(r["rate"])))
    utility = [("Purpose checks", _measurement(measured["utility"]))]
    if measured["utility"]["status"] == "measured":
        sacrifices = {s["check"]: s for s in m["sacrifices"]}
        for task in measured["utility"]["tasks"]:
            score = task["after"]
            if task["status"] != "ok":
                status = "failed"
            elif score is None:
                status = "not measured"
            elif score >= THRESHOLD:
                status = "met"
            elif task["task"] in sacrifices and score >= sacrifices[task["task"]]["floor"]:
                status = "accepted sacrifice"
            else:
                status = "failed"
            reason = "not recorded in the signed manifest; " + measured["utility"]["source"]
            utility.append((task["task"], f'{status}; before={_score(task["before"], reason)}; '
                            f'after={_score(score, reason)}'))
    utility += [("Product purpose threshold (not a measured value)", str(THRESHOLD)),
                ("Sacrifices", _json(m["sacrifices"]))]
    residual = [(r["risk"], _json(r)) for r in m["residualRisks"]]
    integrity = [("Digest notation", "Hex groups separated by /; remove spaces and slashes to reconstruct"),
                 ("Tool revision", _digest(m["bindings"]["toolRevision"])),
                 ("Input digests", _json({k: _digest(v) for k, v in m["bindings"]["inputs"].items()})),
                 ("Bound release file digests", _json({k: _digest(v) for k, v in m["bindings"]["files"].items()})),
                 ("Signature status", "HMAC-SHA256 verified with the controller key; schema and contract digest checked"),
                 ("Verification scope", "Manifest only; release files, input digests and gate checks not re-run"),
                 ("Recipient verification", 'pets-release verify "<release>"'),
                 ("Controller verification", 'pets-release verify --full --kit "<kit>" "<release>"')]
    bodies = (purpose, [("Legal basis", CONTROLLER), ("DPIA", CONTROLLER)], method, risk, utility, residual, integrity)
    return [(heading, body) for heading, body in zip(HEADINGS, bodies)]


def render(m):
    """Return deterministic HTML and Markdown, escaping manifest prose in both."""
    html = ['<!doctype html><html lang="en"><meta charset="UTF8"><title>Evidence pack</title>',
            '<body><h1>DPO / Findata evidence pack</h1>',
            '<p>Technical evidence, not a DPIA, legal opinion, permit or anonymity certification.</p>']
    md = ["# DPO / Findata evidence pack", "", "Technical evidence, not a DPIA, legal opinion, permit or anonymity certification.", ""]
    for i, (heading, rows) in enumerate(sections(m), 1):
        html.append(f'<section id="section-{i}"><h2>{i}. {heading}</h2><dl>')
        md += [f"## {i}. {heading}", ""]
        for label, value in rows:
            html.append(f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>")
            md += [f"- {escape(label)}: {escape(value)}"]
        html.append("</dl></section>")
        md.append("")
    html.append("</body></html>")
    return "\n".join(html) + "\n", "\n".join(md)
