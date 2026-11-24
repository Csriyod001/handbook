#!/usr/bin/env bash
# ==============================================================================
# Module 1 Automated Verification Script (labs/m1-foundations/verify_m1.sh)
# Supports: VERIFY_MODE=static (default, offline/no-cluster) | cluster (strict CLI tools)
# ==============================================================================
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$(cd "$LAB_DIR/../../scripts" && pwd):$PATH"
VERIFY_MODE="${VERIFY_MODE:-static}"
cd "$LAB_DIR"

echo "================================================================================"
echo "  Module 1 Verification (MODE=${VERIFY_MODE}): Containers, Bounded Queue & OpenTofu"
echo "================================================================================"

echo "[1/5] Checking required files in labs/m1-foundations/..."
for f in \
  "README.md" \
  "pyproject.toml" \
  "Dockerfile" \
  "Dockerfile.baseline" \
  "app/main.py" \
  "tests/test_main.py" \
  "infra/versions.tf" \
  "infra/variables.tf" \
  "infra/main.tf" \
  "infra/outputs.tf" \
  "infra/k8s-bootstrap/versions.tf" \
  "infra/k8s-bootstrap/variables.tf" \
  "infra/k8s-bootstrap/main.tf" \
  "infra/k8s-bootstrap/outputs.tf" \
  ".github/workflows/ci.yml" \
  "../../.github/workflows/ci.yml" \
  "docs/adr-001-container-and-model-cache-strategy.md"; do
  if [ ! -f "$f" ]; then
    echo "  [FAIL] Missing required file: $f"
    exit 1
  fi
  echo "  [OK] Found $f"
done

echo ""
echo "[2/5] Verifying Dockerfile hardening & SSOT variables..."
grep -q "FROM .* AS builder" Dockerfile && echo "  [OK] Multi-stage builder stage present"
grep -q "UV_COMPILE_BYTECODE=1" Dockerfile && echo "  [OK] uv bytecode compilation enabled"
grep -q "USER 10001:10001" Dockerfile && echo "  [OK] Non-root UID 10001 enforced"
grep -q 'SERVICE_NAME="ai-inference-service"' Dockerfile && echo "  [OK] Canonical Image/Service 'ai-inference-service' configured"
grep -q 'HF_HOME="/cache/huggingface"' Dockerfile && echo "  [OK] Canonical non-root HF_HOME=/cache/huggingface configured"
grep -q 'VLLM_CACHE_ROOT="/tmp/vllm-cache"' Dockerfile && echo "  [OK] Canonical VLLM_CACHE_ROOT=/tmp/vllm-cache configured"
grep -q "uv pip install --no-cache -r pyproject.toml" Dockerfile && echo "  [OK] Dependencies installed from pyproject.toml"

echo ""
echo "[3/5] Verifying OpenTofu declarative configuration & SSOT names..."
grep -q 'default     = "ai-platform-local"' infra/variables.tf && echo "  [OK] Cluster name 'ai-platform-local' verified"
grep -q 'default     = "ai-platform"' infra/variables.tf && echo "  [OK] Namespace 'ai-platform' verified"
grep -q 'default     = "/tmp/ai-infra-hf-cache"' infra/variables.tf && echo "  [OK] Host cache '/tmp/ai-infra-hf-cache' verified"
grep -q 'default     = "/cache/huggingface"' infra/variables.tf && echo "  [OK] Container cache '/cache/huggingface' verified"
grep -q 'default     = "hf-model-cache-pvc"' infra/variables.tf && echo "  [OK] PVC name 'hf-model-cache-pvc' verified"
grep -q "kubeadm_config_patches" infra/main.tf && echo "  [OK] Kind worker node labels wired via kubeadm_config_patches"

if command -v tofu >/dev/null 2>&1; then
  echo "  [RUN] Running tofu fmt -check & tofu validate (Stage 1 & Stage 2)..."
  (cd infra && tofu fmt -check && tofu init -backend=false >/dev/null && tofu validate)
  (cd infra/k8s-bootstrap && tofu fmt -check && tofu init -backend=false >/dev/null && tofu validate)
  echo "  [OK] OpenTofu fmt & validate passed for both Stage 1 & Stage 2"
elif [ "$VERIFY_MODE" = "cluster" ]; then
  echo "  [FAIL] VERIFY_MODE=cluster requires 'tofu' CLI"
  exit 1
else
  echo "  [SKIP] 'tofu' CLI not installed; static HCL check only (run on full workstation for tofu validate)"
fi

echo ""
echo "[4/5] Verifying GitHub Actions CI & Trivy security gate..."
grep -q "aquasecurity/trivy-action" .github/workflows/ci.yml && echo "  [OK] Trivy security scan configured in CI"
grep -q 'skip-files: "labs/m1-foundations/Dockerfile.baseline"' .github/workflows/ci.yml && echo "  [OK] Trivy config skips intentional anti-pattern Dockerfile.baseline"
grep -q "tofu validate" .github/workflows/ci.yml && echo "  [OK] OpenTofu validation configured in CI"

if command -v trivy >/dev/null 2>&1; then
  echo "  [RUN] Running trivy config scan..."
  trivy config --severity CRITICAL,HIGH --exit-code 1 --skip-files Dockerfile.baseline .
  echo "  [OK] Trivy config scan passed"
elif [ "$VERIFY_MODE" = "cluster" ]; then
  echo "  [FAIL] VERIFY_MODE=cluster requires 'trivy' CLI"
  exit 1
else
  echo "  [SKIP] 'trivy' CLI not installed; Trivy config runtime scan skipped in static mode"
fi

echo ""
echo "[5/5] Running automated unit & resilience tests (pytest)..."
PYTHONPATH="$LAB_DIR" pytest -v tests/test_main.py

echo "================================================================================"
echo "  [SUCCESS] Module 1 Verification Passed (MODE=${VERIFY_MODE})!"
echo "================================================================================"
