#!/usr/bin/env bash
# ==============================================================================
# Module 6 (M6 Capstone): Automated Verification & Grading Script (verify_capstone.sh)
# Evaluates all 5 Program Definitions of Done (DoD #1 - DoD #5) for 100/100 points
# and enforces Mandatory Auto-Fail Guardrails.
#
# Usage:
#   VERIFY_MODE=static|cluster bash verify_capstone.sh [--target workspace|examples]
# Defaults:
#   VERIFY_MODE=static
#   --target workspace (enforces zero <TODO> placeholders in learner deliverables;
#                       pass --target examples to validate worked examples/ samples)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export PATH="${REPO_ROOT}/scripts:${PATH}"

TARGET="workspace"
VERIFY_MODE="${VERIFY_MODE:-static}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1 (usage: $0 [--target workspace|examples])" >&2
      exit 1
      ;;
  esac
done

if [[ "${TARGET}" != "workspace" && "${TARGET}" != "examples" ]]; then
  echo "[FAIL] Invalid --target '${TARGET}' (expected 'workspace' or 'examples')" >&2
  exit 1
fi

CHAPTER_FILE="${REPO_ROOT}/chapters/06-capstone-siamshield-ai.md"
K8S_STACK="${SCRIPT_DIR}/k8s/siamshield-platform.yaml"
K8S_CRDS="${SCRIPT_DIR}/k8s/siamshield-crds.yaml"
K8S_NETPOL="${REPO_ROOT}/labs/m4-gateway/k8s/network-policies.yaml"
SIMULATOR="${SCRIPT_DIR}/src/siamshield_simulator.py"
DEFENSE_GUIDE="${SCRIPT_DIR}/docs/interview-defense-guide.md"

DESIGN_STARTER="${SCRIPT_DIR}/docs/design-doc.md"
OPT_STARTER="${SCRIPT_DIR}/reports/capstone-optimization-report.md"
RUNBOOK_STARTER="${SCRIPT_DIR}/docs/runbooks/capstone-runbook.md"
POSTMORTEM_STARTER="${SCRIPT_DIR}/docs/postmortems/capstone-postmortem.md"

if [[ "${TARGET}" == "examples" ]]; then
  DESIGN_DOC="${SCRIPT_DIR}/examples/design-doc-sample.md"
  OPT_REPORT="${SCRIPT_DIR}/examples/capstone-optimization-report-sample.md"
  RUNBOOK="${SCRIPT_DIR}/examples/capstone-runbook-sample.md"
  POSTMORTEM="${SCRIPT_DIR}/examples/capstone-postmortem-sample.md"
else
  DESIGN_DOC="${DESIGN_STARTER}"
  OPT_REPORT="${OPT_STARTER}"
  RUNBOOK="${RUNBOOK_STARTER}"
  POSTMORTEM="${POSTMORTEM_STARTER}"
fi

SCORE=0

echo "================================================================================"
echo " [CAPSTONE GRADER] Project SiamShield AI (MODE=${VERIFY_MODE}, TARGET=${TARGET})"
echo "================================================================================"

# ------------------------------------------------------------------------------
# 0. Verify Chapter 6 textbook completeness, Rubric & Starter Templates
# ------------------------------------------------------------------------------
if [[ ! -f "${CHAPTER_FILE}" ]]; then
  echo "[FAIL] Missing Chapter 6 file: ${CHAPTER_FILE}" >&2
  exit 1
fi
for section in \
  "1. Executive Summary & Learning Objectives" \
  "2. Architecture Overview" \
  "3. Core Theory & Deep-Dive Engineering Math" \
  "4. Hands-on Lab (Dual-Path Execution)" \
  "5. Chaos & Troubleshooting Drills" \
  "6. Optimization Exercise" \
  "7. Architecture Decision Record (ADR) & Capstone Design Documentation" \
  "8. Mid-Level Interview Trade-off Questions & Model Answers" \
  "9. Capstone Evaluation Rubric (Mapped to 5 Program DoDs)"; do
  grep -q "${section}" "${CHAPTER_FILE}"
done
if grep -qE "/home/non|/root/\.cache/huggingface" "${CHAPTER_FILE}"; then
  echo "[FAIL] Chapter 6 still contains hardcoded user paths or legacy /root/.cache/huggingface" >&2
  exit 1
