#!/usr/bin/env bash
# ==============================================================================
# Module 3 (M3): Automated Verification Script (verify_m3.sh)
# Supports:
#   VERIFY_MODE=static|cluster
#   --target examples|workspace (default: examples — grades starter template structure
#                                + reference examples/ arithmetic; workspace checks
#                                learner-completed optimization-report-template.md)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export PATH="${REPO_ROOT}/scripts:${PATH}"

TARGET="examples"
VERIFY_MODE="${VERIFY_MODE:-static}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1 (usage: $0 [--target examples|workspace])" >&2
      exit 1
      ;;
  esac
done

CHAPTER_FILE="${REPO_ROOT}/chapters/03-vllm-serving-optimization.md"
TEMPLATE_FILE="${SCRIPT_DIR}/optimization-report-template.md"
SAMPLE_FILE="${SCRIPT_DIR}/examples/optimization-report-sample.md"

echo "=================================================================="
echo " [M3 VERIFY] Starting Milestone 3 Verification (MODE=${VERIFY_MODE}, TARGET=${TARGET})"
echo "=================================================================="

# 1. Verify Chapter 3 file & mandatory sections
if [[ ! -f "${CHAPTER_FILE}" ]]; then
  echo "[FAIL] Missing chapter file: ${CHAPTER_FILE}" >&2
  exit 1
fi

for section in \
  "1. Executive Summary & Learning Objectives" \
  "2. Architecture Overview" \
  "3. Core Theory & Deep-Dive Engineering Math" \
  "4. Hands-on Lab (Dual-Path Execution)" \
  "5. Chaos & Troubleshooting Drills" \
  "6. Optimization Exercise" \
  "7. Architecture Decision Record (ADR) & Cost/Handoff Documentation" \
  "8. Mid-Level Interview Trade-off Questions & Model Answers"; do
  if ! grep -q "${section}" "${CHAPTER_FILE}"; then
    echo "[FAIL] Chapter 3 is missing mandatory section: ${section}" >&2
    exit 1
  fi
done
echo "[PASS] Chapter 3 contains all 8 mandatory sections."

# 2. Verify Canonical V1 metrics and V1 engine guardrails in Chapter 3
for metric in \
  "vllm:kv_cache_usage_perc" \
  "vllm:num_requests_running" \
  "vllm:num_requests_waiting" \
  "vllm:prefix_cache_hits_total" \
  "vllm:prefix_cache_queries_total" \
  "vllm:num_preemptions_total" \
  "vllm:time_to_first_token_seconds_bucket" \
  "vllm:inter_token_latency_seconds_bucket" \
  "vllm:time_per_output_token_seconds_bucket" \
  "vllm:generation_tokens_total" \
  "--no-enable-prefix-caching" \
  "VLLM_CPU_KVCACHE_SPACE=1" \
  "/cache/huggingface"; do
  if ! grep -q -- "${metric}" "${CHAPTER_FILE}"; then
    echo "[FAIL] Chapter 3 is missing required guardrail/metric: ${metric}" >&2
    exit 1
  fi
done
echo "[PASS] Chapter 3 includes all canonical vLLM V1 metrics and guardrails."

# 3. Verify dry-run outputs cleanly (without mutating file modes or creating host cache dirs)
DRY_TMP_CACHE="/tmp/m3_dryrun_should_not_exist_$$"
rm -rf "${DRY_TMP_CACHE}"
BASE_CPU_OUT="$(HOST_HF_CACHE="${DRY_TMP_CACHE}" bash "${SCRIPT_DIR}/start_vllm_baseline.sh" --local-cpu --dry-run)"
if [[ -d "${DRY_TMP_CACHE}" ]]; then
  rm -rf "${DRY_TMP_CACHE}"
  echo "[FAIL] --dry-run unexpectedly created host cache directory" >&2
  exit 1
fi
echo "${BASE_CPU_OUT}" | grep -q "VLLM_CPU_KVCACHE_SPACE=1"
echo "${BASE_CPU_OUT}" | grep -q "Qwen/Qwen2.5-0.5B-Instruct"
echo "${BASE_CPU_OUT}" | grep -q -- "--no-enable-prefix-caching"

BASE_GPU_OUT="$(bash "${SCRIPT_DIR}/start_vllm_baseline.sh" --cloud-gpu --dry-run)"
echo "${BASE_GPU_OUT}" | grep -q "HF_HOME=/cache/huggingface"
echo "${BASE_GPU_OUT}" | grep -q "Qwen/Qwen2.5-7B-Instruct"
echo "${BASE_GPU_OUT}" | grep -q -- "--gpu-memory-utilization 0.85"
echo "${BASE_GPU_OUT}" | grep -q -- "--no-enable-prefix-caching"
echo "[PASS] start_vllm_baseline.sh validated for both --local-cpu and --cloud-gpu (zero dry-run side effects)."

