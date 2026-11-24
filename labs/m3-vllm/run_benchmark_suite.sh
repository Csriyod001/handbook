#!/usr/bin/env bash
# ==============================================================================
# Module 3 (M3): vLLM V1 Serving Benchmark Suite & Unit Economics Calculator
# Supports:
#   --simulate : Deterministic benchmark evaluation & Unit Economics calculation
#   --live     : Runs `vllm bench serve` against a live server on http://localhost:8000
# ==============================================================================
set -euo pipefail

MODE="simulate"
SERVER_URL="http://localhost:8000"
METRICS_URL=""
API_KEY="${OPENAI_API_KEY:-}"
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
BACKEND="${BACKEND:-vllm}"
GPU_HOURLY_COST="${GPU_HOURLY_COST:-0.85}"
MANAGED_API_COST_PER_1M="${MANAGED_API_COST_PER_1M:-0.60}"
UTILIZATION_RATIO="${UTILIZATION_RATIO:-0.50}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --simulate)
      MODE="simulate"
      shift
      ;;
    --live)
      MODE="live"
      shift
      ;;
    --url)
      SERVER_URL="$2"
      shift 2
      ;;
    --metrics-url)
      METRICS_URL="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--simulate | --live] [--url http://localhost:8000] [--metrics-url http://localhost:8000] [--api-key KEY] [--model MODEL_NAME] [--backend vllm|openai-chat]" >&2
      exit 1
      ;;
  esac
done

METRICS_URL="${METRICS_URL:-${SERVER_URL}}"

echo "================================================================================"
echo " vLLM V1 Serving Benchmark Suite & Unit Economics Calculator"
echo " Shared System Prompt Prefix: 2048 tokens | Suffix: 128 tokens | Output: 256 tokens"
echo "================================================================================"

if [[ "${MODE}" == "live" ]]; then
  if ! command -v vllm >/dev/null 2>&1; then
    echo "[FAIL] --live mode requires 'vllm' CLI installed in the active environment." >&2
    exit 1
  fi
  if [[ -n "${API_KEY}" ]]; then
    export OPENAI_API_KEY="${API_KEY}"
  fi
  echo "[LIVE BENCHMARK] Target Server: ${SERVER_URL} | Metrics: ${METRICS_URL} | Backend: ${BACKEND} | Model: ${MODEL}"
  echo "[INFO] Ensure --model matches the served model name on ${SERVER_URL}."
  for conc in 1 8 16 32; do
    num_prompts=$((conc * 4))
    if (( num_prompts < 20 )); then
      num_prompts=20
    fi
    echo "--------------------------------------------------------------------------------"
    echo "[LIVE BENCHMARK] Running concurrency=${conc} (num-prompts=${num_prompts})..."
    vllm bench serve \
      --backend "${BACKEND}" \
      --base-url "${SERVER_URL}" \
      --model "${MODEL}" \
      --dataset-name prefix_repetition \
      --prefix-repetition-prefix-len 2048 \
      --prefix-repetition-suffix-len 128 \
      --prefix-repetition-num-prefixes 1 \
      --prefix-repetition-output-len 256 \
      --num-prompts "${num_prompts}" \
      --max-concurrency "${conc}" \
      --percentile-metrics ttft,itl,e2el
  done

  echo "--------------------------------------------------------------------------------"
  echo "[LIVE METRICS] Scraping Prometheus V1 metrics from ${METRICS_URL}/metrics ..."
  METRICS_PAYLOAD="$(curl -s "${METRICS_URL}/metrics" || true)"
  echo "${METRICS_PAYLOAD}" | grep -E "vllm:(kv_cache_usage_perc|num_requests_waiting|prefix_cache_hits_total|prefix_cache_queries_total|num_preemptions_total|inter_token_latency_seconds|time_per_output_token_seconds)" || true
  METRICS_PAYLOAD="${METRICS_PAYLOAD}" python3 - <<'PYEOF'
import os, re
raw = os.environ.get("METRICS_PAYLOAD", "")
def sum_metric(name):
    total = 0.0
    for line in raw.splitlines():
        if line.startswith(name) and not line.startswith("#"):
            parts = line.strip().split()
            if parts:
                try:
                    total += float(parts[-1])
                except ValueError:
                    pass
    return total
hits = sum_metric("vllm:prefix_cache_hits_total")
queries = sum_metric("vllm:prefix_cache_queries_total")
if queries > 0:
    print(f"[LIVE APC SUMMARY] hits={hits:.0f} tokens | queries={queries:.0f} tokens | Hit Rate = {(hits / queries) * 100.0:.1f}%")