fi

for f in "${DESIGN_STARTER}" "${OPT_STARTER}" "${RUNBOOK_STARTER}" "${POSTMORTEM_STARTER}" "${DESIGN_DOC}" "${OPT_REPORT}" "${RUNBOOK}" "${POSTMORTEM}" "${DEFENSE_GUIDE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "[FAIL] Missing required Capstone document: ${f}" >&2
    exit 1
  fi
done

grep -q "Decision 1:" "${DESIGN_STARTER}"
grep -q "Decision 2:" "${DESIGN_STARTER}"
grep -q "Decision 3:" "${DESIGN_STARTER}"
grep -q "5 Whys" "${POSTMORTEM_STARTER}"

if [[ "${TARGET}" == "workspace" ]]; then
  TODO_FOUND=0
  for wf in "${DESIGN_DOC}" "${OPT_REPORT}" "${RUNBOOK}" "${POSTMORTEM}"; do
    if grep -qE "<TODO|<FILL_ME" "${wf}"; then
      echo "[FAIL] Workspace deliverable still contains unfilled <TODO> placeholders: ${wf}" >&2
      TODO_FOUND=1
    fi
  done
  if [[ "${TODO_FOUND}" -ne 0 ]]; then
    echo "       Complete all starter templates first (or run '--target examples' to check repo reference samples)." >&2
    exit 1
  fi
fi
echo "[PASS] Chapter 6 textbook, starter templates, and target deliverables ready."

# ------------------------------------------------------------------------------
# DoD #1: Architecture Design Document (20 Points)
# ------------------------------------------------------------------------------
grep -q "299,593" "${DESIGN_DOC}"
grep -q "27.1%" "${DESIGN_DOC}"
grep -q "Decision 1:" "${DESIGN_DOC}"
grep -q "Decision 2:" "${DESIGN_DOC}"
grep -q "Decision 3:" "${DESIGN_DOC}"
grep -q "/cache/huggingface" "${DESIGN_DOC}"
if grep -q "/root/\.cache/huggingface" "${DESIGN_DOC}"; then
  echo "[FAIL] DoD #1 (${DESIGN_DOC}) still references legacy /root/.cache/huggingface" >&2
  exit 1
fi
SCORE=$((SCORE + 20))
echo "[DoD #1 PASS] Architecture Design Doc verified (VRAM Math + Break-even 27.1% + 3 Decisions): +20 pts"

# ------------------------------------------------------------------------------
# DoD #2: Reproducible Two-Tier Stack & Security/PDPA Guardrails (25 Points)
# ------------------------------------------------------------------------------
grep -q "hf-model-cache-pvc" "${K8S_STACK}"
grep -q "/cache/huggingface" "${K8S_STACK}"
grep -q "VLLM_CACHE_ROOT" "${K8S_STACK}"
grep -q "terminationGracePeriodSeconds: 60" "${K8S_STACK}"
grep -q "runAsUser: 10001" "${K8S_STACK}"
grep -q "siamshield-tier-realtime" "${K8S_CRDS}"
grep -q "siamshield-tier-batch" "${K8S_CRDS}"
grep -q "vllm-keda-scaler" "${K8S_CRDS}"
grep -q "kind: NetworkPolicy" "${K8S_NETPOL}"
if grep -q "/root/\.cache/huggingface" "${K8S_STACK}"; then
  echo "[FAIL] DoD #2: siamshield-platform.yaml must use /cache/huggingface, not /root/.cache/huggingface" >&2
  exit 1
fi

REPO_ROOT="${REPO_ROOT}" SIMULATOR="${SIMULATOR}" K8S_STACK="${K8S_STACK}" K8S_CRDS="${K8S_CRDS}" python3 - <<'PYEOF'
import ast
import os
import yaml

REPO_ROOT = os.environ["REPO_ROOT"]
SIMULATOR = os.environ["SIMULATOR"]
K8S_STACK = os.environ["K8S_STACK"]
K8S_CRDS = os.environ["K8S_CRDS"]

m4_cfg_path = f"{REPO_ROOT}/labs/m4-gateway/litellm_config.yaml"
m4_pdpa_path = f"{REPO_ROOT}/labs/m4-gateway/mock_vllm_server/pdpa_guardrail.py"
with open(m4_cfg_path, "r", encoding="utf-8") as f:
    m4_cfg = yaml.safe_load(f)
