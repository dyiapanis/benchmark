# Wolverine / Sekreto — Stealth Bench V1 campaign results

Addendum to this fork: we ran the [Browser Use Stealth Bench V1](README.md)
task set with **Wolverine** (the engine behind [Sekreto](https://sekreto.ai)) —
a Firefox-native, Camoufox-based browser automation product — as an additional
provider, across **six full 80-task runs** (2026-08-28 → 2026-09-01) plus a
**depth series on the Cloudflare cluster through the customer MCP surface**
(2026-09-02 → 2026-10-03).

**Headline: our scores are NOT competitive with the leaderboard band.** Best
configuration: 8/80 = **10.0%** (bare engine, datacenter egress). Full product
through the customer surface: **0-3.75%** across four runs. Official
browser-use-cloud results in this same repo: 73.8-80.0% per run. We publish
the complete raw data anyway — that is the point of an open rig, and our
methodology pre-committed to publishing regardless of outcome. Nothing on this
page is a leaderboard claim.

All raw JSONLs are in [`results/`](results/) and every number below
reproduces from them with the included scoring scripts.

---

## 1. Rig identity

- Task set: `Stealth_Bench_V1.enc` — byte-identical to upstream's at the fork
  point (80 tasks; decrypt per the README). Vendor mix: Cloudflare 22,
  PerimeterX 18, Datadome 13, reCaptcha 6, Akamai 6, Custom Antibot 5,
  GeeTest 4, hCaptcha 3, Kasada 1, Shape 1, Temu Slider 1 (sums to 80).
- Judge criteria: upstream's `judge.py` (`construct_judge_messages` +
  `JudgementResult`) used verbatim — the judge answers only "was the agent
  blocked / did it complete the task".
- Scoring rule: a task is green iff >50% of its **valid** attempts are judged
  True. Valid attempt = the agent loop produced a real final_result, the judge
  returned a verdict, and neither a harness/agent-LLM error occurred (the
  runner's `valid_rec` rule, shipped in `wolverine_bench/run_stealth.py`;
  judge-error attempts are excluded from the majority, never scored).
  Headline scores are quoted as green/80 (raw, cross-run comparable); where a
  run lost attempts to infra, the green/valid form is given alongside.

## 2. Declared deviations (read before comparing)

1. **Harness swap.** browser-use's agent (0.11.5) is Chromium-CDP-hardwired
   (`BrowserChannel` has no Firefox path; Firefox deprecated CDP). Camoufox is
   Juggler/Firefox. There is no honest way to plug a Firefox-native engine
   into their runner — so the agent loop is ours (`wolverine_bench/`):
   same task inputs, same judge, same timeout/step budget shape, same JSONL
   output schema, different browser layer. This is the deviation the rig
   exists to measure.
2. **Agent model.** kimi-k2.6 (css-mode runs) / glm-5.3-flash / kimi-k3 (MCP
   series) via Ollama Cloud, not the models upstream's official rows used.
3. **Judge model.** deepseek-v4-flash-vision-exp via OpenCode Go (runs 2-7),
   minimax-m3 via Ollama Cloud (runs 9-15, vision-verified). **Cross-judge
   comparisons are invalid** — run 7 (3.75%) vs run 9 (1.25%) differ by judge
   severity, not regression. Same-judge comparisons start at run 9.
4. **Headful control.** Our `local_headful` control is stock Chromium via
   Playwright; upstream's 50% control used browser-use's own stealth-patched
   Chromium build. Not comparable — declared deviation. The headless control
   IS comparable (both stock).

## 3. Controls (harness validation)

| Control (ours, through our harness) | Result | Official (this repo) |
|---|---|---|
| local_headless (stock Chromium) | 0/5 sampled, all blocked at entry | 1-3/80 per run = 1.2-3.8% |
| local_headful (stock Chromium) | 0/3 sampled — not comparable (see deviation 4) | 39-42/80 = 48.8-52.5% |

Headless control is consistent with the official band (0/5 is within noise of
a 2-3% pass rate); the headful control is a declared non-comparison.

## 4. Fleet configuration per run

| Run | Date | Surface | Egress | Engine | Agent (mode / model) | Judge |
|---|---|---|---|---|---|---|
| run2 | 2026-08-29 | local Camoufox via Playwright-Firefox | datacenter (Hetzner host: Ryzen 9 7940HS, 16 threads) | Camoufox 152.0.4-beta.29 | css-mode / kimi-k2.6 | deepseek-v4-flash-vision-exp |
| run3 | 2026-08-29 | local Camoufox | DataImpulse residential (stdlib SOCKS5 auth relay, `relay_stdlib.py`) | beta.29 | css / kimi-k2.6 | deepseek-v4-flash-vision-exp |
| run4/5 | 2026-08-29 | deployed product: gateway REST `/tabs`, warm worker pool (2GB perf-1x, Fly fra) | datacenter (Fly fra) | beta.29 | ref-mode / kimi-k2.6 | deepseek-v4-flash-vision-exp |
| run6 | 2026-08-29 | deployed product, per-tab proxy requested | DataImpulse residential per-tab (http-auth CONNECT) | beta.29 | ref / kimi-k2.6 | deepseek-v4-flash-vision-exp |
| run7 | 2026-08-29 | deployed product + stale-ref fix (see `tests_stale_ref.py`) | datacenter (Fly fra) | beta.29 | ref / kimi-k2.6 | deepseek-v4-flash-vision-exp |
| run9 | 2026-09-01 | deployed product + session-instance reuse | datacenter (Fly fra) | beta.29 | ref / kimi-k2.6 | minimax-m3 |
| run10-15 | 2026-09-02 → 2026-10-03 | deployed product via the **customer MCP surface** (`/mcp`, `wolverine_bench/mcp_driver.py`) — what a paying tenant gets; Cloudflare cluster (22 tasks) x3 attempts | session-sticky residential, bound per tenant session by the gateway (DataImpulse pool) | deployed pool: beta.29 → beta.30 → beta.31-era builds across the window (engine build is NOT a controlled variable in this series) | ref / kimi-k2.6 (run10), glm-5.3-flash (run11/14), kimi-k3 (run15) | minimax-m3 |

Proxy A/B entry smoke (`results/proxy_smoke.json`, 2026-08-29): the 20 tasks
that hard-blocked at entry from datacenter were retried entry-only through
DataImpulse residential with the same engine: **12/20 loaded clean vs 0/20
from datacenter** — IP reputation was the dominant entry-block factor, but
(as run 3 shows) entry-pass did not convert into full-task passes.

## 5. Ledger — full 80-task runs

| # | Config | Score | Infra (HE rows) | Valid attempts | Raw file |
|---|---|---|---|---|---|
| run2 | bare engine, datacenter, css-agent | **8/80 = 10.0%** | 1* | 79 | `camoufox_run2.jsonl` |
| run3 | bare engine, residential, css-agent | **5/80 = 6.25%** | 1* | 79 | `camoufox_run3.jsonl` |
| run4/5 | product (gateway), datacenter, ref-agent | **1/80 = 1.25%** | 7 | 73 | `gateway_run4.jsonl` |
| run6 | product, per-tab residential | **0/80 = 0%** | 24 | 56 | `run6_gw_beta29_residential.jsonl` |
| run7 | product + stale-ref fix, datacenter | **3/80 = 3.75%** | 6 | 73 | `run7_sek83_datacenter.jsonl` |
| run9 | product + session reuse, datacenter | **1/80 = 1.25%** | 5 | 75 | `run9_sek85_scored.jsonl` |

\* Task 70 (Akamai) hit a Playwright page-content error in both bare-engine
runs; the harness version of that era recorded `HARNESS_ERROR:` as the final
result but still judged the attempt False. The current strict rule
(`valid_rec`) excludes those rows as invalid; the era rule counted them as
False verdicts. **Green counts are identical under both rules** — the rows
affect only the valid-attempt denominators (79 vs 80), never a green.
run7 additionally has 1 judge-error attempt excluded from its 73.

Six-run mean (green/80): **3.75%** (sample stdev 3.79pp). run8 was a
judge-misconfig discard (superseded by run9). run1 was a selector-bug
shakedown (`camoufox_run1_SELECTOR_BUG.jsonl`, kept for provenance).

## 6. Per-vendor breakdown (green tasks, full runs)

| Vendor (n) | run2 bare/DC | run3 bare/res | run4 prod/DC | run6 prod/res | run7 fix/DC | run9 fix/DC |
|---|---|---|---|---|---|---|
| Cloudflare (22) | 4 = 18.2% | 4 = 18.2% | 1 = 4.5% | 0 | 1 = 4.5% | 1 = 4.5% |
| PerimeterX (18) | 1 = 5.6% | 1 = 5.6% | 0 | 0 | 0 | 0 |
| Datadome (13) | 2 = 15.4% | 0 | 0 | 0 | 0 | 0 |
| Akamai (6) | 0 | 0 | 0 | 0 | 2 = 33.3% | 0 |
| reCaptcha (6) | 0 | 0 | 0 | 0 | 0 | 0 |
| GeeTest (4) | 0 | 0 | 0 | 0 | 0 | 0 |
| Custom Antibot (5) | 1 = 20% | 0 | 0 | 0 | 0 | 0 |
| hCaptcha (3) | 0 | 0 | 0 | 0 | 0 | 0 |
| Kasada (1) | 0 | 0 | 0 | 0 | 0 | 0 |
| Shape (1) | 0 | 0 | 0 | 0 | 0 | 0 |
| Temu Slider (1) | 0 | 0 | 0 | 0 | 0 | 0 |

## 7. MCP customer-surface depth series (Cloudflare cluster, 22 tasks x3 attempts)

Through the deployed product's MCP endpoint — tenant key, session-sticky
residential egress, product step budget (22) and deadline (300s), judge
minimax-m3, 3-attempt majority.

| Run | Driver model | Tasks green | Note |
|---|---|---|---|
| run10 | kimi-k2.6 | 0/22 | single-attempt probe |
| run11 | glm-5.3-flash | **2/22 = 9.1%** | best of series (2026-09-03) |
| run12 | glm-5.3-flash | (aborted restart, 5 rows) | not a run |
| run14 | glm-5.3-flash | 0/22 | same config as run11, different day |
| run15 | kimi-k3 | **0/22** | 2026-10-03: **all 66/66 attempts blocked at entry — every `goto` in every attempt returned HTTP 401/429** (two rows surface as MAX_STEPS because the agent burned its budget retrying entry); the driver-capability question is mooted by an IP-reputation entry wall. DataImpulse pool health regressed vs 2026-09-03 (run11 got mixed challenge-vs-pass entries on the same path) |

(`run13` does not exist — a log copy of run11. Solver-only experiments on
beta.30 are `run10_solver_beta30*.jsonl`, excluded from the ledger.)

## 8. Comparison against the official baselines

Recomputed from this repo's own `stealth_bench/official_results/` (all runs;
pooled mean = total successful / total tasks; per-run range over the same
runs):

