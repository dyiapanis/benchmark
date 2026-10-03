#!/usr/bin/env python3
"""Score the MCP/cloudflare depth series (runs 10-15) + solver experiments.

Portable publication form of the MCP-series scoring script.
"""
import json
import os
import re
from collections import defaultdict

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
FILES = [
    "run10_mcp_cloudflare.jsonl",
    "run10_solver_beta30.jsonl",
    "run10_solver_beta30_residential.jsonl",
    "run11_mcp_cloudflare_glmflash.jsonl",
    "run12_mcp_cloudflare_glmflash.jsonl",
    "run14_mcp_cloudflare_glmflash.jsonl",
    "run15_mcp_cloudflare_kimi_k3.jsonl",
]

def classify(rec):
    v = rec.get("verdict")
    if v is True or v is False:
        return ("verdict", bool(v))
    fr = str(rec.get("final_result", ""))
    if "MAX_STEPS" in fr: return ("max_steps", False)
    if "DEADLINE" in fr: return ("deadline", False)
    if "BLOCKED" in fr[:20]: return ("blocked", False)
    if "UNPARSEABLE" in fr: return ("unparseable", False)
    if re.search(r"retries exhausted|HARNESS|tab died|\bERROR\b", fr, re.I): return ("he", False)
    if fr in ("", "None", "none"): return ("incomplete", False)
    return ("other", False)

for fn in FILES:
    p = os.path.join(RES, fn)
    if not os.path.exists(p):
        print(f"{fn}: MISSING"); continue
    by_task = defaultdict(list)
    nrec = 0
    for line in open(p):
        line = line.strip()
        if not line: continue
        try: rec = json.loads(line)
        except json.JSONDecodeError: continue
        nrec += 1
        tid = rec.get("task_id")
        if tid is None: continue
        by_task[tid].append(classify(rec))
    green = 0; mix = defaultdict(int); poisoned = 0
    for tid, atts in by_task.items():
        verd = [passed for c, passed in atts if c == "verdict"]
        inval = [c for c, _ in atts if c != "verdict"]
        for c in inval: mix[c] += 1
        if verd and any(v is None for v in verd): poisoned += 1
        if verd and sum(verd)/len(verd) > 0.5: green += 1
    det = " ".join(f"{k}:{v}" for k, v in sorted(mix.items()))
    print(f"{fn}: rows={nrec} tasks={len(by_task)} green={green} invalid-attempts[{det}] poisoned={poisoned}")