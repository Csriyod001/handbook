# Specification & Engineering Style Guide (Single Source of Truth)

เอกสารฉบับนี้คือ **Single Source of Truth (SSOT)** สำหรับการเขียนเนื้อหาทุกบทใน `chapters/` และการพัฒนาโค้ดปฏิบัติการทุกโมดูลใน `labs/` ของหนังสือคู่มือเชิงปฏิบัติการ **"Zero to Mid-Level-Capable AI Platform & AI Infrastructure Engineering Handbook (12-Week Competency-Based Roadmap)"**

ผู้เขียนและผู้พัฒนาโค้ดในทุกบท (Chapters 00–06) และทุกแล็บ (`labs/m1-foundations` ถึง `labs/m6-capstone-siamshield`) **ต้องยึดถือโครงสร้าง ชื่อตัวแปร พอร์ต ชื่อโมเดล ชื่อ Prometheus Metrics และกฎความถูกต้องทางวิศวกรรมในเอกสารนี้ตรงกัน 100%** ห้ามตั้งชื่อต่างกันข้ามบทโดยเด็ดขาด

---

## 1. โครงสร้างโฟลเดอร์มาตรฐานของ Repository (Canonical Directory Structure)

```text
ai-infra-handbook/
├── README.md                              # หน้าแรกของ GitHub Learning Roadmap & สารบัญหลัก
├── SPEC_AND_STYLE_GUIDE.md                # มาตรฐานกลาง (Single Source of Truth) ฉบับนี้
├── Makefile                               # คำสั่งตรวจสภาพแวดล้อม (check-env), รันแล็บ, และรวมเล่มหนังสือ
├── chapters/                              # เนื้อหาหนังสือเรียนเชิงปฏิบัติการ (Practical Engineering Handbook)
│   ├── 00-onboarding-and-setup.md         # บทที่ 0: การเตรียมเครื่อง Local 16GB RAM, เครื่องมือ & แนวคิด Hybrid Lab
│   ├── 01-foundations-containers-iac.md   # บทที่ 1 (W1-W2): Production Containers (uv), Bounded Queue, CI/CD & OpenTofu
│   ├── 02-kubernetes-gpu-orchestration.md # บทที่ 2 (W3-W4): K8s Probes, Helm, VRAM Math, Time-Slicing vs MIG & Fake GPU
│   ├── 03-vllm-serving-optimization.md    # บทที่ 3 (W5-W6): vLLM V1 Internals, PagedAttention, APC, Quantization & Benchmarking
│   ├── 04-ai-gateway-governance.md        # บทที่ 4 (W7-W8): LiteLLM Proxy, Virtual Keys, Redis Cache, Fallbacks, PDPA & K8s EPP
│   ├── 05-observability-autoscaling-sre.md# บทที่ 5 (W9-W10): Prometheus/Grafana, DCGM, vLLM V1 Metrics, KEDA & Incident Drill
│   └── 06-capstone-siamshield-ai.md       # บทที่ 6 (W11-W12): Capstone Design Doc, Two-Tier Platform, Chaos & Interview Defense
├── labs/                                  # โค้ดปฏิบัติการจริง, Starter Scaffolds, Manifests และสคริปต์ตรวจผลลัพธ์
│   ├── m1-foundations/                    # แล็บ Module 1 (Dockerfile, FastAPI Bounded Queue, OpenTofu, Trivy CI)
│   ├── m2-k8s-gpu/                        # แล็บ Module 2 (Helm Chart, Startup/Readiness Probes, VRAM Calculator, Time-slicing)
│   ├── m3-vllm/                           # แล็บ Module 3 (vLLM V1 Baseline vs Optimized Scripts, Benchmark Suite; symlinked as m3-vllm-serving)
│   ├── m4-gateway/                        # แล็บ Module 4 (LiteLLM Config, Mock vLLM Server + Dockerfile, PDPA Guardrail, Failover Tests; symlinked as m4-ai-gateway)
│   ├── m5-observability-sre/              # แล็บ Module 5 (Grafana Dashboard JSON, Alert Rules, KEDA ScaledObject, Chaos Script & docs/)
│   └── m6-capstone-siamshield/            # แล็บ Module 6 (End-to-End Project SiamShield AI: Multi-Tier Realtime + Batch Platform)
└── dist/                                  # ไฟล์หนังสือฉบับรวมเล่มสมบูรณ์ (Compiled Complete Handbook Artifacts)
```

