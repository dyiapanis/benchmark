"""Camoufox (Playwright-Firefox) browser driver for the stealth bench.

Minimal tool surface: goto, click, type, read, screenshot, done.
No CDP — this is the whole point: Firefox-native automation over Juggler,
exactly what our production engine exposes.
"""
import base64
import time
from camoufox.sync_api import Camoufox

class WolverineBrowser:
    """One browser per task run. Reuses the official judge's screenshot convention."""

    def __init__(self, headless: bool = True, proxy: dict | str | None = None):
        self.headless = headless
        # accept both forms: {"server": "..."} or "socks5://host:port"
        if isinstance(proxy, str):
            proxy = {"server": proxy}
        self._proxy = proxy
        self._pw = None
        self._browser = None
        self.page = None

    def __enter__(self):
        self._pw = Camoufox(headless=self.headless, proxy=self._proxy)
        self._browser = self._pw.__enter__()
        self.page = self._browser.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self._pw.__exit__(*exc)
        except Exception:
            pass

    # ── tools ────────────────────────────────────────────────────────────
    def goto(self, url: str) -> str:
        resp = self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)  # let JS settle briefly
        status = resp.status if resp else 0
        return f"goto {url} -> HTTP {status}, title={self.page.title()!r}"

    def click(self, selector: str) -> str:
        el = self.page.locator(selector).first
        el.click(timeout=10000)
        self.page.wait_for_timeout(500)
        return f"clicked {selector!r}"

    def type(self, selector: str, text: str) -> str:
        el = self.page.locator(selector).first
        el.fill(text, timeout=10000)
        return f"typed into {selector!r}"

    def press(self, key: str) -> str:
        self.page.keyboard.press(key)
        self.page.wait_for_timeout(400)
        return f"pressed {key}"

    def read(self) -> str:
        # visible text, collapsed — the agent's page context
        return self.page.inner_text("body")[:12000]

    def screenshot_b64(self) -> str:
        return base64.b64encode(self.page.screenshot()).decode()

    def challenge_wait(self, max_wait_s: int = 12) -> bool:
        """If a challenge page is showing, wait for it to auto-clear (real-browser
        behavior). Returns True if a challenge is STILL present after waiting."""
        if not self.challenge_detected():
            return False
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            time.sleep(2)
            try:
                self.page.wait_for_timeout(500)
            except Exception:
                pass
            if not self.challenge_detected():
                return False
        return True

    def challenge_detected(self) -> bool:
        content = self.page.content()[:30000].lower()
        return any(m in content for m in [
            "just a moment", "checking your browser", "cf-challenge",
            "attention required", "verify you are human", "captcha",
            "access denied", "perimeterx", "px-captcha", "datadome",
            "are you a robot", "unusual traffic",
        ])
