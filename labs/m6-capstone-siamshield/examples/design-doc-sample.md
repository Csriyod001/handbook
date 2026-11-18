# Architecture Design Document (Sample Reference): `Project SiamShield AI` — Multi-Tier Enterprise AI Inference Platform

- **รหัสเอกสาร (Document ID):** `CAPSTONE-DOD-001-SAMPLE`
- **สถานะ (Status):** Worked Reference Sample (เปรียบเทียบหลังทำ `docs/design-doc.md` ด้วยตนเอง)
- **ผู้รับผิดชอบ (Author):** Reference Solution — Senior AI Infrastructure Engineering Track
- **คลัสเตอร์และเนมสเปซมาตรฐาน:** `ai-platform-local` (Namespace: `ai-platform`, `monitoring`, `keda`)

---

## 1. Executive Summary & System Requirements

**`Project SiamShield AI`** คือแพลตฟอร์มกลางสำหรับให้บริการโมเดลภาษาขนาดใหญ่ (`Qwen/Qwen2.5-7B-Instruct-AWQ`) แก่ระบบงาน 2 ระดับความสำคัญของสถาบันการเงินไทย:
1. **`tier-realtime` (`sk-realtime-team`, `Criticality: Critical`):** ระบบผู้ช่วยวิเคราะห์ความเสี่ยงและแชตบอตบริการลูกค้าสด
   - **SLO:** `TTFT p95 < 800 ms`, `ITL p95 < 30 ms`, `Availability >= 99.9%`
2. **`tier-batch` (`sk-batch-team`, `Criticality: Sheddable`):** ระบบสรุปเอกสารกรมธรรม์และสัญญาจำนวนมากหลังบ้าน
   - **SLO:** `Throughput >= 1,000 tokens/sec`, ยอมรับการถูกจำกัดอัตรา (`HTTP 429`) เมื่อคลัสเตอร์ตึงมือ
3. **ข้อบังคับด้านกฎหมายและงบประมาณ (Hard Constraints):**
   - **PDPA Compliance:** ต้องคัดกรองเลขประจำตัวประชาชนไทย 13 หลัก (`<THAI_ID_REDACTED>`) และเบอร์โทรศัพท์มือถือไทย (`<THAI_PHONE_REDACTED>`) ที่ชั้น Pre-call 100%
   - **Hardware Envelope:** งบประมาณฮาร์ดแวร์ 1–2× NVIDIA L4 GPUs (24GB GDDR6 VRAM, `300 GB/s` Memory Bandwidth, `$0.85/hr` ต่อใบ) และรองรับการรันจำลองครบวงจรบนเครื่องวิศวกร RAM 16GB (`$0` Local Path)

---

## 2. การคำนวณความจุหน่วยความจำการ์ดจอและเศรษฐศาสตร์ต่อหน่วย (VRAM Sizing & Unit Economics Math)

### 2.1 การคำนวณพื้นที่ VRAM บนการ์ด NVIDIA L4 (24.0 GB) สำหรับ `Qwen/Qwen2.5-7B-Instruct-AWQ`

พารามิเตอร์สถาปัตยกรรมของโมเดล `Qwen2.5-7B`:
- จำนวนพารามิเตอร์ ($P$) = $7.62 \times 10^9$
- จำนวนเลเยอร์ ($L$) = $28$, จำนวน KV Heads ($H_{kv}$) = $4$ (Grouped-Query Attention), มิติต่อหัว ($D_h$) = $128$

1. **ขนาด KV-Cache ต่อ 1 โทเคน (เก็บใน `fp16/bf16` = 2 ไบต์):**
   $$\text{KV}_{\text{bytes/token}} = 2 \times L \times H_{kv} \times D_h \times 2 = 2 \times 28 \times 4 \times 128 \times 2 = 57,344\text{ Bytes} = \mathbf{56\text{ KiB/token}}$$

