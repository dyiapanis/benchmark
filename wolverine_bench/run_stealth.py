"""Runner: decrypt Stealth_Bench_V1, run tasks through Camoufox agent, judge, JSONL.

Resume-safe: per-task results appended to results JSONL; already-done tasks skipped.
Controls: --browser local_headless / local_headful run the same harness on vanilla
Chromium (the validation anchor).
"""
import argparse
import base64
import os
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

from wolverine_bench.driver import WolverineBrowser
from wolverine_bench.agent import run_task

HERE = Path(__file__).parent.parent
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_tasks():
    key = base64.urlsafe_b64encode(hashlib.sha256(b"Stealth_Bench_V1").digest())
    enc = (HERE / "Stealth_Bench_V1.enc").read_text()
    return json.loads(Fernet(key).decrypt(base64.b64decode(enc)))


def judge(task_text, final_result, steps, screenshots):
    """Call the judge with THEIR prompt, via Ollama Cloud vision model."""
    import sys
    sys.path.insert(0, str(HERE))
    from judge import construct_judge_messages, JudgementResult
    import httpx

    messages = construct_judge_messages(task_text, final_result, steps, screenshots)
    # convert langchain messages -> openai format (text + image parts)
    out_msgs = []
    for m in messages:
        cls = type(m).__name__
        role = "assistant" if cls == "AIMessage" else "user"
        content = m.content
        parts = []
        if isinstance(content, str):
            parts.append({"type": "text", "text": content})
        else:
            for c in content:
                ctype = c.get("type") if isinstance(c, dict) else getattr(c, "type", None)
                if ctype == "text":
                    txt = c.get("text") if isinstance(c, dict) else c.text
                    parts.append({"type": "text", "text": txt})
                elif ctype == "image_url":
                    iu = c.get("image_url") if isinstance(c, dict) else c.image_url
                    url = iu.get("url") if isinstance(iu, dict) else iu.url
                    parts.append({"type": "image_url", "image_url": {"url": url}})
        out_msgs.append({"role": role, "content": parts})

    judge_model = os.environ.get("WOLVERINE_JUDGE_MODEL", "deepseek-v4-flash-vision-exp")
    backend = os.environ.get("WOLVERINE_JUDGE_BACKEND", "opencode")
    if backend == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        key = os.environ["OPENROUTER_API_KEY"]
    elif backend == "opencode":
        url = "https://opencode.ai/zen/go/v1/chat/completions"
        key = os.environ["OPENCODE_GO_API_KEY"]
    else:
        url = f"{os.environ['OLLAMA_BASE_URL']}/chat/completions"
        key = os.environ["OLLAMA_API_KEY"]
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": judge_model, "messages": out_msgs, "temperature": 0.0, "max_tokens": 4000},
        timeout=180,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    # parse JudgementResult fields from the judge's response
    import re
    m = re.search(r"\{.*\}", text, re.S)
    parsed = {}
    parse_ok = m is not None
    if m:
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            parse_ok = False
    jr = JudgementResult(
        reasoning=parsed.get("reasoning"),
        verdict=bool(parsed.get("verdict", False)),
        failure_reason=parsed.get("failure_reason"),
        impossible_task=bool(parsed.get("impossible_task", False)),
        reached_captcha=bool(parsed.get("reached_captcha", False)),
    )
    if not parse_ok:
        # run11 task 13: completed work failed judge-JSON parse and silently
        # banked as verdict=False with no reason. Surface it instead.
        jr.failure_reason = f"JUDGE_PARSE_FAILURE: {text[:200]}"
    return jr, text


def valid_rec(r):
    """A record counts as a completed attempt only if the agent loop produced a
    real final_result AND the judge returned a verdict. HARNESS_ERRORs, judge
    errors, and AGENT_LLM_ERRORs (Ollama Cloud flakes) are poisoned results:
    never resume-skip over them, never score them."""
    return (
        r.get("verdict") in (True, False)
        and not str(r.get("final_result", "")).startswith(("HARNESS_ERROR", "AGENT_LLM_ERROR"))
        and not (r.get("judge") or {}).get("error")
    )


def majority_score(records):
    """Group records by task_id; a task is green iff True is a strict majority
    of its valid attempts. (Cloudflare/Turnstile is a ~40% coin-flip per attempt
    — single samples are noise, 3x majority is the rule.)"""
    by_task = {}
    for r in records:
        if valid_rec(r):
            by_task.setdefault(r["task_id"], []).append(bool(r["verdict"]))
    return {tid: (sum(v) * 2 > len(v), len(v), sum(v)) for tid, v in by_task.items()}


def load_records(path):
    recs = []
    for line in Path(path).read_text().splitlines():
        try:
            recs.append(json.loads(line))
        except Exception:
            pass
    return recs


