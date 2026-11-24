#!/usr/bin/env bash
# ==============================================================================
# Module 3 (M3): Start vLLM V1 Server in Optimized Mode (Config C / D / Local RTX 4050)
# Supports:
#   --local-cpu      : Runs Qwen/Qwen2.5-0.5B-Instruct with APC & Tuned Token Budget
#   --local-rtx4050  : Runs Qwen/Qwen2.5-3B-Instruct-AWQ (awq_marlin, FP8 KV, 0.85 util, 6GB VRAM)
#   --cloud-gpu      : Runs Qwen/Qwen2.5-7B-Instruct-AWQ (awq_marlin, 0.92 util, APC, Chunked Prefill)
#   --cloud-gpu-fp8  : Runs Qwen/Qwen2.5-7B-Instruct (FP8 weights + FP8 KV-cache, 0.92 util, APC)
#   --dry-run        : Prints the exact command and environment variables without executing
# ==============================================================================
set -euo pipefail

MODE="local-cpu"
DRY_RUN=false
PORT="${PORT:-8000}"
HOST_HF_CACHE="${HOST_HF_CACHE:-/tmp/ai-infra-hf-cache}"
USER_HF_HOME="${HF_HOME:-}"
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.11.0}"
MODEL_REVISION="${MODEL_REVISION:-}"

for arg in "$@"; do
  case "$arg" in
    --local-cpu)
      MODE="local-cpu"
      ;;
    --local-rtx4050)
      MODE="local-rtx4050"
      ;;
    --cloud-gpu)
      MODE="cloud-gpu"
      ;;
    --cloud-gpu-fp8)
      MODE="cloud-gpu-fp8"
      ;;
    --dry-run)
      DRY_RUN=true
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--local-cpu | --local-rtx4050 | --cloud-gpu | --cloud-gpu-fp8] [--dry-run]" >&2
      exit 1
      ;;
  esac
done

if [[ -n "${USER_HF_HOME}" ]]; then
  export HF_HOME="${USER_HF_HOME}"
elif [[ "${MODE}" == "local-cpu" || "${MODE}" == "local-rtx4050" ]]; then
  export HF_HOME="${HOST_HF_CACHE}"
else
  export HF_HOME="/cache/huggingface"
fi
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-/tmp/vllm-cache}"

echo "[M3-OPTIMIZED] Mode: ${MODE}"
echo "[M3-OPTIMIZED] HF_HOME=${HF_HOME} (Host cache: ${HOST_HF_CACHE})"

REVISION_ARGS=()
if [[ -n "${MODEL_REVISION}" ]]; then
  REVISION_ARGS=(--revision "${MODEL_REVISION}")
fi

if [[ "${MODE}" == "local-cpu" ]]; then
  export VLLM_CPU_KVCACHE_SPACE=1
  MODEL="Qwen/Qwen2.5-0.5B-Instruct"
  CMD=(
    vllm serve "${MODEL}"
    "${REVISION_ARGS[@]}"
    --host 0.0.0.0
    --port "${PORT}"
    --dtype bfloat16
    --max-model-len 2048
    --enable-prefix-caching
    --max-num-batched-tokens 1024
    --max-num-seqs 16
  )
  echo "[M3-OPTIMIZED] VLLM_CPU_KVCACHE_SPACE=${VLLM_CPU_KVCACHE_SPACE}"
elif [[ "${MODE}" == "local-rtx4050" ]]; then
  MODEL="Qwen/Qwen2.5-3B-Instruct-AWQ"
  CMD=(
    docker run --rm --gpus all --ipc=host
    -v "${HF_HOME}:/cache/huggingface"
    -e HF_HOME=/cache/huggingface
    -e VLLM_CACHE_ROOT=/tmp/vllm-cache
    -p "${PORT}:8000"
    "${VLLM_IMAGE}"
    --model "${MODEL}"
    "${REVISION_ARGS[@]}"
    --host 0.0.0.0
    --port 8000
    --quantization awq_marlin
    --dtype float16
    --kv-cache-dtype fp8
    --gpu-memory-utilization 0.85
    --max-model-len 2048
    --enforce-eager
    --enable-prefix-caching
    --max-num-batched-tokens 1024
    --max-num-seqs 16
  )
elif [[ "${MODE}" == "cloud-gpu-fp8" ]]; then
  MODEL="Qwen/Qwen2.5-7B-Instruct"
  CMD=(
    vllm serve "${MODEL}"
    "${REVISION_ARGS[@]}"
    --host 0.0.0.0
    --port "${PORT}"
    --quantization fp8
    --kv-cache-dtype fp8
    --dtype bfloat16
    --gpu-memory-utilization 0.92
    --max-model-len 4096
    --enable-prefix-caching
    --max-num-batched-tokens 2048
    --max-num-seqs 64
  )
else
  MODEL="Qwen/Qwen2.5-7B-Instruct-AWQ"
  CMD=(
    vllm serve "${MODEL}"
    "${REVISION_ARGS[@]}"
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