| Entry | Per-run range | Pooled mean |
|---|---|---|
| browser-use-cloud | 73.8 - 80.0% (5 runs) | 77.25% |
| anchor | 69.6 - 73.8% (3 runs) | 72.38% |
| onkernel | 66.2 - 71.2% (3 runs) | 68.33% |
| browserless | 52.5 - 61.2% (3 runs) | 56.67% |
| local_headful (their patched Chromium) | 48.8 - 52.5% (5 runs) | 49.75% |
| steel | 43.8 - 49.4% (3 runs) | 46.84% |
| browserbase | 40.0 - 46.2% (4 runs) | 42.81% |
| hyperbrowser | 35.0 - 43.8% (3 runs) | 39.58% |
| local_headless | 1.2 - 3.8% (9 runs) | 2.36% |
| **Wolverine/Sekreto — bare engine, our IP (run2)** | | **10.0%** |
| **Wolverine/Sekreto — full product (runs 4-9)** | | **0 - 3.75%** |

Spider Cloud's published 85% and Browser Use's blog-quoted 81% come from
their own marketing/leaderboard roundings of the same underlying data (their
fork: [spider-rs/benchmark](https://github.com/spider-rs/benchmark)); the
recomputed rows above are what this repo's raw files support. Either way, the
gap to the band is two orders of magnitude for us — not in dispute.

## 9. What we conclude (measured, not aspirational)

1. **Engine ceiling on our egress is ~10%.** Bare Camoufox, datacenter: 10%.
   Cheap residential did NOT lift it (6.25%) — the DataImpulse pool is itself
   partially flagged by hardened vendors. The 81-85% band embeds premium
   curated residential supply + challenge-solving features we did not
   replicate.
2. **The product stack subtracts score vs the bare engine at every
   configuration** (10% → 0-3.75%): the ref-mode agent is measurably weaker
   than the css-mode agent, worker churn re-triggers challenges on fresh
   identities, and mid-flow challenge survival is the dominant loss. The
   stale-ref fix (run7) and session reuse (run9) recovered infra losses
   (HARNESS_ERROR 24 → 5-6) with zero pass-rate gain.
3. **Agent-loop ceiling:** even the best run had ~32% non-stealth failures
   (MAX_STEPS / completed-but-failed). With perfect stealth, this harness
   caps around ~68% for an agent of this class.
4. **The contested-vendor bet resolved against Firefox-native so far:**
   Datadome 0% (Spider 77%, BU 69%), Akamai 0-33% on one run (Spider 62%,
   BU 85%). Cloudflare is the only vendor with any consistent pass rate.
5. **run15's entry wall** shows the current cheap-residential pool can be
   rejected outright by the whole Cloudflare cluster (universal 401/429),
   upstream of any driver or engine capability.

Fix-forward directions, in evidence-backed priority order: premium IP supply
(a product/cost decision, $5-15/GB class), challenge-solver integration,
agent step efficiency.

## 10. Reproduce

```bash
# scoring — every table above reproduces from results/*.jsonl
python3 score_campaign.py       # 6-run ledger          -> results/ledger.json
python3 vendor_breakdown.py     # per-vendor + fail mix -> results/vendor_breakdown.json
python3 score_mcp_series.py     # MCP depth series (runs 10-15)
python3 summarize.py            # means + bands
python3 tests_stale_ref.py      # offline unit checks of the stale-ref fix
python3 verify_published_numbers.py  # machine-verifies EVERY number in this
                                      # document against the raw JSONLs
                                      # (exits non-zero on any mismatch)

# run the bench yourself (needs a gateway/tenant key and an agent LLM)
SEKRETO_API_KEY=... OLLAMA_API_KEY=... ./launch_run15_mcp_cloudflare.sh
# or the bare engine locally:
# python3 wolverine_bench/run_stealth.py --browser camoufox
#   [--proxy socks5://127.0.0.1:1080] [--category Cloudflare] [--attempts 3]
```

## 11. Data release notes

- `results/*.jsonl` contain the target-site URLs, per-step action traces,
  block/challenge outcomes, and judge reasoning for all our attempts. The
  80-site list is upstream's own public task file (decrypt key in the
  upstream README); publishing our outcomes against it is the deliberate
  point of this release.
- No credentials ship in this repo: tenant keys, proxy credentials, and LLM
  keys are read from the environment at runtime in the published scripts.
- Files: `wolverine_bench/` (harness: runner, agent loop, three drivers —
  bare Camoufox, gateway REST, MCP — plus stock-Chromium controls),
  `launch_run*.sh` (steering scripts as run), `relay*.py` /
  `start_relay.sh` / `proxy_*.py` (residential-proxy plumbing),
  `smoke_camoufox.py`, `tests_stale_ref.py`, scoring scripts, and the raw JSONLs.

Campaign window: 2026-08-28 → 2026-10-03. Maintained by the Sekreto team;
questions via [support@sekreto.ai](mailto:support@sekreto.ai).