with open(m4_pdpa_path, "r", encoding="utf-8") as f:
    m4_pdpa = f.read()

with open(SIMULATOR, "r", encoding="utf-8") as f:
    ast.parse(f.read(), filename=SIMULATOR)

with open(K8S_STACK, "r", encoding="utf-8") as f:
    docs = [d for d in yaml.safe_load_all(f) if d is not None]
assert len(docs) == 15, f"Expected 15 Core K8s documents in siamshield-platform.yaml, got {len(docs)}"
assert not any(d.get("kind") == "Secret" for d in docs), "Hardcoded Secret objects must NOT appear in siamshield-platform.yaml"

with open(K8S_CRDS, "r", encoding="utf-8") as f:
    crd_docs = [d for d in yaml.safe_load_all(f) if d is not None]
assert len(crd_docs) == 9, f"Expected 9 CRD/EPP/KEDA documents in siamshield-crds.yaml, got {len(crd_docs)}"

for svc_name, expected_app in [
    ("vllm-primary-svc", "vllm-serving"),
    ("vllm-secondary-svc", "vllm-serving"),
    ("litellm-gateway-svc", "litellm-gateway"),
]:
    svc = next(d for d in docs if d.get("kind") == "Service" and d["metadata"]["name"] == svc_name)
    assert svc["metadata"].get("labels", {}).get("app") == expected_app, (
        f"Service {svc_name} must carry label app={expected_app} for ServiceMonitor discovery"
    )

pvc = next(d for d in docs if d.get("kind") == "PersistentVolumeClaim" and d["metadata"]["name"] == "hf-model-cache-pvc")
assert "ReadWriteMany" in pvc["spec"]["accessModes"], "PVC must specify ReadWriteMany across Primary & Secondary"
assert pvc["spec"].get("storageClassName") == "standard"

pg_pvc = next(d for d in docs if d.get("kind") == "PersistentVolumeClaim" and d["metadata"]["name"] == "postgres-data-pvc")
assert "ReadWriteOnce" in pg_pvc["spec"]["accessModes"]

cm = next(d for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "litellm-config")
assert yaml.safe_load(cm["data"]["litellm_config.yaml"]) == m4_cfg, "Capstone ConfigMap litellm_config.yaml drifted from M4"
assert cm["data"]["pdpa_guardrail.py"].strip() == m4_pdpa.strip(), "Capstone ConfigMap pdpa_guardrail.py drifted from M4"
ast.parse(cm["data"]["pdpa_guardrail.py"], filename="capstone-configmap:pdpa_guardrail.py")

vllm_primary = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == "vllm-primary")
vllm_secondary = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == "vllm-secondary")
assert vllm_primary["spec"]["template"]["metadata"]["labels"]["inference-pool"] == "vllm-qwen-pool"
assert vllm_secondary["spec"]["template"]["metadata"]["labels"]["inference-pool"] == "vllm-qwen-pool-secondary"

for dep in (vllm_primary, vllm_secondary):
    dep_name = dep["metadata"]["name"]
    pod_spec = dep["spec"]["template"]["spec"]
    pod_sc = pod_spec["securityContext"]
    c = pod_spec["containers"][0]
    envs = {e["name"]: e["value"] for e in c["env"]}
    assert c["image"] == "mock-vllm-server:1.0.0", f"{dep_name} must use mock-vllm-server:1.0.0"
    assert pod_sc["runAsNonRoot"] is True
    assert pod_sc["runAsUser"] == 10001
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["securityContext"]["allowPrivilegeEscalation"] is False
    assert envs.get("HF_HOME") == "/cache/huggingface"
    assert envs.get("VLLM_CACHE_ROOT") == "/tmp/vllm-cache"
    assert c["startupProbe"]["httpGet"]["path"] == "/health"
    assert c["livenessProbe"]["httpGet"]["path"] == "/health"

for req_dep in ["redis", "postgres", "litellm-gateway"]:
    assert any(d.get("kind") == "Deployment" and d["metadata"]["name"] == req_dep for d in docs), f"Missing Deployment {req_dep}"

