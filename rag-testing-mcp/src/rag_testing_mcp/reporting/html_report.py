"""
HTML report generator using Jinja2 inline template.

Generates a self-contained, styled HTML evaluation report.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from rag_testing_mcp.models import EvaluationRun

_HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>RAG Evaluation Report — {{ run.run_id }}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e0e0e0; padding: 2rem; }
  h1 { color: #7c8aff; margin-bottom: 0.5rem; }
  h2 { color: #a3b1ff; margin: 1.5rem 0 0.5rem; border-bottom: 1px solid #2a2d3a; padding-bottom: 0.3rem; }
  h3 { color: #c0c8ff; margin: 1rem 0 0.3rem; }
  .meta { color: #888; font-size: 0.9rem; margin-bottom: 1.5rem; }
  .card { background: #1a1d2e; border-radius: 10px; padding: 1.2rem; margin-bottom: 1rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
  .metric { text-align: center; }
  .metric .value { font-size: 2rem; font-weight: 700; color: #7c8aff; }
  .metric .label { font-size: 0.85rem; color: #999; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid #2a2d3a; font-size: 0.85rem; }
  th { color: #a3b1ff; }
  .pass { color: #4caf50; }
  .fail { color: #f44336; }
  .warn { color: #ff9800; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin: 2px; }
  .tag-fail { background: #3a1520; color: #f44336; }
  .tag-ok { background: #15302a; color: #4caf50; }
</style>
</head>
<body>

<h1>📊 RAG Evaluation Report</h1>
<p class="meta">Run: {{ run.run_id }} &bull; {{ run.timestamp }} &bull; Dataset: {{ run.dataset_path }}</p>

<!-- Executive Summary -->
<h2>Executive Summary</h2>
<div class="card grid">
  <div class="metric">
    <div class="value">{{ run.total_questions }}</div>
    <div class="label">Total Questions</div>
  </div>
  <div class="metric">
    <div class="value pass">{{ run.successful }}</div>
    <div class="label">Successful</div>
  </div>
  <div class="metric">
    <div class="value fail">{{ run.failed }}</div>
    <div class="label">Failed</div>
  </div>
  <div class="metric">
    <div class="value fail">{{ run.error_count }}</div>
    <div class="label">API Errors</div>
  </div>
</div>

<!-- Retrieval Metrics -->
<h2>Retrieval Metrics</h2>
<div class="card grid">
  <div class="metric"><div class="value">{{ run.retrieval_summary.recall_at_1 or 'N/A' }}</div><div class="label">Recall@1</div></div>
  <div class="metric"><div class="value">{{ run.retrieval_summary.recall_at_3 or 'N/A' }}</div><div class="label">Recall@3</div></div>
  <div class="metric"><div class="value">{{ run.retrieval_summary.recall_at_5 or 'N/A' }}</div><div class="label">Recall@5</div></div>
  <div class="metric"><div class="value">{{ run.retrieval_summary.precision_at_k or 'N/A' }}</div><div class="label">Precision@K</div></div>
  <div class="metric"><div class="value">{{ run.retrieval_summary.mrr or 'N/A' }}</div><div class="label">MRR</div></div>
</div>

<!-- Generation Metrics -->
<h2>Generation &amp; Faithfulness</h2>
<div class="card grid">
  <div class="metric"><div class="value">{{ run.generation_summary.answer_relevance or 'N/A' }}</div><div class="label">Answer Relevance</div></div>
  <div class="metric"><div class="value">{{ run.generation_summary.faithfulness or 'N/A' }}</div><div class="label">Faithfulness</div></div>
  <div class="metric"><div class="value">{{ run.generation_summary.groundedness or 'N/A' }}</div><div class="label">Groundedness</div></div>
  <div class="metric"><div class="value {% if run.generation_summary.hallucination_risk and run.generation_summary.hallucination_risk > 0.3 %}fail{% else %}pass{% endif %}">{{ run.generation_summary.hallucination_risk or 'N/A' }}</div><div class="label">Hallucination Risk</div></div>
</div>

<!-- Latency -->
<h2>Latency</h2>
<div class="card grid">
  <div class="metric"><div class="value">{{ run.latency.average_ms or 'N/A' }}</div><div class="label">Average (ms)</div></div>
  <div class="metric"><div class="value">{{ run.latency.median_ms or 'N/A' }}</div><div class="label">Median (ms)</div></div>
  <div class="metric"><div class="value">{{ run.latency.p95_ms or 'N/A' }}</div><div class="label">P95 (ms)</div></div>
  <div class="metric"><div class="value">{{ run.latency.p99_ms or 'N/A' }}</div><div class="label">P99 (ms)</div></div>
</div>

<!-- Routing & Cache -->
<h2>Routing &amp; Cache</h2>
<div class="card">
  <p>Cache Hit Rate: <strong>{{ run.routing.cache_hit_rate if run.routing.cache_hit_rate is not none else 'N/A' }}</strong></p>
  <p>Unnecessary Web Searches: <strong class="{% if run.routing.unnecessary_web_searches > 0 %}warn{% endif %}">{{ run.routing.unnecessary_web_searches }}</strong></p>
  <p>Distribution: {{ run.routing.routing_distribution }}</p>
</div>

<!-- Failures -->
<h2>Failure Analysis ({{ run.failures | length }} total)</h2>
{% if run.failures %}
<div class="card">
<table>
  <tr><th>Question ID</th><th>Type</th><th>Reason</th></tr>
  {% for f in run.failures[:30] %}
  <tr>
    <td>{{ f.question_id }}</td>
    <td><span class="tag tag-fail">{{ f.failure_type }}</span></td>
    <td>{{ f.reason[:120] }}</td>
  </tr>
  {% endfor %}
</table>
{% if run.failures | length > 30 %}<p style="color:#888; margin-top:0.5rem;">... and {{ run.failures | length - 30 }} more</p>{% endif %}
</div>
{% else %}
<div class="card"><p class="pass">No failures detected ✓</p></div>
{% endif %}

<!-- Per-Question Results -->
<h2>Per-Question Results</h2>
<div class="card">
<table>
  <tr><th>ID</th><th>Question</th><th>Answered</th><th>Latency</th><th>Faith.</th><th>Ground.</th><th>Failures</th></tr>
  {% for r in run.results %}
  <tr>
    <td>{{ r.id }}</td>
    <td>{{ r.question[:60] }}</td>
    <td class="{% if r.answered %}pass{% else %}fail{% endif %}">{{ r.answered }}</td>
    <td>{{ r.latency_ms | round(0) }}ms</td>
    <td>{{ r.generation.faithfulness or 'N/A' }}</td>
    <td>{{ r.generation.groundedness or 'N/A' }}</td>
    <td>{{ r.failures | length }}</td>
  </tr>
  {% endfor %}
</table>
</div>

</body>
</html>
""")


def save_html_report(run: EvaluationRun, output_dir: Path) -> Path:
    """Render and save a styled HTML evaluation report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"report_{run.run_id.replace('run_', '')}.html"
    html = _HTML_TEMPLATE.render(run=run)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
