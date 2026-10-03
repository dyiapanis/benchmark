#!/bin/bash
# DataImpulse SOCKS5 relay: localhost:1080 (no auth) -> upstream socks5 with creds.
# Browser side only ever sees socks5://127.0.0.1:1080 — Playwright-Firefox constraint solved.
# Published form: UPSTREAM_URI (creds included) comes from the environment.
set -e
exec pproxy -l "socks5://127.0.0.1:1080" -r "$UPSTREAM_URI" -v 0