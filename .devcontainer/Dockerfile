FROM ubuntu:24.04
# ==============================================================================
# AI Infrastructure & Platform Engineering Handbook — Portable DevContainer
# Supports linux/amd64 and linux/arm64 (via TARGETARCH) + Docker-outside-of-Docker
# ==============================================================================

ARG TARGETARCH=amd64
ARG DEBIAN_FRONTEND=noninteractive
ARG KUBECTL_VERSION=v1.32.2
ARG KIND_VERSION=v0.27.0
ARG HELM_VERSION=v3.17.2
ARG TOFU_VERSION=1.9.0
ARG TRIVY_VERSION=0.59.1
ARG PROMETHEUS_VERSION=3.2.1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    jq \
    make \
    unzip \
    gnupg \
    lsb-release \
    python3 \
    python3-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 1. Install Docker CLI (for Docker-outside-of-Docker via /var/run/docker.sock)
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list && \
    apt-get update && apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

# 2. Install Astral uv & Python Engineering Packages
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh && \
    uv venv /opt/lab-venv && \
    uv pip install --python /opt/lab-venv/bin/python --no-cache \
      fastapi uvicorn pydantic httpx pytest pyyaml ruff

# 3. Install Cloud-Native & SRE CLI Toolchain (multi-arch via TARGETARCH)
RUN set -eux; \
    if [ "${TARGETARCH}" = "amd64" ]; then TRIVY_ARCH="64bit"; else TRIVY_ARCH="ARM64"; fi; \
    curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" -o /usr/local/bin/kubectl && \
    chmod 0755 /usr/local/bin/kubectl; \
    curl -fsSL "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${TARGETARCH}" -o /usr/local/bin/kind && \
    chmod 0755 /usr/local/bin/kind; \
    curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${TARGETARCH}.tar.gz" -o /tmp/helm.tgz && \
    tar -xzf /tmp/helm.tgz -C /tmp && mv "/tmp/linux-${TARGETARCH}/helm" /usr/local/bin/helm && chmod 0755 /usr/local/bin/helm && \
    rm -rf /tmp/helm.tgz "/tmp/linux-${TARGETARCH}"; \
    curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_${TARGETARCH}.zip" -o /tmp/tofu.zip && \
    unzip -q /tmp/tofu.zip -d /tmp/tofu && mv /tmp/tofu/tofu /usr/local/bin/tofu && chmod 0755 /usr/local/bin/tofu && \
    rm -rf /tmp/tofu.zip /tmp/tofu; \
    curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-${TRIVY_ARCH}.tar.gz" -o /tmp/trivy.tgz && \
    tar -xzf /tmp/trivy.tgz -C /tmp trivy && mv /tmp/trivy /usr/local/bin/trivy && chmod 0755 /usr/local/bin/trivy && \
    rm -f /tmp/trivy.tgz; \
    curl -fsSL "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-${TARGETARCH}.tar.gz" -o /tmp/prom.tgz && \
    tar -xzf /tmp/prom.tgz -C /tmp && mv "/tmp/prometheus-${PROMETHEUS_VERSION}.linux-${TARGETARCH}/promtool" /usr/local/bin/promtool && chmod 0755 /usr/local/bin/promtool && \
    rm -rf /tmp/prom.tgz "/tmp/prometheus-${PROMETHEUS_VERSION}.linux-${TARGETARCH}"

ENV PATH="/opt/lab-venv/bin:/usr/local/bin:${PATH}" \
    HF_HOME="/cache/huggingface" \
    VLLM_CACHE_ROOT="/tmp/vllm-cache"

RUN mkdir -p /workspace /cache/huggingface /tmp/vllm-cache && chmod 777 /cache/huggingface /tmp/vllm-cache

WORKDIR /workspace

CMD ["bash"]
