"""The jinja2 page template, kept as a Python constant so it ships with the package without package-data config."""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>pets-release dashboard</title>
<style>
body{font:14px/1.45 system-ui,Segoe UI,sans-serif;margin:0;color:#1b1f24;background:#f6f7f9}
header{background:#14365d;color:#fff;padding:18px 28px}
header h1{margin:0 0 4px;font-size:22px} header p{margin:0;opacity:.85}
main{max-width:1100px;margin:0 auto;padding:12px 28px 48px}
section{background:#fff;border:1px solid #d9dde3;border-radius:6px;margin:18px 0;padding:14px 18px}
h2{margin:0 0 8px;font-size:18px} h3{margin:14px 0 6px;font-size:14px;color:#444}
table{border-collapse:collapse;width:100%;margin:4px 0 8px}
th,td{border-bottom:1px solid #e5e8ec;padding:4px 8px;text-align:left;vertical-align:top;font-size:13px}
th{background:#f0f2f5} code{font:12px Consolas,monospace;word-break:break-all}
.badge{display:inline-block;border-radius:10px;padding:1px 9px;font-size:12px;margin-left:8px}
.complete{background:#d7f0dd;color:#14532d} .missing{background:#fbd5d5;color:#7f1d1d}
.unmeasured{background:#fdecc8;color:#7a4b00}
.note{color:#7f1d1d;font-style:italic} .note.unmeasured{color:#7a4b00}
.scope-release{color:#14532d;font-weight:600} .scope-producer{color:#5b21b6;font-weight:600}
svg{max-width:100%;background:#fafbfc;border:1px solid #e5e8ec}
</style></head><body>
<header><h1>Privacy release dashboard</h1>
<p>Scenario {{ release.get('scenario', 'missing') }} &middot; recipient {{ release.get('recipient', 'missing') }}
&middot; created {{ release.get('created', 'missing') }} &middot; scope {{ release.get('releaseScopeId', 'missing') }}
&middot; manifest schema {{ schema_version or 'missing' }}</p>
<p>Rendered from the privacy manifest alone. Schema, value forms, counts and file links only; no row values.</p></header>
<main>
{% macro notes(blocks) %}
{% for b in blocks %}{% if b.state == 'missing' %}
<p class="note" data-key="{{ b.key }}">missing: manifest key <code>{{ b.key }}</code> is absent.</p>
{% elif b.state == 'unmeasured' %}
<p class="note unmeasured" data-key="{{ b.key }}">not yet measured: <code>{{ b.key }}</code>{% if b.reason %} ({{ b.reason }}){% endif %}.</p>
{% endif %}{% endfor %}
{% endmacro %}
{% macro badge(s) %}<span class="badge {{ s.status }}">{{ 'complete' if s.status == 'complete' else 'missing' if s.status == 'missing' else 'not yet measured' }}</span>{% endmacro %}

{% set s = secs[1] %}
<section id="item-1" data-status="{{ s.status }}"><h2>1. Data types identified {{ badge(s) }}</h2>
<p>Source: <code>inventory</code>.
{% if s.rows %}{{ s.rows|length }} columns{% for role, n in s.roles %}; {{ role }}: {{ n }}{% endfor %}.{% endif %}</p>
{{ notes(s.blocks) }}
{% if s.rows %}<table><tr><th>Table</th><th>Column</th><th>Role</th><th>Subtype</th><th>Detection evidence</th></tr>
{% for r in s.rows %}<tr><td>{{ r.table }}</td><td>{{ r.column }}</td><td>{{ r.role }}</td><td>{{ r.subtype }}</td><td>{{ r.evidence|join('; ') }}</td></tr>
{% endfor %}</table>{% endif %}</section>

{% set s = secs[2] %}
<section id="item-2" data-status="{{ s.status }}"><h2>2. PET per field type {{ badge(s) }}</h2>
<p>Sources: <code>pets</code>, <code>fieldJustifications</code>, <code>contract</code>.</p>
{{ notes(s.blocks) }}
{% if s.rows %}<table><tr><th>Table.column</th><th>Decision</th><th>PET</th><th>Rung (floor)</th><th>Output column</th><th>Value form</th><th>Why</th></tr>
{% for r in s.rows %}<tr><td>{{ r.table }}.{{ r.column }}</td><td>{{ r.decision }}</td>
<td>{{ r.pet or '-' }}{% if r.petParams %} ({{ r.petParams }}){% endif %}</td>
<td>{{ r.rung }} ({{ r.floor }}), {{ r.source }}</td><td>{{ r.outputColumn or '-' }}</td>
<td>{% if r.form %}<code>{{ r.form }}</code>{% if r.formParams %} ({{ r.formParams }}){% endif %}{% else %}-{% endif %}</td>
<td>{{ r.reason }}</td></tr>
{% endfor %}</table>{% endif %}</section>

{% set s = secs[3] %}
<section id="item-3" data-status="{{ s.status }}"><h2>3. Protected output {{ badge(s) }}</h2>
<p>Sources: <code>contract</code>, <code>bindings.files</code>, <code>gate</code>, <code>exportAssertions</code>, <code>assertionEvidence</code>.
Scope <span class="scope-release">release</span> = checked on the released files; <span class="scope-producer">producer</span> = checked on the producer side (e.g. against originals or keys), not provable from the release alone.</p>
{{ notes(s.blocks) }}
{% if s.files %}<h3>Released files</h3>
<table><tr><th>File</th><th>SHA-256</th></tr>
{% for f in s.files %}<tr><td><a href="{{ f.href }}">{{ f.name }}</a></td><td><code>{{ f.sha256 }}</code></td></tr>
{% endfor %}</table>{% endif %}
{% if s.forms %}<h3>Value forms (contract)</h3>
<table><tr><th>File</th><th>Column</th><th>Form</th><th>Params</th><th>Required</th></tr>
{% for f in s.forms %}<tr><td>{{ f.file }}</td><td>{{ f.column }}</td><td><code>{{ f.form }}</code></td><td>{{ f.params }}</td><td>{{ 'yes' if f.required else 'no' }}</td></tr>
{% endfor %}</table>{% endif %}
{% if s.qi %}<h3>Quasi-identifiers (contract)</h3>
<table><tr><th>Table</th><th>Column</th><th>Derived from</th></tr>
{% for q in s.qi %}<tr><td>{{ q.table }}</td><td>{{ q.column }}</td><td>{{ q.derived_from }}</td></tr>
{% endfor %}</table>{% endif %}
{% if s.tokens %}<h3>Tokens (contract)</h3>
<table><tr><th>Table</th><th>Column</th><th>Scope</th></tr>
{% for t in s.tokens %}<tr><td>{{ t.table }}</td><td>{{ t.column }}</td><td>{{ t.scope }}</td></tr>
{% endfor %}</table>{% endif %}
{% if s.asserts %}<h3>Export assertions</h3>
<table><tr><th>Assertion</th><th>Value</th><th>Scope</th><th>Check (version)</th><th>Hits / denominator</th><th>Status</th></tr>
{% for a in s.asserts %}<tr data-assertion="{{ a.name }}"><td>{{ a.name }}</td><td>{{ a.value|lower }}</td>
{% if a.has_evidence %}<td class="scope-{{ a.scope }}">{{ a.scope }}</td><td>{{ a.check }} ({{ a.version }})</td><td>{{ a.hits }} / {{ a.n }} {{ a.unit }}</td><td>{{ a.status }}</td>
{% else %}<td colspan="4" class="note">missing: no evidence record in <code>assertionEvidence</code></td>{% endif %}</tr>
{% endfor %}</table>{% endif %}
{% if s.checks %}<h3>Gate: {{ s.gate_status }} ({{ s.checks|length }} checks)</h3>
<table><tr><th>Check</th><th>Version</th><th>Scope</th><th>Hits / denominator</th><th>Status</th></tr>
{% for c in s.checks %}<tr><td>{{ c.check }}</td><td>{{ c.version }}</td><td class="scope-{{ c.scope }}">{{ c.scope }}</td><td>{{ c.hits }} / {{ c.denominator.n }} {{ c.denominator.unit }}</td><td>{{ c.status }}</td></tr>
{% endfor %}</table>{% endif %}</section>

{% set s = secs[4] %}
<section id="item-4" data-status="{{ s.status }}"><h2>4. Utility before and after {{ badge(s) }}</h2>
<p>Sources: <code>measured.utility</code>, <code>sacrifices</code>.</p>
{{ notes(s.blocks) }}
{% if s.tasks %}<table><tr><th>Purpose check</th><th>Before</th><th>After</th><th>Status</th></tr>
{% for t in s.tasks %}<tr><td>{{ t.task }}</td><td>{{ t.before|fmt }}</td><td>{{ t.after|fmt }}</td><td>{{ t.status }}</td></tr>
{% endfor %}</table>{% endif %}
{% if s.blocks[1].ok %}<h3>Sacrifices</h3>
{% if s.sacrifices %}<table><tr><th>Check</th><th>Floor</th><th>Before</th><th>After</th><th>Reason</th></tr>
{% for r in s.sacrifices %}<tr><td>{{ r.check }}</td><td>{{ r.floor|fmt }}</td><td>{{ r.before|fmt }}</td><td>{{ r.after|fmt }}</td><td>{{ r.reason }}</td></tr>
{% endfor %}</table>{% else %}<p>No sacrifices recorded.</p>{% endif %}{% endif %}</section>

{% set s = secs[5] %}
<section id="item-5" data-status="{{ s.status }}"><h2>5. Sharing scenario {{ badge(s) }}</h2>
<p>Sources: <code>release</code>, <code>fitFor</code>, <code>notFitFor</code>, <code>residualRisks</code>, <code>measured.privacy</code>.</p>
{{ notes(s.blocks) }}
{% if s.release %}<p>Scenario <b>{{ s.release.scenario }}</b>, recipient <b>{{ s.release.recipient }}</b>, created {{ s.release.created }}.</p>{% endif %}
{% if s.fit %}<h3>Fit for</h3><ul>{% for f in s.fit %}<li>{{ f.scenario }}: {{ f.reason }}</li>{% endfor %}</ul>{% endif %}
{% if s.blocks[2].ok %}<h3>Not fit for</h3>
{% if s.notfit %}<ul>{% for f in s.notfit %}<li>{{ f.scenario }}: {{ f.reason }}</li>{% endfor %}</ul>{% else %}<p>None recorded.</p>{% endif %}{% endif %}
{% if s.components %}<h3>Privacy before and after</h3>
<table><tr><th>Component</th><th>Before</th><th>After</th></tr>
{% for c in s.components %}<tr><td>{{ c.component }}</td><td>{{ c.before|fmt }}</td><td>{{ c.after|fmt }}</td></tr>
{% endfor %}</table>{% endif %}
{% if s.risks %}<h3>Residual risks</h3>
<table><tr><th>Risk</th><th>Kind</th><th>Rate</th><th>Description</th></tr>
{% for r in s.risks %}<tr><td>{{ r.risk }}</td><td>{{ r.kind }}</td><td>{{ r.rate_text }}</td><td>{{ r.description }}</td></tr>
{% endfor %}</table>{% endif %}</section>

{% set s = extra.baselines %}
<section id="baselines" data-status="{{ s.status }}"><h2>Baseline comparison (B0 / B2 / B2-k) {{ badge(s) }}</h2>
<p>Source: <code>measured.baselines</code>.</p>
{{ notes(s.blocks) }}
{% if s.metrics %}<table><tr><th>Metric</th>{% for n in s.names %}<th>{{ n }}</th>{% endfor %}</tr>
{% for metric, vals in s.metrics %}<tr><td>{{ metric }}</td>{% for n in s.names %}<td>{{ vals[n]|fmt if n in vals else '-' }}</td>{% endfor %}</tr>
{% endfor %}</table>{% endif %}</section>

{% set s = extra.ksets %}
<section id="k-sets" data-status="{{ s.status }}"><h2>Per-person k on both QI sets {{ badge(s) }}</h2>
<p>Source: <code>measured.kSets</code>. Target k = {{ s.k if s.k is not none else '-' }}. Before suppression: the plan applied; released: the published tables.</p>
{{ notes(s.blocks) }}
{% if s.sets %}<table><tr><th>Set</th><th>QIs</th><th>Stage</th><th>Persons</th><th>Min k</th><th>Median k</th><th>Below k</th><th>Below-k share</th></tr>
{% for x in s.sets %}{% if x.status == 'measured' %}{% for stage, v in (('before suppression', x.beforeSuppression), ('released', x.released)) %}<tr data-set="{{ x.set }}"><td>{{ x.title }}</td><td>{{ x.qi_text }}</td><td>{{ stage }}</td><td>{{ v.persons }}</td><td>{{ v.minK if v.minK is not none else '-' }}</td><td>{{ v.medianK if v.medianK is not none else '-' }}</td><td>{{ v.belowK }}</td><td>{{ v.belowKShare|fmt }}</td></tr>
{% endfor %}{% else %}<tr data-set="{{ x.set }}"><td>{{ x.title }}</td><td colspan="7" class="unmeasured">not measured: {{ x.reason }}</td></tr>
{% endif %}{% endfor %}</table>{% endif %}
{% if s.coincide %}<p class="k-sets-coincide">Sets (a) and (b) coincide: every catalogued QI outside the scenario's set is withheld (listed below).</p>{% endif %}
{% if s.blocks[0].ok %}<h3>Withheld catalogued QIs and why</h3>
{% if s.withheld %}<table><tr><th>Field</th><th>Justification</th></tr>
{% for w in s.withheld %}<tr><td>{{ w.table }}.{{ w.column }}</td><td>{{ w.reason }}</td></tr>
{% endfor %}</table>{% else %}<p>No catalogued QI withheld.</p>{% endif %}{% endif %}</section>

{% set s = extra.chart %}
<section id="chart" data-status="{{ s.status }}"><h2>Privacy versus utility {{ badge(s) }}</h2>
<p>Source: <code>measured.search</code>.</p>
{{ notes(s.blocks) }}
{% if s.svg %}{% set g = s.svg %}
<p>Candidates {{ s.summary.candidates }}, accepted {{ s.summary.accepted }}, bound reached {{ s.summary.boundReached|lower }}. Filled points were accepted by the search.{% if s.unscored %} {{ s.unscored }} rejected candidates had a purpose check that could not be scored; they are not plotted.{% endif %}</p>
<svg viewBox="0 0 {{ g.w }} {{ g.h }}" width="{{ g.w }}" height="{{ g.h }}" role="img" aria-label="Privacy risk versus utility">
<line x1="{{ g.pad }}" y1="{{ g.h - g.pad }}" x2="{{ g.w - g.pad }}" y2="{{ g.h - g.pad }}" stroke="#555"/>
<line x1="{{ g.pad }}" y1="{{ g.pad }}" x2="{{ g.pad }}" y2="{{ g.h - g.pad }}" stroke="#555"/>
<text x="{{ g.w // 2 }}" y="{{ g.h - 8 }}" font-size="12" text-anchor="middle">risk (0 to {{ g.xmax|fmt }})</text>
<text x="12" y="{{ g.h // 2 }}" font-size="12" text-anchor="middle" transform="rotate(-90 12 {{ g.h // 2 }})">utility (0 to {{ g.ymax|fmt }})</text>
<polyline points="{{ g.line }}" fill="none" stroke="#9aa5b1"/>
{% for p in g.points %}<circle cx="{{ p.x }}" cy="{{ p.y }}" r="5" stroke="#14365d" fill="{{ '#14365d' if p.accepted else '#fff' }}"><title>step {{ p.step }}</title></circle>
{% endfor %}</svg>{% endif %}</section>
</main></body></html>
"""
