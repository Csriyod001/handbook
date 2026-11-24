#!/usr/bin/env bash
# ==============================================================================
# AI Infrastructure & Platform Engineering Handbook — Environment Verification
# Can be invoked via `make check-env`, `python3 scripts/make check-env`, or directly
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
echo "  1. ตรวจสอบทรัพยากรฮาร์ดแวร์ (Hardware, RAM & GPU Guardrail Check)"
echo "================================================================================"
OS_NAME=$(uname -s)
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
TOTAL_RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0)
FREE_DISK_GB=$(df -BG . 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}' || echo 0)

echo "  • Operating System : $OS_NAME ($(uname -m))"
echo "  • CPU Cores        : $CPU_CORES cores"
if [ "$TOTAL_RAM_MB" -ge 20000 ]; then
  echo "  • System RAM       : [OK] ${TOTAL_RAM_MB} MB (>= 20GB — Full Local Stack + Observability Ready)"
elif [ "$TOTAL_RAM_MB" -ge 15000 ]; then
  echo "  • System RAM       : [OK] ${TOTAL_RAM_MB} MB (>= 16GB RAM Safe for Hybrid Labs)"
else
  echo "  • System RAM       : [WARN] ${TOTAL_RAM_MB} MB (< 16GB — ตั้งค่า .wslconfig ตาม Ch00 หรือใช้ Mock Mode)"
fi
if [ "$FREE_DISK_GB" -ge 20 ]; then
  echo "  • Free Disk Space  : [OK] ${FREE_DISK_GB} GB available"
else
  echo "  • Free Disk Space  : [WARN] ${FREE_DISK_GB} GB available (แนะนำอย่างน้อย 20 GB)"
fi
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader >/dev/null 2>&1; then
  GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -n 1)
  echo "  • Local CUDA GPU   : [OK] ${GPU_INFO} (พร้อมรัน Path A2 / vLLM CUDA)"
else
  echo "  • Local CUDA GPU   : [INFO] ไม่พบ NVIDIA GPU ใน WSL2 (ใช้ Mode A Mock / Cloud L4 / AWS g6.xlarge)"
fi
echo "  • HF Cache Mount   : [OK] ${HOST_HF_CACHE} -> Container HF_HOME=/cache/huggingface"

echo ""
echo "================================================================================"
echo "  2. ตรวจสอบเครื่องมือวิศวกรรม (CLI Toolchain Check)"
echo "================================================================================"
get_cmd_version() {
  local cmd="$1"
  local out=""
  if out="$("$cmd" --version 2>/dev/null | head -n 1)" && [ -n "$out" ]; then
    printf '%s' "$out"
    return 0
  fi
  if out="$("$cmd" version --client 2>/dev/null | head -n 1)" && [ -n "$out" ]; then
    printf '%s' "$out"
    return 0
  fi
  if [ "$cmd" = "nvidia-smi" ] && out="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1)" && [ -n "$out" ]; then
    printf '%s' "$out"
    return 0
  fi
  return 1
}

for cmd in git python3 make curl jq docker uv kubectl kind helm tofu trivy promtool nvidia-smi; do
  if command -v "$cmd" >/dev/null 2>&1; then
    if VER="$(get_cmd_version "$cmd")"; then
      printf "  • %-10s : [OK] %s\n" "$cmd" "$VER"
    elif [ "$cmd" = "docker" ]; then
      printf "  • %-10s : [WARN] WSL2 Docker Desktop integration ยังไม่เปิดใช้งาน (ดูวิธีเปิดใน Ch00)\n" "$cmd"
    else
      printf "  • %-10s : [OK] installed\n" "$cmd"
    fi
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
  "PORTABILITY_AND_QUICKSTART.md" \
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
  "labs/optional-cloud-aws" \
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
  echo "  [SUCCESS] โครงสร้างบทที่ 0–6 และแล็บ M1–M6 + Optional AWS ครบถ้วนสมบูรณ์ 100%!"
  echo "--------------------------------------------------------------------------------"
else
  exit 1
fi
