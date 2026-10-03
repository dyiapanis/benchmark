"""Wolverine gateway driver for the stealth bench.

Drives the DEPLOYED PRODUCT (https://sekreto-gw.fly.dev) over its REST API:
create tab (with per-tab proxy), navigate, click, type, read, screenshot,
solve-captcha. Same tool surface as WolverineBrowser so agent.py is unchanged.

This is the benchmark Sekreto actually wants: the full product stack —
identity store, triage, captcha solver — not raw python camoufox.
"""
import base64
import os
import time

import httpx

GW = os.environ.get("WOLVERINE_BENCH_URL", "https://sekreto-gw.fly.dev")
KEY = os.environ.get("WOLVERINE_API_KEY", os.environ.get("SEKRETO_API_KEY", ""))


def _headers():
    if not KEY:
        raise RuntimeError("WOLVERINE_API_KEY / SEKRETO_API_KEY not set")
    return {"Authorization": f"Bearer {KEY}"}


class GatewayBrowser:
    """One tab on the gateway per task. Mirrors WolverineBrowser's methods."""

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        self.tab_id = None
        self._last_url = None
        self._resurrections = 0
        # ponytail: 90s → 240s — residential-proxy navigations (gw+proxy+churn)
        # exceed 90s on heavy sites; ReadTimeout mid-task was killing tasks 4/8/9.
        self._client = httpx.Client(timeout=240, headers=_headers())

    def __enter__(self):
        import time as _t
        # ponytail: pool-exhaustion retry — tab creation 503s ("all contexts full")
        # when previous task tabs haven't drained yet. Honor retry_after, cap ~60s.
        last = None
        for attempt in range(8):
            try:
                r = self._client.post(f"{GW}/tabs", json={"url": "about:blank", **({"proxy": self.proxy} if self.proxy else {})})
                if r.status_code in (500, 503) and attempt < 7:
                    retry = r.json().get("retry_after", 5) if "json" in r.headers.get("content-type","") else 5
                    _t.sleep(min(float(retry), 10))
                    continue
                r.raise_for_status()
                self.tab_id = r.json().get("tabId") or r.json().get("id") or r.json().get("tab_id")
                return self
            except httpx.HTTPStatusError as e:
                last = e
                _t.sleep(5)
                continue
        # ponytail: `last` is None when the loop exits without any exception
        # (shouldn't happen, but the TypeError it caused was miscategorized as
        # a harness/infra failure in run 8). Raise a real exception either way.
        if isinstance(last, BaseException):
            raise last
        raise RuntimeError(f"{self.__class__.__name__} retries exhausted (tab={self.tab_id})")

    def __exit__(self, *exc):
        if self.tab_id:
            try:
                self._client.delete(f"{GW}/tabs/{self.tab_id}")
            except Exception:
                pass
        self._client.close()

    def _resurrect(self):
        """Tab vanished (worker churn/eviction 404s): fresh tab + replay last goto.
        ponytail: single resurrection per task — if the worker keeps dying, the task
        legitimately fails (prevents infinite churn loops against a broken pool)."""
        import time as _t
        self._resurrections += 1
        if self._resurrections > 2:
            raise RuntimeError("tab died 3x — giving up (pool churn)")
        _t.sleep(3)
        old_tab = self.tab_id
        r = self._client.post(f"{GW}/tabs", json={"url": "about:blank", **({"proxy": self.proxy} if self.proxy else {})})
        r.raise_for_status()
        self.tab_id = r.json().get("tabId") or r.json().get("id")
        if self._last_url:
            self._post("navigate", url=self._last_url)
        return f"resurrected tab {old_tab} -> {self.tab_id}, replayed {self._last_url}"

    def _post(self, path, **json_body):
        # ponytail: linear backoff on 5xx — 2GB perf boxes choke under screenshot+captcha load
        import time as _t
        last = None
        for attempt in range(3):
            try:
                r = self._client.post(f"{GW}/tabs/{self.tab_id}/{path}", json=json_body or {})
                if r.status_code == 404 and path != "navigate":
                    # stale-ref fix: two 404 shapes — dead TAB (resurrect) vs stale REF
                    # (do NOT resurrect: nuking the tab over a bad ref destroyed
                    # cookies/identity and killed tasks as "tab died 3x").
                    err = ""
                    try:
                        err = r.json().get("error", "")
                    except Exception:
                        pass
                    if "tab not found" in err:
                        self._resurrect()
                        continue
                    # stale ref — return the server's error json, caller surfaces it
                    return {"ok": False, "error": err or f"HTTP 404 on {path}"}
                if r.status_code >= 500 and attempt < 2:
                    _t.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                last = e
                if attempt < 2:
                    _t.sleep(5 * (attempt + 1))
                    continue
                raise
        # ponytail: `last` is None when the loop exits without any exception
        # (shouldn't happen, but the TypeError it caused was miscategorized as
        # a harness/infra failure in run 8). Raise a real exception either way.
        if isinstance(last, BaseException):
            raise last
        raise RuntimeError(f"{self.__class__.__name__} retries exhausted (tab={self.tab_id})")

    # ── tool surface (same contract as WolverineBrowser) ─────────────────
    def goto(self, url: str) -> str:
        self._last_url = url
        out = self._post("navigate", url=url)
        status = out.get("status_code") or out.get("status") or out.get("http_status") or "?"
        return f"goto {url} -> HTTP {status}"

    def click(self, ref: str) -> str:
        out = self._post("click", **{"ref": ref})
        if out.get("ok") is False:
            # stale-ref fix: stale/hallucinated ref — recoverable, tell the agent to re-read
            return f"STALE_REF: {out.get('error', 'ref not found')} — call read() to get fresh refs"
        if out.get("ok") is True and out.get("trusted") is False:
            return f"clicked ref {ref!r} (untrusted JS fallback)"
        return f"clicked ref {ref!r}"

    def type(self, ref: str, text: str) -> str:
        out = self._post("type", **{"ref": ref, "text": text})
        if out.get("ok") is False:
            return f"STALE_REF: {out.get('error', 'ref not found')} — call read() to get fresh refs"
        return f"typed into ref {ref!r}"

    def press(self, key: str) -> str:
        self._post("press", key=key)
        return f"pressed {key}"

    def _get_json(self, path, tries: int = 3):
        import time as _t
        last = None
        for attempt in range(tries):
            try:
                r = self._client.get(f"{GW}{path}")
                if r.status_code == 404 and f"/tabs/{self.tab_id}/" in path:
                    self._resurrect()
                    path = f"/tabs/{self.tab_id}/" + path.rsplit("/", 1)[-1]
                    continue
                if r.status_code >= 500 and attempt < tries - 1:
                    _t.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                last = e
                if attempt < tries - 1:
                    _t.sleep(5 * (attempt + 1))
                    continue
                raise
        # ponytail: `last` is None when the loop exits without any exception
        # (shouldn't happen, but the TypeError it caused was miscategorized as
        # a harness/infra failure in run 8). Raise a real exception either way.
        if isinstance(last, BaseException):
            raise last
        raise RuntimeError(f"{self.__class__.__name__} retries exhausted (tab={self.tab_id})")

    def read(self) -> str:
        return str(self._get_json(f"/tabs/{self.tab_id}/snapshot").get("snapshot", ""))[:12000]

    def snapshot(self) -> str:
        r = self._client.get(f"{GW}/tabs/{self.tab_id}/snapshot")
        r.raise_for_status()
        return str(r.json().get("snapshot", ""))[:12000]

    def screenshot_b64(self) -> str:
        import time as _t
        for attempt in range(3):
            try:
                r = self._client.get(f"{GW}/tabs/{self.tab_id}/screenshot")
                if r.status_code == 404:
                    self._resurrect()
                    continue
                if r.status_code >= 500 and attempt < 2:
                    _t.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    return r.json().get("image") or r.json().get("screenshot", "")
                return base64.b64encode(r.content).decode()
            except httpx.HTTPStatusError:
                if attempt == 2:
                    raise
                _t.sleep(5 * (attempt + 1))
        return ""

    def solve_captcha(self) -> str:
        """Product capability the local driver lacks: POST /tabs/{id}/solve-captcha."""
        try:
            out = self._post("solve-captcha")
            return f"solve-captcha: {out}"
        except Exception as e:
            return f"solve-captcha error: {e}"

    def challenge_detected(self) -> bool:
        try:
            r = self._client.get(f"{GW}/tabs/{self.tab_id}/snapshot")
            r.raise_for_status()
            content = str(r.json().get("snapshot", "")).lower()[:30000]
        except Exception:
            return False
        return any(m in content for m in [
            "just a moment", "checking your browser", "cf-challenge",
            "attention required", "verify you are human", "captcha",
            "access denied", "perimeterx", "px-captcha", "datadome",
            "are you a robot", "unusual traffic",
        ])

    def challenge_wait(self, max_wait_s: int = 12) -> bool:
        """Gateway variant: challenge detected -> try solve-captcha, then wait."""
        if not self.challenge_detected():
            return False
        self.solve_captcha()  # product's own solver first
        import time as _t
        deadline = _t.time() + max_wait_s
        while _t.time() < deadline:
            _t.sleep(4)
            if not self.challenge_detected():
                return False
        return True