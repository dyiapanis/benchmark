#!/usr/bin/env python3
"""Per-vendor breakdown + failure mix for every full 80-task run.
Same majority-green rule as the harness --score. Reconciles against the tables
in WOLVERINE_RESULTS.md.

Portable publication form of the campaign vendor-breakdown script.
"""
import json
import os
import re
from collections import defaultdict

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
OUT = os.path.join(RES, "vendor_breakdown.json")

FULL_RUNS = {
    "run2_bare_css_datacenter": "camoufox_run2.jsonl",
    "run3_bare_css_residential": "camoufox_run3.jsonl",
    "run4_product_ref_datacenter": "gateway_run4.jsonl",
    "run6_product_ref_residential": "run6_gw_beta29_residential.jsonl",
    "run7_product_ref_datacenter_sek83": "run7_sek83_datacenter.jsonl",
    "run9_product_ref_datacenter_sek85": "run9_sek85_scored.jsonl",
}

def classify(rec):
    v = rec.get("verdict")
    if v is True or v is False:
        return ("verdict", bool(v))
    fr = str(rec.get("final_result", ""))
    if "MAX_STEPS" in fr: return ("max_steps", False)
    if "DEADLINE" in fr: return ("deadline", False)
    if fr.startswith("BLOCKED") or "BLOCKED" in fr[:20]: return ("blocked", False)
    if "UNPARSEABLE" in fr: return ("unparseable", False)
    if fr.startswith("HARNESS") or re.search(r"retries exhausted|tab died|\bERROR\b", fr, re.I):
        return ("he", False)
    if fr in ("", "None", "none"): return ("incomplete", False)
    return ("other", False)

def score_run(fn):
    by_task = defaultdict(list)
    vendors = {}
    with open(os.path.join(RES, fn)) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rec = json.loads(line)
            except json.JSONDecodeError: continue
            tid = rec.get("task_id")
            if tid is None: continue
            by_task[tid].append(classify(rec))
            vendors[tid] = rec.get("vendor", "Unknown")
    tasks = {}
    for tid, atts in by_task.items():
        verd = [p for c, p in atts if c == "verdict"]
        green = bool(verd) and (sum(verd) / len(verd) > 0.5)
        mix = defaultdict(int)
        for c, p in atts:
            mix["pass" if (c == "verdict" and p) else c] += 1
        tasks[tid] = {"vendor": vendors[tid], "attempts": len(atts),
                      "verdict_attempts": len(verd),
                      "invalid_attempts": sum(1 for c, _ in atts if c != "verdict"),
                      "green": green, "mix": dict(mix)}
    return tasks

def main():
    ledger = {}
    for run_id, fn in FULL_RUNS.items():
        tasks = score_run(fn)
        per_vendor = defaultdict(lambda: {"tasks": 0, "green": 0})
        total_mix = defaultdict(int)
        invalid_tasks = 0
        for tid, t in tasks.items():
            v = t["vendor"]
            per_vendor[v]["tasks"] += 1
            if t["green"]:
                per_vendor[v]["green"] += 1
            else:
                if t["verdict_attempts"] == 0:
                    invalid_tasks += 1
                if t["mix"]:
                    worst = max((k for k in t["mix"] if k != "pass"),
                                key=lambda k: t["mix"][k], default="other")
                    total_mix[worst] += 1
        for v in sorted(per_vendor):
            pv = per_vendor[v]
            pv["pct"] = round(100 * pv["green"] / pv["tasks"], 1) if pv["tasks"] else None
        green = sum(1 for t in tasks.values() if t["green"])
        ledger[run_id] = {
            "file": fn, "tasks_with_results": len(tasks),
            "green": green, "pct_of_80": round(100 * green / 80, 2),
            "invalid_no_verdict_tasks": invalid_tasks,
            "fail_mix_tasks": dict(total_mix),
            "per_vendor": {v: per_vendor[v] for v in sorted(per_vendor)},
        }
    with open(OUT, "w") as f:
        json.dump(ledger, f, indent=2)
    for run_id, d in ledger.items():
        print(f"\n== {run_id}: {d['green']}/80 = {d['pct_of_80']}%  (invalid/no-verdict tasks: {d['invalid_no_verdict_tasks']})")
        for v, pv in d["per_vendor"].items():
            print(f"   {v:12s} {pv['green']:3d}/{pv['tasks']:<3d} = {pv['pct']}%")
        print(f"   fail-mix: {d['fail_mix_tasks']}")

main()