2. **การจัดสรรพื้นที่ VRAM แบบ Modeled Capacity Budget เมื่อตั้ง `--gpu-memory-utilization 0.92`:**
   - งบประมาณ VRAM ที่อนุญาตให้ `vLLM` ใช้งาน: $24.0\text{ GB} \times 0.92 = \mathbf{22.08\text{ GB}}$
   - ขนาด Model Weights ในรูปแบบ **AWQ 4-bit (`awq_marlin`)**: $\mathbf{4.42\text{ GB}}$ (ลดลงจาก `15.24 GB` ในรูปแบบ BF16)
   - พื้นที่ CUDA Context + Activation Buffer + CUDAGraphs: $\mathbf{1.66\text{ GB}}$
   - **พื้นที่สุทธิสำหรับ KV-Cache Block Pool ($V_{\text{KV\_Pool}}$):**
     $$V_{\text{KV\_Pool}} = 22.08 - 4.42 - 1.66 = \mathbf{16.00\text{ GB}}\text{ (เพิ่มขึ้น 4.76 เท่าเมื่อเทียบกับ 3.36 GB ใน BF16)}$$
   - **ความจุโทเคนสูงสุดใน KV-Cache Pool พร้อมกัน:**
     $$N_{\text{max\_tokens}} = \frac{16.00 \times 1024^3}{57,344} \approx \mathbf{299,593\text{ tokens}}\text{ (หรือ } 18,724\text{ บล็อก บล็อกละ 16 โทเคน)}$$

### 2.2 การคำนวณจุดคุ้มทุน (Break-Even Utilization Analysis)

กำหนดให้ต้นทุนเครื่อง Cloud L4 GPU $C_{\text{hour}} = \$0.85/\text{hr}$, อัตราการผลิตโทเคนที่ผ่านเกณฑ์ SLA ของโครงแบบ AWQ + APC คือ $T_{\text{peak}} = 1,450\text{ tokens/sec}$ ($5.22\text{M tokens/hr}$), และราคาอ้างอิงของ Managed API ภายนอกคือ $P_{\text{API}} = \$0.60 / 1\text{M tokens}$:

$$\text{Cost}_{1\text{M}}(u) = \frac{0.85 \times 1,000,000}{1,450 \times 3,600 \times u} = \frac{\$0.1628}{u}$$

จุดคุ้มทุน ($u_{\text{break-even}}$) ที่ทำให้การรันเองมีต้นทุนเท่ากับ Managed API ($\text{Cost}_{1\text{M}}(u) = \$0.60$):
$$u_{\text{break-even}} = \frac{0.1628}{0.60} = 0.2714 \approx \mathbf{27.1\%}$$

ที่ระดับการใช้งานเฉลี่ย $u = 50\%$ ต้นทุนต่อ 1 ล้านโทเคนของ `SiamShield AI` อยู่ที่ **$\$0.33 / 1\text{M tokens}$** (ประหยัดกว่าการใช้ Managed API ถึง **45.0%**)

---

## 3. ตารางเปรียบเทียบทางเลือกเชิงวิศวกรรมใน 3 การตัดสินใจหลัก (3 Core Architectural Decisions)

### Decision 1: กลยุทธ์การบีบอัดโมเดลและการจัดการแคช (`vLLM` V1 Engine Configuration)

| เกณฑ์การประเมิน | ทางเลือก 1A: `Qwen2.5-7B` BF16 (Baseline) | ทางเลือก 1B: External Managed LLM API | ทางเลือก 1C (ที่เลือก): **`Qwen2.5-7B-Instruct-AWQ` (`awq_marlin`) + APC + Chunked Prefill (`2048`)** |
| :--- | :---: | :---: | :---: |
| **ขนาด KV-Cache Pool บน L4 (24GB)** | `3.36 GB` (~62.9k tokens) | ไม่สามารถควบคุมได้ | **`16.00 GB` (~299.6k tokens — ใหญ่ขึ้น 4.76x)** |
| **TTFT p95 / ITL p95 ที่ Concurrency 32** | `6,120 ms` / `94.0 ms` (เกิด Preemption) | `750–1,200 ms` (ขึ้นกับเครือข่ายภายนอก) | **`640 ms` / `23.5 ms` (ผ่านเกณฑ์ SLA 100%)** |
| **ต้นทุนที่ Utilization 50% (`$/1M tok`)** | `$1.21 / 1M` (จุดคุ้มทุน 100.9% ที่ C=32, 390 tok/s; `$1.12 / 1M` / 93.7% ที่ C=16, 420 tok/s) | `$0.60 / 1M` | **`$0.33 / 1M` (จุดคุ้มทุนเพียง 27.1%)** |
| **อธิปไตยข้อมูล (Data Sovereignty / PDPA)** | ข้อมูลอยู่ภายในคลัสเตอร์องค์กร 100% | ข้อมูลต้องส่งออกนอกเครือข่ายองค์กร | **ข้อมูลอยู่ภายในคลัสเตอร์องค์กร 100%** |