---

## 2. โครงสร้างบังคับของทุกบทใน `chapters/` (Mandatory Chapter Template)

ทุกบทเรียนตั้งแต่บทที่ 1 ถึงบทที่ 6 (`chapters/01-*.md` ถึง `chapters/06-*.md`) **ต้องมีความยาวและความลึกระดับหนังสือเรียนเชิงวิศวกรรม (Textbook-Grade Engineering Depth)** ห้ามเขียนสรุปย่อแบบสไลด์หรือเขียนข้ามขั้นตอน และต้องประกอบด้วย **8 หัวข้อบังคับตามลำดับต่อไปนี้ครบทุกบท**:

### หัวข้อที่ 1: Chapter Overview & Learning Objectives (ภาพรวมและเป้าหมายเชิงสมรรถนะ)
- ระบุสัปดาห์ที่เรียน (Week), เวลาที่ใช้ (15 ชม./สัปดาห์: ทฤษฎี 4 ชม. + Lab/Optimization 9 ชม. + Documentation/Review 2 ชม.)
- ระบุความเชื่อมโยงกับ **Definition of Done (DoD ข้อที่ 1–5)** และ **Milestone Gate (Gate 1 / Gate 2 / Gate 3)**
- รายการ Learning Objectives ที่วัดผลได้จริง (Actionable & Verifiable)

### หัวข้อที่ 2: Architecture Diagram & System Context (แผนภาพสถาปัตยกรรม Mermaid)
- ต้องมีแผนภาพ **Mermaid Diagram** (`flowchart TD`, `flowchart LR`, หรือ `sequenceDiagram`) อย่างน้อย 1–2 แผนภาพที่แสดง Data Flow, Control Plane, ชื่อพอร์ต, ชื่อ Component และจุดคอขวดของระบบในบทนั้นอย่างชัดเจน
- กฎไวยากรณ์ Mermaid: ต้องใส่เครื่องหมายคำพูดครอบ Label ที่มีวงเล็บหรืออักขระพิเศษเสมอ เช่น `nodeA["vLLM V1 Pod (Port 8000)"]` และห้ามใช้แท็ก HTML ใน Label

### หัวข้อที่ 3: Deep-Dive Engineering Theory, Math & Trade-offs (ทฤษฎีเจาะลึก สูตรคำนวณ และตารางเปรียบเทียบ)
- อธิบายหลักการทำงานเชิงลึกโดยเน้น **"ทำไม (Why)"** และ **"ได้อะไรแลกกับเสียอะไร (Engineering Trade-offs)"**
- ต้องมี **สูตรคณิตศาสตร์วิศวกรรม (LaTeX Math)** พร้อม **ตัวอย่างการคำนวณด้วยตัวเลขจริงทีละบรรทัด (Worked Numerical Examples)** เช่น:
  - สูตรคำนวณขนาด Container Image / Queue Wait Time & Little's Law (บทที่ 1)
  - สูตรคำนวณ **GPU VRAM Sizing (Weights + GQA KV-Cache + Activation/CUDA Context Overhead)** และ Arithmetic Intensity (บทที่ 2)
  - สูตรคำนวณ **KV-Cache Block Allocation, Token Budget (`max_num_batched_tokens`), Throughput และ Unit Economics (Cost per 1M Tokens)** (บทที่ 3)
  - สูตรคำนวณ **Cache Hit Savings, Retry Amplification Factor และ Tail-Latency Hedging** (บทที่ 4)
  - สูตร **PromQL Histograms (`histogram_quantile`), KEDA Scaling Thresholds และ Error Budget Burn Rate** (บทที่ 5)
  - สูตร **Multi-Tier Latency Budget Breakdown & Capacity Planning** (บทที่ 6)
- ต้องมี **ตารางเปรียบเทียบทางเลือก (Trade-off Matrix)** อย่างน้อย 1 ตารางในทุกบท

