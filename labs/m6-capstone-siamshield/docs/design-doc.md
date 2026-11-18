# Architecture Design Document: `Project SiamShield AI` — Multi-Tier Enterprise AI Inference Platform

- **รหัสเอกสาร (Document ID):** `CAPSTONE-DOD-001`
- **สถานะ (Status):** Draft (ผู้เรียนกรอกผลคำนวณและการตัดสินใจให้ครบถ้วน แล้วยืนยันด้วย `bash verify_capstone.sh --target workspace`)
- **ผู้รับผิดชอบ (Author):** `<TODO: กรอกชื่อ/บทบาทวิศวกรของคุณ>`
- **คลัสเตอร์และเนมสเปซมาตรฐาน:** `ai-platform-local` (Namespace: `ai-platform`, `monitoring`, `keda`)

> **คำแนะนำสำหรับผู้เรียน:** เอกสารนี้เป็นแม่แบบเริ่มต้น (**Starter Template**) ให้คำนวณตัวเลข VRAM Sizing, Break-even Utilization และเปรียบเทียบ Trade-off ทั้ง 3 การตัดสินใจด้วยตนเองก่อน จากนั้นลบแท็ก `<TODO:...>` ทั้งหมดแล้วรัน `bash verify_capstone.sh --target workspace` (ดูตัวอย่างอ้างอิงเฉพาะหลังลงมือทำเสร็จแล้วได้ที่ `examples/design-doc-sample.md`)

---

## 1. Executive Summary & System Requirements

**`Project SiamShield AI`** คือแพลตฟอร์มกลางสำหรับให้บริการโมเดลภาษาขนาดใหญ่ (`Qwen/Qwen2.5-7B-Instruct-AWQ`) แก่ระบบงาน 2 ระดับความสำคัญของสถาบันการเงินไทย:
1. **`tier-realtime` (`realtime-team`, `Criticality: Critical`):** `TTFT p95 < 800 ms`, `ITL p95 < 30 ms`, `Availability >= 99.9%`
2. **`tier-batch` (`batch-team`, `Criticality: Sheddable`):** `Throughput >= 1,000 tokens/sec` (ยอมรับ `HTTP 429` และ Load Shedding ได้)
3. **PDPA & Hardware Constraints:** แปลงเลขบัตรประชาชน 13 หลัก (`<THAI_ID_REDACTED>`) และเบอร์โทรไทย (`<THAI_PHONE_REDACTED>`) ที่ Pre-call Layer 100% บนงบ 1–2× NVIDIA L4 GPUs (24GB VRAM, `$0.85/hr` ต่อใบ)

---

## 2. การคำนวณความจุหน่วยความจำการ์ดจอและเศรษฐศาสตร์ต่อหน่วย (VRAM Sizing & Unit Economics Math)

### 2.1 การคำนวณพื้นที่ VRAM บนการ์ด NVIDIA L4 (24.0 GB) สำหรับ `Qwen/Qwen2.5-7B-Instruct-AWQ`

พารามิเตอร์สถาปัตยกรรมของ `Qwen2.5-7B`: $L = 28, H_{kv} = 4, D_h = 128$:
1. **ขนาด KV-Cache ต่อ 1 โทเคน (`fp16/bf16` = 2 ไบต์):**
   $$\text{KV}_{\text{bytes/token}} = 2 \times L \times H_{kv} \times D_h \times 2 = \text{<TODO: คำนวณจำนวนไบต์/โทเคน และ KiB/token>}$$
2. **พื้นที่ KV-Cache Pool แบบ Modeled (`--gpu-memory-utilization 0.92`, AWQ Weights `4.42 GB`, Overhead `1.66 GB`):**
   - $V_{\text{KV\_Pool}} = \text{<TODO: คำนวณขนาดสุทธิ (GB)>}$
   - $N_{\text{max\_tokens}} = \frac{V_{\text{KV\_Pool}} \times 1024^3}{\text{KV}_{\text{bytes/token}}} \approx \text{<TODO: คำนวณจำนวน tokens (เป้าหมาย ~299,593)>}$

### 2.2 การคำนวณจุดคุ้มทุน (Break-Even Utilization Analysis)

