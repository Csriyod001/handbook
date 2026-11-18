# ==============================================================================
# AI Infrastructure & Platform Engineering Handbook — Master Makefile
# Single Source of Truth Variables (Must match SPEC_AND_STYLE_GUIDE.md)
# ==============================================================================

SHELL := /bin/bash
CLUSTER_NAME := ai-platform-local
K8S_NAMESPACE := ai-platform
MON_NAMESPACE := monitoring
GPU_OPERATOR_NS := gpu-operator
KEDA_NAMESPACE := keda
HOST_HF_CACHE := /tmp/ai-infra-hf-cache
LOCAL_CPU_MODEL := Qwen/Qwen2.5-0.5B-Instruct
CLOUD_GPU_MODEL := Qwen/Qwen2.5-7B-Instruct
CLOUD_GPU_AWQ_MODEL := Qwen/Qwen2.5-7B-Instruct-AWQ

.DEFAULT_GOAL := help

.PHONY: help check-env init-cache verify-structure verify-static verify-cluster verify-all build-handbook clean-cache

help: ## แสดงรายการคำสั่งทั้งหมดของ AI Infrastructure Handbook
	@echo "================================================================================"
	@echo "  AI Infrastructure & Platform Engineering Handbook (12-Week Roadmap)"
	@echo "  Canonical Namespace: $(K8S_NAMESPACE) | Cluster: $(CLUSTER_NAME)"
	@echo "================================================================================"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo "================================================================================"

init-cache: ## สร้างโฟลเดอร์กลางสำหรับเก็บ Model Weights Cache (HF_HOME) บนเครื่อง Host
	@mkdir -p $(HOST_HF_CACHE)
	@chmod 777 $(HOST_HF_CACHE)
	@echo "[OK] Shared Hugging Face cache directory ready at: $(HOST_HF_CACHE)"

check-env: init-cache ## ตรวจสอบความพร้อมของเครื่อง (RAM 16GB, Disk, Docker, kind, kubectl, helm, tofu, uv)
	@bash scripts/check-env.sh

verify-structure: ## ตรวจสอบความครบถ้วนของบทเรียนที่ 0–6 และแล็บทุกโมดูลใน Repository
	@MISSING=0; \
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
		"labs/m1-foundations/verify_m1.sh" \
		"labs/m2-k8s-gpu/verify_m2.sh" \
		"labs/m3-vllm/verify_m3.sh" \
		"labs/m4-gateway/verify_m4.sh" \
		"labs/m5-observability-sre/verify_m5.sh" \
		"labs/m6-capstone-siamshield/verify_capstone.sh" \
		"dist"; do \
		if [ -e "$$path" ]; then \
			printf "  • %-48s : [OK]\n" "$$path"; \
		else \
			printf "  • %-48s : [MISSING]\n" "$$path"; \
			MISSING=1; \
		fi; \
	done; \
	if [ "$$MISSING" -eq 0 ]; then \
		echo "--------------------------------------------------------------------------------"; \
		echo "  [SUCCESS] บทที่ 0–6 และแล็บ M1–M6 พร้อมใช้งานครบสมบูรณ์ 100%!"; \
		echo "--------------------------------------------------------------------------------"; \
	else \
		exit 1; \
	fi

verify-static: check-env verify-structure ## ตรวจสคริปต์และ Unit Tests โหมด Static (ไม่ต้องใช้ Docker/K8s)
	@VERIFY_MODE=static bash labs/m1-foundations/verify_m1.sh
	@VERIFY_MODE=static bash labs/m2-k8s-gpu/verify_m2.sh
	@VERIFY_MODE=static bash labs/m3-vllm/verify_m3.sh
	@VERIFY_MODE=static bash labs/m4-gateway/verify_m4.sh
	@VERIFY_MODE=static bash labs/m5-observability-sre/verify_m5.sh
	@VERIFY_MODE=static bash labs/m6-capstone-siamshield/verify_capstone.sh --target examples

verify-cluster: check-env ## ตรวจ Runtime, OpenTofu, Helm, Container และ Endpoint จริงบน Kind/Cluster
	@VERIFY_MODE=cluster bash labs/m1-foundations/verify_m1.sh
	@VERIFY_MODE=cluster bash labs/m2-k8s-gpu/verify_m2.sh
	@VERIFY_MODE=cluster bash labs/m4-gateway/verify_m4.sh
	@VERIFY_MODE=cluster bash labs/m5-observability-sre/verify_m5.sh
	@VERIFY_MODE=cluster bash labs/m6-capstone-siamshield/verify_capstone.sh

verify-all: verify-static ## รันชุดตรวจสอบอัตโนมัติทุกโมดูล (Alias ของ verify-static)

build-handbook: ## รวมไฟล์ทุกบทเป็นหนังสือฉบับสมบูรณ์ใน dist/FULL_MANUSCRIPT.md และตรวจสอบคุณภาพ Markdown
	@python3 scripts/build_manuscript.py
	@python3 scripts/build_manuscript.py --check
	@echo "[OK] Compiled handbook written and verified at dist/FULL_MANUSCRIPT.md"

clean-cache: ## ล้างไฟล์ชั่วคราวในโฟลเดอร์แคชจำลอง
	@rm -rf $(HOST_HF_CACHE)/*
	@echo "[OK] Cleaned $(HOST_HF_CACHE)"
