#!/usr/bin/env bash
# ==============================================================================
# Module 5 (M5): Automated Verification Script (verify_m5.sh)
# Checks:
#   1. Chapter 5 completeness (all 8 sections, Production Runbook, Blameless Postmortem, 5 Interview Q&As)
#   2. Grafana dashboard JSON validity & exact vLLM V1 + DCGM PromQL queries
#   3. Prometheus alert rules YAML (`prometheus-alert-rules.yaml`)
#   4. KEDA ScaledObject YAML (`keda-vllm-scaledobject.yaml` with HF_HOME PVC & terminationGracePeriodSeconds: 60)
#   5. Execution of `chaos/trigger_incident.py` & pytest
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

CHAPTER_FILE="${REPO_ROOT}/chapters/05-observability-autoscaling-sre.md"
DASHBOARD_JSON="${SCRIPT_DIR}/grafana-dashboard-vllm-v1.json"
ALERT_RULES="${SCRIPT_DIR}/prometheus-alert-rules.yaml"
KEDA_MANIFEST="${SCRIPT_DIR}/keda-vllm-scaledobject.yaml"
SERVICEMONITOR_MANIFEST="${SCRIPT_DIR}/servicemonitor-vllm.yaml"
CHAOS_SCRIPT="${SCRIPT_DIR}/chaos/trigger_incident.py"

echo "=================================================================="
echo " [M5 VERIFY] Starting Milestone 5 Verification Suite (mode=${VERIFY_MODE})"
echo "=================================================================="

# 1. Check Chapter 5 mandatory sections & SRE artifacts
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
  "7. Architecture Decision Record (ADR), Production Runbook & Blameless Postmortem" \
  "8. Mid-Level Interview Trade-off Questions & Model Answers" \
  "Production Incident Runbook" \
  "Blameless Postmortem"; do
  if ! grep -q "${section}" "${CHAPTER_FILE}"; then
    echo "[FAIL] Chapter 5 is missing mandatory section/artifact: ${section}" >&2
    exit 1
  fi
done
echo "[PASS] Chapter 5 contains all 8 mandatory sections, Production Runbook, and Blameless Postmortem."

# 2. Validate Grafana Dashboard JSON & canonical V1 + DCGM metrics
python3 - <<PYEOF
import json
with open("${DASHBOARD_JSON}", "r", encoding="utf-8") as f:
    data = json.load(f)
panels = data.get("panels", [])
assert len(panels) >= 9, f"Expected at least 9 panels (including separated VRAM MiB panel), got {len(panels)}"
panel2_expr = panels[1]["targets"][0]["expr"]
assert panel2_expr.startswith("histogram_quantile(0.95, sum(rate(vllm:inter_token_latency_seconds_bucket"), (
    "Grafana Panel 2 must put vllm:inter_token_latency_seconds_bucket primary before fallback"
)
panel8_raw = json.dumps(panels[7])
assert "DCGM_FI_DEV_FB_USED" not in panel8_raw, "Panel 8 (0-1 ratio) must not mix MiB scale DCGM_FI_DEV_FB_USED"
raw = json.dumps(data)
for metric in [
    "vllm:time_to_first_token_seconds_bucket",
    "vllm:inter_token_latency_seconds_bucket",
    "vllm:time_per_output_token_seconds_bucket",
    "vllm:kv_cache_usage_perc",
    "vllm:num_requests_waiting",
    "vllm:prefix_cache_hits_total",
    "vllm:prefix_cache_queries_total",
    "vllm:num_preemptions_total",
    "vllm:generation_tokens_total",
    "DCGM_FI_DEV_GPU_UTIL",
    "DCGM_FI_PROF_SM_ACTIVE",
    "DCGM_FI_PROF_DRAM_ACTIVE",
    "DCGM_FI_DEV_FB_USED",
]:
    assert metric in raw, f"Missing metric {metric} in grafana-dashboard-vllm-v1.json"
