import json, glob, statistics

files = sorted(glob.glob('evaluation/results/run_*.json'))
with open(files[-1]) as f:
    run = json.load(f)

print('=== LATENCY PER QUESTION (sorted by latency) ===')
results_sorted = sorted(run['results'], key=lambda r: r['latency_ms'], reverse=True)
for r in results_sorted:
    cache = 'CACHE HIT ' if r.get('cache_hit') else 'CACHE MISS'
    routing = (r.get('routing') or 'unknown')[:40]
    print(f"  [{r['id']}] {cache}  {r['latency_ms']:>8.0f}ms  {routing}")

print()
timings_cache = [r['latency_ms'] for r in run['results'] if r.get('cache_hit')]
timings_miss  = [r['latency_ms'] for r in run['results'] if not r.get('cache_hit')]

print('=== CACHE HIT vs MISS BREAKDOWN ===')
if timings_cache:
    print(f"  Cache HIT  ({len(timings_cache)} queries):")
    print(f"    Avg    = {statistics.mean(timings_cache):.0f}ms")
    print(f"    Median = {statistics.median(timings_cache):.0f}ms")
    print(f"    Max    = {max(timings_cache):.0f}ms")
    print(f"    Min    = {min(timings_cache):.0f}ms")
if timings_miss:
    print(f"  Cache MISS ({len(timings_miss)} queries):")
    print(f"    Avg    = {statistics.mean(timings_miss):.0f}ms")
    print(f"    Median = {statistics.median(timings_miss):.0f}ms")
    print(f"    Max    = {max(timings_miss):.0f}ms")
    print(f"    Min    = {min(timings_miss):.0f}ms")

print()
print('=== ROUTING-BASED LATENCY ===')
by_routing = {}
for r in run['results']:
    route = r.get('routing') or 'unknown'
    by_routing.setdefault(route, []).append(r['latency_ms'])
for route, times in sorted(by_routing.items()):
    avg = statistics.mean(times)
    print(f"  {route:<50} count={len(times)}  avg={avg:.0f}ms")

print()
all_times = [r['latency_ms'] for r in run['results']]
print('=== OVERALL (current - skewed by cache hits) ===')
print(f"  Average = {statistics.mean(all_times):.0f}ms")
print(f"  Median  = {statistics.median(all_times):.0f}ms")
if len(all_times) >= 2:
    p95_idx = int(0.95 * (len(all_times) - 1))
    print(f"  P95     = {sorted(all_times)[p95_idx]:.0f}ms")
print()
print('=== THE REAL PROBLEM ===')
print("  11/12 queries are cache hits (5-20ms).")
print("  The average and P95 are misleading because of 1 warmup query")
print("  and 2 cross-collection fallback queries (~2600ms).")
print("  Real latency for fresh queries (cache MISS): see above.")
