"""Proxy scheme probe: find the form Firefox accepts for DataImpulse.

Tries: http://user:pass@host:823, socks5://user:pass@host:823 (inline creds in server
string — Firefox accepts inline credentials, playwright's dict auth is what failed).
Prints which scheme loads https://gamestop.com clean (known-blocked from datacenter).

Published form: proxy creds are read from the environment at runtime
(DATAIMPULSE_LOGIN / DATAIMPULSE_PASSWORD); the original local script resolved
them from a secret store.
"""
import os, sys

login = os.environ["DATAIMPULSE_LOGIN"]
password = os.environ["DATAIMPULSE_PASSWORD"]
host = "gw.dataimpulse.com:823"

from camoufox.sync_api import Camoufox

candidates = [
    {"server": f"http://{login}:{password}@{host}"},
    {"server": f"socks5://{login}:{password}@{host}"},
]

for proxy in candidates:
    scheme = proxy["server"].split('//')[0]
    try:
        with Camoufox(headless=True, proxy=proxy) as browser:
            page = browser.new_page()
            resp = page.goto("https://www.gamestop.com", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            content = page.content()[:30000].lower()
            blocked = "just a moment" in content
            # confirm egress IP changed
            page.goto("https://api.ipify.org", timeout=20000)
            egress = page.inner_text("body").strip()
            print(f"{scheme:8s} -> gamestop blocked={blocked}, egress IP={egress}")
            page.close()
    except Exception as e:
        print(f"{scheme:8s} -> ERROR {type(e).__name__}: {str(e)[:90]}")