OPT_GPU_OUT="$(bash "${SCRIPT_DIR}/start_vllm_optimized.sh" --cloud-gpu --dry-run)"
echo "${OPT_GPU_OUT}" | grep -q "HF_HOME=/cache/huggingface"
echo "${OPT_GPU_OUT}" | grep -q "Qwen/Qwen2.5-7B-Instruct-AWQ"
echo "${OPT_GPU_OUT}" | grep -q -- "--quantization awq_marlin"
echo "${OPT_GPU_OUT}" | grep -q -- "--gpu-memory-utilization 0.92"
echo "${OPT_GPU_OUT}" | grep -q -- "--enable-prefix-caching"
echo "${OPT_GPU_OUT}" | grep -q -- "--max-num-batched-tokens 2048"
echo "[PASS] start_vllm_optimized.sh validated for AWQ, 0.92 util, APC, and Chunked Prefill."

RTX_BASE_OUT="$(bash "${SCRIPT_DIR}/start_vllm_baseline.sh" --local-rtx4050 --dry-run)"
echo "${RTX_BASE_OUT}" | grep -q "Qwen/Qwen2.5-1.5B-Instruct"
echo "${RTX_BASE_OUT}" | grep -q -- "--gpus all"
echo "${RTX_BASE_OUT}" | grep -q -- "--ipc=host"

RTX_OPT_OUT="$(bash "${SCRIPT_DIR}/start_vllm_optimized.sh" --local-rtx4050 --dry-run)"
echo "${RTX_OPT_OUT}" | grep -q "Qwen/Qwen2.5-3B-Instruct-AWQ"
echo "${RTX_OPT_OUT}" | grep -q -- "--kv-cache-dtype fp8"
echo "${RTX_OPT_OUT}" | grep -q -- "--ipc=host"

FP8_GPU_OUT="$(bash "${SCRIPT_DIR}/start_vllm_optimized.sh" --cloud-gpu-fp8 --dry-run)"
echo "${FP8_GPU_OUT}" | grep -q -- "--quantization fp8"
echo "${FP8_GPU_OUT}" | grep -q -- "--kv-cache-dtype fp8"
echo "[PASS] Local RTX 4050 6GB CUDA and Cloud L4 FP8 profiles validated."

python3 "${SCRIPT_DIR}/eval_thai_quality.py" --simulate >/dev/null
pytest "${SCRIPT_DIR}/eval_thai_quality.py" -v
echo "[PASS] Quantization Quality Eval Gate (eval_thai_quality.py) verified."

# 4. Run benchmark suite simulation & verify physics + Unit Economics output
grep -q -- "--backend" "${SCRIPT_DIR}/run_benchmark_suite.sh"
grep -q -- "--api-key" "${SCRIPT_DIR}/run_benchmark_suite.sh"
grep -q -- "--metrics-url" "${SCRIPT_DIR}/run_benchmark_suite.sh"
BENCH_OUT="$(bash "${SCRIPT_DIR}/run_benchmark_suite.sh" --simulate)"
echo "${BENCH_OUT}" | grep -q "C: AWQ+APC+Tune"
echo "${BENCH_OUT}" | grep -q "56.0"
echo "${BENCH_OUT}" | grep -q "27.1% utilization required"
echo "[PASS] run_benchmark_suite.sh simulation, L4 bandwidth-bounded C=1 decode, and Unit Economics math verified."

if command -v vllm >/dev/null 2>&1; then
  vllm --version >/dev/null 2>&1 && echo "[OK] vllm CLI detected"
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] VERIFY_MODE=cluster requires 'vllm' CLI installed" >&2
  exit 1
else
  echo "[SKIP] 'vllm' CLI not installed; --live benchmark execution skipped in static mode"
fi

# 5. Check starter template & worked examples
if [[ ! -f "${TEMPLATE_FILE}" || ! -f "${SAMPLE_FILE}" ]]; then
  echo "[FAIL] Missing template or sample report file in labs/m3-vllm/" >&2
  exit 1
fi
for sec in "## 1." "## 2." "## 3." "## 4." "## 5."; do
  grep -q "${sec}" "${TEMPLATE_FILE}" || { echo "[FAIL] Missing section ${sec} in ${TEMPLATE_FILE}" >&2; exit 1; }
done

if [[ "${TARGET}" == "workspace" ]]; then
  if grep -q "<TODO" "${TEMPLATE_FILE}"; then
    echo "[FAIL] Learner report ${TEMPLATE_FILE} still contains unfilled <TODO> placeholders" >&2
    exit 1
  fi
  echo "[PASS] Learner optimization-report-template.md validated (workspace target)."
else
  grep -q "299,593 tokens" "${SAMPLE_FILE}"
  grep -q "27.1%" "${SAMPLE_FILE}"
  grep -q "56.0" "${SAMPLE_FILE}"
  echo "[PASS] Starter template structure & worked sample arithmetic (examples/) verified."
fi

echo "=================================================================="
echo " [M3 VERIFY] ALL MILESTONE 3 CHECKS PASSED (MODE=${VERIFY_MODE}, TARGET=${TARGET})"
echo "=================================================================="
