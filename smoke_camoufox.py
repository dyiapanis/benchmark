"""Smoke: launch Camoufox via Playwright-Firefox, hit a protected site, report."""
from camoufox.sync_api import Camoufox
import time, sys

SITE = sys.argv[1] if len(sys.argv) > 1 else "https://www.cloudflare.com"
import sys
with Camoufox(headless=True) as browser:
    page = browser.new_page()
    t0 = time.time()
    resp = page.goto(SITE, timeout=30000, wait_until="domcontentloaded")
    status = resp.status if resp else "?"
    title = page.title()
    # crude bot-check: look for challenge markers
    content = page.content()[:20000].lower()
    challenge = any(m in content for m in ["just a moment", "checking your browser", "cf-challenge", "attention required", "verify you are human", "captcha"])
    print(f"site={SITE} status={status} title={title!r} challenge={challenge} load={time.time()-t0:.1f}s")