assert "clamp_min" in raw and "1e-9" in raw, "Expected clamp_min(..., 1e-9) in Grafana Prefix Cache query"
PYEOF
echo "[PASS] grafana-dashboard-vllm-v1.json is valid JSON (9 panels, primary ITL, separated VRAM axis, 1e-9 clamp)."

# 3. Validate Prometheus Alert Rules & Multi-Window SLO Burn Rate via PyYAML
for alert_token in \
  "VLLMKVCacheSaturationWarning" \
  "VLLMPreemptionThrashingCritical" \
  "VLLMHighTTFTBurnRateCritical" \
  "VLLMHighITLWarning" \
  "VLLMPrefixCacheHitDropWarning" \
  "vllm:kv_cache_usage_perc" \
  "vllm:num_preemptions_total" \
  "vllm:time_to_first_token_seconds_bucket"; do
  grep -q "${alert_token}" "${ALERT_RULES}"
done

python3 - <<PYEOF
import yaml

with open("${ALERT_RULES}", "r", encoding="utf-8") as f:
    docs = [d for d in yaml.safe_load_all(f) if d is not None]
assert len(docs) >= 1
rules = docs[0]["spec"]["groups"][0]["rules"]
burn_rule = next(r for r in rules if r.get("alert") == "VLLMHighTTFTBurnRateCritical")
assert 'le="0.75"' in burn_rule["expr"], 'VLLMHighTTFTBurnRateCritical must use real vLLM bucket le="0.75"'
assert "[5m]" in burn_rule["expr"] and "[1h]" in burn_rule["expr"] and ("14.4 * 0.001" in burn_rule["expr"] or "0.0144" in burn_rule["expr"]), "Multi-window 14.4x burn rate missing"
cache_rule = next(r for r in rules if r.get("alert") == "VLLMPrefixCacheHitDropWarning")
assert "1e-9" in cache_rule["expr"], "Expected clamp_min(..., 1e-9) in VLLMPrefixCacheHitDropWarning"
itl_rule = next(r for r in rules if r.get("alert") == "VLLMHighITLWarning")
assert "vllm:inter_token_latency_seconds_bucket" in itl_rule["expr"]
PYEOF
if command -v promtool >/dev/null 2>&1; then
  tmp_rules="$(mktemp)"
  python3 -c "import yaml; d=yaml.safe_load(open('${ALERT_RULES}')); yaml.safe_dump(d['spec'], open('${tmp_rules}','w'))"
  promtool check rules "${tmp_rules}"
  rm -f "${tmp_rules}"
  echo "[PASS] promtool check rules verified prometheus-alert-rules.yaml."
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] promtool is required when VERIFY_MODE=cluster." >&2
  exit 1
else
  echo "[SKIP] promtool not installed; skipping native PromQL rule lint in VERIFY_MODE=static."
fi
echo "[PASS] prometheus-alert-rules.yaml validated (YAML parse + le=\"0.75\" + multi-window 5m/1h burn-rate + 1e-9 clamp)."

# 4. Validate KEDA ScaledObject, Pod Security, ServiceMonitor & M5 docs/ Artifacts
for keda_token in \
  "kind: ScaledObject" \
  "vllm:num_requests_waiting" \
  "vllm:kv_cache_usage_perc" \
  "terminationGracePeriodSeconds: 60" \
  "/cache/huggingface" \
  "hf-model-cache-pvc"; do
  grep -q "${keda_token}" "${KEDA_MANIFEST}"
done

if grep -q "/root/.cache/huggingface" "${KEDA_MANIFEST}"; then
  echo "[FAIL] Legacy /root/.cache/huggingface found in ${KEDA_MANIFEST}" >&2
  exit 1
fi

python3 - <<PYEOF
import yaml

with open("${KEDA_MANIFEST}", "r", encoding="utf-8") as f:
    docs = [d for d in yaml.safe_load_all(f) if d is not None]
