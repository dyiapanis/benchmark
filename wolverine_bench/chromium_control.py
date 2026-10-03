"""Vanilla Chromium control driver — same tool surface as WolverineBrowser.

These are the harness-validation baselines: local_headless should score ~3%,
local_headful ~50% (matching the official stealth bench numbers) if our harness
is comparable to browser-use's.
"""
import base64


class LocalChromium:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self.page = self._browser.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def goto(self, url: str) -> str:
        resp = self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)
        status = resp.status if resp else 0
        return f"goto {url} -> HTTP {status}, title={self.page.title()!r}"

    def click(self, selector: str) -> str:
        self.page.locator(selector).first.click(timeout=10000)
        self.page.wait_for_timeout(500)
        return f"clicked {selector!r}"

    def type(self, selector: str, text: str) -> str:
        self.page.locator(selector).first.fill(text, timeout=10000)
        return f"typed into {selector!r}"

    def press(self, key: str) -> str:
        self.page.keyboard.press(key)
        self.page.wait_for_timeout(400)
        return f"pressed {key}"

    def read(self) -> str:
        return self.page.inner_text("body")[:12000]

    def screenshot_b64(self) -> str:
        return base64.b64encode(self.page.screenshot()).decode()

    def challenge_wait(self, max_wait_s: int = 12) -> bool:
        """Mirror WolverineBrowser.challenge_wait for the controls."""
        if not self.challenge_detected():
            return False
        import time as _t
        deadline = _t.time() + max_wait_s
        while _t.time() < deadline:
            _t.sleep(2)
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