### หัวข้อที่ 4: Step-by-Step Hands-On Lab (แล็บปฏิบัติการแยก 2 เส้นทางชัดเจน)
- ปูพื้นด้วย **Business Scenario & Pain Point** และ **Engineering Constraints (SLOs, Budget, Security)**
- แยกขั้นตอนคำสั่ง (พร้อมบล็อกโค้ดที่คัดลอกไปรันได้จริง) ออกเป็น 2 เส้นทางอย่างชัดเจน:
  1. **`No-GPU Local Path ($0 — 16GB RAM Safe)`**: เส้นทางหลักสำหรับทำบนเครื่องคอมพิวเตอร์ส่วนตัว (Linux/WSL2/macOS) โดยใช้ `kind`, `fake-gpu-operator`, `Qwen/Qwen2.5-0.5B-Instruct` (เมื่อรัน `vllm-cpu` 1 Pod) หรือ **Lightweight FastAPI Mock vLLM Streaming Server (<80MB RAM/Pod)** เมื่อทดสอบ Multi-replica, Gateway Failover และ KEDA Autoscaling
  2. **`Cloud L4 GPU Path (~$0.60–$0.80/hr)`**: เส้นทางสำหรับรันทดสอบประสิทธิภาพจริงบนการ์ด **NVIDIA L4 (24GB VRAM)** ด้วยโมเดล `Qwen/Qwen2.5-7B-Instruct` (BF16 vs AWQ/FP8) พร้อมคำสั่ง `tofu destroy` / ปิดอินสแตนซ์ทันทีเมื่อจบแล็บเพื่อคุมงบรวมทั้งคอร์สไม่เกิน \$10

### หัวข้อที่ 5: Failure Injection & Chaos Engineering Drill (การจำลองความล้มเหลวและการกู้คืน)
- จำลองสถานการณ์พังจริง (เช่น Security Scan Block, Read-only RootFS Crash, Probe Misconfiguration `CrashLoopBackOff`, KV-Cache Preemption Thrashing, Primary Backend Blackhole/Latency Spike, PII Leak Attempt)
- แสดงอาการที่เกิดขึ้นจริงใน Log / Metrics และขั้นตอนการแก้ไขเชิงวิศวกรรม

### หัวข้อที่ 6: Measurable Optimization Exercise (โจทย์ปรับจูนประสิทธิภาพ 5 ขั้นตอน)
ต้องเขียนครบทั้ง 5 ขั้นตอนอย่างเป็นวิทยาศาสตร์:
1. **Baseline:** การตั้งค่าเริ่มต้นที่ยังไม่ได้จูน พร้อมวิธีวัดผล
2. **Hypothesis:** สมมติฐานเชิงวิศวกรรมที่ระบุตัวแปรต้น ตัวแปรตาม และเป้าหมายตัวเลขที่คาดหวัง
3. **Fix:** การลงมือปรับโค้ด/พารามิเตอร์ทีละขั้น
4. **Measure:** ตารางเปรียบเทียบตัวเลข **Before vs After** ที่ชัดเจน (เช่น Image Size, p50/p95/p99 TTFT, p50/p95/p99 ITL, Tokens/sec, KV-Cache Usage %, Error Rate %, Cost per 1M Tokens)
5. **Explain:** คำอธิบายเชิงกลไกภายใน (Under-the-hood mechanics) ว่าทำไมตัวเลขจึงดีขึ้นตามนั้น

### หัวข้อที่ 7: Architecture Decision Record (ADR) & Engineering Artifacts
- บันทึกเหตุผลการตัดสินใจทางสถาปัตยกรรม (ADRs), สัญญาการส่งมอบข้ามบท (Handoff Contract), หรือเอกสาร SRE / Design Doc ของโมดูลนั้นๆ

### หัวข้อที่ 8: Mid-Level Interview Trade-Off Questions & Model Answers (คำถามสัมภาษณ์พร้อมเฉลยละเอียด)
- มีคำถามสัมภาษณ์เชิงลึก **4–5 ข้อต่อบท** (รวม **28 ข้อ** ทั้งเล่ม)
- **บังคับ:** ทุกข้อต้องใช้หัวข้อ `#### เฉลยแนวทางการตอบระดับ Strong Mid-Level (Model Answer)` ที่อธิบายทั้งหลักการ เหตุผลเชิงตัวเลข ข้อดี-ข้อเสีย และตัวอย่างการแก้ปัญหาหน้างานจริง (ไม่ใช่มีแต่คำถามทิ้งไว้)

