# คู่มือการสอบป้องกันสถาปัตยกรรมระดับ Mid-Level: `Project SiamShield AI` (`CAPSTONE-DOD-005`)

เอกสารฉบับนี้รวบรวมแนวทางการตอบคำถามเชิงลึกสำหรับการสอบป้องกันโปรเจกต์จบ (**Capstone Architecture Defense**) ต่อคณะกรรมการวิศวกรอาวุโส (Principal AI Infrastructure Panel) โดยครอบคลุมทั้ง 5 มิติของระบบ

---

## 1. การป้องกันการตัดสินใจเรื่อง VRAM Sizing, Quantization และ `--max-model-len`

- **ประเด็นสำคัญที่ต้องอธิบายให้ชัดเจน:**
  - บนการ์ด NVIDIA L4 (24GB VRAM) การรัน `Qwen/Qwen2.5-7B-Instruct` แบบ `bfloat16` กินพื้นที่น้ำหนักโมเดลไปถึง `15.24 GB` ทำให้เหลือพื้นที่ KV-Cache Pool เพียง `3.36 GB` (ความจุประมาณ 62,914 โทเคนแบบ Modeled) ซึ่งเกิด Preemption Thrashing ทันทีที่ Concurrency = 32
  - การเปลี่ยนมาใช้ **`Qwen/Qwen2.5-7B-Instruct-AWQ` (`--quantization awq_marlin`)** ร่วมกับการเพิ่ม **`--gpu-memory-utilization 0.92`** ลดขนาดน้ำหนักโมเดลเหลือ `4.42 GB` และขยาย KV-Cache Pool แบบ Modeled เป็น **`16.00 GB` (~299,593 โทเคน หรือเพิ่มขึ้น 4.76 เท่า)** *(หมายเหตุ: บนเครื่องจริง GPU driver overhead อาจต่างกันเล็กน้อย หากปิด CUDAGraphs ด้วย `--enforce-eager` จะช่วยประหยัด VRAM เพิ่มได้อีกราว `0.5–1.0 GB`)*
  - ส่วนการตั้งค่า `--max-model-len 4096` ไม่ได้ทำให้ขนาดรวมของ KV-Cache Pool ใหญ่ขึ้น แต่ทำหน้าที่เป็น Admission Guardrail ป้องกันไม่ให้คำขอเดียวที่ยาวผิดปกติเข้ามาผูกขาดบล็อกใน Pool

---

## 2. การป้องกันการตัดสินใจเรื่อง Two-Tier Isolation (`tier-realtime` vs `tier-batch`)

- **ทำไมไม่แยกการ์ดจอ L4 ใบละ Tier แบบตายตัว (Hard Physical Split)?**
  - หากแยกขาดจากกัน เมื่อการ์ดของ `tier-realtime` ล่มหรือต้องอัปเดต ระบบหน้าบ้านจะล่มทันที (ไม่มี HA) และในเวลากลางคืนที่ลูกค้าใช้น้อย การ์ดใบนั้นจะว่างเปล่าทำให้ Fleet Utilization ต่ำกว่าจุดคุ้มทุน (`27.1%`)
  - สถาปัตยกรรม **Priority-Shaped Shared Pool + Warm Standby Failover** ใช้กลไกควบคุม 3 ชั้น:
    1. `LiteLLM Proxy` จำกัดโควตา RPM/TPM ของ `sk-batch-team` (`10 RPM`)
    2. `K8s Gateway API Inference Extension (EPP)` + `llm-d` กำหนด `InferenceObjective` ของ Realtime เป็น `priority: 100` (Critical) และของ Batch เป็น `priority: -10` (Sheddable) โดยตัดโหลด Batch ทันทีเมื่อ `vllm:kv_cache_usage_perc > 0.85`
    3. `vLLM` V1 Unified Chunked Prefill (`--max-num-batched-tokens 2048`) หั่น Prompt ยาวของงาน Batch ไม่ให้สร้าง Head-of-Line Blocking ต่อเฟส Decode ของงาน Realtime

---

