#!/usr/bin/env bash
# ==============================================================================
# Module 3 (M3): Start vLLM V1 Server in Optimized Mode (Config C)
# Supports:
#   --local-cpu  : Runs Qwen/Qwen2.5-0.5B-Instruct with APC & Tuned Token Budget
#   --cloud-gpu  : Runs Qwen/Qwen2.5-7B-Instruct-AWQ (awq_marlin, 0.92 util, APC, Chunked Prefill)
#   --dry-run    : Prints the exact command and environment variables without executing
# ==============================================================================
set -euo pipefail

MODE="local-cpu"
DRY_RUN=false
PORT="${PORT:-8000}"
HOST_HF_CACHE="${HOST_HF_CACHE:-/tmp/ai-infra-hf-cache}"
USER_HF_HOME="${HF_HOME:-}"

for arg in "$@"; do
  case "$arg" in
    --local-cpu)
      MODE="local-cpu"
      ;;
    --cloud-gpu)
      MODE="cloud-gpu"
      ;;
    --dry-run)
      DRY_RUN=true
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--local-cpu | --cloud-gpu] [--dry-run]" >&2
      exit 1
      ;;
  esac
done

# Note: `--local-cpu` targets the vLLM CPU wheel/container; `--dry-run` has zero filesystem side effects.
if [[ -n "${USER_HF_HOME}" ]]; then
  export HF_HOME="${USER_HF_HOME}"
elif [[ "${MODE}" == "local-cpu" ]]; then
  export HF_HOME="${HOST_HF_CACHE}"
else
  export HF_HOME="/cache/huggingface"
fi
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-/tmp/vllm-cache}"

echo "[M3-OPTIMIZED] Mode: ${MODE}"
echo "[M3-OPTIMIZED] HF_HOME=${HF_HOME} (Host cache: ${HOST_HF_CACHE})"

if [[ "${MODE}" == "local-cpu" ]]; then
  export VLLM_CPU_KVCACHE_SPACE=1
  MODEL="Qwen/Qwen2.5-0.5B-Instruct"
  CMD=(
    vllm serve "${MODEL}"
    --host 0.0.0.0
    --port "${PORT}"
    --dtype bfloat16
    --max-model-len 2048
    --enable-prefix-caching
    --max-num-batched-tokens 1024
    --max-num-seqs 16
  )
  echo "[M3-OPTIMIZED] VLLM_CPU_KVCACHE_SPACE=${VLLM_CPU_KVCACHE_SPACE}"
else
  MODEL="Qwen/Qwen2.5-7B-Instruct-AWQ"
  CMD=(
    vllm serve "${MODEL}"
    --host 0.0.0.0
    --port "${PORT}"
    --quantization awq_marlin
    --dtype float16
    --gpu-memory-utilization 0.92
    --max-model-len 4096
    --enable-prefix-caching
    --max-num-batched-tokens 2048
    --max-num-seqs 64
  )
fi

echo "[M3-OPTIMIZED] Command: ${CMD[*]}"

if [[ "${DRY_RUN}" == "true" ]]; then
  exit 0
fi

mkdir -p "${HF_HOME}" "${VLLM_CACHE_ROOT}"
exec "${CMD[@]}"
