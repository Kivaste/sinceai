"""Choose, aggregate proof and explicitly protected preview pages. No external assets."""
from jinja2 import Environment, StrictUndefined

from pets_release.measure.baselines import composite

ENV = Environment(autoescape=True, undefined=StrictUndefined)
DEMONSTRATIONS = {
    "risks": "Data types and privacy risks found", "pets": "PETs chosen and why",
    "protected": "The protected output", "measurements": "Measured privacy and utility",
    "limitations": "Scenario and limitations",
}

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>sinceai · Purpose-first PETs</title><style>
:root{color-scheme:light;--ink:#142d3d;--muted:#526773;--green:#08785e;--paper:#f5f6f0}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
header{padding:24px 5%;display:flex;justify-content:space-between;border-bottom:1px solid #dce2da}
.brand{font-size:25px;font-weight:800;letter-spacing:-1px}.brand span{color:var(--green)}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
main{max-width:1260px;margin:auto;padding:42px 32px}h1{font-size:clamp(32px,4vw,52px);line-height:1.1;letter-spacing:-2px;margin:12px 0 18px}
h2{font-size:23px;margin:8px 0}h3{font-size:15px;margin:22px 0 8px}.intro{max-width:730px;color:var(--muted);font-size:18px;margin-bottom:30px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:22px}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px;margin:28px 0}
.card{background:white;border:1px solid #dce2da;border-radius:16px;padding:26px;box-shadow:0 5px 20px #142d3d05}
.tag{display:inline-block;background:#e4f2eb;color:var(--green);border-radius:6px;padding:4px 9px;font-size:12px;font-weight:750;margin:0 4px 5px 0}
.tag.warn{background:#fff1de;color:#89530b}.value{font-size:30px;font-weight:750;letter-spacing:-1px}.muted{color:var(--muted)}
button,.button{display:inline-block;background:var(--ink);color:white;border:0;border-radius:8px;padding:13px 21px;font:inherit;font-weight:650;cursor:pointer;text-decoration:none;margin-top:15px}
button:hover,.button:hover{background:var(--green)}a{color:var(--green)}button:disabled{opacity:.5;cursor:wait}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e5e9e3;padding:9px 5px}th{color:var(--muted)}
details{margin-top:15px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
.steps{display:flex;gap:12px;list-style:none;padding:0;flex-wrap:wrap}.steps li{background:#e9ede6;border-radius:8px;padding:8px 15px}.steps .done{background:#e0f2e7;color:var(--green)}
.wide{margin-top:22px}.notice{border-left:3px solid var(--green);padding-left:15px}.footer{margin-top:35px;font-size:13px;color:var(--muted)}
</style></head><body>
<header><div class="brand">since<span>ai</span></div><div class="eyebrow">Local · Offline · Content-free</div></header>
<main>
{% if banner %}<p class="notice" role="status">{{ banner }}</p>{% endif %}
{% if view == 'choose' %}
<div class="eyebrow">Purpose first. Proof included.</div>
<h1>Share for a purpose.<br>Prove what leaves.</h1>
<p class="intro">Choose a sharing scenario. Release only the detail it needs, then independently re-check the privacy proof.</p>
<div class="grid">
{% for s in scenarios %}<section class="card">
<span class="tag">{{ s.scenario }}</span><h2>{{ s.title }}</h2>
{% if not s.supported %}<p class="notice">Not yet supported by this build. An attempted run will show the production CLI outcome, not a release.</p>{% endif %}
<p class="muted">To {{ s.recipient }} · {{ s.context }}</p>
<h3>Purpose checks</h3>{% for check in s.purposeChecks %}<span class="tag">{{ check }}</span>{% endfor %}
<p>{{ s.purpose }}</p>
<h3>Privacy floors</h3><p class="muted">{% for target in s.privacyTargets %}{{ target.kind | replace('_',' ') }}{% if target.k is defined %} ≥ {{ target.k }} per {{ target.unit }}{% endif %}{% if target.min is defined %} ≥ {{ target.min }}{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}</p>
<details><summary>{{ s.floors | length }} field floors from the scenario policy</summary><table><tr><th>Field</th><th>Floor</th></tr>{% for f in s.floors %}<tr><td>{{ f.table }}.{{ f.column }}</td><td>{{ f.floor }}</td></tr>{% endfor %}</table></details>
<details><summary>Allowed sacrifices</summary>{% for sacrifice in s.sacrifices %}<p>{{ sacrifice.check }} · fixed floor {{ sacrifice.floor_score }}<br><span class="muted">{{ sacrifice.reason }}</span></p>{% else %}<p>None</p>{% endfor %}</details>
<button data-scenario="{{ s.scenario }}">Run scenario →</button>
</section>{% endfor %}</div><p id="error" role="alert"></p>
{% elif view == 'demo' %}
{{ demonstration | safe }}
<a class="button" data-route="/result">Back to aggregate proof</a>
{% elif view == 'rows' %}
<h1>Protected release rows</h1><p class="notice">{{ preview.label }}</p>
<p>After protection only. Limited verification re-ran at display time. Before values are never shown as rows.</p>
{% for table in preview.tables %}<section class="card wide"><h2>{{ table.file }}</h2><div style="overflow:auto"><table><tr>{% for column in table.columns %}<th>{{ column }}</th>{% endfor %}</tr>{% for row in table.rows %}<tr>{% for value in row %}<td>{{ value }}</td>{% endfor %}</tr>{% endfor %}</table></div></section>{% endfor %}
<a class="button" data-route="/result">Back to aggregate proof</a>
{% else %}
<div class="eyebrow">{{ result.scenario | default('Sharing scenario') }} · Release proof</div>
<nav>{% for route, title in demonstrations.items() %}<a class="tag" data-route="/demo/{{ route }}">{{ loop.index }}. {{ title }}</a>{% endfor %}</nav>
<h1>{{ result.status }}</h1><p class="intro">{% if result.status == 'RELEASED' %}The gate passed. Both verification tiers re-ran on this release.{% elif result.status == 'RUNNING' %}Running the production CLI locally. Unknown is never a pass.{% elif result.status == 'REFUSED' %}The candidate was refused. Nothing was published.{% elif result.status == 'IDLE' %}Choose a sharing scenario to begin.{% else %}A step failed or could not complete. This is not a verified release.{% endif %}</p>
<ol class="steps">{% for step in result.steps %}<li class="{{ 'done' if step.exit == 0 else '' }}">{{ step.name }} · {{ 'passed' if step.exit == 0 else ('running' if step.exit is none and result.status == 'RUNNING' else 'failed') }}</li>{% endfor %}</ol>
{% if result.supported is defined and not result.supported %}<p class="notice">Not yet supported by this build. The outcome above is from the production CLI.</p>{% endif %}
{% if result.gate is defined %}<div class="stats">
<section class="card"><div class="eyebrow">Gate</div><div class="value">{{ result.gate.passed }}/{{ result.gate.total }}</div><div class="muted">checks completed</div></section>
<section class="card"><div class="eyebrow">Person k</div><div class="value">{{ result.personK.minK if result.personK else 'N/A' }}</div><div class="muted">{{ 'minimum group size' if result.personK else 'not a scenario target' }}</div></section>
<section class="card"><div class="eyebrow">Recipient verification</div><div class="value">{{ verification(result.steps, 1, 'Limited') }}</div><div class="muted">producer claims remain attested</div></section>
<section class="card"><div class="eyebrow">Controller verification</div><div class="value">{{ verification(result.steps, 2, 'Full') }}</div><div class="muted">kit + key, server-side only</div></section></div>
<div class="grid"><section class="card"><h2>Purpose, before &amp; after</h2>
{% if result.measured.utility.tasks is defined %}<table><tr><th>Purpose check</th><th>Before</th><th>After</th><th>Status</th></tr>{% for task in result.measured.utility.tasks %}<tr><td>{{ task.task }}</td><td>{{ task.before }}</td><td>{{ task.after }}</td><td>{{ task.status }}</td></tr>{% endfor %}</table>{% else %}<p class="muted">{{ result.measured.utility.status | replace('_',' ') }}</p>{% endif %}
<details><summary>Sacrifices ({{ result.sacrifices | length }})</summary><pre>{{ result.sacrifices | tojson(indent=2) }}</pre></details></section>
<section class="card"><h2>Export assertions</h2><p class="muted">Narrow claims, each bound to its own check.</p><table><tr><th>Assertion</th><th>Check / scope</th><th>Hits</th></tr>{% for name, evidence in result.assertionEvidence.items() %}<tr><td>{{ name }}</td><td>{{ evidence.check }}<br><span class="muted">{{ evidence.scope }}</span></td><td>{{ evidence.hits }}</td></tr>{% endfor %}</table></section></div>
<section class="card wide"><h2>Residual risks</h2><p class="notice">Limited verification does not prove producer claims. Digests catch accidents; only full verification checks the signature.</p><details><summary>Measured risks and limitations ({{ result.residualRisks | length }})</summary><pre>{{ result.residualRisks | tojson(indent=2) }}</pre></details></section>
{% endif %}
{% if result.failures is defined %}<section class="card"><h2>Failing checks</h2>{% if not result.refusalReportAvailable %}<p>No refusal report available. Failing check names and counts are unknown.</p>{% elif result.failures %}<table><tr><th>Check</th><th>Status</th><th>Hits</th></tr>{% for failure in result.failures %}<tr><td>{{ failure.check }}</td><td>{{ failure.status }}</td><td>{{ failure.hits }}</td></tr>{% endfor %}</table>{% else %}<p>No gate check records available; see the pre-gate refusal reasons below.</p>{% endif %}<pre>{{ result.reasons | default([]) | tojson(indent=2) }}</pre></section>{% endif %}
{% if result.targets is defined %}<section class="card wide"><h2>Targets met / not met</h2><p>Strict utility targets and allowed sacrifice floors are separate. Unknown is never met.</p><table><tr><th>Privacy floor / utility threshold</th><th>Target</th><th>Measured</th><th>Outcome</th></tr>{% for target in result.targets %}<tr><td>{{ target.name }}</td><td>{{ target.threshold }}</td><td>{{ target.measured if target.measured is not none else 'not measured' }}</td><td>{{ target.status }}</td></tr>{% endfor %}</table></section>{% endif %}
{% if result.status == 'RELEASED' %}<a class="button" data-route="/dashboard">Open full dashboard →</a><a class="button" data-route="/rows">Protected release rows →</a>{% endif %}
<a class="button" data-route="/">Choose another scenario</a>
{% endif %}
<p class="footer">No raw row previews. No external assets. The same input, key, creation time and revision produce the same release bytes.</p>
</main><script>
const auth = location.search;
document.querySelectorAll('[data-route]').forEach(a => a.href = a.dataset.route + auth);
document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', async () => {
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try {
    const response = await fetch('/api/run' + auth, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({scenario: button.dataset.scenario})});
    if (response.status === 409) throw new Error('Busy, run in progress');
    if (!response.ok) throw new Error('Run could not start');
    location.href = '/result' + auth;
  } catch (error) {
    document.getElementById('error').textContent = error.message === 'Busy, run in progress' ? error.message : 'Run could not start. Check the local server and try again.';
    document.querySelectorAll('button').forEach(b => b.disabled = false);
  }
}));
{% if view == 'result' and result.status == 'RUNNING' %}setTimeout(() => location.reload(), 1000);{% endif %}
</script></body></html>'''


def choose_page(scenarios, banner=""):
    return ENV.from_string(PAGE).render(view="choose", scenarios=scenarios, banner=banner)


def result_page(result, banner=""):
    return ENV.from_string(PAGE).render(view="result", result=result, verification=verification,
                                      demonstrations=DEMONSTRATIONS, banner=banner)


def verification(steps, index, success):
    if len(steps) <= index:
        return "Pending"
    code = steps[index]["exit"]
    return success if code == 0 else ("Running" if code is None else "Failed")


def rows_page(preview, banner=""):
    return ENV.from_string(PAGE).render(view="rows", preview=preview, banner=banner)


DEMO = r'''
{% macro value(v) %}{{ v if v is not none else 'not measured' }}{% endmacro %}
<div class="eyebrow">{{ result.scenario | default('Sharing scenario') }} · {{ result.status }}</div>
<nav>{% for route, title in demonstrations.items() %}<a class="tag" data-route="/demo/{{ route }}">{{ loop.index }}. {{ title }}</a>{% endfor %}</nav>
<h1>{{ demonstrations[item] }}</h1>
{% if item == 'risks' %}
<section class="card"><h2>Production detector</h2><p>Observed field roles from the production detect command; not policy-assigned roles.</p>
<table><tr><th>Field</th><th>Role</th><th>Subtype</th></tr>{% for f in result.get('detectedInventory', []) %}<tr><td>{{ f.table }}.{{ f.column }}</td><td>{{ f.privacy_role }}</td><td>{{ f.subtype }}</td></tr>{% else %}<tr><td colspan="3">not measured — detector unavailable or not run</td></tr>{% endfor %}</table></section>
<section class="card wide"><h2>Baseline privacy and k distribution</h2><p>Baseline attacker linkage rates, person-k distribution and scorecard privacy before protection: not measured unless supplied below. A successful gate is not a baseline measurement.</p>
{% for component in measured.get('privacy', {}).get('components', []) %}<p>{{ component.component }} · Before {{ value(component.before) }} · After {{ value(component.after) }}</p>{% endfor %}
{% for row in measured.get('baselines', {}).get('rows', []) %}<p>{{ row.baseline }} · {{ row.metric }} · {{ value(row.value) }}</p>{% endfor %}
<h3>Attacker linkage rates</h3>{% for risk in result.get('residualRisks', []) if risk.kind == 'linkage' %}<pre>{{ risk.rate | tojson(indent=2) }}</pre>{% else %}<p>not measured</p>{% endfor %}</section>
{% elif item == 'pets' %}
<section class="card"><p>Purpose checks: {{ policy.get('purposeChecks', []) | join(', ') }}. Each field's reason identifies the check it serves, or why it is withheld.</p><table><tr><th>Field</th><th>PET</th><th>Detail level</th><th>Justification / purpose served</th></tr>
{% for f in result.get('fieldJustifications', []) %}<tr><td>{{ f.table }}.{{ f.column }}</td><td>{% for pet in result.get('pets', []) if pet.table == f.table and pet.column == f.column %}{{ pet.pet }} {{ pet.params }}<br>{% endfor %}</td><td>{{ f.rung }}</td><td>{{ f.reason }}</td></tr>{% else %}<tr><td colspan="4">No published field justifications available</td></tr>{% endfor %}</table></section>
{% elif item == 'protected' %}
<section class="card"><p>Before is schema detail only, never source rows. After comes from fieldJustifications in the published manifest.</p><table><tr><th>Field</th><th>Before (field level only)</th><th>After</th><th>Reason / trade-off</th></tr>
{% for f in result.get('fieldJustifications', []) %}<tr><td>{{ f.table }}.{{ f.column }}</td><td>source {{ families.get(f.table ~ '.' ~ f.column, 'field') }}</td><td>{{ f.rung }}{% if f.outputColumn %} → {{ f.outputColumn }}{% endif %}</td><td>{{ f.reason }}</td></tr>{% else %}<tr><td colspan="4">No protected release available</td></tr>{% endfor %}</table></section>
{% if result.status == 'RELEASED' %}<a class="button" data-route="/rows">Protected release rows (fresh verify required) →</a>{% endif %}
{% elif item == 'measurements' %}
<section class="card"><h2>pets-eval scorecard, before &amp; after</h2><p>Privacy measurement: {{ measured.get('privacy', {}).get('status', 'not_measured') | replace('_', ' ') }}</p><p>Summary reconstructed from the production manifest's measured task scores and risk components, rounded to the scorecard's four decimals. Utility is the mean scenario task score; composite is the weighted harmonic mean (30 privacy / 25 utility). Missing scores remain not measured.</p><table><tr><th>Score</th><th>Before</th><th>After</th></tr>
{% for name in ['privacy', 'utility', 'composite'] %}{% set component = scorecard.get(name, {}) %}<tr><td>{{ name }}</td><td>{{ value(component.get('before')) }}</td><td>{{ value(component.get('after')) }}</td></tr>{% endfor %}</table>
<h3>Measured risk components (including attacker rates when available)</h3><table><tr><th>Component</th><th>Before</th><th>After</th></tr>{% for component in measured.get('privacy', {}).get('components', []) %}<tr><td>{{ component.component }}</td><td>{{ value(component.before) }}</td><td>{{ value(component.after) }}</td></tr>{% else %}<tr><td colspan="3">not measured</td></tr>{% endfor %}</table>
<h3>Attacker linkage rates</h3><table><tr><th>Component</th><th>Before</th><th>After</th></tr>{% for component in measured.get('privacy', {}).get('components', []) if component.component == 'linkage_reid' or (component.component.startswith('risk.') and 'linkage' in component.component) %}<tr><td>{{ component.component }}</td><td>{{ value(component.before) }}</td><td>{{ value(component.after) }}</td></tr>{% else %}<tr><td colspan="3">not measured</td></tr>{% endfor %}</table>
<h3>Person-k after protection</h3>{% if result.get('personK') %}<pre>{{ result.personK | tojson(indent=2) }}</pre>{% else %}<p>not measured</p>{% endif %}
<h3>Purpose-check scores</h3><table><tr><th>Check</th><th>Before</th><th>After</th><th>Status</th></tr>{% for task in measured.get('utility', {}).get('tasks', []) %}<tr><td>{{ task.task }}</td><td>{{ value(task.before) }}</td><td>{{ value(task.after) }}</td><td>{{ task.status }}</td></tr>{% else %}<tr><td colspan="4">not measured</td></tr>{% endfor %}</table></section>
<section class="card wide"><h2>Targets met / not met</h2><p>Strict targets and allowed sacrifice floors are separate.</p><table><tr><th>Target</th><th>Threshold</th><th>Measured</th><th>Outcome</th></tr>{% for t in result.get('targets', []) %}<tr><td>{{ t.name }}</td><td>{{ t.threshold }}</td><td>{{ value(t.measured) }}</td><td>{{ t.status }}</td></tr>{% endfor %}</table></section>
{% elif item == 'limitations' %}
<section class="card"><h2>Recipient, purpose and Trust context</h2><p>Recipient: {{ policy.get('recipient', 'not available') }}</p><p>Purpose: {{ policy.get('purpose', 'not available') }}</p><p>Trust: {{ policy.get('trust', 'not available') }}</p><h3>Not-fit-for uses</h3>{% for use in result.get('notFitFor', []) %}<p>{{ use.scenario }} · {{ use.reason }}</p>{% else %}<p>No published fit-for assessment available</p>{% endfor %}</section>
<section class="card wide"><h2>Sacrifices</h2><p>Scores, rung changes, fallback counts and checker-independence limitations are shown only when recorded by the production manifest. No fallback is assumed from a successful status.</p><pre>{{ result.get('sacrifices', []) | tojson(indent=2) }}</pre><h2>Residual risks</h2><pre>{{ result.get('residualRisks', []) | tojson(indent=2) }}</pre></section>
<section class="card wide"><h2>Proof and honest refusal</h2>{% if result.get('gate') %}<p>Gate {{ result.gate.passed }}/{{ result.gate.total }}</p>{% endif %}<p>Limited verify: {{ verification(result.steps, 1, 'passed (limited)') }} · Full verify: {{ verification(result.steps, 2, 'passed (full)') }}</p>
{% if result.status == 'REFUSED' or result.status == 'FAILED' %}<h3>Failing checks</h3>{% if not result.get('refusalReportAvailable') %}<p>No refusal report available. Failing check names and counts are unknown.</p>{% endif %}{% for f in result.get('failures', []) %}<p>{{ f.check }} · {{ f.status }} · hits {{ f.hits }}</p>{% endfor %}<pre>{{ result.get('reasons', []) | tojson(indent=2) }}</pre>{% endif %}<p>Limited verification does not prove producer claims. Only full verification checks the signature.</p></section>
{% endif %}'''


def demonstration_page(result, item, banner=""):
    policy = result.get("policy", {})
    measured = result.get("measured", {})
    scorecard = {c["component"]: c for c in measured.get("privacy", {}).get("components", [])
                 if c["component"] in {"privacy", "utility", "composite"}}
    # The closed measured manifest stores task scores, not utility/composite summary fields.
    # Reconstruct the scorecard summary without reading private raw scorecard files.
    required = policy.get("purposeChecks", [])
    utility = measured.get("utility", {})
    tasks = {t["task"]: t for t in utility.get("tasks", [])}
    if (measured.get("privacy", {}).get("status") == utility.get("status") == "measured"
            and required and all(t in tasks and tasks[t]["status"] == "ok" for t in required)):
        for side in ("before", "after"):
            scores = [t[side] for t in tasks.values()]
            risks = [c[side] for c in measured["privacy"]["components"]
                     if c["component"].startswith("risk.") and c[side] is not None]
            if scores and all(s is not None for s in scores) and risks:
                mean = sum(scores) / len(scores)
                # Use unrounded privacy for the composite, just as pets-eval does.
                privacy = 1 - (0.5 * max(risks) + 0.5 * sum(risks) / len(risks))
                scorecard.setdefault("utility", {})[side] = round(mean, 4)
                scorecard.setdefault("composite", {})[side] = round(composite(privacy, mean), 4)
    families = {f["table"] + "." + f["column"]: f["family"] for f in policy.get("floors", [])}
    content = ENV.from_string(DEMO).render(result=result, item=item, demonstrations=DEMONSTRATIONS,
                                         policy=policy, measured=measured, families=families,
                                         scorecard=scorecard, verification=verification)
    return ENV.from_string(PAGE).render(view="demo", demonstration=content, banner=banner)
