"""Content-free choose, live progress and result pages. No external assets."""
from jinja2 import Environment, StrictUndefined

ENV = Environment(autoescape=True, undefined=StrictUndefined)

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
{% if view == 'choose' %}
<div class="eyebrow">Purpose first. Proof included.</div>
<h1>Share for a purpose.<br>Prove what leaves.</h1>
<p class="intro">Choose a sharing scenario. Release only the detail it needs, then independently re-check the privacy proof.</p>
<div class="grid">
{% for s in scenarios %}<section class="card">
<span class="tag">{{ s.scenario }}</span><h2>{{ 'Emergency care research' if s.scenario == 'HEALTH-S1' else 'Contact-centre analytics' }}</h2>
<p class="muted">To {{ s.recipient }} · {{ 'Controlled research' if s.scenario == 'HEALTH-S1' else 'Redacted free text' }}</p>
<h3>Purpose checks</h3>{% for check in s.purposeChecks %}<span class="tag">{{ check }}</span>{% endfor %}
<p>{{ 'Study crowding, diagnosis groups, revisits and lab relationships without sharing direct identifiers.' if s.scenario == 'HEALTH-S1' else 'Analyse contact reasons and handling time while redacting sensitive spans and withholding the customer table.' }}</p>
<h3>Privacy floors</h3><p class="muted">{% for target in s.privacyTargets %}{{ target.kind | replace('_',' ') }}{% if target.k is defined %} ≥ {{ target.k }} per {{ target.unit }}{% endif %}{% if target.min is defined %} ≥ {{ target.min }}{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}</p>
<details><summary>{{ s.floors | length }} field floors from the scenario policy</summary><table><tr><th>Field</th><th>Floor</th></tr>{% for f in s.floors %}<tr><td>{{ f.table }}.{{ f.column }}</td><td>{{ f.floor }}</td></tr>{% endfor %}</table></details>
<details><summary>Allowed sacrifices</summary>{% for sacrifice in s.sacrifices %}<p>{{ sacrifice.check }} · fixed floor {{ sacrifice.floor_score }}<br><span class="muted">{{ sacrifice.reason }}</span></p>{% else %}<p>None</p>{% endfor %}</details>
<button data-scenario="{{ s.scenario }}">Run scenario →</button>
</section>{% endfor %}</div><p id="error" role="alert"></p>
{% else %}
<div class="eyebrow">{{ result.scenario | default('Sharing scenario') }} · Release proof</div>
<h1>{{ result.status }}</h1><p class="intro">{% if result.status == 'RELEASED' %}The gate passed. Both verification tiers re-ran on this release.{% elif result.status == 'RUNNING' %}Running the production CLI locally. Unknown is never a pass.{% elif result.status == 'REFUSED' %}The candidate was refused. Nothing was published.{% elif result.status == 'IDLE' %}Choose a sharing scenario to begin.{% else %}A step failed or could not complete. This is not a verified release.{% endif %}</p>
<ol class="steps">{% for step in result.steps %}<li class="{{ 'done' if step.exit == 0 else '' }}">{{ step.name }} · {{ 'passed' if step.exit == 0 else ('running' if step.exit is none and result.status == 'RUNNING' else 'failed') }}</li>{% endfor %}</ol>
{% if result.gate is defined %}<div class="stats">
<section class="card"><div class="eyebrow">Gate</div><div class="value">{{ result.gate.passed }}/{{ result.gate.total }}</div><div class="muted">checks completed</div></section>
<section class="card"><div class="eyebrow">Person k</div><div class="value">{{ result.personK.minK if result.personK else 'N/A' }}</div><div class="muted">{{ 'minimum group size' if result.personK else 'not a scenario target' }}</div></section>
<section class="card"><div class="eyebrow">Recipient verification</div><div class="value">{{ 'Limited' if result.steps | length > 1 and result.steps[1].exit == 0 else 'Pending' }}</div><div class="muted">producer claims remain attested</div></section>
<section class="card"><div class="eyebrow">Controller verification</div><div class="value">{{ 'Full' if result.steps | length > 2 and result.steps[2].exit == 0 else 'Pending' }}</div><div class="muted">kit + key, server-side only</div></section></div>
<div class="grid"><section class="card"><h2>Purpose, before &amp; after</h2>
{% if result.measured.utility.tasks is defined %}<table><tr><th>Purpose check</th><th>Before</th><th>After</th><th>Status</th></tr>{% for task in result.measured.utility.tasks %}<tr><td>{{ task.task }}</td><td>{{ task.before }}</td><td>{{ task.after }}</td><td>{{ task.status }}</td></tr>{% endfor %}</table>{% else %}<p class="muted">{{ result.measured.utility.status | replace('_',' ') }}</p>{% endif %}
<details><summary>Sacrifices ({{ result.sacrifices | length }})</summary><pre>{{ result.sacrifices | tojson(indent=2) }}</pre></details></section>
<section class="card"><h2>Export assertions</h2><p class="muted">Narrow claims, each bound to its own check.</p><table><tr><th>Assertion</th><th>Check / scope</th><th>Hits</th></tr>{% for name, evidence in result.assertionEvidence.items() %}<tr><td>{{ name }}</td><td>{{ evidence.check }}<br><span class="muted">{{ evidence.scope }}</span></td><td>{{ evidence.hits }}</td></tr>{% endfor %}</table></section></div>
<section class="card wide"><h2>Residual risks</h2><p class="notice">Limited verification does not prove producer claims. Digests catch accidents; only full verification checks the signature.</p><details><summary>Measured risks and limitations ({{ result.residualRisks | length }})</summary><pre>{{ result.residualRisks | tojson(indent=2) }}</pre></details></section>
{% endif %}
{% if result.failures is defined %}<section class="card"><h2>Failing checks</h2><table><tr><th>Check</th><th>Status</th><th>Hits</th></tr>{% for failure in result.failures %}<tr><td>{{ failure.check }}</td><td>{{ failure.status }}</td><td>{{ failure.hits }}</td></tr>{% endfor %}</table><pre>{{ result.reasons | default([]) | tojson(indent=2) }}</pre></section>{% endif %}
{% if result.status == 'RELEASED' %}<a class="button" data-route="/dashboard">Open full dashboard →</a>{% endif %}
<a class="button" data-route="/">Choose another scenario</a>
{% endif %}
<p class="footer">No row previews. No external assets. The same input, key, creation time and revision produce the same release bytes.</p>
</main><script>
const auth = location.search;
document.querySelectorAll('[data-route]').forEach(a => a.href = a.dataset.route + auth);
document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', async () => {
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try {
    const response = await fetch('/api/run' + auth, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({scenario: button.dataset.scenario})});
    if (!response.ok) throw new Error('Run could not start');
    location.href = '/result' + auth;
  } catch (_) {
    document.getElementById('error').textContent = 'Run could not start. Check the local server and try again.';
    document.querySelectorAll('button').forEach(b => b.disabled = false);
  }
}));
{% if view == 'result' and result.status == 'RUNNING' %}setTimeout(() => location.reload(), 1000);{% endif %}
</script></body></html>'''


def choose_page(scenarios):
    return ENV.from_string(PAGE).render(view="choose", scenarios=scenarios)


def result_page(result):
    return ENV.from_string(PAGE).render(view="result", result=result)
