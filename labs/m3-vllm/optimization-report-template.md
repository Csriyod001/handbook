# รายงานผลการปรับจูน `vLLM` V1 Engine และการวิเคราะห์ Unit Economics (M3 Learner Report Template)

> **แบบฟอร์มส่งมอบประจำ Milestone M3 (DoD #3):** กรอกข้อมูลจากการทดสอบของคุณจริงลงในช่อง `[TODO: ...]` ด้านล่าง (สามารถศึกษาตัวอย่างการคำนวณได้ที่ [`examples/optimization-report-sample.md`](examples/optimization-report-sample.md))  
> **เกณฑ์ SLA เป้าหมาย:** ที่ Concurrency = 32 บน Config C ต้องได้ **TTFT p95 < 800 ms**, **ITL p95 < 30 ms**, และ **`vllm:num_preemptions_total == 0`**

---

## 1. ข้อมูลสภาพแวดล้อมและเวิร์กโหลดที่ใช้ทดสอบ (Test Environment & Workload Profile)

- **ฮาร์ดแวร์และ Path ที่รัน (`local-cpu` หรือ `cloud-gpu`):** `<TODO: ระบุ GPU SKU เช่น NVIDIA L4 24GB (ระบุ Usable VRAM จาก nvidia-smi) หรือ Local CPU>`
- **ค่าเช่าเครื่องต่อชั่วโมง ($C_{\text{hour}}$):** `<TODO: e.g. $0.85/hour>`
- **พาธแคชโมเดล (`HF_HOME`):** `<TODO: /cache/huggingface หรือ /tmp/ai-infra-hf-cache>`
- **โมเดล Config A/B vs Config C:** `<TODO: Qwen/Qwen2.5-7B-Instruct (BF16) vs Qwen/Qwen2.5-7B-Instruct-AWQ (awq_marlin)>`
- **เวิร์กโหลด (`run_benchmark_suite.sh`):** Shared Prefix `2,048` tokens, Suffix `128` tokens, Output `256` tokens, Prompts >= `max(20, conc * 4)`

---

## 2. ตารางเปรียบเทียบขนาด KV-Cache Pool (VRAM Allocation Breakdown)

| รายการหน่วยความจำบน GPU เป้าหมาย | Config A & B (`bfloat16`, util `0.85`) | Config C (`awq_marlin`, util `0.92`) | ผลต่างเชิงวิศวกรรม |
| :--- | :---: | :---: | :--- |
| **Total Usable VRAM Budget (Spec × util)** | `<TODO> GB` | `<TODO> GB` | `<TODO>` |
| **Model Weights ($V_{\text{weights}}$)** | `<TODO> GB` | `<TODO> GB` | `<TODO>` |
| **CUDA Context + Activations + CUDAGraphs** | `<TODO> GB` | `<TODO> GB` | `<TODO>` |
| **Available KV-Cache Block Pool ($V_{\text{KV\_Pool}}$)** | `<TODO> GB` | `<TODO> GB` | `<TODO: e.g. เพิ่มขึ้น >= 3x>` |
| **Max Concurrent KV Tokens (`56 KiB/token` สำหรับ 7B)** | `<TODO> tokens` | `<TODO> tokens` | `<TODO>` |

---

## 3. ตารางผลการทดสอบ Benchmark ที่ระดับ Concurrency 1, 8, 16, 32

| โครงแบบ (Configuration) | Concurrency | TTFT p95 (ms) | ITL p95 (ms) | Output Throughput (tok/s) | Peak `vllm:kv_cache_usage_perc` | Prefix Hit Rate (%) | `vllm:num_preemptions_total` | สถานะ SLA |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Config A (BF16, No APC)** | 1 | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` |
| **Config A (BF16, No APC)** | 16 | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` |
| **Config A (BF16, No APC)** | 32 | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` |
| **Config B (BF16 + APC)** | 32 | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` |
| **Config C (AWQ + APC + Tune)** | 1 | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO>` |
| **Config C (AWQ + APC + Tune)** | 32 | `<TODO: < 800>` | `<TODO: < 30>` | `<TODO>` | `<TODO>` | `<TODO>` | `<TODO: 0>` | `<TODO: PASS/FAIL>` |

---

## 4. การวิเคราะห์เศรษฐศาสตร์ต่อหน่วย (Unit Economics & Break-even Analysis)

- **สมการต้นทุน:** $\text{Cost}_{1\text{M}}(u) = \frac{C_{\text{hour}} \times 1,000,000}{T_{\text{peak}} \times 3,600 \times u}$
- **สมการจุดคุ้มทุนเทียบ Commercial API ($P_{\text{API}} = \$0.60 / 1\text{M}$):** $u_{\text{break-even}} = \frac{C_{\text{hour}} \times 1,000,000}{T_{\text{peak}} \times 3,600 \times P_{\text{API}}}$

| ระดับ Utilization ($u$) | Tokens / Hour (Config C) | Cost Config A (\$/1M) | Cost Config C (\$/1M) | Managed API (\$/1M) | ผลการวิเคราะห์ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **10%** | `<TODO>` | `<TODO>` | `<TODO>` | `$0.60` | `<TODO>` |
| **Break-even (`<TODO>%`)** | `<TODO>` | `<TODO>` | `$0.60` | `$0.60` | `จุดคุ้มทุน` |
| **50%** | `<TODO>` | `<TODO>` | `<TODO>` | `$0.60` | `<TODO>` |
| **80%** | `<TODO>` | `<TODO>` | `<TODO>` | `$0.60` | `<TODO>` |
| **100%** | `<TODO>` | `<TODO>` | `<TODO>` | `$0.60` | `<TODO>` |

---

## 5. ข้อสรุปและคำแนะนำสำหรับการนำไปใช้งานจริง (Production Recommendation)

1. `<TODO: สรุปการเลือกใช้ Config C และอธิบายผลของ Memory Bandwidth + PagedAttention + APC ต่อ TTFT/ITL>`
2. `<TODO: ระบุขีดจำกัดความจุต่อ 1 Pod และค่า Threshold ที่ส่งต่อให้บทที่ 4 (AI Gateway) และบทที่ 5 (KEDA)>`
