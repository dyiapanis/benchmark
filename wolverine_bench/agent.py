"""Agent loop: tool-calling LLM (Ollama Cloud, OpenAI-compatible) driving WolverineBrowser.

Mirrors browser-use Agent's role in the benchmark: take a task, drive the browser,
return final_result + steps + screenshots. Same inputs/outputs as their Agent so the
judge is used identically.
"""
import json
import os
import re
import time
import httpx

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1")
OLLAMA_KEY = os.environ["OLLAMA_API_KEY"]
AGENT_MODEL = os.environ.get("WOLVERINE_AGENT_MODEL", "kimi-k2.6")
MAX_STEPS = int(os.environ.get("WOLVERINE_MAX_STEPS", "22"))
# Wall-clock abort: MAX_STEPS alone let wander-loops run 20 min on worker time.
TASK_DEADLINE_S = int(os.environ.get("WOLVERINE_TASK_DEADLINE_S", "300"))
# agent-side guard (stale-ref fix): refs hallucinated by the model never appear in any
# read() snapshot; track the refs we actually gave it and inject a corrective obs.
_last_snapshot_refs = set()

SYSTEM_CSS = """You are a browser automation agent completing a task on a website.
You have these tools:
- goto(url) — navigate the current tab
- click(selector)
- type(selector, text)
- press(key) — e.g. Enter
- read() — returns the page's visible text
- screenshot() — view the current page
- done(answer) — finish with your final answer

Rules:
- The task names ONE site. Stay on it.
- If blocked by a captcha/antibot challenge or the page refuses to load, call done() with "BLOCKED: <reason>".
- Be efficient: usually read() first, then act.
- For selectors, prefer stable ones: id (#x), name ([name=x]), role-based paths, or obvious text/label selectors.

Respond with ONE JSON object per turn:
{"thought": "...", "tool": "goto|click|type|press|read|screenshot|done", "args": {...}}
"""

SYSTEM_REF = """You are a browser automation agent completing a task on a website.
You have these tools:
- goto(url) — navigate the current tab
- click(ref) — click an element by its ref id from the snapshot
- type(ref, text) — type text into an element by ref id
- press(key) — e.g. Enter
- read() — returns the page's accessibility snapshot (elements have [ref] ids)
- screenshot() — view the current page
- done(answer) — finish with your final answer

Rules:
- The task names ONE site. Stay on it.
- If blocked by a captcha/antibot challenge or the page refuses to load, call done() with "BLOCKED: <reason>".
- read() gives you the snapshot with ref ids in brackets like [e12]. Use those exact refs for click/type.
- Refs go stale after the page changes. If an action returns STALE_REF, call read() once for fresh refs and retry the action. Do NOT invent refs you have not seen in the latest read().
- read() first to get refs, then act.

Respond with ONE JSON object per turn:
{"thought": "...", "tool": "goto|click|type|press|read|screenshot|done", "args": {...}}
"""

import os as _os
SYSTEM = SYSTEM_REF if _os.environ.get("WOLVERINE_AGENT_MODE") == "ref" else SYSTEM_CSS