assert any(d.get("kind") == "Job" and d["metadata"]["name"] == "litellm-init-virtual-keys" for d in docs)
assert any(d.get("kind") == "ServiceAccount" and d["metadata"]["name"] == "vllm-qwen-epp-sa" for d in crd_docs)
assert any(d.get("kind") == "Role" and d["metadata"]["name"] == "vllm-qwen-epp-role" for d in crd_docs)
assert any(d.get("kind") == "RoleBinding" and d["metadata"]["name"] == "vllm-qwen-epp-binding" for d in crd_docs)

epp_dep = next(d for d in crd_docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == "vllm-qwen-epp")
epp_spec = epp_dep["spec"]["template"]["spec"]
assert epp_spec["serviceAccountName"] == "vllm-qwen-epp-sa"
epp_container = epp_spec["containers"][0]
assert epp_container["image"].endswith("epp:v1.0.0")
assert "--pool-name=vllm-qwen-pool" in epp_container["args"]

pool_doc = next(d for d in crd_docs if d.get("kind") == "InferencePool")
assert pool_doc["apiVersion"] == "inference.networking.k8s.io/v1"
obj_docs = [d for d in crd_docs if d.get("kind") == "InferenceObjective"]
assert len(obj_docs) == 2 and all(d["apiVersion"] == "llm-d.ai/v1" for d in obj_docs)
assert all("poolRefs" in d["spec"] and "criticality" not in d["spec"] and "modelName" not in d["spec"] for d in obj_docs)
rt_obj = next(d for d in obj_docs if "realtime" in d["metadata"]["name"])
bt_obj = next(d for d in obj_docs if "batch" in d["metadata"]["name"])
assert rt_obj["spec"]["priority"] > 0 and bt_obj["spec"]["priority"] < 0

scaled = next(d for d in crd_docs if d.get("kind") == "ScaledObject")
triggers = scaled["spec"]["triggers"]
q_trig = next(t for t in triggers if "num_requests_waiting" in t["metadata"]["query"])
kv_trig = next(t for t in triggers if "kv_cache_usage_perc" in t["metadata"]["query"])
assert q_trig.get("name") == "vllm-waiting-requests-queue"
assert kv_trig.get("name") == "vllm-kv-cache-usage-ratio"
assert q_trig.get("metricType") == "AverageValue"
assert kv_trig.get("metricType") == "Value"
assert 'pod=~"vllm-primary-.*"' in q_trig["metadata"]["query"]
assert 'pod=~"vllm-primary-.*"' in kv_trig["metadata"]["query"]
assert "server_id=" not in q_trig["metadata"]["query"]
assert "server_id=" not in kv_trig["metadata"]["query"]
PYEOF

if command -v kubectl >/dev/null 2>&1; then
  kubectl apply --dry-run=client --validate=false -f "${K8S_STACK}" >/dev/null
  echo "[OK] kubectl client dry-run passed on ${K8S_STACK}."
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] VERIFY_MODE=cluster requires 'kubectl' CLI installed" >&2
  exit 1
else
  echo "[SKIP] 'kubectl' CLI not installed; Kubernetes dry-run/cluster validation skipped in static mode"
fi

if command -v docker >/dev/null 2>&1 && docker --version >/dev/null 2>&1; then
  echo "[OK] docker CLI detected ($(docker --version | head -n 1))"
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] VERIFY_MODE=cluster requires 'docker' CLI installed" >&2
  exit 1
else
  echo "[SKIP] 'docker' CLI not active; mock-vllm-server container build skipped in static mode"
fi

python3 "${SIMULATOR}" > /dev/null
pytest "${SIMULATOR}" -v
SCORE=$((SCORE + 25))
echo "[DoD #2 PASS] Unified K8s Stack (24 YAML docs + M4 ConfigMap/AST parity), Non-root UID 10001, /cache/huggingface PVC & Simulator verified: +25 pts"

# ------------------------------------------------------------------------------
# DoD #3: Measurable Two-Tier Optimization Report (20 Points)
# ------------------------------------------------------------------------------
OPT_REPORT="${OPT_REPORT}" python3 - <<'PYEOF'
import os
import re

opt_report = os.environ["OPT_REPORT"]
with open(opt_report, "r", encoding="utf-8") as f:
    text = f.read()

