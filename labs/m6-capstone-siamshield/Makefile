# ==============================================================================
# Module 6 (M6 Capstone): Project SiamShield AI — Master Makefile (DoD #2)
# Connects IaC (M1), Helm/K8s (M2), vLLM V1 (M3), Gateway (M4), and KEDA/SRE (M5)
# ==============================================================================
SHELL := /bin/bash
CLUSTER_NAME := ai-platform-local
K8S_NAMESPACE := ai-platform
HOST_HF_CACHE := /tmp/ai-infra-hf-cache
VERIFY_MODE ?= static
VERIFY_TARGET ?= examples

.DEFAULT_GOAL := verify

.PHONY: help init-cache build-images create-secrets simulate deploy-core deploy-netpol deploy-crds deploy-k8s chaos-live verify verify-workspace

help: ## แสดงคำสั่งทั้งหมดของโปรเจกต์จบ Project SiamShield AI
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

init-cache: ## เตรียมโฟลเดอร์แคชสำหรับ HF_HOME (/tmp/ai-infra-hf-cache -> /cache/huggingface)
	@mkdir -p $(HOST_HF_CACHE)

build-images: ## สร้างและโหลดอิมเมจ mock-vllm-server:1.0.0 สำหรับโหมด Local kind
	docker build -t mock-vllm-server:1.0.0 -f ../m4-gateway/mock_vllm_server/Dockerfile ../m4-gateway
	kind load docker-image mock-vllm-server:1.0.0 --name $(CLUSTER_NAME)

create-secrets: ## สร้าง Kubernetes Secret litellm-secrets จากไฟล์ .env (อย่า hardcode ใน Git)
	@test -f ../m4-gateway/.env || (echo "Copy ../m4-gateway/.env.example to ../m4-gateway/.env first" && exit 1)
	kubectl create secret generic litellm-secrets -n $(K8S_NAMESPACE) --from-env-file=../m4-gateway/.env --dry-run=client -o yaml | kubectl apply -f -

simulate: init-cache ## รันเอ็นจินจำลอง Two-Tier Platform & Chaos Verification
	@python3 src/siamshield_simulator.py

deploy-core: init-cache ## ดีพลอย Core Stack (Zero-CRD: Mock vLLM, LiteLLM, Redis, Postgres)
	kubectl apply -f k8s/siamshield-platform.yaml

deploy-netpol: ## ดีพลอย Zero-Trust NetworkPolicies จาก M4
	kubectl apply -f ../m4-gateway/k8s/network-policies.yaml

deploy-crds: ## ดีพลอย CRD Stack (GAIE v1 InferencePool, llm-d InferenceObjective, KEDA ScaledObject)
	kubectl apply -f k8s/siamshield-crds.yaml

deploy-k8s: deploy-core deploy-netpol deploy-crds ## ดีพลอยสแต็ก SiamShield AI ทั้งหมดลงคลัสเตอร์ Kubernetes (ai-platform)

chaos-live: ## ยิง Live Chaos Test เข้าพอร์ต 8000/4000 (เพิ่ม --reset หลังจบ)
	@python3 ../m5-observability-sre/chaos/trigger_incident.py --live --dry-run

verify: init-cache ## รันสคริปต์ตรวจประเมิน (examples sample หรือ workspace ของผู้เรียน)
	@VERIFY_MODE=$(VERIFY_MODE) bash verify_capstone.sh --target $(VERIFY_TARGET)

verify-workspace: init-cache ## ตรวจคำตอบจริงของผู้เรียน (บังคับ zero <TODO> และผ่านเกณฑ์ SLA)
	@VERIFY_MODE=$(VERIFY_MODE) bash verify_capstone.sh --target workspace