else:
    print("[LIVE APC SUMMARY] prefix_cache_queries_total=0 (no prefix cache queries recorded yet)")
PYEOF
  exit 0
fi

echo "[SIMULATE MODE] Modeled L4 GPU projections anchored to 300 GB/s HBM/GDDR6 bandwidth."
echo "[SIMULATE MODE] Real Cloud GPU numbers vary slightly by kernel & PCIe; run --live on L4 VM to measure."
GPU_HOURLY_COST="${GPU_HOURLY_COST}" \
MANAGED_API_COST_PER_1M="${MANAGED_API_COST_PER_1M}" \
UTILIZATION_RATIO="${UTILIZATION_RATIO}" \
python3 - <<'PYEOF'
import os

gpu_hourly_cost = float(os.environ["GPU_HOURLY_COST"])
api_cost_1m = float(os.environ["MANAGED_API_COST_PER_1M"])
util = float(os.environ["UTILIZATION_RATIO"])

# Anchored to NVIDIA L4 300 GB/s memory bandwidth:
# - Config A (BF16 15.24 GB weights) @ C=1: min decode floor ~50.8ms/tok -> ~18.2 tok/s @ 54.5ms ITL
# - Config C (AWQ ~5.4 GB runtime safetensors weights) @ C=1: ~56.0 tok/s @ 17.8ms ITL;
#   20+ prompts with 1 cold miss + 19 hits at 2048/2176 yields ~89.4% max prefix hit rate.
rows = [
    ("A: BF16-NoAPC",   1,  310.0, 54.5,   18.2,  12.4,  0.0, ""),
    ("A: BF16-NoAPC",   8,  980.0, 58.0,  136.0,  68.0,  0.0, ""),
    ("A: BF16-NoAPC",  16, 2450.0, 66.0,  420.0,  98.5,  0.0, ""),
    ("A: BF16-NoAPC",  32, 6120.0, 94.0,  390.0, 100.0,  0.0, " (SLA BREACH: Preemption!)"),
    ("SEP", 0, 0, 0, 0, 0, 0, ""),
    ("B: BF16+APC",    16,  460.0, 29.0,  890.0,  42.0, 88.5, ""),
    ("B: BF16+APC",    32, 1420.0, 39.0,  980.0,  89.0, 89.1, ""),
    ("SEP", 0, 0, 0, 0, 0, 0, ""),
    ("C: AWQ+APC+Tune", 1,  195.0, 17.8,   56.0,   2.8, 89.4, ""),
    ("C: AWQ+APC+Tune", 8,  280.0, 19.2,  495.0,  14.5, 88.2, ""),
    ("C: AWQ+APC+Tune",16,  390.0, 21.1,  960.0,  26.2, 88.9, ""),
    ("C: AWQ+APC+Tune",32,  640.0, 23.5, 1450.0,  48.5, 89.4, " (PASS SLA <800ms TTFT)"),
    ("SEP", 0, 0, 0, 0, 0, 0, ""),
    ("D: FP8+FP8KV",   32,  590.0, 24.8, 1380.0,  31.0, 89.4, " (Ada FP8 + 2x KV Capacity)"),
]

print(f"Config          | Conc | TTFT p95 (ms) | ITL p95 (ms) | Throughput (tok/s) | KV Usage | Prefix Hit % | Cost/1M (${gpu_hourly_cost:.2f}/h @ {util * 100:.0f}% util)")
print("-" * 132)

for cfg, conc, ttft, itl, tput, kv, hit, note in rows:
    if cfg == "SEP":
        print("-" * 132)
        continue
    # Cost per 1M tokens at utilization `util`:
    # tokens_per_hour = tput * 3600 * util
    # cost_1m = gpu_hourly_cost / (tokens_per_hour / 1_000_000)
    cost_1m = (gpu_hourly_cost * 1_000_000) / (tput * 3600.0 * util)
    print(f"{cfg:<15} | {conc:>4} | {ttft:>13.1f} | {itl:>12.1f} | {tput:>18.1f} | {kv:>7.1f}% | {hit:>11.1f}% | ${cost_1m:.2f}{note}")

print("=" * 80)
be_a = (gpu_hourly_cost * 1_000_000) / (420.0 * 3600.0 * api_cost_1m) * 100.0
be_c = (gpu_hourly_cost * 1_000_000) / (1450.0 * 3600.0 * api_cost_1m) * 100.0
print(f"Break-even Utilization vs Managed API (${api_cost_1m:.2f} / 1M tokens):")
print(f"  - Config A (420 tok/s): {be_a:.1f}% utilization required")
print(f"  - Config C (1450 tok/s): {be_c:.1f}% utilization required")
PYEOF
