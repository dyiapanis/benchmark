#!/usr/bin/env bash
# Run 10 (real): Cloudflare cluster through the MCP customer surface.
# Tenant key -> gateway binds session-sticky residential egress.
#
# Published form of the exact steering scripts used for the campaign
# (2026-08-28 .. 2026-10-03). Credentials are read from the environment at
# runtime -- SEKRETO_API_KEY (gateway tenant key) and OLLAMA_API_KEY (agent +
# judge backend). The original local wrappers sourced them from a secret
# store; nothing is embedded here.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
[ -n "${SEKRETO_API_KEY:-}" ] || { echo "FATAL: SEKRETO_API_KEY not set"; exit 1; }
[ "${#OLLAMA_API_KEY}" -ge 40 ] || { echo "FATAL: OLLAMA_API_KEY missing"; exit 1; }
export WOLVERINE_AGENT_MODEL=kimi-k2.6
export WOLVERINE_JUDGE_MODEL=minimax-m3
export WOLVERINE_JUDGE_BACKEND=ollama
echo "preflight: ollama-key=ok driver=$WOLVERINE_AGENT_MODEL judge=$WOLVERINE_JUDGE_MODEL/$WOLVERINE_JUDGE_BACKEND surface=MCP(tenant) egress=session-sticky-residential"
python3 wolverine_bench/run_stealth.py --browser mcp --category Cloudflare --run-name run10_mcp_cloudflare