### ส่วนปิดท้ายบท: Automated Verification, Deliverables, Pass Criteria & Curated Resources
- รายการไฟล์ Deliverable ที่ต้องมีในโฟลเดอร์ `labs/mX-...`
- วิธีรันสคริปต์ตรวจสอบผลลัพธ์อัตโนมัติ (`bash labs/mX-.../verify_*.sh`)
- Checklist เกณฑ์ผ่านประจำบท (`Pass Criteria`) และแหล่งเรียนรู้ทางการ (`Curated Verified Resources`) ประจำบท

---

## 3. ตารางตัวแปรกลางที่ใช้ร่วมกันทั้งเล่ม (Canonical Shared Variables & Naming Conventions)

ทุกบทและทุกไฟล์คอนฟิกใน `labs/` ต้องใช้ค่าตัวแปรกลางตามตารางนี้ตรงกัน 100%:

### 3.1 โครงสร้างคลัสเตอร์, Namespace และ Storage (`Kubernetes & Kind`)
| หมวดหมู่ | ชื่อตัวแปร / Resource | ค่ามาตรฐาน (Canonical Value) | หมายเหตุการใช้งาน |
| :--- | :--- | :--- | :--- |
| **Kind Cluster Name** | `CLUSTER_NAME` | `ai-platform-local` | สร้างด้วย `kind create cluster --name ai-platform-local` |
| **Primary Namespace** | `K8S_NAMESPACE` | `ai-platform` | Namespace หลักสำหรับ Deploy AI Gateway, vLLM และ App |
| **Monitoring Namespace** | `MON_NAMESPACE` | `monitoring` | สำหรับ `kube-prometheus-stack`, Grafana และ DCGM Exporter |
| **GPU Operator Namespace** | `GPU_OPERATOR_NS` | `gpu-operator` | สำหรับ `fake-gpu-operator` (Local) หรือ NVIDIA GPU Operator |
| **KEDA Namespace** | `KEDA_NAMESPACE` | `keda` | สำหรับติดตั้ง KEDA Operator |
| **Host Model Cache Dir** | `HOST_HF_CACHE` | `/tmp/ai-infra-hf-cache` | ผูกเข้า Kind Worker ผ่าน `extraMounts` เพื่อไม่ให้โหลดโมเดลซ้ำ |
| **Container Mount Path** | `HF_HOME` | `/cache/huggingface` | Environment variable `HF_HOME=/cache/huggingface` (หลีกเลี่ยง `/root` ที่ติดสิทธิ์ `0700 root:root` ใน Non-root container อย่าง `vllm/vllm-openai`) คู่กับ `VLLM_CACHE_ROOT=/tmp/vllm-cache` |
| **K8s PVC Name & Storage** | `MODEL_CACHE_PVC` | `hf-model-cache-pvc` | `ReadWriteOnce` (`local-path`/Block disk) สำหรับ Single-Node VM/Kind และ `ReadWriteMany` (`NFS`/`EFS`/`Filestore`) สำหรับ Multi-Node KEDA Autoscale (OpenTofu M1 สร้างไว้ให้ Local Kind; Helm `modelCache.createPvc` สลับเปิด-ปิดได้) |

