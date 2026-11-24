# ==============================================================================
# PRODUCTION MULTI-STAGE DOCKERFILE FOR AI INFERENCE SERVICE (Module 1 & 2)
# Standards:
# - Image Name/Tag: `ai-inference-service:1.0.0` (matches Module 2 Helm Chart)
# - Port: `8000` (matches Module 2 Helm Chart & SPEC_AND_STYLE_GUIDE.md)
# - Astral `uv` with bytecode compilation & copy link mode
# - Strict dependency layer separation (pyproject.toml copied before app/)
# - Non-root user `appuser` (UID 10001)
# - Compatible with Kubernetes `readOnlyRootFilesystem: true`
# - Externalized Model Cache Volume at `HF_HOME=/cache/huggingface`
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder (Installs dependencies and compiles Python bytecode)
# ------------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.7-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Copy dependency specification FIRST to maximize Docker layer cache hits
COPY pyproject.toml ./

# Create isolated virtual environment at /opt/venv and install production deps from pyproject.toml
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -r pyproject.toml

# ------------------------------------------------------------------------------
# Stage 2: Production Runtime (Minimal, Hardened, Non-Root)
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="ai-inference-service" \
      org.opencontainers.image.description="Production AI Inference Wrapper (Namespace: ai-platform)" \
      org.opencontainers.image.version="1.0.0"

# Create non-root group and user (UID/GID 10001) and prepare mount target dirs
# Use neutral /cache/huggingface (no /root traversal hacks needed; compatible with upstream vLLM UID 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -d /home/appuser -s /sbin/nologin appuser && \
    mkdir -p /app /cache/huggingface /tmp/vllm-cache /tmp/torchinductor /tmp/triton && \
    chown -R 10001:10001 /app /cache/huggingface /tmp/vllm-cache /tmp/torchinductor /tmp/triton

# Copy pre-built virtual environment from builder stage
COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv

WORKDIR /app

# Copy application source code LAST so code edits never invalidate /opt/venv
COPY --chown=10001:10001 app/ /app/app/

# Canonical environment variables matching SPEC_AND_STYLE_GUIDE.md & Helm values.yaml
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE_NAME="ai-inference-service" \
    K8S_NAMESPACE="ai-platform" \
    PORT="8000" \
    MODEL_ID="Qwen/Qwen2.5-0.5B-Instruct" \
    HF_HOME="/cache/huggingface" \
    VLLM_CACHE_ROOT="/tmp/vllm-cache" \
    TORCHINDUCTOR_CACHE_DIR="/tmp/torchinductor" \
    TRITON_CACHE_DIR="/tmp/triton" \
    TMPDIR="/tmp" \
    ENABLE_BOUNDED_QUEUE="true" \
    MAX_CONCURRENT_REQUESTS="4" \
    QUEUE_ACQUIRE_TIMEOUT_SEC="0.08"

EXPOSE 8000

USER 10001:10001

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
