"""Probe: navigate a known-BLOCKED Cloudflare site through the deployed MCP
customer surface, poll for challenge markers, and report what the solver does.
Usage: python3 probe_cf.py <url> [watch_secs]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from wolverine_bench.mcp_driver import McpBrowser  # noqa: E402

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.indeed.com"
watch = int(sys.argv[2]) if len(sys.argv) > 2 else 60

b = McpBrowser()
try:
    t0 = time.time()
    out = b.goto(url)
    print(f"=== goto returned in {time.time()-t0:.1f}s (auto-solve ran inside navigate)")
    print(out[:800])
    print(f"=== watching {watch}s for challenge clear...")
    deadline = time.time() + watch
    last = None
    while time.time() < deadline:
        detected = b.challenge_detected()
        status = "CHALLENGE" if detected else "clear"
        if status != last:
            print(f"[{time.time()-t0:6.1f}s] {status}")
            last = status
        if not detected:
            snap = b.read()[:400]
            print(f"[{time.time()-t0:6.1f}s] cleared — snapshot head:\n{snap}")
            break
        time.sleep(5)
    else:
        snap = b.read()[:600]
        print(f"=== still challenged after {watch}s — snapshot head:\n{snap}")
finally:
    b.close()