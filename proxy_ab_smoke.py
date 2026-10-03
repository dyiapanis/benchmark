"""A/B smoke: proxy vs datacenter on the tasks that blocked at step 1-2 in run 2.

Takes the 20 worst-blocked tasks, retries each entry URL through Camoufox WITH the
DataImpulse residential proxy, reports which sites now load clean. Pennies of cost.

Published form: proxy creds are read from the environment at runtime
(DATAIMPULSE_LOGIN / DATAIMPULSE_PASSWORD); the original local script resolved
them from a secret store.
"""
import base64, hashlib, json, re, sys
from pathlib import Path
from cryptography.fernet import Fernet

BENCH = Path(__file__).resolve().parent
proxy = {"server": "socks5://127.0.0.1:1080"}  # via local stdlib relay (auth upstream)

# 1. Tasks that blocked at step 1-2 in run 2 (challenge-persisted failures)
blocked = []
for line in open(BENCH/"results/camoufox_run2.jsonl"):
    d = json.loads(line)
    if not d['verdict'] and 'BLOCKED: challenge' in d['final_result']:
        blocked.append(d['task_id'])
blocked = sorted(blocked)[:20]
print(f"retrying {len(blocked)} challenge-blocked tasks through residential proxy")

# 2. Task set for URLs
key = base64.urlsafe_b64encode(hashlib.sha256(b"Stealth_Bench_V1").digest())
tasks = json.loads(Fernet(key).decrypt(base64.b64decode((BENCH/"Stealth_Bench_V1.enc").read_text())))

from camoufox.sync_api import Camoufox

results = []
with Camoufox(headless=True, proxy=proxy) as browser:
    for tid in blocked:
        t = next(x for x in tasks if x['task_id']==tid)
        url = re.search(r"Go to (https?://[^\s,]+)", t['confirmed_task'])
        url = url.group(1) if url else None
        if not url:
            continue
        try:
            page = browser.new_page()
            resp = page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)  # give challenge pages time to clear
            content = page.content()[:30000].lower()
            markers = ["just a moment", "checking your browser", "verify you are human",
                       "access denied", "px-captcha", "datadome", "are you a robot", "unusual traffic"]
            fired = [m for m in markers if m in content]
            title = page.title()[:50]
            print(f"  [{tid:3d}] {url[:45]:45s} status={resp.status if resp else '?'} blocked={bool(fired)} title={title!r}")
            results.append({'task_id': tid, 'url': url, 'blocked': bool(fired), 'title': title})
            page.close()
        except Exception as e:
            print(f"  [{tid:3d}] {url[:45]:45s} ERROR {type(e).__name__}: {str(e)[:60]}")
            results.append({'task_id': tid, 'url': url, 'blocked': None, 'error': str(e)[:100]})

clean = sum(1 for r in results if r.get('blocked') is False)
blocked_now = sum(1 for r in results if r.get('blocked') is True)
errs = sum(1 for r in results if r.get('blocked') is None)
print(f"\nA/B smoke result: {clean}/{len(results)} now load clean (was 0), {blocked_now} still blocked, {errs} errors")
json.dump(results, open(BENCH/"results/proxy_smoke.json","w"), indent=1)