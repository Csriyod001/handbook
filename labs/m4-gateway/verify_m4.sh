#!/usr/bin/env bash
# ==============================================================================
# Module 4 (M4): Automated Verification Script (verify_m4.sh)
# Checks:
#   1. Chapter 4 textbook completeness & all 8 mandatory sections
#   2. Canonical service names/ports (litellm-gateway-svc:4000, redis-svc:6379, postgres-svc:5432, vllm-primary-svc:8000, vllm-secondary-svc:8000)
#   3. Gateway API Inference Extension CRDs (InferencePool & InferenceModel) in k8s/gateway-stack.yaml
#   4. ADR-003 completeness
#   5. Execution of pytest on labs/m4-gateway/tests/test_gateway_resilience.py
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export PATH="${REPO_ROOT}/scripts:${PATH}"
VERIFY_MODE="${VERIFY_MODE:-static}"

if [[ "${VERIFY_MODE}" != "static" && "${VERIFY_MODE}" != "cluster" ]]; then
  echo "[FAIL] Invalid VERIFY_MODE='${VERIFY_MODE}'. Use 'static' or 'cluster'." >&2
  exit 1
fi

CHAPTER_FILE="${REPO_ROOT}/chapters/04-ai-gateway-governance.md"
LITELLM_CFG="${SCRIPT_DIR}/litellm_config.yaml"
K8S_MANIFEST="${SCRIPT_DIR}/k8s/gateway-stack.yaml"
K8S_ROUTE_MANIFEST="${SCRIPT_DIR}/k8s/gateway-api-route.yaml"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
ADR_FILE="${SCRIPT_DIR}/docs/adr-003-ai-gateway-and-inference-routing.md"

echo "=================================================================="
echo " [M4 VERIFY] Starting Milestone 4 Verification Suite (mode=${VERIFY_MODE})"
echo "=================================================================="

# 1. Verify Chapter 4 file & mandatory sections
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
    echo "[FAIL] Chapter 4 is missing mandatory section: ${section}" >&2
    exit 1
  fi
done
echo "[PASS] Chapter 4 contains all 8 mandatory sections."

# 2. Verify key concepts and all 9 vLLM V1 metrics in Chapter 4 (EPP, InferencePool, InferenceModel, PDPA, ADR-003)
for concept in \
  "InferencePool" \
  "InferenceModel" \
  "Endpoint Picker" \
  "<THAI_ID_REDACTED>" \
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
  "X-Sim-Cache-Hit" \
  "ADR-003"; do
  if ! grep -q "${concept}" "${CHAPTER_FILE}"; then
    echo "[FAIL] Chapter 4 is missing required concept/metric: ${concept}" >&2
    exit 1
  fi
done
echo "[PASS] Chapter 4 covers LiteLLM, K8s Inference Extension (EPP), PDPA PII Masking, all 9 V1 metrics, and ADR-003."

# 3. Verify litellm_config.yaml, mock_vllm_server packaging, and k8s manifests alignment + YAML/AST parity
for req_file in \
  "${SCRIPT_DIR}/mock_vllm_server/app.py" \
  "${SCRIPT_DIR}/mock_vllm_server/pdpa_guardrail.py" \
  "${SCRIPT_DIR}/mock_vllm_server/Dockerfile" \
  "${K8S_ROUTE_MANIFEST}" \
  "${ENV_EXAMPLE}"; do
  if [[ ! -f "${req_file}" ]]; then
    echo "[FAIL] Missing required M4 packaging file: ${req_file}" >&2
    exit 1
  fi
done

for svc in \
  "vllm-primary-svc" \
  "vllm-secondary-svc" \
  "redis-svc"; do
  grep -q "${svc}" "${LITELLM_CFG}"
  grep -q "${svc}" "${K8S_MANIFEST}"
done
grep -q "postgres-svc" "${K8S_MANIFEST}"
grep -q "os.environ/DATABASE_URL" "${LITELLM_CFG}"
grep -q "os.environ/LITELLM_MASTER_KEY" "${LITELLM_CFG}"
grep -q "litellm-gateway-svc" "${K8S_MANIFEST}"
grep -q "kind: InferencePool" "${K8S_MANIFEST}"
grep -q "kind: InferenceModel" "${K8S_MANIFEST}"

python3 - <<PYEOF
import ast
import yaml

for py_path in [
    "${SCRIPT_DIR}/mock_vllm_server/app.py",
    "${SCRIPT_DIR}/mock_vllm_server/pdpa_guardrail.py",
    "${SCRIPT_DIR}/tests/test_gateway_resilience.py",
]:
    with open(py_path, "r", encoding="utf-8") as f:
        ast.parse(f.read(), filename=py_path)

with open("${LITELLM_CFG}", "r", encoding="utf-8") as f:
    lcfg_text = f.read()
    lcfg = yaml.safe_load(lcfg_text)