### 3.2 มาตรฐานพอร์ตและชื่อ Service (Ports & Service Names)
| บริการ (Component) | Kubernetes Service Name | Container Port | Local Host Port-Forward | Health / Metrics Endpoints |
| :--- | :--- | :--- | :--- | :--- |
| **AI Inference Wrapper (M1–M2)** | `ai-inference-svc` (`ai-inference-service:1.0.0`) | `8000` | `localhost:8000` | `/healthz`, `/readyz`, `/health`, `/metrics` |
| **vLLM / Mock vLLM Primary (M3–M6)** | `vllm-primary-svc` (`mock-vllm-server:1.0.0` สำหรับ Local) | `8000` | `localhost:8000` | `/health`, `/healthz`, `/readyz`, `/v1/models`, `/v1/chat/completions`, `/metrics` |
| **vLLM / Mock vLLM Secondary (M4, M6)** | `vllm-secondary-svc` (`mock-vllm-server:1.0.0` สำหรับ Local) | `8000` | `localhost:8001` | `/health`, `/healthz`, `/readyz`, `/v1/models`, `/v1/chat/completions`, `/metrics` |
| **LiteLLM AI Gateway** | `litellm-gateway-svc` | `4000` | `localhost:4000` | `/health/liveliness`, `/health/readiness`, `/v1/chat/completions`, `/metrics` |
| **Redis (Cache & Rate Limit)** | `redis-svc` | `6379` | `localhost:6379` | `PING` |
| **PostgreSQL (LiteLLM DB)** | `postgres-svc` | `5432` | `localhost:5432` | `pg_isready` |
| **Prometheus Server** | `prometheus-operated` | `9090` | `localhost:9090` | `/-/healthy`, `/api/v1/query` |
| **Grafana Dashboard** | `monitoring-grafana` | `3000` (K8s svc `80`) | `localhost:3000` | `/api/health` |
| **DCGM Exporter (Real/Mock)** | `dcgm-exporter-svc` | `9400` | `localhost:9400` | `/metrics` |

### 3.3 มาตรฐานโมเดลที่ใช้ในแล็บ (Canonical Model Identifiers)
| บริบทการใช้งาน | ชื่อโมเดลมาตรฐาน (Hugging Face ID) | การตั้งค่าหน่วยความจำบังคับ | เหตุผลทางวิศวกรรม |
| :--- | :--- | :--- | :--- |
| **Local CPU Path (Single Pod)** | `Qwen/Qwen2.5-0.5B-Instruct` | `VLLM_CPU_KVCACHE_SPACE=1`, `--max-model-len 2048`, `--dtype bfloat16` | กิน RAM < 2.5 GB ต่อ Pod ป้องกันเครื่องผู้เรียนที่มี RAM 16GB ค้าง (OOM) |
| **Local Multi-Pod / Chaos Path** | `mock-qwen2.5-7b` (ผ่าน `mock_vllm_server`) | ใช้ RAM < 80 MB ต่อ Pod | จำลอง Streaming TTFT/ITL และ `/metrics` ของ vLLM V1 สำหรับซ้อม Gateway/KEDA บนเครื่อง 16GB |
| **Cloud GPU Baseline (L4 24GB)** | `Qwen/Qwen2.5-7B-Instruct` | `--dtype bfloat16`, `--gpu-memory-utilization 0.85`, `--max-model-len 8192`, `--no-enable-prefix-caching` | ใช้เป็น Baseline (Weights ~15.2 GB) เพื่อแสดงอาการ KV-Cache ตึงเมื่อ Concurrency สูง |
| **Cloud GPU Optimized (L4 24GB)** | `Qwen/Qwen2.5-7B-Instruct-AWQ` *(หรือ FP8)* | `--quantization awq_marlin` (หรือ `fp8`), `--gpu-memory-utilization 0.92`, `--max-model-len 4096`, `--max-num-batched-tokens 2048` | ลด Weights เหลือ ~4.5 GB (AWQ) ขยายกองกลาง KV-Cache >3 เท่า เปิด APC (ค่าเริ่มต้น V1) |
| **Cloud GPU Time-Slicing (4 Pods)** | `Qwen/Qwen2.5-0.5B-Instruct` | `--gpu-memory-utilization 0.20 --enforce-eager` | ปิด CUDA Graph (`--enforce-eager`) เพื่อประหยัด VRAM overhead ต่อโปรเซสเมื่อรัน 4 Pods บนการ์ดใบเดียว |
| **VRAM Math Worked Example** | `meta-llama/Llama-3.1-8B-Instruct` | $P=8\text{B}, L=32, H_{\text{kv}}=8, d_{\text{head}}=128$ (128 KiB/token ใน FP16) | ใช้เป็นโจทย์มาตรฐานสำหรับคำนวณ GQA KV-Cache ด้วยมือและใน `vram_calculator.py` |

### 3.4 มาตรฐานชื่อ Prometheus Metrics (vLLM V1 Engine & NVIDIA DCGM)
> **ข้อควรระวังสูงสุด:** ห้ามใช้ชื่อ Metric เก่าของ vLLM V0 ที่เลิกใช้แล้ว หรือเขียนชื่อ Counter โดยตกคำว่า `_total`

