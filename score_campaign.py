#!/usr/bin/env python3
"""Score every raw JSONL in results/ using the SAME majority rule as the
harness's --score mode: per-task green only if >50% of VALID attempts are true.
Classify non-verdict outcomes. Emit one summary table + a machine ledger JSON.

Portable publication form of the campaign scoring script.
"""
import glob
import json
import os
import re
from collections import defaultdict

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
OUT = os.path.join(RES, "ledger.json")

FULL_RUNS = {
    "run2": "camoufox_run2.jsonl",            # bare engine, datacenter, css-agent
    "run3": "camoufox_run3.jsonl",            # bare engine, residential, css-agent
    "run4": "gateway_run4.jsonl",             # product, datacenter, ref-agent
    "run6": "run6_gw_beta29_residential.jsonl",
    "run7": "run7_sek83_datacenter.jsonl",
    "run9": "run9_sek85_scored.jsonl",
}

def classify(rec):
    """Return (verdict_class, passed). verdict_class in
    PASS/BLOCKED/MAX_STEPS/HE/unparseable/incomplete."""
    v = rec.get("verdict")
    if v is True or v is False:
        return ("verdict", bool(v))
    fr = str(rec.get("final_result", ""))
    if "MAX_STEPS" in fr:
        return ("max_steps", False)
    if "DEADLINE" in fr:
        return ("deadline", False)
    if fr.startswith("BLOCKED"):
        return ("blocked", False)
    if "UNPARSEABLE" in fr:
        return ("unparseable", False)
    if fr.startswith("HARNESS") or re.search(r"retries exhausted|tab died|ERROR", fr, re.I):
        return ("he", False)
    if fr in ("", "None", "none"):
        return ("incomplete", False)
    return ("other", False)

def load(name):
    recs = []
    with open(os.path.join(RES, name)) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return recs

def score_run(name):
    recs = load(name)
    by_task = defaultdict(list)
    for r in recs:
        tid = r.get("task_id")
        if tid is None:
            continue
        cls, passed = classify(r)
        by_task[tid].append((cls, passed))
    tasks = {}
    for tid, atts in by_task.items():
        verd = [p for c, p in atts if c == "verdict"]
        n_invalid = sum(1 for c, _ in atts if c != "verdict")
        green = bool(verd) and (sum(verd) / len(verd) > 0.5)
        tasks[tid] = {"attempts": len(atts), "verdict_attempts": len(verd),
                      "invalid_attempts": n_invalid, "green": green}
    return tasks

def main():
    ledger = {}
    for run_id, fn in FULL_RUNS.items():
        tasks = score_run(fn)
        green = sum(1 for t in tasks.values() if t["green"])
        ledger[run_id] = {"file": fn, "tasks": len(tasks), "green": green,
                          "attempt_rows": sum(t["attempts"] for t in tasks.values())}
    print(json.dumps(ledger, indent=2))
    with open(OUT, "w") as f:
        json.dump(ledger, f, indent=2)

main()