---

### Decision 2: สถาปัตยกรรมการแยกโหลด `tier-realtime` vs `tier-batch` และการคุ้มครองข้อมูล PDPA

| เกณฑ์การประเมิน | ทางเลือก 2A: แยกการ์ดจอขาดจากกัน (1 L4 Realtime + 1 L4 Batch) | ทางเลือก 2B: แชร์พูลเดียวกันผ่าน K8s Service Round-Robin | ทางเลือก 2C (ที่เลือก): **`LiteLLM Proxy` Tier Shaper + Pre-Call PDPA Guardrail + K8s `EPP` Priority Shedding** |
| :--- | :---: | :---: | :---: |
| **ความพร้อมใช้งานเมื่อพอดหลักล่ม (HA)** | ไม่มี HA สำหรับ Realtime (ล่มทันที) | กระจายโหลดไปพอดที่ค้าง 50% | **สลับเส้นทางทันที (`num_retries: 0`) ใน `< 3.0s` (`stream_timeout`) ไปยัง `vllm-secondary-svc`** |
| **การป้องกัน Noisy Neighbor จากงาน Batch** | แยกขาดแต่ใช้ GPU ไม่คุ้มตอนกลางคืน | งาน Batch แย่งคิวจน Realtime ค้าง | **จำกัด RPM/TPM (`10 RPM`) ของ Batch + ตัดโหลด `Sheddable` ทันทีเมื่อ KV-Cache `> 85%`** |
| **การป้องกันเลขบัตรประชาชนไทย 13 หลักรั่วไหล** | ไม่มีในตัว ต้องให้แอปจัดการเอง | ไม่มีในตัว | **บังคับแปลงเป็น `<THAI_ID_REDACTED>` ที่ชั้น Pre-call ก่อนลง Redis Cache 100%** |

---

### Decision 3: กลยุทธ์การขยายขนาดอัตโนมัติและการจัดการวงจรชีวิตพอด (Autoscaling & Pod Lifecycle)

| เกณฑ์การประเมิน | ทางเลือก 3A: Kubernetes CPU/Memory HPA + โหลดโมเดลจากอินเทอร์เน็ต | ทางเลือก 3B: Bake โมเดล 4.4GB ลงใน Docker Image เดียว | ทางเลือก 3C (ที่เลือก): **`KEDA` (`num_requests_waiting` + `kv_cache_usage_perc`) + Shared `hf-model-cache-pvc` + 60s Graceful Drain** |
| :--- | :---: | :---: | :---: |
| **ความแม่นยำในการตรวจจับคอขวด LLM** | ล้มเหลว (CPU อยู่ที่ ~40% แม้คิวรอเต็ม) | ล้มเหลวถ้าใช้ CPU HPA | **แม่นยำ 100% (สเกลทันทีเมื่อคิวรอ `> 5` หรือ KV-Cache `> 0.80`)** |
| **เวลาบูตพอดใหม่ตอน Scale-Out** | `180–240+ วินาที` (ดาวน์โหลดซ้ำทุกครั้ง) | อิมเมจใหญ่ ~6 GB ดึงข้ามโหนดช้า | **`< 10 วินาที` (Mock Pod) / `~35–75 วินาที` (Cloud L4 GPU) จาก `/cache/huggingface`** |
| **คำขอสตรีมมิ่งหลุดตอน Scale-In** | หลุดทันทีเมื่อถูกส่ง `SIGKILL` | หลุดหากไม่ตั้งค่า Drain | **`0 คำขอหลุด` (`preStop: sleep 5` + `terminationGracePeriodSeconds: 60`)** |