## 3. การป้องกันการตัดสินใจเรื่อง PDPA PII Masking & Cache Synergy

- **ทำไมต้องวาง `PDPAPIIMasker` ไว้ที่ชั้น Pre-call ก่อน Cache Lookup?**
  1. ป้องกันไม่ให้เลขบัตรประชาชนไทย 13 หลักและเบอร์โทรศัพท์ถูกบันทึกลงใน Redis (`redis-svc:6379`) หรือ PostgreSQL (`postgres-svc:5432`) ตามมาตรฐาน **OWASP LLM02:2025 Sensitive Information Disclosure**
  2. ช่วยทำ **Prompt Normalization**: คำถามเดียวกันของลูกค้าคนละราย (ต่างกันแค่เลขบัตรประชาชน 13 หลัก) จะถูกแปลงเป็น `<THAI_ID_REDACTED>` เหมือนกันทุกตัวอักษร ทำให้เกิด **Redis Exact Cache Hit (`< 5 ms`)** และ **`vLLM` Automatic Prefix Cache Hit (`89.4%`)** สูงขึ้นอย่างมีนัยสำคัญ

---

## 4. การป้องกันการตัดสินใจเรื่อง KEDA Autoscaling & Zero-Downtime Pod Lifecycle

- **ทำไมใช้ KEDA แทน CPU/Memory HPA และ Shared PVC ช่วยลดเวลา Scale-Out ได้อย่างไร?**
  - CPU/Memory HPA ใช้ไม่ได้กับ `vLLM` เพราะ VRAM ถูกจองคงที่ 92% ตั้งแต่ตอนบูต และงานคำนวณรันบน GPU
  - เราจึงใช้ KEDA อ่านค่า `sum(vllm:num_requests_waiting{namespace="ai-platform",pod=~"vllm-primary-.*"}) > 5` และ `avg(vllm:kv_cache_usage_perc{namespace="ai-platform",pod=~"vllm-primary-.*"}) > 0.80` จาก Prometheus ทุก 15 วินาที (ตั้งค่า `num_retries: 0` เพื่อ Failover ไป `vllm-secondary-svc` ทันทีภายใน `stream_timeout: 3.0s`)
  - พอดใหม่เมานต์โวลุ่มกลาง `hf-model-cache-pvc` เข้าที่พาธไม่ใช้สิทธิ์ root **`HF_HOME=/cache/huggingface`** (`VLLM_CACHE_ROOT=/tmp/vllm-cache`, UID 10001) ทำให้ไม่ต้องดาวน์โหลดโมเดล ~4.4GB ซ้ำจาก Hugging Face Hub (ลดเวลาบูตจาก `180–240+ วินาที` เหลือ `< 10 วินาที` บน Mock Pod ใน Local `kind` และเหลือประมาณ **`~35–75 วินาที`** สำหรับการ Load Weights + PyTorch Warmup บน Cloud L4 GPU จริง) และตอน Scale-in มี `preStop: sleep 5` คู่กับ `terminationGracePeriodSeconds: 60` เพื่อรอให้สตรีมที่ค้างอยู่จบสมบูรณ์ 100%

---

## 5. การป้องกันการตัดสินใจเชิงเศรษฐศาสตร์ (Unit Economics & Break-Even Defense)

- ด้วยสมการ $\text{Cost}_{1\text{M}}(u) = \frac{C_{\text{hour}} \times 1,000,000}{T_{\text{peak}} \times 3,600 \times u}$ ที่ $C_{\text{hour}} = \$0.85/\text{hr}$ และ $T_{\text{peak}} = 1,450\text{ tokens/sec}$:
  - ต้นทุนที่ Utilization 100% คือ **`$0.16 / 1M tokens`**
  - ต้นทุนที่ Utilization 50% คือ **`$0.33 / 1M tokens`** (ประหยัดกว่า Managed API ที่คิด `$0.60 / 1M tokens` ถึง 45%)
  - จุดคุ้มทุน (**Break-even Utilization**) อยู่ที่เพียง **`27.1%`** เท่านั้น
