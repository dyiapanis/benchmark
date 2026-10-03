#!/usr/bin/env python3
"""Acceptance verification: every number published in WOLVERINE_RESULTS.md must
reproduce from results/*.jsonl (fork copies) and this repo's official results.
Prints PASS/FAIL per claim. Exit 1 on any failure.

Counting rules (mirrors wolverine_bench/run_stealth.py):
- valid attempt (valid_rec): verdict in (True, False), final_result not
  HARNESS_ERROR/AGENT_LLM_ERROR-prefixed, no judge.error
- task green: strict majority of valid attempts True
- infra column: rows whose final_result starts with HARNESS_ERROR
"""
import base64
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from cryptography.fernet import Fernet

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
OFFICIAL = os.path.join(HERE, "stealth_bench", "official_results")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def strict_valid(rec):
    v = rec.get("verdict")
    fr = str(rec.get("final_result", ""))
    return (
        v in (True, False)
        and not fr.startswith(("HARNESS_ERROR", "AGENT_LLM_ERROR"))
        and not (rec.get("judge") or {}).get("error")
    )


def load(fn):
    recs = []
    for line in open(os.path.join(RES, fn)):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return recs


def score(fn):
    """(tasks_attempted, green, valid_attempts, he_rows)"""
    by_task = defaultdict(list)
    he = 0
    for r in load(fn):
        if str(r.get("final_result", "")).startswith("HARNESS_ERROR"):
            he += 1
        if r.get("task_id") is not None:
            by_task[r["task_id"]].append(r)
    green = 0
    valid_total = 0
    for atts in by_task.values():
        verd = [bool(r["verdict"]) for r in atts if strict_valid(r)]
        valid_total += len(verd)
        if verd and sum(verd) * 2 > len(verd):
            green += 1
    return len(by_task), green, valid_total, he


print("== Section 5 ledger (green/80 + infra + valid attempts) ==")
for run, fn, want_green, want_he, want_valid in [
    ("run2", "camoufox_run2.jsonl", 8, 1, 79),
    ("run3", "camoufox_run3.jsonl", 5, 1, 79),
    ("run4", "gateway_run4.jsonl", 1, 7, 73),
    ("run6", "run6_gw_beta29_residential.jsonl", 0, 24, 56),
    ("run7", "run7_sek83_datacenter.jsonl", 3, 6, 73),
    ("run9", "run9_sek85_scored.jsonl", 1, 5, 75),
]:
    n, green, valid, he = score(fn)
    check(f"{run} tasks attempted", n, 80)
    check(f"{run} green", green, want_green)
    check(f"{run} HE rows", he, want_he)
    if want_valid is not None:
        check(f"{run} valid attempts", valid, want_valid)
def task_row(fn, tid):
    for r in load(fn):
        if r.get("task_id") == tid:
            return r
    return None

check("run2 task-70 HE row vendor", task_row("camoufox_run2.jsonl", 70)["vendor"], "Akamai")
check("run2 task-70 final_result is HE-prefixed",
      str(task_row("camoufox_run2.jsonl", 70)["final_result"]).startswith("HARNESS_ERROR"), True)
check("run3 task-70 HE row vendor", task_row("camoufox_run3.jsonl", 70)["vendor"], "Akamai")
check("run3 task-70 final_result is HE-prefixed",
      str(task_row("camoufox_run3.jsonl", 70)["final_result"]).startswith("HARNESS_ERROR"), True)

print("\n== Section 6 per-vendor (green per vendor per run) ==")
def vendor_greens(fn):
    by_task = defaultdict(list)
    vendor_of = {}
    for r in load(fn):
        if r.get("task_id") is not None:
            by_task[r["task_id"]].append(r)
            vendor_of[r["task_id"]] = r.get("vendor", "?")
    gv = defaultdict(int)
    for tid, atts in by_task.items():
        verd = [bool(r["verdict"]) for r in atts if strict_valid(r)]
        if verd and sum(verd) * 2 > len(verd):
            gv[vendor_of[tid]] += 1
    return gv

VENDOR_WANT = {
    "camoufox_run2.jsonl": {"Cloudflare": 4, "PerimeterX": 1, "Datadome": 2, "Akamai": 0, "Custom Antibot": 1, "reCaptcha": 0},
    "camoufox_run3.jsonl": {"Cloudflare": 4, "PerimeterX": 1, "Datadome": 0, "Custom Antibot": 0},
    "gateway_run4.jsonl": {"Cloudflare": 1},
    "run6_gw_beta29_residential.jsonl": {"Cloudflare": 0},
    "run7_sek83_datacenter.jsonl": {"Cloudflare": 1, "Akamai": 2},
    "run9_sek85_scored.jsonl": {"Cloudflare": 1, "Akamai": 0},
}
for fn, wants in VENDOR_WANT.items():
    gv = vendor_greens(fn)
    for vendor, want in wants.items():
        check(f"per-vendor {fn} {vendor}", gv.get(vendor, 0), want)

