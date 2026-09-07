import json, glob, os
from collections import Counter

# Auto-pick latest run
files = sorted(glob.glob('evaluation/results/run_*.json'))
latest = files[-1]
print(f"Reading: {latest}\n")

with open(latest) as f:
    run = json.load(f)

PREV = {"LATENCY_FAILURE": 8, "CITATION_FAILURE": 6, "GROUNDING_FAILURE": 5, "GENERATION_FAILURE": 3}

print('=== FINAL EVALUATION SUMMARY ===')
print(f'  Questions : {run["total_questions"]} | Passed: {run["successful"]} | Errors: {run["error_count"]}')
print(f'  Failures  : {len(run["failures"])}   (Run1:22 -> Run2:15 -> Run3:4 -> Run4:{len(run["failures"])})')
print()
print('=== RETRIEVAL QUALITY ===')
r = run['retrieval_summary']
print(f'  Recall@1    = {r["recall_at_1"]:>6}   (was 0.0)')
print(f'  Recall@3    = {r["recall_at_3"]:>6}   (was 0.0)')
print(f'  Recall@5    = {r["recall_at_5"]:>6}   (was 0.0)')
print(f'  Precision@K = {r["precision_at_k"]:>6}   (was 0.0)')
print(f'  MRR         = {r["mrr"]:>6}   (was 0.0)')
print()
print('=== GENERATION QUALITY ===')
g = run['generation_summary']
print(f'  Answer Relevance  = {g["answer_relevance"]:>6}  (was 0.4789)')
print(f'  Faithfulness      = {g["faithfulness"]:>6}  (was 0.6875)')
print(f'  Groundedness      = {g["groundedness"]:>6}  (was 0.6125)')
print(f'  Hallucination Risk= {g["hallucination_risk"]:>6}  (was 0.3875)')
print()
print('=== LATENCY (Cache-Aware) ===')
l = run['latency']
print(f'  Overall  avg={l["average_ms"]}ms  median={l["median_ms"]}ms  p95={l["p95_ms"]}ms')
print()
if l.get('cache_hit_count'):
    sla = "OK" if l.get('cache_hit_sla_ok', True) else "WARN"
    print(f'  Cache HIT  ({l["cache_hit_count"]} queries) [{sla}]')
    print(f'    avg={l["cache_hit_avg_ms"]}ms   p95={l["cache_hit_p95_ms"]}ms   (SLA <500ms)')
if l.get('cache_miss_count'):
    sla = "OK" if l.get('fresh_query_sla_ok', True) else "FAIL"
    print(f'  Cache MISS ({l["cache_miss_count"]} queries) [{sla}]')
    print(f'    avg={l["cache_miss_avg_ms"]}ms   p95={l["cache_miss_p95_ms"]}ms  (SLA <15000ms)')
if l.get('by_routing'):
    print(f'  Per-routing-path averages:')
    for route, avg in l['by_routing'].items():
        print(f'    {route:<50} {avg:.0f}ms')
print()
print('=== ROUTING ===')
ro = run['routing']
print(f'  Cache Hit Rate         = {ro["cache_hit_rate"]}  ({ro["cache_hits"]} hits / {ro["cache_hits"]+ro["cache_misses"]} queries)')
print(f'  Unnecessary Web Search = {ro["unnecessary_web_searches"]}')
print(f'  Routing distribution   : {ro["routing_distribution"]}')
print()
print('=== FAILURES BY TYPE ===')
types = Counter(f['failure_type'] for f in run['failures'])
for t, count in types.most_common():
    prev = PREV.get(t, 0)
    print(f'  {t}: {count}  (was {prev})')
print()
print('=== PER-QUESTION RESULTS ===')
print(f'  {"ID":<6} {"OK?":<5} {"Latency":>10} {"Faith":>6} {"Grnd":>6} {"Hallu":>6} {"#Fail":>5}')
print(f'  {"-"*58}')
for res in run['results']:
    gen = res['generation']
    ok = "OK" if len(res["failures"]) == 0 else "FAIL"
    print(f'  [{res["id"]}] {ok:<5} {res["latency_ms"]:>9.0f}ms '
          f'  {str(gen["faithfulness"]):>5}  {str(gen["groundedness"]):>5}  '
          f'{str(gen["hallucination_risk"]):>5}  {len(res["failures"]):>4}')
print()
if run['failures']:
    print('=== REMAINING FAILURES ===')
    for f in run['failures']:
        print(f'  [{f["question_id"]}] {f["failure_type"]}')
        print(f'    {f["reason"][:100]}')