| ชื่อ Metric มาตรฐาน (vLLM V1 / DCGM) | ประเภท (Type) | ความหมายและสูตร PromQL มาตรฐานที่ใช้ในเล่ม |
| :--- | :--- | :--- |
| `vllm:kv_cache_usage_perc` | `Gauge` (0.0–1.0) | สัดส่วนการใช้งาน KV-Cache Block Pool บน GPU (`1.0` = เต็ม 100%) *(หมายเหตุ: ใน V0 เดิมเคยใช้ชื่อ `vllm:gpu_cache_usage_perc`)* |
| `vllm:num_requests_running` | `Gauge` | จำนวนคำขอที่กำลังประมวลผลอยู่ใน Batch ปัจจุบัน |
| `vllm:num_requests_waiting` | `Gauge` | จำนวนคำขอที่ติดคิวรอ (Waiting queue depth) ใช้ผูกกับ KEDA Autoscaler |
| `vllm:prefix_cache_hits_total` | `Counter` (Tokens) | จำนวน Tokens สะสมที่ได้ใช้ซ้ำจาก Automatic Prefix Cache (APC) |
| `vllm:prefix_cache_queries_total` | `Counter` (Tokens) | จำนวน Tokens สะสมทั้งหมดที่ตรวจสอบผ่าน APC<br>**PromQL Hit Rate:** `rate(vllm:prefix_cache_hits_total[5m]) / rate(vllm:prefix_cache_queries_total[5m])` |
| `vllm:num_preemptions_total` | `Counter` | จำนวนครั้งสะสมที่คำขอถูกถอดออกจาก Batch (`RECOMPUTE`) เพราะ KV-Cache เต็ม |
| `vllm:time_to_first_token_seconds_bucket` | `Histogram` | ใช้คำนวณ **p95 TTFT:** `histogram_quantile(0.95, sum(rate(vllm:time_to_first_token_seconds_bucket[5m])) by (le))` |
| `vllm:inter_token_latency_seconds_bucket` | `Histogram` | ใช้คำนวณ **p95 ITL:** `histogram_quantile(0.95, sum(rate(vllm:inter_token_latency_seconds_bucket[5m])) by (le)) or histogram_quantile(0.95, sum(rate(vllm:time_per_output_token_seconds_bucket[5m])) by (le))` *(Metric หลักของ `vLLM` V1 `>= v0.8`; คงชื่อ V0 `time_per_output_token_seconds_bucket` เป็น `or` fallback)* |
| `vllm:generation_tokens_total` | `Counter` | จำนวน Output Tokens สะสม ใช้คำนวณ Throughput: `sum(rate(vllm:generation_tokens_total[1m]))` |
| `DCGM_FI_DEV_FB_USED` | `Gauge` (MiB) | พื้นที่หน่วยความจำการ์ดจอ (VRAM Framebuffer) ที่ถูกใช้งานจริง |
| `DCGM_FI_DEV_GPU_UTIL` | `Gauge` (0–100%) | เปอร์เซ็นต์เวลาที่มี Kernel รันบน GPU *(คำเตือน: ไม่สะท้อนความอิ่มตัวจริงของ Batch)* |
| `DCGM_FI_PROF_SM_ACTIVE` | `Gauge` (0.0–1.0) | สัดส่วนที่ Streaming Multiprocessors ทำงานจริง (ใช้วิเคราะห์ Compute-bound) |
| `DCGM_FI_PROF_DRAM_ACTIVE` | `Gauge` (0.0–1.0) | สัดส่วนการใช้แบนด์วิดท์หน่วยความจำการ์ดจอ (ใช้วิเคราะห์ Memory-bandwidth-bound ช่วง Decode) |

---

## 4. กฎเหล็กความถูกต้องทางเทคนิค 9 ข้อจาก Independent Review (Mandatory Engineering Guardrails)

ในการเขียนเนื้อหาบทที่ 1–6 และโค้ดแล็บทุกไฟล์ ผู้เขียนต้องตรวจสอบให้ผ่านกฎเหล็ก 9 ข้อต่อไปนี้เสมอ:

1. **พฤติกรรมเริ่มต้นของ `vLLM` V1 Engine & สาเหตุของการขยาย KV-Cache:**
   - ใน `vLLM` V1 ทั้ง **Automatic Prefix Caching (`--enable-prefix-caching`)** และ **Unified Chunked Prefill** ถูกเปิดใช้งานเป็นค่าเริ่มต้น (Enabled by default) ดังนั้นการทดสอบ Baseline ที่ต้องการจำลองระบบไร้แคชต้องใส่แฟล็ก `--no-enable-prefix-caching` อย่างชัดเจน
   - ห้ามเขียนว่าการลด `--max-model-len` หรือการเปิด Chunked Prefill ทำให้กองกลาง KV-Cache ใหญ่ขึ้น 3 เท่า! สิ่งที่ทำให้กองกลาง KV-Cache บนการ์ด 24GB ขยายตัว >3 เท่าคือ **Quantization (ลดขนาด Model Weights จาก ~15.2 GB ใน BF16 ลงเหลือ ~4.5 GB ใน AWQ หรือ ~8 GB ใน FP8) ร่วมกับการเพิ่ม `--gpu-memory-utilization` (0.85 → 0.92)** ส่วนการลด `--max-model-len 4096` มีหน้าที่ช่วยให้ผ่าน Startup validation บน VRAM จำกัด และป้องกันคำขอยาวเดี่ยวๆ ผูกขาด KV-Cache
2. **ชื่อ Metric ของ `vLLM` V1 และการยกเลิก `SWAP` Preemption Mode:**
   - ต้องใช้ชื่อ Counter `vllm:prefix_cache_hits_total` และ `vllm:prefix_cache_queries_total` เสมอ
   - ต้องอธิบายให้ชัดเจนว่า `vLLM` V1 ยกเลิกโหมด `SWAP` (การย้ายบล็อก KV-Cache ข้ามสาย PCIe ลง CPU RAM) แล้วใช้โหมด `RECOMPUTE` เป็นหลัก เพราะการส่งข้อมูลข้ามคอขวด PCIe ช้ากว่าการคำนวณ Prefill ใหม่ด้วย Chunked Prefill + Prefix Cache
3. **การป้องกันเครื่อง Local 16GB RAM ค้าง (OOM Protection Strategy):**
   - ห้ามสั่งรัน `vllm-cpu` หลาย Pods พร้อมกับ Prometheus/Postgres/Redis บนเครื่อง 16GB RAM โดยเด็ดขาด
   - เมื่อรัน `vllm-cpu` จริงบนเครื่อง Local ให้รันเพียง **1 Pod** ด้วยโมเดล `Qwen/Qwen2.5-0.5B-Instruct` (`VLLM_CPU_KVCACHE_SPACE=1`)
   - เมื่อต้องการทดสอบ Multi-replica Routing, Failover, Rate Limit และ KEDA Autoscaling ในบทที่ 4–6 ให้ใช้ **Lightweight FastAPI Mock vLLM Streaming Server** ที่กิน RAM < 80 MB ต่อ Pod เป็นค่าเริ่มต้นสำหรับ Local Path
4. **ความแตกต่างของ `fake-gpu-operator`, โหมดเช่า Cloud GPU และ `--enforce-eager`:**
   - ระบุให้ชัดว่า Run:ai `fake-gpu-operator` จำลองจำนวน GPU บน `kind` ผ่าน Topology/Node Labels ของตัวเอง ในขณะที่ไฟล์ ConfigMap `time-slicing` ของ NVIDIA ใช้กับ `nvidia-device-plugin` จริง
   - แยกแยะชัดเจนว่าการเช่า GPU แบบ Container (เช่น RunPod Pod / Modal) เหมาะกับงานรัน `vLLM` เดี่ยวๆ ในบทที่ 3 แต่ถ้าจะติดตั้ง `k3s` + NVIDIA Device Plugin ในบทที่ 2 ต้องเช่าแบบ **Full GPU VM** (เช่น GCP/AWS Spot L4 VM หรือ Vast.ai VM mode)
   - เมื่อรัน `vLLM` หลายโปรเซสบนการ์ดจอใบเดียวกันด้วย Time-Slicing ต้องใส่แฟล็ก `--enforce-eager` เพื่อปิดการจองหน่วยความจำของ CUDA Graphs ต่อโปรเซส
