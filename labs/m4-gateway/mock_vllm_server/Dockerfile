# ==============================================================================
# PRODUCTION MULTI-STAGE DOCKERFILE FOR MOCK VLLM V1 SERVER (Modules 4, 5 & 6)
# Build Context: labs/m4-gateway
#   docker build -t mock-vllm-server:1.0.0 -f mock_vllm_server/Dockerfile .
#   kind load docker-image mock-vllm-server:1.0.0 --name ai-platform-local
# ==============================================================================

FROM ghcr.io/astral-sh/uv:0.5-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache fastapi "uvicorn[standard]" pydantic

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="mock-vllm-server" \
      org.opencontainers.image.description="Lightweight OpenAI-compatible Mock vLLM V1 Server with APC & Chaos API" \
      org.opencontainers.image.version="1.0.0"

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -d /home/appuser -s /sbin/nologin appuser && \
    mkdir -p /app /cache/huggingface /tmp/vllm-cache /tmp/torchinductor /tmp/triton && \
    chown -R 10001:10001 /app /cache/huggingface /tmp/vllm-cache /tmp/torchinductor /tmp/triton

COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 mock_vllm_server /app/mock_vllm_server

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME="/cache/huggingface" \
    VLLM_CACHE_ROOT="/tmp/vllm-cache" \
    HOME="/tmp" \
    TMPDIR="/tmp" \
    PORT="8000" \
    SERVER_ID="vllm-primary-svc" \
    MODEL_NAME="Qwen/Qwen2.5-7B-Instruct-AWQ"

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "mock_vllm_server.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
