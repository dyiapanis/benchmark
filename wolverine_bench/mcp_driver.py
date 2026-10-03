"""MCP driver for the stealth bench — drives the deployed product through the
CUSTOMER surface: gateway /mcp, tools/call browser_navigate (auto-fires the
captcha solver inside navigation), browser_snapshot/click/type/press.

Same interface as GatewayBrowser/WolverineBrowser so agent.py is unchanged:
goto/click/type/press/read/screenshot_b64/challenge_detected/challenge_wait.
challenge_wait returns True = challenge PERSISTED (matches gateway_driver).
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

GW = os.environ.get("WOLVERINE_BENCH_URL", "https://sekreto-gw.fly.dev")
API_KEY = os.environ.get("SEKRETO_API_KEY", "")

# MCP 2026-07-28 stateless: every request declares itself via params._meta
# (SEP-2575); SEP-2243 Mcp-Method/Mcp-Name headers must match the body.
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


def _mcp_post(payload, timeout=90):
    method = payload["method"]
    target = payload.get("params", {}).get("name")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {API_KEY}",
        "Mcp-Method": method,
    }
    if target:
        headers["Mcp-Name"] = target
    req = urllib.request.Request(
        GW.rstrip("/") + "/mcp", data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        # Worker reap / drain mid-task: gateway returns 404/502 when the
        # routed worker dies. The browser context died with it — raise the
        # typed error so the caller restarts with goto.
        raise McpTabLost(f"HTTP {e.code}") from e
    body = resp.read().decode().strip()
    if not body:
        return None
    if body.startswith("data: ") or "\ndata: " in body[:50]:
        for line in body.split("\n"):
            if line.startswith("data: "):
                raw = line[6:].strip()
                if raw and raw != "[DONE]":
                    return json.loads(raw)
        return None
    return json.loads(body)


class McpTabLost(Exception):
    """Worker died mid-task — browser context lost; caller must re-navigate."""


class McpBrowser:
    def __init__(self, proxy=None):  # proxy ignored: gateway binds session egress
        self._counter = 0

    def _call(self, tool, args, timeout=120):
        return self._call_once(tool, args, timeout)

    def _call_once(self, tool, args, timeout=120):
        self._counter += 1
        body = _mcp_post(
            {"jsonrpc": "2.0", "id": self._counter, "method": "tools/call",
             "params": {"name": tool, "arguments": args, "_meta": META}},
            timeout=timeout,
        )
        if body is None:
            raise RuntimeError("empty MCP response")
        if "error" in body:
            raise RuntimeError(f"MCP error: {body['error']}")
        blocks = body.get("result", {}).get("content", [])
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        if body.get("result", {}).get("isError"):
            raise RuntimeError(f"tool error: {'; '.join(texts)[:300]}")
        return "\n".join(texts)

    # ── agent.py surface ────────────────────────────────────────────────
    def goto(self, url):
        # MCP navigate auto-fires the solver (fixed build) and returns a snapshot.
        out = self._call("browser_navigate", {"url": url, "timeout_secs": 90}, timeout=180)
        return f"goto {url}\n{out}"[:6000]

    def read(self):
        return self._call("browser_snapshot", {})[:12000]

    def click(self, ref):
        return self._call("browser_click", {"ref": ref})[:4000]

    def type(self, ref, text):
        return self._call("browser_type", {"ref": ref, "text": text})[:4000]

    def press(self, key):
        return self._call("browser_press", {"key": key})[:2000]

    def screenshot_b64(self):
        try:
            out = self._call("browser_screenshot", {})
            m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", out)
            if m:
                return m.group(1)
            if re.fullmatch(r"[A-Za-z0-9+/=\s]+", out) and len(out) > 1000:
                return re.sub(r"\s", "", out)
        except Exception:
            pass
        return None

    def close(self):
        try:
            self._call("browser_close", {})
        except Exception:
            pass

    _MARKERS = [
        "just a moment", "checking your browser", "cf-challenge",
        "attention required", "verify you are human", "captcha",
        "access denied", "perimeterx", "px-captcha", "datadome",
        "are you a robot", "unusual traffic",
    ]

    def challenge_detected(self):
        try:
            content = self.read().lower()[:30000]
        except Exception:
            return False
        return any(m in content for m in self._MARKERS)

    def challenge_wait(self, max_wait_s=15):
        """True = challenge persisted. Navigate already auto-solved; give the
        interstitial a bounded window to clear, re-snapshotting."""
        if not self.challenge_detected():
            return False
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            time.sleep(4)
            if not self.challenge_detected():
                return False
        return True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()