กำหนด $C_{\text{hour}} = \$0.85/\text{hr}$, $T_{\text{peak}} = 1,450\text{ tokens/sec}$, ราคาอ้างอิง Managed API = $\$0.60 / 1\text{M tokens}$:
- ต้นทุนต่อ 1M โทเคนที่ Utilization $u$: $\text{Cost}_{1\text{M}}(u) = \text{<TODO: แสดงสมการและค่าคงที่ที่ u=1.0>}$
- จุดคุ้มทุน ($u_{\text{break-even}}$): $\text{<TODO: คำนวณเป็น % (เทียบกับ Managed API $0.60)>}$
- ต้นทุนที่ $u = 50\%$: $\text{<TODO: คำนวณ $/1M tokens และ % ที่ประหยัดกว่า>}$

---

## 3. ตารางเปรียบเทียบทางเลือกเชิงวิศวกรรมใน 3 การตัดสินใจหลัก (3 Core Architectural Decisions)

### Decision 1: กลยุทธ์การบีบอัดโมเดลและการจัดการแคช (`vLLM` V1 Engine Configuration)

| เกณฑ์การประเมิน | ทางเลือก 1A: `Qwen2.5-7B` BF16 (Baseline) | ทางเลือก 1B: External Managed LLM API | ทางเลือก 1C (ที่เลือก): `Qwen2.5-7B-Instruct-AWQ` + APC + Chunked Prefill |
| :--- | :---: | :---: | :---: |
| **ขนาด KV-Cache Pool บน L4** | `3.36 GB` | ไม่เปิดเผย | `<TODO: กรอกขนาด GB และจำนวน tokens>` |
| **TTFT p95 / ITL p95 (Concurrency 32)** | `<TODO: ค่า Baseline>` | `750–1,200 ms` | `<TODO: ค่าที่วัดได้/เป้าหมาย <800ms / <30ms>` |
| **ต้นทุนที่ Utilization 50%** | `<TODO: คำนวณราคา BF16>` | `$0.60 / 1M` | `<TODO: ราคา/1M และ Break-even %>` |
| **Data Sovereignty / PDPA** | ภายในองค์กร 100% | ส่งออกนอกเครือข่าย | `<TODO: สรุปความสอดคล้อง PDPA>` |

### Decision 2: สถาปัตยกรรมการแยกโหลด `tier-realtime` vs `tier-batch` และการคุ้มครองข้อมูล PDPA

| เกณฑ์การประเมิน | ทางเลือก 2A: Physical GPU Split | ทางเลือก 2B: K8s Service Round-Robin | ทางเลือก 2C (ที่เลือก): LiteLLM + PDPA Guardrail + K8s EPP |
| :--- | :---: | :---: | :---: |
| **HA Failover (`vllm-secondary-svc`)** | `<TODO: ข้อจำกัด>` | `<TODO: ข้อจำกัด>` | `<TODO: อธิบาย num_retries: 0 + stream_timeout: 3.0s>` |
| **Batch Isolation / Load Shedding** | `<TODO: ข้อเสีย utilization>` | `<TODO: ปัญหา Noisy Neighbor>` | `<TODO: อธิบาย RPM limit + EPP Sheddable>` |
| **PDPA Redaction Layer** | ไม่มีในตัว | ไม่มีในตัว | `<TODO: อธิบาย <THAI_ID_REDACTED> ก่อนลง Redis Cache>` |

### Decision 3: กลยุทธ์การขยายขนาดอัตโนมัติและการจัดการวงจรชีวิตพอด (Autoscaling & Pod Lifecycle)

| เกณฑ์การประเมิน | ทางเลือก 3A: CPU HPA + Cold Hub Download | ทางเลือก 3B: Bake Weights in Image | ทางเลือก 3C (ที่เลือก): KEDA + `hf-model-cache-pvc` + 60s Drain |
| :--- | :---: | :---: | :---: |
| **ความแม่นยำในการตรวจจับคอขวด** | `<TODO: เหตุผลที่ CPU HPA พลาด>` | `<TODO>` | `<TODO: อธิบาย vLLM waiting queue & KV-Cache trigger>` |
| **เวลา Scale-Out Ready** | `180–240+ s` | อิมเมจใหญ่ ~6GB | `<TODO: แยกค่า Mock Pod vs Cloud L4 GPU จาก /cache/huggingface>` |
| **Zero-Drop Scale-In** | `<TODO>` | `<TODO>` | `<TODO: อธิบาย preStop + terminationGracePeriodSeconds: 60>` |