5. **การคุมภาระงานด้วย Guided Starter Scaffolds และตัด Cloud Remote State ที่ไม่จำเป็น:**
   - ในบทที่ 1–2 ให้ใช้ Local State สำหรับ OpenTofu (ไม่ต้องเสียเวลาตั้ง S3/DynamoDB State Locking) และมีโครงสร้างโค้ดต้นแบบใน `labs/` เพื่อให้ผู้เรียนโฟกัสกับการเขียนส่วนสำคัญของ AI Infrastructure ภายในเวลา 15 ชม./สัปดาห์
6. **ความครบถ้วนของบทที่ 6 (Capstone Project SiamShield AI):**
   - บทที่ 6 ต้องมีครบทั้ง 8 หัวข้อตามเทมเพลตมาตรฐานของหนังสือเหมือนบทที่ 1–5 ทุกประการ (รวมถึงทฤษฎีการแยกโหลด `tier-realtime` vs `tier-batch`, โจทย์ Optimization 5 ขั้นตอน, และคำถามสัมภาษณ์ป้องกันโปรเจกต์จบ 5 ข้อพร้อมเฉลย)
7. **ความถูกต้องของลิงก์แหล่งเรียนรู้ (Curated Verified Resources):**
   - แยกหมวดหมู่แหล่งเรียนรู้แต่ละบทให้ชัดเจน ใช้ URL ทางการที่ตรวจสอบแล้ว (เช่น `https://docs.astral.sh/uv/guides/integration/docker/`, `https://docs.nvidia.com/aiperf/`, `https://github.com/run-ai/fake-gpu-operator`)
8. **การผูก Volume Cache (`HF_HOME`) จริง vs ขอบเขตของ OpenTelemetry:**
   - ทุก Kubernetes Deployment/Helm Chart ของโมเดลในบทที่ 2, 3, 5, 6 ต้องมีการผูก Volume สำหรับ `HF_HOME=/cache/huggingface` (และตั้ง `VLLM_CACHE_ROOT=/tmp/vllm-cache`) เพื่อป้องกันการดาวน์โหลดโมเดลซ้ำตอน Pod รีสตาร์ทหรือ Autoscale และใช้งานร่วมกับ Non-root `UID 10001` ได้โดยตรง
   - สำหรับ OpenTelemetry GenAI Semantic Conventions ให้สอนในระดับโครงสร้างมาตรฐานของ Span/Metric attributes และการผูกผ่าน LiteLLM callback โดยไม่ต้องติดตั้ง Jaeger/Tempo แยกต่างหากบนคลัสเตอร์ Local 16GB
9. **มาตรฐานภาษา รูปแบบสมการ และตัวอย่างคำนวณจริง:**
   - ใช้ภาษาไทยที่สละสลวยและเป็นมืออาชีพ คงศัพท์เทคนิคเป็นภาษาอังกฤษ ตรวจสอบไม่ให้มีอักษรผิดภาษา และทุกสมการคณิตศาสตร์ต้องมีตัวอย่างแทนค่าตัวเลขจริงกำกับเสมอ
10. **ความซื่อสัตย์ระหว่าง Mock Benchmark กับ Production GPU SLA:**
   - ห้ามนำตัวเลขความเร็วของ Lightweight Mock Pod (`<80MB` RAM, บูตใน `8–10 วินาที`, failover `~60 ms`) ไปกล่าวอ้างเป็นความเร็วของ Production `vLLM` GPU Pod หรือ Real LiteLLM Gateway; ใน Production จริงการบูต GPU Pod จาก Shared PVC (`HF_HOME=/cache/huggingface`) ใช้เวลา ~`35–75 วินาที` (เทียบกับ `180–240+ วินาที` เมื่อต้องดาวน์โหลดใหม่) และการทำ Primary-to-Secondary Failover ใช้เวลา ~`3.0–3.5 วินาที` ตามค่า `stream_timeout` (โดยต้องตั้ง `num_retries: 0`)
   - แยก **Starter Templates** ออกจาก **Worked Reference Examples (`examples/`)** เพื่อไม่ให้ผู้เรียนคัดลอกคำตอบล่วงหน้าโดยไม่ได้ลงมือทดลองและวัดผลจริง
