# ตัวอย่างเฉลย: รายงานผลการปรับจูน `vLLM` V1 Engine และการวิเคราะห์ Unit Economics (M3 Sample Solution)

> **Reference Sample Solution (`examples/`):** ใช้ตรวจสอบคณิตศาสตร์และความสมบูรณ์เปรียบเทียบกับรายงานที่ผู้เรียนกรอกเองใน `labs/m3-vllm/optimization-report-template.md`  
> **หมายเหตุตัวเลขจำลอง vs จริง:** ตัวเลขชุด `--simulate` ด้านล่างปรับตามขีดจำกัดฟิสิกส์หน่วยความจำของ NVIDIA L4 (`300 GB/s`, Usable CUDA VRAM `~22.49–24.0 GB`); ค่าจาก `--live` จริงบน Cloud VM จะแปรผันเล็กน้อยตามไดรเวอร์และการตั้งค่า Shared Prompt

---

## 1. ข้อมูลสภาพแวดล้อมและเวิร์กโหลดที่ใช้ทดสอบ (Test Environment & Workload Profile)

- **ฮาร์ดแวร์เป้าหมาย (Cloud GPU Path):** NVIDIA L4 GPU (`24,576 MiB` = `24.0 GiB`, Usable CUDA VRAM หลังหัก ECC/Driver ~`22.49 GiB`, Memory Bandwidth `300 GB/s`), 8 vCPU, 32 GB Host RAM (`$0.85/hour`)
- **ฮาร์ดแวร์จำลอง (Local CPU Path):** `Qwen/Qwen2.5-0.5B-Instruct` (`VLLM_CPU_KVCACHE_SPACE=1`, `--max-model-len 2048`, `HF_HOME=/tmp/ai-infra-hf-cache`)
- **โมเดลที่ใช้ทดสอบบน GPU (Canonical Path: `HF_HOME=/cache/huggingface`):**
  - Baseline (Config A & B): `Qwen/Qwen2.5-7B-Instruct` (`--dtype bfloat16`, น้ำหนักพารามิเตอร์ `~15.24 GB`)
  - Optimized (Config C): `Qwen/Qwen2.5-7B-Instruct-AWQ` (`--quantization awq_marlin`, `--dtype float16`, พารามิเตอร์เชิงทฤษฎี `~4.42 GB` แต่ไฟล์ Safetensors จริงบน Hugging Face ~`5.4–5.6 GB` เพราะ `embed_tokens` และ `lm_head` คงความละเอียด `FP16`)
- **ลักษณะเวิร์กโหลด (RAG / Enterprise Agent Profile):**
  - Shared System Prompt Prefix: `2,048` โทเคน
  - Unique User Suffix: `128` โทเคน
  - Output Generation Length: `256` โทเคน
  - จำนวนคำขอทดสอบขั้นต่ำต่อระดับ Concurrency: `max(20, conc * 4)` (เพื่อให้คำนวณ `p95` ได้มีนัยสำคัญ)
  - เกณฑ์ SLA ที่ต้องผ่าน: **TTFT p95 < 800 ms** และ **ITL p95 < 30 ms** ที่ระดับ **Concurrency = 32**

---

## 2. ตารางเปรียบเทียบขนาด KV-Cache Pool (VRAM Allocation Breakdown)

*(คำนวณเทียบฐานสเปกการ์ด `24.0 GB` กับน้ำหนักโมเดลทางทฤษฎี หากหัก Driver Reserve ~1.5 GB และน้ำหนัก Safetensors จริง ~5.5 GB พื้นที่ KV Pool ของ Config C จะยังเหลือ ~13.7 GB หรือขยายขึ้น >3.5–4.7 เท่าเหนือ Config A อย่างชัดเจน)*

| รายการหน่วยความจำบน NVIDIA L4 (24.0 GB Spec Baseline) | Config A & B (`bfloat16`, util `0.85`) | Config C (`awq_marlin`, util `0.92`) | ผลต่างเชิงวิศวกรรม |
| :--- | :---: | :---: | :--- |
| **Total Usable VRAM Budget (Spec × util)** | `20.40 GB` | `22.08 GB` | เพิ่มพื้นที่ใช้งานจริง `+1.68 GB` |
| **Model Weights ($V_{\text{weights}}$ ประมาณการ)** | `15.24 GB` | `4.42 GB` *(~5.5 GB disk/runtime)* | ประหยัด VRAM จากน้ำหนักโมเดล `~9.7–10.8 GB` |
| **CUDA Context + Activations + CUDAGraphs** | `1.80 GB` | `1.66 GB` | ลดขนาด Activation Buffer ลง `-0.14 GB` |
| **Available KV-Cache Block Pool ($V_{\text{KV\_Pool}}$)** | **`3.36 GB`** | **`16.00 GB`** *(~13.7–16.0 GB)* | **ขยายพื้นที่ KV-Cache Pool เพิ่มขึ้น >4 เท่า (4.76x)** |
| **Max Concurrent KV Tokens (`56 KiB/token`)** | **`~62,914 tokens`** | **`~299,593 tokens`** | รองรับ Context รวมพร้อมกันได้เกือบ 3 แสนโทเคน |

---

## 3. ตารางผลการทดสอบ Benchmark ที่ระดับ Concurrency 1, 8, 16, 32

