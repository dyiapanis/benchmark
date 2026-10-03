"""Stale-ref regression checks: a stale-ref 404 must NOT resurrect the tab;
a hallucinated ref must be caught.

Runs the gateway_driver._post + agent click guard against canned server
responses. Fails loudly if the fix regresses. (Offline: needs no network.)
"""
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wolverine_bench.gateway_driver as gd  # noqa: E402
import wolverine_bench.agent as ag  # noqa: E402


class FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
    def json(self):
        return self._body if isinstance(self._body, dict) else json.loads(self._body)
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
    @property
    def headers(self):
        return {}

class FakeClient:
    def __init__(self, responses): self.responses = list(responses); self.posts = []
    def post(self, url, json=None):
        self.posts.append((url, json))
        return self.responses.pop(0)

def test_stale_ref_404_no_resurrect():
    b = gd.GatewayBrowser.__new__(gd.GatewayBrowser)
    b.tab_id = "p9"; b._resurrections = 0; b._last_url = "https://x.com"
    b.proxy = None
    b._client = FakeClient([FakeResp(404, {"ok": False, "error": "ref e99 not found — call /snapshot first"})])
    def boom(): raise AssertionError("must not resurrect on stale ref")
    b._resurrect = boom
    out = b._post("click", **{"ref": "e99"})
    assert out.get("ok") is False and "e99" in out["error"], out
    assert b._resurrections == 0
    print("PASS: stale-ref 404 -> returned error json, no resurrect")

def test_dead_tab_404_still_resurrects():
    b = gd.GatewayBrowser.__new__(gd.GatewayBrowser)
    b.tab_id = "p9"; b._resurrections = 0; b._last_url = "https://x.com"; b.proxy = None
    calls = {"resurrected": 0}
    def fake_resurrect():
        calls["resurrected"] += 1
        b.tab_id = "p10"
        return "resurrected"
    b._resurrect = fake_resurrect
    b._client = FakeClient([
        FakeResp(404, {"ok": False, "error": "tab not found"}),
        FakeResp(200, {"ok": True, "clicked": "e1", "trusted": True}),
    ])
    out = b._post("click", **{"ref": "e1"})
    assert calls["resurrected"] == 1 and out.get("ok") is True, out
    print("PASS: dead-tab 404 -> resurrect, retry succeeds")

def test_click_surface_messages():
    b = gd.GatewayBrowser.__new__(gd.GatewayBrowser)
    b.tab_id = "p1"; b._resurrections = 0; b._last_url = None; b.proxy = None
    b._client = FakeClient([
        FakeResp(404, {"ok": False, "error": "ref e42 not found — call /snapshot first"}),
        FakeResp(200, {"ok": True, "clicked": "e1", "trusted": False}),
        FakeResp(200, {"ok": True, "clicked": "e2", "trusted": True}),
    ])
    msg = b.click("e42")
    assert "STALE_REF" in msg and "read()" in msg, msg
    msg = b.click("e1")
    assert "untrusted" in msg, msg
    msg = b.click("e2")
    assert msg == "clicked ref 'e2'", msg
    print("PASS: click() surfaces STALE_REF / untrusted / clean messages")

def test_agent_hallucination_guard():
    ag._last_snapshot_refs.clear()
    ag._last_snapshot_refs.update(["e1", "e5", "e12"])
    sel = "e99"
    assert sel not in ag._last_snapshot_refs and re.fullmatch(r"e\d+", sel)
    obs = f"HALLUCINATED_REF check: {sel!r} not in snapshot"
    assert "e99" in obs and "HALLUCINATED" in obs
    # valid ref passes through
    assert "e5" in ag._last_snapshot_refs
    # regex extracts refs from a snapshot line
    snap = '- link "Sign in" [e7]\n- button "Go" [e12]'
    refs = set(re.findall(r"\[(e\d+)\]", snap))
    assert refs == {"e7", "e12"}, refs
    print("PASS: agent-side hallucination guard logic")

if __name__ == "__main__":
    test_stale_ref_404_no_resurrect()
    test_dead_tab_404_still_resurrects()
    test_click_surface_messages()
    test_agent_hallucination_guard()
    print("\nALL STALE-REF CHECKS PASS")