assert "/root/.cache/huggingface" not in text, "Optimization report must not reference /root/.cache/huggingface"
assert "<THAI_ID_REDACTED>" in text, "Optimization report must document <THAI_ID_REDACTED>"

def extract_row_numbers(row_prefix):
    for line in text.splitlines():
        if line.lstrip().startswith("|") and row_prefix in line:
            nums = [float(x.replace(",", "")) for x in re.findall(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:ms|%|GB)", line)]
            return line, nums
    raise AssertionError(f"Missing measurement table row matching '{row_prefix}' in {opt_report}")

ttft_line, ttft_nums = extract_row_numbers("TTFT p95")
assert any(n < 800.0 for n in ttft_nums), f"TTFT p95 must be < 800 ms in: {ttft_line}"

itl_line, itl_nums = extract_row_numbers("ITL p95")
assert any(n < 30.0 for n in itl_nums), f"ITL p95 must be < 30 ms in: {itl_line}"

apc_line, apc_nums = extract_row_numbers("Automatic Prefix Cache")
assert any(n >= 70.0 for n in apc_nums), f"APC Hit Rate must be >= 70% in: {apc_line}"

cost_line, _ = extract_row_numbers("Unit Cost")
costs = [float(x) for x in re.findall(r"\$(\d+(?:\.\d+)?)\s*/\s*1M", cost_line)]
assert any(c < 0.60 for c in costs), f"Optimized unit cost must be < $0.60 / 1M tok in: {cost_line}"
PYEOF
SCORE=$((SCORE + 20))
echo "[DoD #3 PASS] Two-Tier Optimization Report SLOs verified (TTFT < 800ms, ITL < 30ms, APC >= 70%, Cost < \$0.60/1M): +20 pts"

# ------------------------------------------------------------------------------
# DoD #4: SRE Observability, Runbook & Blameless Postmortem (20 Points)
# ------------------------------------------------------------------------------
grep -q "vllm:kv_cache_usage_perc" "${RUNBOOK}"
grep -q "vllm:num_requests_waiting" "${RUNBOOK}"
grep -q "terminationGracePeriodSeconds: 60" "${RUNBOOK}"
grep -q "/cache/huggingface" "${RUNBOOK}"
grep -q 'pod=~"vllm-primary-\.\*"' "${RUNBOOK}"
if grep -qE "/root/\.cache/huggingface|X-LiteLLM-Fallback-Triggered" "${RUNBOOK}"; then
  echo "[FAIL] DoD #4 (${RUNBOOK}) contains deprecated /root/.cache/huggingface or non-existent X-LiteLLM-Fallback-Triggered header" >&2
  exit 1
fi
grep -q "5 Whys" "${POSTMORTEM}"
grep -q "<THAI_ID_REDACTED>" "${POSTMORTEM}"
grep -q "/cache/huggingface" "${POSTMORTEM}"
if grep -q "/root/\.cache/huggingface" "${POSTMORTEM}"; then
  echo "[FAIL] DoD #4 (${POSTMORTEM}) still references /root/.cache/huggingface" >&2
  exit 1
fi
SCORE=$((SCORE + 20))
echo "[DoD #4 PASS] SRE Production Runbook & Blameless Postmortem verified: +20 pts"

# ------------------------------------------------------------------------------
# DoD #5: Mid-Level Architecture Defense Guide (15 Points)
# ------------------------------------------------------------------------------
grep -q "awq_marlin" "${DEFENSE_GUIDE}"
grep -q "Sheddable" "${DEFENSE_GUIDE}"
grep -q "<THAI_ID_REDACTED>" "${DEFENSE_GUIDE}"
grep -q "27.1%" "${DEFENSE_GUIDE}"
grep -q "/cache/huggingface" "${DEFENSE_GUIDE}"
if grep -q "/root/\.cache/huggingface" "${DEFENSE_GUIDE}"; then
  echo "[FAIL] DoD #5 (${DEFENSE_GUIDE}) still references /root/.cache/huggingface" >&2
  exit 1
fi
SCORE=$((SCORE + 15))
echo "[DoD #5 PASS] Mid-Level Interview Defense Guide verified: +15 pts"

echo "================================================================================"
echo " [CAPSTONE GRADER] FINAL SCORE: ${SCORE} / 100 Points (STATUS: MID-LEVEL READY)"
echo "================================================================================"