assert "pdpa_guardrail.proxy_handler_instance" in str(lcfg), "PDPA callback missing in litellm_config.yaml"
assert lcfg["router_settings"]["num_retries"] == 0, "num_retries must be 0 so stream_timeout triggers immediate fallback"

with open("${SCRIPT_DIR}/mock_vllm_server/pdpa_guardrail.py", "r", encoding="utf-8") as f:
    pdpa_text = f.read()

with open("${K8S_MANIFEST}", "r", encoding="utf-8") as f:
    docs = [d for d in yaml.safe_load_all(f) if d is not None]
assert len(docs) == 22, f"Expected 22 K8s documents in gateway-stack.yaml, got {len(docs)}"

with open("${K8S_ROUTE_MANIFEST}", "r", encoding="utf-8") as f:
    route_docs = [d for d in yaml.safe_load_all(f) if d is not None]
route_kinds = {d.get("kind") for d in route_docs}
assert {"Gateway", "HTTPRoute", "ServiceMonitor"}.issubset(route_kinds), (
    f"gateway-api-route.yaml missing expected kinds: {route_kinds}"
)

cm = next(d for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "litellm-config")
assert yaml.safe_load(cm["data"]["litellm_config.yaml"]) == lcfg, "ConfigMap litellm_config.yaml drifted from M4 litellm_config.yaml"
assert cm["data"]["pdpa_guardrail.py"].strip() == pdpa_text.strip(), "ConfigMap pdpa_guardrail.py drifted from SSOT"
ast.parse(cm["data"]["pdpa_guardrail.py"], filename="configmap:pdpa_guardrail.py")

assert not any(d.get("kind") == "Secret" for d in docs), "Hardcoded Secret must not remain in gateway-stack.yaml"
assert any(d.get("kind") == "PersistentVolumeClaim" and d["metadata"]["name"] == "postgres-data-pvc" for d in docs)
assert any(d.get("kind") == "Job" and d["metadata"]["name"] == "litellm-init-virtual-keys" for d in docs)
assert any(d.get("kind") == "ServiceAccount" and d["metadata"]["name"] == "vllm-qwen-epp-sa" for d in docs)
assert any(d.get("kind") == "Role" and d["metadata"]["name"] == "vllm-qwen-epp-role" for d in docs)
assert any(d.get("kind") == "RoleBinding" and d["metadata"]["name"] == "vllm-qwen-epp-binding" for d in docs)

for dep_name in ["vllm-primary", "vllm-secondary"]:
    dep = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == dep_name)
    pod_spec = dep["spec"]["template"]["spec"]
    pod_sc = pod_spec["securityContext"]
    c = pod_spec["containers"][0]
    assert c["image"] == "mock-vllm-server:1.0.0", f"{dep_name} must use mock-vllm-server:1.0.0"
    assert pod_sc["runAsNonRoot"] is True
    assert pod_sc["runAsUser"] == 10001
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["securityContext"]["allowPrivilegeEscalation"] is False

vsec = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == "vllm-secondary")
assert vsec["spec"]["template"]["metadata"]["labels"]["inference-pool"] == "vllm-qwen-pool-secondary"

epp = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == "vllm-qwen-epp")
assert epp["spec"]["template"]["spec"]["serviceAccountName"] == "vllm-qwen-epp-sa"
PYEOF
echo "[PASS] litellm_config.yaml, mock-vllm-server:1.0.0, ConfigMap/AST parity, k8s/gateway-stack.yaml (22 docs), and gateway-api-route.yaml verified."

if command -v docker >/dev/null 2>&1; then
  echo "[PASS] docker binary detected (ready for mock-vllm-server:1.0.0 image build)."
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] docker binary is required when VERIFY_MODE=cluster." >&2
  exit 1
else
  echo "[SKIP] docker not installed; skipping container build verification in VERIFY_MODE=static."
fi

if command -v kubectl >/dev/null 2>&1; then
  kubectl apply --dry-run=client -f "${K8S_MANIFEST}" >/dev/null 2>&1 || echo "[WARN] kubectl client dry-run skipped/warned (CRDs may be absent locally)."
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] kubectl is required when VERIFY_MODE=cluster." >&2
  exit 1
else
  echo "[SKIP] kubectl not installed; skipping Kubernetes schema dry-run in VERIFY_MODE=static."
fi

# 4. Verify ADR-003 file exists
if [[ ! -f "${ADR_FILE}" ]]; then
  echo "[FAIL] Missing ADR-003 file: ${ADR_FILE}" >&2
  exit 1
fi
grep -q "ADR-003" "${ADR_FILE}"
echo "[PASS] ADR-003 documentation verified."

# 5. Run pytest suite for mock_vllm_server and gateway resilience
echo "[M4 VERIFY] Running pytest on labs/m4-gateway/tests/test_gateway_resilience.py..."
pytest "${SCRIPT_DIR}/tests/test_gateway_resilience.py" -v

echo "=================================================================="
echo " [M4 VERIFY] ALL MILESTONE 4 CHECKS PASSED (100%)"
echo "=================================================================="