print("\n== Section 1 vendor mix (task set) ==")
key = base64.urlsafe_b64encode(hashlib.sha256(b"Stealth_Bench_V1").digest())
tasks = json.loads(Fernet(key).decrypt(base64.b64decode(open(os.path.join(HERE, "Stealth_Bench_V1.enc"), "rb").read())))
cats = defaultdict(int)
for t in tasks:
    cats[t["category"]] += 1
for vendor, want in [("Cloudflare", 22), ("PerimeterX", 18), ("Datadome", 13), ("reCaptcha", 6),
                     ("Akamai", 6), ("Custom Antibot", 5), ("GeeTest", 4), ("hCaptcha", 3)]:
    check(f"task-set count {vendor}", cats[vendor], want)
check("task-set total", sum(cats.values()), 80)

print("\n== Section 7 MCP series ==")
for fn, want_rows, want_tasks, want_green in [
    ("run10_mcp_cloudflare.jsonl", 22, 22, 0),
    ("run11_mcp_cloudflare_glmflash.jsonl", 66, 22, 2),
    ("run12_mcp_cloudflare_glmflash.jsonl", 5, 2, 0),
    ("run14_mcp_cloudflare_glmflash.jsonl", 66, 22, 0),
    ("run15_mcp_cloudflare_kimi_k3.jsonl", 66, 22, 0),
]:
    recs = load(fn)
    n, green, _, _ = score(fn)
    check(f"{fn} rows", len(recs), want_rows)
    check(f"{fn} tasks", n, want_tasks)
    check(f"{fn} green", green, want_green)

r15 = load("run15_mcp_cloudflare_kimi_k3.jsonl")
entry_blocked = sum(
    1 for r in r15
    if all("TOOL_ERROR" in s and ("401" in s or "429" in s)
           for s in (r.get("steps") or []) if "goto" in s)
    and any("goto" in s for s in (r.get("steps") or []))
)
check("run15 attempts entry-blocked at steps level (every goto 401/429)", entry_blocked, 66)

print("\n== Section 3 controls ==")
for fn, want_rows in [("control_headless.jsonl", 5), ("control_headful.jsonl", 3)]:
    recs = load(fn)
    check(f"{fn} rows", len(recs), want_rows)
    check(f"{fn} all verdict False", all(r.get("verdict") is False for r in recs), True)

print("\n== proxy smoke 12/20 ==")
ps = json.load(open(os.path.join(RES, "proxy_smoke.json")))
check("proxy smoke clean", sum(1 for r in ps if r.get("blocked") is False), 12)
check("proxy smoke total", len(ps), 20)

print("\n== Section 8 official baselines ==")
def official_runs(provider):
    runs = []
    for fn in sorted(os.listdir(OFFICIAL)):
        if provider in fn:
            for r in json.load(open(os.path.join(OFFICIAL, fn))):
                tot = sum(r["tasks_total_by_category"].values())
                runs.append((r["tasks_successful"], tot))
    return runs

# (provider, n_runs, doc pooled mean at 2dp)
for provider, want_runs, want_mean in [
    ("browser-use-cloud", 5, 77.25), ("anchor", 3, 72.38), ("onkernel", 3, 68.33),
    ("browserless", 3, 56.67), ("local_headful", 5, 49.75), ("steel", 3, 46.84),
    ("browserbase", 4, 42.81), ("hyperbrowser", 3, 39.58), ("local_headless", 9, 2.36),
]:
    runs = official_runs(provider)
    check(f"official {provider} run count", len(runs), want_runs)
    mean = 100.0 * sum(s for s, _ in runs) / sum(t for _, t in runs)
    check(f"official {provider} pooled mean (2dp)", round(mean, 2), want_mean)

# local_headless per-run band quoted as 1-3/80
lh = official_runs("local_headless")
check("local_headless per-run band 1-3", (min(s for s, _ in lh), max(s for s, _ in lh)), (1, 3))

print("\n== six-run mean/stdev ==")
vals = [10.0, 6.25, 1.25, 0.0, 3.75, 1.25]
check("six-run mean", round(statistics.mean(vals), 2), 3.75)
check("six-run stdev", round(statistics.stdev(vals), 2), 3.79)

print("\n" + "=" * 60)
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PUBLISHED NUMBERS RECONCILE")