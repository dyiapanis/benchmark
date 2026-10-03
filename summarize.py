import os
import statistics

import json

HERE = os.path.dirname(os.path.abspath(__file__))
ledger = json.load(open(os.path.join(HERE, "results", "vendor_breakdown.json")))
scores = {}
for run_id, d in ledger.items():
    scores[run_id] = 100 * d["green"] / 80

vals = list(scores.values())
mean = statistics.mean(vals)
stdev_sample = statistics.stdev(vals)

print("verification of published numbers (green/80):")
for k, v in scores.items():
    print(f"  {k:45s} {v:.2f}%")
print(f"\nsix-run mean: {mean:.2f}%  sample-stdev: {stdev_sample:.2f}pp")

bare = [scores["run2_bare_css_datacenter"], scores["run3_bare_css_residential"]]
print(f"\nbare-engine band: {min(bare)}-{max(bare)}%")
print("MCP Cloudflare cluster best-of-series: 2/22 = %.1f%% (run11)" % (100 * 2 / 22))