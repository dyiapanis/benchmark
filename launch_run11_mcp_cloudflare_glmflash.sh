#!/usr/bin/env bash
# Run 11 (a.k.a. launch_run14 script): Cloudflare cluster x3 attempts through
# the MCP customer surface. Tenant key -> gateway binds session-sticky
# residential egress. Agent: glm-5.3-flash. Judge: minimax-m3.
# 3x majority per the Turnstile coin-flip rule (single attempts are noise).
#
# Published form of the exact steering scripts used for the campaign.
# Credentials are read from the environment at runtime -- nothing embedded.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
[ -n "${SEKRETO_API_KEY:-}" ] || { echo "FATAL: SEKRETO_API_KEY not set"; exit 1; }
[ "${#OLLAMA_API_KEY}" -ge 40 ] || { echo "FATAL: OLLAMA_API_KEY missing"; exit 1; }
export WOLVERINE_AGENT_MODEL=glm-5.3-flash
export WOLVERINE_JUDGE_MODEL=minimax-m3
export WOLVERINE_JUDGE_BACKEND=ollama
echo "preflight: ollama-key=ok driver=$WOLVERINE_AGENT_MODEL judge=$WOLVERINE_JUDGE_MODEL/$WOLVERINE_JUDGE_BACKEND surface=MCP(tenant) egress=session-sticky-residential attempts=3"
python3 wolverine_bench/run_stealth.py --browser mcp --category Cloudflare --attempts 3 --run-name run11_mcp_cloudflare_glmflash
python3 wolverine_bench/run_stealth.py --score run11_mcp_cloudflare_glmflash