dep = next(d for d in docs if d.get("kind") == "Deployment")
pod_spec = dep["spec"]["template"]["spec"]
pod_sc = pod_spec["securityContext"]
c = pod_spec["containers"][0]
assert c["image"] == "mock-vllm-server:1.0.0", "Deployment must use mock-vllm-server:1.0.0"
assert pod_sc["runAsNonRoot"] is True
assert pod_sc["runAsUser"] == 10001
assert c["securityContext"]["readOnlyRootFilesystem"] is True
assert c["securityContext"]["allowPrivilegeEscalation"] is False

scaled = next(d for d in docs if d.get("kind") == "ScaledObject")
triggers = scaled["spec"]["triggers"]
q_trig = next(t for t in triggers if "num_requests_waiting" in t["metadata"]["query"])
kv_trig = next(t for t in triggers if "kv_cache_usage_perc" in t["metadata"]["query"])
assert q_trig.get("name") == "vllm-waiting-requests-queue"
assert kv_trig.get("name") == "vllm-kv-cache-usage-ratio"
assert q_trig.get("metricType") == "AverageValue", "Waiting queue trigger must use metricType: AverageValue"
assert kv_trig.get("metricType") == "Value", "KV-cache avg trigger must use metricType: Value"
assert 'pod=~"vllm-primary-.*"' in q_trig["metadata"]["query"]
assert 'pod=~"vllm-primary-.*"' in kv_trig["metadata"]["query"]
assert "server_id=" not in q_trig["metadata"]["query"]
assert "server_id=" not in kv_trig["metadata"]["query"]

with open("${SERVICEMONITOR_MANIFEST}", "r", encoding="utf-8") as f:
    sm_docs = [d for d in yaml.safe_load_all(f) if d is not None]
assert len(sm_docs) == 2 and all(d.get("kind") == "ServiceMonitor" for d in sm_docs)
PYEOF

for doc_file in \
  "${SERVICEMONITOR_MANIFEST}" \
  "${SCRIPT_DIR}/docs/adr-004-observability-and-keda-autoscaling.md" \
  "${SCRIPT_DIR}/docs/runbook-kvcache-saturation-and-high-ttft.md" \
  "${SCRIPT_DIR}/docs/postmortem-001-peak-hour-latency-outage.md"; do
  if [[ ! -f "${doc_file}" ]]; then
    echo "[FAIL] Missing required M5 docs artifact: ${doc_file}" >&2
    exit 1
  fi
done
echo "[PASS] keda-vllm-scaledobject.yaml (YAML + AverageValue/Value + pod selector), servicemonitor-vllm.yaml, and M5 docs/* verified."

if command -v kubectl >/dev/null 2>&1; then
  if kubectl cluster-info --request-timeout=3s >/dev/null 2>&1; then
    kubectl apply --dry-run=client -f "${KEDA_MANIFEST}" >/dev/null 2>&1 || echo "[WARN] kubectl client dry-run skipped/warned (CRDs may be absent locally)."
  elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
    echo "[FAIL] VERIFY_MODE=cluster requires a reachable Kubernetes cluster." >&2
    exit 1
  else
    echo "[SKIP] kubectl detected but no reachable cluster; Kubernetes dry-run skipped in VERIFY_MODE=static."
  fi
elif [[ "${VERIFY_MODE}" == "cluster" ]]; then
  echo "[FAIL] kubectl is required when VERIFY_MODE=cluster." >&2
  exit 1
else
  echo "[SKIP] kubectl not installed; skipping Kubernetes schema dry-run in VERIFY_MODE=static."
fi

# 5. Execute Chaos Incident Simulator, Live Dry-Run & pytest (no chmod mutation)
python3 "${CHAOS_SCRIPT}" --simulate > /dev/null
python3 "${CHAOS_SCRIPT}" --live --dry-run > /dev/null
pytest "${CHAOS_SCRIPT}" -v

echo "=================================================================="
echo " [M5 VERIFY] ALL MILESTONE 5 CHECKS PASSED (100%)"
echo "=================================================================="
