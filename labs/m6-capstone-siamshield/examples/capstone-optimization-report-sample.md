# รายงานผลการปรับจูนประสิทธิภาพแบบ 2 ระดับ (Sample Reference) ของ `Project SiamShield AI` (`CAPSTONE-DOD-003-SAMPLE`)

- **รหัสเอกสาร:** `CAPSTONE-DOD-003-SAMPLE`
- **สถานะ:** Worked Reference Sample (เปรียบเทียบหลังกรอก `reports/capstone-optimization-report.md` ด้วยตนเอง)
- **คลัสเตอร์และเนมสเปซ:** `ai-platform-local` (`ai-platform`)
- **โมเดลและฮาร์ดแวร์เป้าหมาย:** `Qwen/Qwen2.5-7B-Instruct-AWQ` บน 1–2× NVIDIA L4 GPUs (24GB VRAM, `300 GB/s`)

---

## 1. โจทย์และสมมติฐานการทดลอง (Baseline vs Hypothesis)

### 1.1 สภาพแวดล้อมตั้งต้น (Baseline: Unisolated BF16 Stack)
- รันโมเดล `Qwen/Qwen2.5-7B-Instruct` (`bfloat16`, `--gpu-memory-utilization 0.85`, `--no-enable-prefix-caching`)
- ทั้งทราฟฟิก `tier-realtime` (Concurrency 16) และ `tier-batch` (Concurrency 32) ยิงเข้า `vllm-primary-svc:8000` โดยตรงผ่าน Kubernetes Service แบบ Round-Robin ไร้ชั้นกรองโควตา ไร้ Redis Cache และใช้ CPU HPA

### 1.2 สมมติฐานการปรับจูน (Two-Tier Optimization Hypothesis)
- การเปลี่ยนเป็น **`Qwen/Qwen2.5-7B-Instruct-AWQ` (`--quantization awq_marlin`, `--gpu-memory-utilization 0.92`, `--enable-prefix-caching`, `--max-num-batched-tokens 2048`)** ร่วมกับการตั้งค่า **`LiteLLM Proxy`** (แยกโควตา `realtime-team` 100 RPM vs `batch-team` 10 RPM, เปิด Pre-call PDPA Redaction, เปิด Redis Exact Cache, ตั้ง `num_retries: 0` + `stream_timeout: 3.0s` Failover) และ **`K8s EPP` + `KEDA`** จะสามารถรักษาค่า `TTFT p95 < 800 ms` และ `ITL p95 < 30 ms` ของ `tier-realtime` ได้ 100% แม้เกิดพายุคำขอจาก `tier-batch`

---

## 2. ตารางผลการวัดค่าเปรียบเทียบ (Before vs After Measurement Table)

| ตัวชี้วัด (End-to-End Metric under Mixed Realtime + Batch Load) | Baseline: Unisolated BF16 Stack | Optimized: `SiamShield AI` Two-Tier Stack | เกณฑ์เป้าหมาย (Target SLO) | ผลการประเมิน |
| :--- | :---: | :---: | :---: | :---: |
| **KV-Cache Pool Capacity per L4 GPU (Modeled)** | `3.36 GB` (~62.9k tok) | **`16.00 GB` (~299.6k tok)** | `> 12.0 GB` | **PASS (+376%)** |
| **`tier-realtime` TTFT p95 (ms)** | `6,420 ms` | **`640.0 ms`** | `< 800 ms` | **PASS (-90.0%)** |
| **`tier-realtime` ITL p95 (ms)** | `96.5 ms` | **`23.5 ms`** | `< 30 ms` | **PASS (-75.6%)** |
| **`tier-realtime` Availability under Primary Hang** | `84.2%` | **`100.0%` (Failover < 3s)** | `>= 99.9%` | **PASS** |
| **Automatic Prefix Cache (APC) Hit Rate (%)** | `0.0%` | **`89.4%`** | `>= 70.0%` | **PASS** |
| **Gateway Redis Exact Cache Hit Rate (%)** | `0.0%` | **`25.0%` (`4.2 ms` latency)** | `>= 15.0%` | **PASS** |
| **Preemptions (`vllm:num_preemptions_total`)** | `52` (Thrashing) | **`0`** | `0` | **PASS** |
| **PDPA Thai 13-Digit ID Leakage Rate (%)** | `100.0%` | **`0.0%` (`<THAI_ID_REDACTED>`)** | `0.0%` | **PASS** |
| **KEDA Scale-Out Ready Time (Warm `HF_HOME=/cache/huggingface` PVC)** | `195.0 s` (Cold Hub) | **`8.5 s`** *(Mock Pod; Cloud L4 GPU ~45–75 s)* | `< 30.0 s (Mock) / < 90.0 s (GPU)` | **PASS** |
| **Unit Cost @ 50% Utilization (`$0.85/hr` L4)** | `$1.21 / 1M tok` | **`$0.33 / 1M tok` (Break-even 27.1%)** | `< $0.60 / 1M tok` | **PASS (-72.7%)** |

---

## 3. คำอธิบายกลไกเชิงวิศวกรรม (Engineering Mechanics Explanation)

1. **การขยาย KV-Cache Pool 4.76 เท่าด้วย AWQ 4-bit + `0.92` Memory Utilization:** ลดขนาดน้ำหนักโมเดลจาก `15.24 GB` ลงเหลือ `4.42 GB` คืนพื้นที่ VRAM ให้ PagedAttention จัดสรรบล็อกได้เกือบ 3 แสนโทเคน กำจัดอาการ Preemption Thrashing (`vllm:num_preemptions_total = 0`)
2. **การปกป้อง `tier-realtime` 3 ชั้น (Defense-in-Depth Traffic Shaping):**
   - ชั้นที่ 1: `LiteLLM Proxy` บล็อกคำขอส่วนเกินของ `batch-team` (`10 RPM`) ด้วย `HTTP 429`
   - ชั้นที่ 2: `Endpoint Picker (EPP)` สั่งตัดโหลด `Sheddable` (`tier-batch`) เมื่อ `vllm:kv_cache_usage_perc > 0.85`
   - ชั้นที่ 3: `vLLM` V1 Unified Chunked Prefill (`--max-num-batched-tokens 2048`) ป้องกันไม่ให้เอกสารยาวของงาน Batch บล็อกเฟส Decode ของงาน Realtime
