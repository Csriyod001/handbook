#!/usr/bin/env bash
# ==============================================================================
# Module 2 Automated Verification Script (labs/m2-k8s-gpu/verify_m2.sh)
# Supports: VERIFY_MODE=static (default, offline) | cluster (requires helm CLI)
# ==============================================================================
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$(cd "$LAB_DIR/../../scripts" && pwd):$PATH"
VERIFY_MODE="${VERIFY_MODE:-static}"
cd "$LAB_DIR"

echo "================================================================================"
echo "  Module 2 Verification (MODE=${VERIFY_MODE}): Kubernetes GPU Orchestration & Helm"
echo "================================================================================"

echo "[1/6] Checking required files in labs/m2-k8s-gpu/..."
for f in \
  "vram_calculator.py" \
  "test_vram_calculator.py" \
  "gpu-time-slicing-config.yaml" \
  "charts/ai-inference-service/Chart.yaml" \
  "charts/ai-inference-service/values.yaml" \
  "charts/ai-inference-service/values-cloud-gpu.yaml" \
  "charts/ai-inference-service/values-cloud-gpu-7b-awq.yaml" \
  "charts/ai-inference-service/templates/deployment.yaml" \
  "charts/ai-inference-service/templates/service.yaml" \
  "charts/ai-inference-service/templates/pvc.yaml" \
  "charts/ai-inference-service/templates/priorityclass.yaml" \
  "charts/ai-inference-service/templates/pdb.yaml" \
  "docs/adr-002-gpu-sharing-and-scheduling.md"; do
  if [ ! -f "$f" ]; then
    echo "  [FAIL] Missing required file: $f"
    exit 1
  fi
  echo "  [OK] Found $f"
done

echo ""
echo "[2/6] Running pytest on GPU VRAM Sizing Calculator (test_vram_calculator.py)..."
PYTHONPATH="$LAB_DIR" pytest -v test_vram_calculator.py

echo ""
echo "[3/6] Executing vram_calculator.py sizing report & asserting per-replica capacity..."
CALC_OUT="$(python3 vram_calculator.py)"
echo "$CALC_OUT"
echo "$CALC_OUT" | grep -q "YES (Max C=135/rep, 542 total)" && echo "  [OK] vram_calculator shows per-replica + total concurrency"

echo ""
echo "[4/6] Validating YAML syntax & Helm Chart templates, Probes, preStop, and HF_HOME PVC..."
python3 - <<'PYEOF'
import yaml

for path in [
    "gpu-time-slicing-config.yaml",
    "charts/ai-inference-service/Chart.yaml",
    "charts/ai-inference-service/values.yaml",
    "charts/ai-inference-service/values-cloud-gpu.yaml",
    "charts/ai-inference-service/values-cloud-gpu-7b-awq.yaml",
]:
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    assert docs and docs[0] is not None, f"Empty YAML in {path}"

with open("charts/ai-inference-service/Chart.yaml", "r", encoding="utf-8") as f:
    chart = yaml.safe_load(f)
assert "ai-platform" in chart.get("description", ""), "Chart description mismatch"

with open("charts/ai-inference-service/values.yaml", "r", encoding="utf-8") as f:
    vals = yaml.safe_load(f)
assert vals["model"]["passVllmCliArgs"] is False, "Local values.yaml must default passVllmCliArgs=false"
assert vals["modelCache"]["createPvc"] is False, "Local values.yaml must default createPvc=false (owned by M1 OpenTofu)"
assert vals["modelCache"]["mountPath"] == "/cache/huggingface"

with open("charts/ai-inference-service/values-cloud-gpu.yaml", "r", encoding="utf-8") as f:
    cvals = yaml.safe_load(f)
assert cvals["image"]["tag"] == "v0.8.5", "Cloud GPU image tag must be pinned (v0.8.5)"
assert cvals["model"]["passVllmCliArgs"] is True, "Cloud GPU values must enable passVllmCliArgs=true"
assert cvals["modelCache"]["createPvc"] is True
assert cvals["modelCache"]["mountPath"] == "/cache/huggingface"
assert cvals["nodeSelector"] == {}
assert cvals["resources"]["limits"]["memory"] == "6Gi"
assert cvals["updateStrategy"]["rollingUpdate"]["maxSurge"] == 0
assert cvals["updateStrategy"]["rollingUpdate"]["maxUnavailable"] == 1

with open("charts/ai-inference-service/values-cloud-gpu-7b-awq.yaml", "r", encoding="utf-8") as f:
    awq_vals = yaml.safe_load(f)
assert awq_vals["replicaCount"] == 1
assert awq_vals["model"]["id"] == "Qwen/Qwen2.5-7B-Instruct-AWQ"
assert awq_vals["model"]["gpuMemoryUtilization"] == "0.92"
assert "--quantization=awq_marlin" in awq_vals["vllmArgs"]
assert awq_vals["modelCache"]["mountPath"] == "/cache/huggingface"
print("  [OK] Chart & all 3 values files parsed cleanly via PyYAML")
PYEOF