def _chat(messages, steps):
    """One LLM call. Reasoning models: content OR reasoning field carries the answer."""
    body = {
        "model": AGENT_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 6000,
    }
    r = httpx.post(
        f"{OLLAMA_URL}/chat/completions",
        headers={"Authorization": f"Bearer {OLLAMA_KEY}"},
        json=body,
        timeout=120,
    )
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    content = msg.get("content") or ""
    if not content.strip():
        content = msg.get("reasoning_content") or msg.get("reasoning") or ""
    # balanced-brace extraction (handles nested args objects)
    start = content.find("{")
    if start == -1:
        return {"tool": "done", "args": {"answer": f"UNPARSEABLE: {content[:300]}"}}
    depth = 0
    end = None
    for i, ch in enumerate(content[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return {"tool": "done", "args": {"answer": f"UNPARSEABLE: {content[:300]}"}}
    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        tool = re.search(r'"tool"\s*:\s*"(\w+)"', content)
        if tool:
            return {"tool": tool.group(1), "args": {}}
        return {"tool": "done", "args": {"answer": f"UNPARSEABLE: {content[:300]}"}}


def run_task(browser, task_text: str):
    """Execute one benchmark task. Returns (final_result, steps, screenshots_b64)."""
    steps = []
    screenshots = []
    url_match = re.search(r"Go to (https?://[^\s,]+)", task_text)
    start_url = url_match.group(1) if url_match else None

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"TASK:\n{task_text}\n\nBegin. (Starting URL: {start_url})"},
    ]

    final = None
    deadline = time.monotonic() + TASK_DEADLINE_S
    for step_no in range(MAX_STEPS):
        # stale-ref fix: refs from a previous task must not leak into this one
        _last_snapshot_refs.clear()
        if time.monotonic() > deadline:
            final = "DEADLINE_EXCEEDED"
            steps.append(f"step {step_no+1}: aborted — wall-clock over {TASK_DEADLINE_S}s")
            break
        try:
            action = _chat(messages, steps)
        except Exception as e:
            final = f"AGENT_LLM_ERROR: {e}"
            break
        tool = action.get("tool", "done")
        args = action.get("args", {}) or {}
        # glm-5.3-flash copies ref ids WITH the snapshot's bracket notation
        # ("[e12]") into selector fields; kimi emitted bare "e12". Normalize
        # both spellings to the bare ref the guard + MCP expect.
        for _k in ("selector", "css_selector", "ref"):
            _v = args.get(_k)
            if _v and re.fullmatch(r"\[(e\d+)\]", _v):
                args[_k] = _v[1:-1]
        try:
            if tool == "goto":
                obs = browser.goto(args["url"])
            elif tool == "click":
                sel = args.get("selector") or args.get("css_selector") or args.get("ref")
                if sel and _last_snapshot_refs and sel not in _last_snapshot_refs and re.fullmatch(r"e\d+", sel):
                    obs = f"HALLUCINATED_REF: {sel!r} was not in the last read() snapshot. Valid refs: {sorted(_last_snapshot_refs)[:15]}. Call read() and use one of those."
                else:
                    obs = browser.click(sel) if sel else "click: no selector given"
            elif tool == "type":
                sel = args.get("selector") or args.get("css_selector") or args.get("ref")
                if sel and _last_snapshot_refs and sel not in _last_snapshot_refs and re.fullmatch(r"e\d+", sel):
                    obs = f"HALLUCINATED_REF: {sel!r} was not in the last read() snapshot. Valid refs: {sorted(_last_snapshot_refs)[:15]}. Call read() and use one of those."
                else:
                    obs = browser.type(sel, args["text"]) if sel else "type: no selector given"
            elif tool == "press":
                obs = browser.press(args.get("key", "Enter"))
            elif tool == "read":
                obs = browser.read()
                _last_snapshot_refs.clear()
                _last_snapshot_refs.update(re.findall(r"\[(e\d+)\]", obs))
            elif tool == "screenshot":
                obs = f"screenshot taken ({len(steps)} steps so far)"
            elif tool == "done":
                ans = str(args.get("answer", "")).strip()
                if not ans:
                    obs = "done() had empty answer — ignored, continue"
                    messages.append({"role": "assistant", "content": json.dumps(action)})
                    messages.append({"role": "user", "content": "Your done(answer) had an empty answer. Either continue with a tool call, or call done() with your final answer text."})
                    steps.append(f"step {step_no+1}: done(empty) ignored")
                    continue
                final = ans
                break
            else:
                obs = f"unknown tool {tool}"
        except Exception as e:
            obs = f"TOOL_ERROR: {type(e).__name__}: {e}"[:300]

        steps.append(f"step {step_no+1}: {tool} {args} -> {obs[:200]}")
        # ponytail: screenshot every 3rd step only — judge caps at 10 images anyway,
        # and per-step PNGs were choking the 2GB gateway boxes
        screenshot_b64 = browser.screenshot_b64() if step_no % 3 == 0 or tool == "done" else None
        if screenshot_b64:
            screenshots.append(screenshot_b64)
        if browser.challenge_detected():
            cleared = browser.challenge_wait(max_wait_s=15)
            if cleared:
                obs_note = "challenge persisted after wait"
                final = f"BLOCKED: challenge page persisted after step {step_no+1} and did not auto-clear"
                break
            else:
                obs = "challenge auto-cleared after wait"
                steps.append(f"step {step_no+1}.5: challenge auto-cleared")
        messages.append({"role": "assistant", "content": json.dumps(action)})
        # Mid-task worker death surfaces as "no browser session" on the NEXT
        # snapshot — previously that exception escaped run_task() and zeroed
        # the task as HARNESS_ERROR (run10's tab-loss kills). Keep it inside
        # the loop: the agent sees the typed error and can re-goto.
        try:
            obs_text = browser.read()[:3000]
        except Exception as e:
            obs_text = f"READ_ERROR: {type(e).__name__}: {e}"[:300]
        messages.append({"role": "user", "content": (
            f"OBSERVATION:\n{obs}\n\nPAGE TEXT (first 3000 chars):\n"
            f"{obs_text}\n(a screenshot of the current page is attached)"
        )})

    if final is None:
        final = "MAX_STEPS_EXCEEDED"
    return final, steps, screenshots
