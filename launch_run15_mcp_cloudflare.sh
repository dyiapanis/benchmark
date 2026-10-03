#!/usr/bin/env bash
# Run 15: Cloudflare cluster x3 attempts through the MCP customer surface.
# Driver swap ONLY: glm-5.3-flash -> kimi-k3 (same 300s clock, same 22 tasks,
# same judge). Answers: can a capable driver finish 3-subtask tasks inside
# the real product budget? Deadline/steps stay at product values.
#
# Published form of the exact steering scripts used for the campaign.
# Credentials are read from the environment at runtime -- nothing embedded.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
[ -n "${SEKRETO_API_KEY:-}" ] || { echo "FATAL: SEKRETO_API_KEY not set"; exit 1; }
[ "${#OLLAMA_API_KEY}" -ge 40 ] || { echo "FATAL: OLLAMA_API_KEY missing"; exit 1; }
export WOLVERINE_AGENT_MODEL=kimi-k3
export WOLVERINE_JUDGE_MODEL=minimax-m3
export WOLVERINE_JUDGE_BACKEND=ollama
echo "preflight: ollama-key=ok driver=$WOLVERINE_AGENT_MODEL judge=$WOLVERINE_JUDGE_MODEL/$WOLVERINE_JUDGE_BACKEND surface=MCP(tenant) egress=session-sticky-residential attempts=3 deadline=300s(default) steps=22(default)"
python3 wolverine_bench/run_stealth.py --browser mcp --category Cloudflare --attempts 3 --run-name run15_mcp_cloudflare_kimi_k3
python3 wolverine_bench/run_stealth.py --score run15_mcp_cloudflare_kimi_k3