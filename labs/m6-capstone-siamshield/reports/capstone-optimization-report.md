# รายงานผลการปรับจูนประสิทธิภาพแบบ 2 ระดับของ `Project SiamShield AI` (Capstone Two-Tier Optimization Report — DoD #3)

- **รหัสเอกสาร:** `CAPSTONE-DOD-003`
- **คลัสเตอร์และเนมสเปซ:** `ai-platform-local` (`ai-platform`)
- **โมเดลและฮาร์ดแวร์เป้าหมาย:** `Qwen/Qwen2.5-7B-Instruct-AWQ` บน 1–2× NVIDIA L4 GPUs (24GB VRAM, `300 GB/s`)

> **คำแนะนำสำหรับผู้เรียน:** รันการจำลอง/วัดผลและเปรียบเทียบ Baseline BF16 กับ Optimized Two-Tier Stack จากนั้นกรอกค่าจริงของคุณลงในตารางด้านล่าง ลบแท็ก `<TODO:...>` ทั้งหมด แล้วรัน `bash verify_capstone.sh --target workspace` (ดูตัวอย่างหลังลองทำด้วยตนเองได้ที่ `examples/capstone-optimization-report-sample.md`)

---

## 1. โจทย์และสมมติฐานการทดลอง (Baseline vs Hypothesis)

### 1.1 สภาพแวดล้อมตั้งต้น (Baseline: Unisolated BF16 Stack)
- `<TODO: ระบุพารามิเตอร์ Baseline (model dtype, gpu-memory-utilization, การขาด isolation / cache / HPA)>`

### 1.2 สมมติฐานการปรับจูน (Two-Tier Optimization Hypothesis)
- `<TODO: ระบุสมมติฐานการเปลี่ยนเป็น AWQ 4-bit (awq_marlin), APC, Chunked Prefill, LiteLLM Tier + Pre-call PDPA Redaction (<THAI_ID_REDACTED>), EPP Sheddable และ KEDA>`

---

## 2. ตารางผลการวัดค่าเปรียบเทียบ (Before vs After Measurement Table)

| ตัวชี้วัด (End-to-End Metric under Mixed Realtime + Batch Load) | Baseline: Unisolated BF16 Stack | Optimized: `SiamShield AI` Two-Tier Stack | เกณฑ์เป้าหมาย (Target SLO) | ผลการประเมิน |
| :--- | :---: | :---: | :---: | :---: |
| **KV-Cache Pool Capacity per L4 GPU (Modeled)** | `<TODO>` | `<TODO: GB / tokens>` | `> 12.0 GB` | `<TODO: PASS/FAIL>` |
| **`tier-realtime` TTFT p95 (ms)** | `<TODO>` | `<TODO: ms>` | `< 800 ms` | `<TODO: PASS/FAIL>` |
| **`tier-realtime` ITL p95 (ms)** | `<TODO>` | `<TODO: ms>` | `< 30 ms` | `<TODO: PASS/FAIL>` |
| **`tier-realtime` Availability under Primary Hang** | `<TODO>` | `<TODO: %>` | `>= 99.9%` | `<TODO: PASS/FAIL>` |
| **Automatic Prefix Cache (APC) Hit Rate (%)** | `<TODO>` | `<TODO: %>` | `>= 70.0%` | `<TODO: PASS/FAIL>` |
| **Gateway Redis Exact Cache Hit Rate (%)** | `<TODO>` | `<TODO: %>` | `>= 15.0%` | `<TODO: PASS/FAIL>` |
| **Preemptions (`vllm:num_preemptions_total`)** | `<TODO>` | `<TODO: count>` | `0` | `<TODO: PASS/FAIL>` |
| **PDPA Thai 13-Digit ID Leakage Rate (%)** | `100.0%` | `<TODO: 0.0% (<THAI_ID_REDACTED>)>` | `0.0%` | `<TODO: PASS/FAIL>` |
| **KEDA Scale-Out Ready Time (Warm `/cache/huggingface` PVC)** | `<TODO: Cold Hub>` | `<TODO: แยกค่า Mock Pod vs Cloud L4 GPU>` | `< 30.0 s (Mock) / < 90.0 s (GPU)` | `<TODO: PASS/FAIL>` |
| **Unit Cost @ 50% Utilization (`$0.85/hr` L4)** | `<TODO>` | `<TODO: $/1M tok & Break-even %>` | `< $0.60 / 1M tok` | `<TODO: PASS/FAIL>` |

---

## 3. คำอธิบายกลไกเชิงวิศวกรรม (Engineering Mechanics Explanation)

1. `<TODO: อธิบายผลของ awq_marlin + --gpu-memory-utilization 0.92 ต่อการลด Preemption Thrashing>`
2. `<TODO: อธิบาย Defense-in-Depth 3 ชั้น (LiteLLM RPM + EPP Sheddable + Chunked Prefill)>`
3. `<TODO: อธิบายบทบาทของ Pre-call PDPA Masking (<THAI_ID_REDACTED>) ต่อ Cache Hit Rate และ Data Privacy>`