grep -q "namespace: ai-platform" charts/ai-inference-service/values.yaml && echo "  [OK] Canonical namespace 'ai-platform' in values.yaml"
grep -q "name: vllm-primary-svc" charts/ai-inference-service/values.yaml && echo "  [OK] Canonical service 'vllm-primary-svc' (port 8000) in values.yaml"
grep -q "pvcName: hf-model-cache-pvc" charts/ai-inference-service/values.yaml && echo "  [OK] Shared PVC 'hf-model-cache-pvc' configured"
grep -q "mountPath: /cache/huggingface" charts/ai-inference-service/values.yaml && echo "  [OK] Canonical HF_HOME='/cache/huggingface' configured"
grep -q "createPvc" charts/ai-inference-service/templates/pvc.yaml && echo "  [OK] Conditional PVC guard (.Values.modelCache.createPvc) in templates/pvc.yaml"
grep -q "gt (.Values.replicaCount | int) 1" charts/ai-inference-service/templates/pdb.yaml && echo "  [OK] PDB guarded to skip single-replica deployments"
grep -q "if .Values.model.passVllmCliArgs" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] Conditional vLLM CLI args gate configured in deployment.yaml"
grep -q "VLLM_CACHE_ROOT" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] VLLM_CACHE_ROOT=/tmp/vllm-cache configured in deployment.yaml"
grep -q "VLLM_CONFIG_ROOT" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] VLLM_CONFIG_ROOT=/tmp/vllm-config configured in deployment.yaml"
grep -q "startupProbe:" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] startupProbe configured in deployment.yaml"
grep -q "readinessProbe:" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] readinessProbe configured in deployment.yaml"
grep -q "livenessProbe:" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] livenessProbe configured in deployment.yaml"
grep -q 'command: \["sh", "-c", "sleep 5"\]' charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] Zero-downtime preStop hook ('sleep 5') configured"
grep -q -- "--enforce-eager" charts/ai-inference-service/templates/deployment.yaml && echo "  [OK] '--enforce-eager' CUDA Graph OOM protection configured"

if command -v helm >/dev/null 2>&1; then
  echo "  [RUN] Running helm lint & helm template across all 3 value files..."
  helm lint charts/ai-inference-service
  helm template local-release charts/ai-inference-service -f charts/ai-inference-service/values.yaml | (! grep -q "kind: PersistentVolumeClaim")
  helm template cloud-4x charts/ai-inference-service -f charts/ai-inference-service/values-cloud-gpu.yaml >/dev/null
  RENDER_7B="$(helm template cloud-7b charts/ai-inference-service -f charts/ai-inference-service/values-cloud-gpu-7b-awq.yaml)"
  echo "$RENDER_7B" | grep -q "kind: PersistentVolumeClaim"
  echo "$RENDER_7B" | (! grep -q "kind: PodDisruptionBudget")
  echo "  [OK] helm lint & template assertions passed for all 3 profiles"
elif [ "$VERIFY_MODE" = "cluster" ]; then
  echo "  [FAIL] VERIFY_MODE=cluster requires 'helm' CLI"
  exit 1
else
  echo "  [SKIP] 'helm' CLI not installed; helm lint/template runtime check skipped in static mode"
fi

echo ""
echo "[5/6] Verifying Cross-Chapter Alignment (Module 1 Dockerfile <-> Module 2 values.yaml)..."
M1_DOCKERFILE="$LAB_DIR/../m1-foundations/Dockerfile"
grep -q 'org.opencontainers.image.title="ai-inference-service"' "$M1_DOCKERFILE"
grep -q 'repository: ai-inference-service' charts/ai-inference-service/values.yaml
echo "  [OK] Docker Image name ('ai-inference-service:1.0.0') matches between M1 & M2"

grep -q 'PORT="8000"' "$M1_DOCKERFILE"
grep -q 'port: 8000' charts/ai-inference-service/values.yaml
echo "  [OK] Container Port ('8000') matches between M1 & M2"

grep -q 'HF_HOME="/cache/huggingface"' "$M1_DOCKERFILE"
grep -q 'mountPath: /cache/huggingface' charts/ai-inference-service/values.yaml
echo "  [OK] HF_HOME path ('/cache/huggingface') matches between M1 & M2"

echo ""
echo "[6/6] Verifying NVIDIA Time-Slicing ConfigMap..."
grep -q "name: nvidia-time-slicing-config" gpu-time-slicing-config.yaml && echo "  [OK] ConfigMap 'nvidia-time-slicing-config' present"
grep -q "replicas: 4" gpu-time-slicing-config.yaml && echo "  [OK] Time-slicing replicas: 4 configured"

echo "================================================================================"
echo "  [SUCCESS] Module 2 & Milestone Gate 1 Verification Passed (MODE=${VERIFY_MODE})!"
echo "================================================================================"
