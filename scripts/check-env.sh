#!/usr/bin/env bash
# ==============================================================================
# AI Infrastructure & Platform Engineering Handbook — Environment Verification
# Can be invoked via `make check-env` or `bash scripts/check-env.sh`
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

CLUSTER_NAME="ai-platform-local"
K8S_NAMESPACE="ai-platform"
HOST_HF_CACHE="/tmp/ai-infra-hf-cache"

mkdir -p "$HOST_HF_CACHE"
chmod 777 "$HOST_HF_CACHE" 2>/dev/null || true

echo "================================================================================"
echo "  1. ตรวจสอบทรัพยากรฮาร์ดแวร์ (Hardware & 16GB RAM Guardrail Check)"
echo "================================================================================"
OS_NAME=$(uname -s)
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
TOTAL_RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0)
FREE_DISK_GB=$(df -BG . 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}' || echo 0)

echo "  • Operating System : $OS_NAME ($(uname -m))"
echo "  • CPU Cores        : $CPU_CORES cores"
if [ "$TOTAL_RAM_MB" -ge 15000 ]; then
  echo "  • System RAM       : [OK] ${TOTAL_RAM_MB} MB (>= 16GB RAM Safe for Hybrid Labs)"
else
  echo "  • System RAM       : [WARN] ${TOTAL_RAM_MB} MB (< 16GB — แนะนำให้ใช้ Mock vLLM Server เสมอ)"
fi
if [ "$FREE_DISK_GB" -ge 20 ]; then
  echo "  • Free Disk Space  : [OK] ${FREE_DISK_GB} GB available"
else
  echo "  • Free Disk Space  : [WARN] ${FREE_DISK_GB} GB available (แนะนำอย่างน้อย 20 GB)"
fi
echo "  • HF Cache Mount   : [OK] ${HOST_HF_CACHE} -> Container HF_HOME=/cache/huggingface"

echo ""
echo "================================================================================"
echo "  2. ตรวจสอบเครื่องมือวิศวกรรม (CLI Toolchain Check)"
echo "================================================================================"
for cmd in git python3 make curl jq docker uv kubectl kind helm tofu trivy promtool nvidia-smi; do
  if command -v "$cmd" >/dev/null 2>&1; then
    VER=$("$cmd" --version 2>/dev/null | head -n 1 || "$cmd" version --client 2>/dev/null | head -n 1 || "$cmd" --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || echo "installed")
    printf "  • %-10s : [OK] %s\n" "$cmd" "$VER"
  else
    printf "  • %-10s : [MISSING] (ดูวิธีติดตั้งใน chapters/00-onboarding-and-setup.md)\n" "$cmd"
  fi
done
if python3 -c "import _pytest.config, pytest" >/dev/null 2>&1; then
  printf "  • %-10s : [OK] %s\n" "pytest" "$(python3 -m pytest --version 2>/dev/null | head -n 1)"
else
  printf "  • %-10s : [SHIM] ใช้ scripts/pytest stdlib fallback (แนะนำติดตั้ง pytest+httpx เพื่อรัน HTTP tests ครบ)\n" "pytest"
fi

echo ""
echo "================================================================================"
echo "  3. ตรวจสอบโครงสร้าง Repository และไฟล์มาตรฐาน (Repository Structure Check)"
echo "================================================================================"
MISSING=0
for path in \
  "README.md" \
  "SPEC_AND_STYLE_GUIDE.md" \
  "Makefile" \
  "chapters/00-onboarding-and-setup.md" \
  "chapters/01-foundations-containers-iac.md" \
  "chapters/02-kubernetes-gpu-orchestration.md" \
  "chapters/03-vllm-serving-optimization.md" \
  "chapters/04-ai-gateway-governance.md" \
  "chapters/05-observability-autoscaling-sre.md" \
  "chapters/06-capstone-siamshield-ai.md" \
  "labs/m1-foundations" \
  "labs/m2-k8s-gpu" \
  "labs/m3-vllm" \
  "labs/m4-gateway" \
  "labs/m5-observability-sre" \
  "labs/m6-capstone-siamshield" \
  "dist"; do
  if [ -e "$path" ]; then
    printf "  • %-45s : [OK]\n" "$path"
  else
    printf "  • %-45s : [MISSING]\n" "$path"
    MISSING=1
  fi
done

if [ "$MISSING" -eq 0 ]; then
  echo "--------------------------------------------------------------------------------"
  echo "  [SUCCESS] โครงสร้างบทที่ 0–6 และแล็บ M1–M6 ครบถ้วนสมบูรณ์ 100% พร้อมฝึกปฏิบัติและทดสอบ!"
  echo "--------------------------------------------------------------------------------"
else
  exit 1
fi