def score_run(run_name):
    path = RESULTS_DIR / f"{run_name}.jsonl"
    recs = load_records(path)
    scores = majority_score(recs)
    total = len(scores)
    greens = sum(1 for g, _, _ in scores.values() if g)
    print(f"[score] {run_name}: {greens}/{total} tasks green (majority of valid attempts)")
    for tid, (green, n, trues) in sorted(scores.items()):
        print(f"  task {tid:3d}: {'PASS' if green else 'FAIL'}  ({trues}/{n} attempts true)")
    poisoned = len(recs) - sum(n for _, n, _ in scores.values())
    if poisoned:
        print(f"  ({poisoned} poisoned records excluded)")
    return greens, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="camoufox", choices=["camoufox", "local_headless", "local_headful", "gateway", "mcp"])
    ap.add_argument("--tasks", type=int, default=0, help="run first N tasks (0=all)")
    ap.add_argument("--category", default=None, help="only run tasks of this vendor category (e.g. Cloudflare)")
    ap.add_argument("--attempts", type=int, default=1,
                    help="valid attempts per task (flake-class vendors need 3; fresh session per attempt)")
    ap.add_argument("--score", default=None, help="score an existing run and exit (no execution)")
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--proxy", default=None, help="e.g. socks5://127.0.0.1:1080")
    args = ap.parse_args()

    if args.score:
        score_run(args.score)
        return

    tasks = load_tasks()
    if args.category:
        tasks = [t for t in tasks if t.get("category", "").lower() == args.category.lower()]
    if args.tasks:
        tasks = tasks[: args.tasks]
    run_name = args.run_name or f"Stealth_Bench_V1_wolverine_{args.browser}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    out_path = RESULTS_DIR / f"{run_name}.jsonl"
    # Resume-safe, poison-proof: keep only valid attempts, rewrite the file, count them.
    done_counts = {}
    if out_path.exists():
        recs = load_records(out_path)
        kept = [r for r in recs if valid_rec(r)]
        out_path.write_text("".join(json.dumps(r) + "\n" for r in kept))
        for r in kept:
            done_counts[r["task_id"]] = done_counts.get(r["task_id"], 0) + 1
        if len(kept) != len(recs):
            print(f"[resume] pruned {len(recs) - len(kept)} poisoned records from {out_path.name}")

    print(f"[bench] browser={args.browser} tasks={len(tasks)} attempts/task={args.attempts} out={out_path.name}")
    # expand to a per-attempt list, honoring what resume already banked
    tasks = [t for t in tasks for _ in range(max(0, args.attempts - done_counts.get(t["task_id"], 0)))]
    for t in tasks:
        task_text = t["confirmed_task"]
        vendor = t.get("category", "?")
        t0 = time.time()
        try:
            if args.browser == "gateway":
                from wolverine_bench.gateway_driver import GatewayBrowser
                ctx = GatewayBrowser(proxy=args.proxy)
            elif args.browser == "mcp":
                from wolverine_bench.mcp_driver import McpBrowser
                ctx = McpBrowser()  # proxy: gateway binds sticky residential egress per session
            elif args.browser == "camoufox":
                ctx = WolverineBrowser(proxy=args.proxy)
            else:
                from wolverine_bench.chromium_control import LocalChromium
                ctx = LocalChromium(headless=(args.browser == "local_headless"))
            with ctx as browser:
                final, steps, shots = run_task(browser, t["confirmed_task"])
        except Exception as e:
            # session-create 503s (pool churn) poison ONE task, never the run —
            # resume prunes these and re-runs them
            final, steps, shots = f"HARNESS_ERROR: {type(e).__name__}: {e}", [], []
        elapsed = time.time() - t0
        if str(final).startswith("HARNESS_ERROR"):
            verdict, judge_info = None, {"skipped": "harness error"}
        else:
            try:
                jr, raw = judge(t["confirmed_task"], final, steps, shots)
                verdict = jr.verdict
                judge_info = {"reasoning": (jr.reasoning or "")[:400], "failure_reason": jr.failure_reason,
                              "reached_captcha": jr.reached_captcha, "impossible": jr.impossible_task,
                              "raw": raw[:1200]}
            except Exception as e:
                verdict = None
                judge_info = {"error": str(e)[:300]}
        rec = {
            "task_id": t["task_id"],
            "vendor": vendor,
            "verdict": verdict,
            "final_result": final[:500],
            "n_steps": len(steps),
            "n_screenshots": len(shots),
            "elapsed_s": round(elapsed, 1),
            "steps": steps,
            "judge": judge_info,
        }
        with open(out_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{t['task_id']:3d}] {vendor:14s} verdict={verdict} {elapsed:5.1f}s {final[:60]}", flush=True)


if __name__ == "__main__":
    main()