| โครงแบบ (Configuration) | Concurrency | TTFT p95 (ms) | ITL p95 (ms) | Output Throughput (tok/s) | Peak `vllm:kv_cache_usage_perc` | Prefix Cache Hit Rate (%) | `vllm:num_preemptions_total` | สถานะ SLA |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Config A (BF16, No APC)** | 1 | 310.0 | 54.5 | 18.2 | 12.4% | 0.0% | 0 | PASS (จำกัดที่ Bandwidth L4) |
| **Config A (BF16, No APC)** | 8 | 980.0 | 58.0 | 136.0 | 68.0% | 0.0% | 0 | FAIL (TTFT/ITL) |
| **Config A (BF16, No APC)** | 16 | 2,450.0 | 66.0 | 420.0 | 98.5% | 0.0% | 4 | FAIL |
| **Config A (BF16, No APC)** | 32 | 6,120.0 | 94.0 | 390.0 | 100.0% | 0.0% | 47 | **FAIL (Preemption)** |
| **Config B (BF16 + APC)** | 16 | 460.0 | 29.0 | 890.0 | 42.0% | 88.5% | 0 | PASS |
| **Config B (BF16 + APC)** | 32 | 1,420.0 | 39.0 | 980.0 | 89.0% | 89.1% | 0 | FAIL (TTFT/ITL) |
| **Config C (AWQ + APC + Tune)** | 1 | 195.0 | 17.8 | 56.0 | 2.8% | 89.4% | 0 | PASS |
| **Config C (AWQ + APC + Tune)** | 8 | 280.0 | 19.2 | 495.0 | 14.5% | 88.2% | 0 | PASS |
| **Config C (AWQ + APC + Tune)** | 16 | 390.0 | 21.1 | 960.0 | 26.2% | 88.9% | 0 | PASS |
| **Config C (AWQ + APC + Tune)** | 32 | **640.0** | **23.5** | **1,450.0** | **48.5%** | **89.4%** | **0** | **PASS SLA 100%** |

---

## 4. การวิเคราะห์เศรษฐศาสตร์ต่อหน่วย (Unit Economics & Break-even Analysis)

### สูตรการคำนวณ
$$\text{Cost}_{1\text{M}}(u) = \frac{C_{\text{hour}} \times 1,000,000}{T_{\text{peak}} \times 3,600 \times u}$$

โดยที่:
- $C_{\text{hour}} = \$0.85/\text{hour}$ (Cloud L4 GPU Instance)
- ราคาอ้างอิงของ Managed Commercial API ($P_{\text{API}}$) = $\$0.60 / 1\text{M tokens}$
- อัตราการผลิตโทเคนสูงสุดที่ผ่านเกณฑ์ SLA:
  - $T_{\text{peak, A}} = 420\text{ tokens/sec}$ (ที่ Concurrency 16 ก่อนเกิด Preemption รุนแรง)
  - $T_{\text{peak, C}} = 1,450\text{ tokens/sec}$ (ที่ Concurrency 32 ผ่านทุกเกณฑ์ SLA)

### ตารางต้นทุนต่อ 1 ล้านโทเคนตามระดับการใช้งานจริง (Utilization Sensitivity)

| ระดับการใช้งานเฉลี่ย ($u$) | ปริมาณโทเคนต่อชั่วโมง (Config C) | ต้นทุน Config A (\$/1M tok) | ต้นทุน Config C (\$/1M tok) | ต้นทุน Managed API (\$/1M tok) | ส่วนประหยัดสุทธิของ Config C เทียบกับ API |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **10%** | `0.52M tok/hr` | `$5.62` | `$1.63` | **`$0.60`** | แพงกว่า API (ควรใช้ Serverless/API) |
| **27.1% (จุดคุ้มทุน)** | `1.42M tok/hr` | `$2.07` | **`$0.60`** | **`$0.60`** | **คุ้มทุนพอดี (Break-even Point)** |
| **50%** | `2.61M tok/hr` | `$1.12` | **`$0.33`** | `$0.60` | **ประหยัดลง 45.0% (`-$0.27/1M`)** |
| **80%** | `4.18M tok/hr` | `$0.70` | **`$0.20`** | `$0.60` | **ประหยัดลง 66.1% (`-$0.40/1M`)** |
| **100%** | `5.22M tok/hr` | `$0.56` | **`$0.16`** | `$0.60` | **ประหยัดลง 72.9% (`-$0.44/1M`)** |

---

## 5. ข้อสรุปและคำแนะนำสำหรับการนำไปใช้งานจริง (Production Recommendation)

1. **บังคับใช้ Config C (`Qwen/Qwen2.5-7B-Instruct-AWQ` + `--quantization awq_marlin` + `--gpu-memory-utilization 0.92` + `--enable-prefix-caching` + `--max-num-batched-tokens 2048` ผ่าน `values-cloud-gpu-7b-awq.yaml`) เป็นมาตรฐานการติดตั้ง Production** เนื่องจากขยายขนาด KV-Cache Pool ได้กว่า 4 เท่า กำจัด Preemption Thrashing เหลือ `0` และลดต้นทุนต่อ 1 ล้านโทเคนลงเหลือ `$0.33` ที่ระดับการใช้งาน 50%
2. **ตั้งค่าขีดจำกัดการรับโหลดต่อ Pod ที่ Concurrency = 32** และส่งสัญญาณเมทริกซ์ `vllm:kv_cache_usage_perc` (`> 0.80`) และ `vllm:num_requests_waiting` (`> 5` ต่อ Pod หรือ `> 10` รวมทั้งคลัสเตอร์) ให้แก่ AI Gateway (บทที่ 4) และ KEDA Autoscaler (บทที่ 5)
