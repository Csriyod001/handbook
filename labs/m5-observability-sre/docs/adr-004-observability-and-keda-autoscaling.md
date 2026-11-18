# ADR-004: การออกแบบระบบ AI Observability 3 ชั้น และ KEDA Autoscaling บนสัญญาณเฉพาะทางของ `vLLM` V1

- **สถานะ (Status):** Accepted
- **วันที่ (Date):** 2026-11-11
- **ผู้รับผิดชอบ (Owners):** AI Platform SRE & Infrastructure Architecture Team
- **โมดูลที่เกี่ยวข้อง:** M5 (Observability, Autoscaling & SRE), ต่อยอดจาก M4 (Gateway & Metrics Exposition) และเชื่อมสู่ Capstone M6

---

## 1. บริบทและปัญหา (Context & Problem Statement)

ระบบให้บริการโมเดลภาษาขนาดใหญ่ (`vLLM` V1 Engine) บน Kubernetes มีพฤติกรรมการใช้ทรัพยากรต่างจากเว็บแอปพลิเคชันทั่วไปอย่างสิ้นเชิง การพึ่งพา Kubernetes HPA แบบดั้งเดิม (CPU / Host RAM) หรือการอ่านเพียง `DCGM_FI_DEV_GPU_UTIL` นำไปสู่ความล้มเหลว 3 ประการใน Production:
1. **HPA Blindness ต่อคอขวดจริง:** ขณะคิวรอใน `vLLM` Scheduler เต็ม (`vllm:num_requests_waiting = 14`) หรือพื้นที่ KV-Cache ใกล้ล้น (`vllm:kv_cache_usage_perc = 0.92`) ค่า Host CPU อาจอยู่ที่เพียง `12%` ทำให้ HPA ไม่สั่ง Scale-out จนเกิด Preemption Thrashing (`RECOMPUTE`)
2. **GPU Utilization Misinterpretation:** `DCGM_FI_DEV_GPU_UTIL` วัดเพียง "สัดส่วนเวลาที่มี Kernel รันบน GPU" (แม้ใช้ SM เพียง 5% ก็อาจโชว์ 100%) จึงไม่สามารถแยก **Compute-Bound Prefill** ออกจาก **HBM Memory-Bandwidth-Bound Decode** ได้หากไม่มี Profiling Counters (`DCGM_FI_PROF_SM_ACTIVE` / `DCGM_FI_PROF_DRAM_ACTIVE`)
3. **Cold-Start Pull Penalty & Broken Streams:** หาก KEDA สเกลพอดใหม่ขึ้นมาแล้วต้องดาวน์โหลดโมเดลซ้ำผ่านอินเทอร์เน็ตจะเสียเวลา 5–10 นาที หรือหากสเกลลงโดยไม่มี `preStop` + `terminationGracePeriodSeconds: 60` การเชื่อมต่อ SSE Streaming ของลูกค้าจะถูกตัดทิ้งทันที

---

## 2. ทางเลือกที่พิจารณา (Considered Options)

| เกณฑ์การประเมิน | Option 1: K8s HPA มาตรฐาน (CPU / Host Memory) | Option 2: Prometheus Adapter + Single GPU Util Metric | Option 3 (ที่เลือก): **3-Layer Telemetry + KEDA Dual-Trigger + Shared `HF_HOME` PVC** |
| :--- | :---: | :---: | :---: |
| **ตรวจจับคิวรอและ KV-Cache Saturation** | ไม่ได้ (มองไม่เห็น State ภายใน GPU/vLLM) | ไม่แม่นยำ (`GPU_UTIL` ค้าง 100% แม้คิวว่าง) | **แม่นยำ 100% (`num_requests_waiting` + `kv_cache_usage_perc`)** |
| **แยกคอขวด Prefill vs Decode** | ไม่ได้ | ไม่ได้ | **ได้ผ่าน `SM_ACTIVE` vs `DRAM_ACTIVE` + TTFT/ITL Histograms** |
| **Scale-out Readiness Latency** | ช้า (~5–10 นาที) | ช้า (~5–10 นาที) | **เร็วขึ้นมาก (`< 10s` Mock Pod; `~35–75s` Cloud L4 GPU PVC vs 195s+ Cold Download)** |
| **Multi-Pod KEDA `avg()` Scaling Correctness** | N/A | เสี่ยง Scale-down ผิดพลาดจาก `AverageValue` | **ถูกต้องทั้ง `N >= 1` ด้วย `metricType: AverageValue` (Queue) + `Value` (KV Avg)** |

---

## 3. การตัดสินใจ (Decision)

เราตัดสินใจเลือก **Option 3** โดยมีข้อกำหนดเชิงวิศวกรรมดังนี้:
1. **3-Layer AI Telemetry & SLO Rules ([grafana-dashboard-vllm-v1.json](../grafana-dashboard-vllm-v1.json), [prometheus-alert-rules.yaml](../prometheus-alert-rules.yaml)):**
   - **Layer 1 (DCGM Hardware):** ติดตามทั้ง `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_PROF_SM_ACTIVE`, และ `DCGM_FI_PROF_DRAM_ACTIVE` (แผงกราฟ `0.0–1.0`) แยกคนละ Panel กับ `DCGM_FI_DEV_FB_USED` (หน่วย MiB)
   - **Layer 2 (`vLLM` V1 Engine):** ติดตาม `vllm:time_to_first_token_seconds_bucket` (ใช้ขอบเขต `le="0.75"` เป็นเกณฑ์เตือนอนุรักษ์นิยมสำหรับ SLA `< 800ms` ให้ตรงกับถังจริงของ `vLLM`), `vllm:inter_token_latency_seconds_bucket` (เป็น Primary `or vllm:time_per_output_token_seconds_bucket` Compat Alias), `vllm:kv_cache_usage_perc`, `vllm:num_requests_waiting`, `vllm:prefix_cache_hits_total` / `queries_total` (ใช้ `clamp_min(..., 1e-9)` เพื่อไม่ให้เกิดความคลาดเคลื่อนเมื่อ QPS ต่ำ), `vllm:num_preemptions_total`, และ `vllm:generation_tokens_total` ผ่าน [servicemonitor-vllm.yaml](../servicemonitor-vllm.yaml)
   - **Layer 3 (OTel GenAI + Multi-Window Burn Rate):** ใช้ OpenTelemetry GenAI Semantic Conventions (`v1.28+`) และตั้ง Alert `VLLMHighTTFTBurnRateCritical` แบบ **Multi-Window (`5m` AND `1h` @ `14.4x` Burn Rate บน `99.9%` SLO)**
2. **KEDA Dual-Trigger Configuration ([keda-vllm-scaledobject.yaml](../keda-vllm-scaledobject.yaml)):**
   - **Trigger 1 (`Queue`):** `metricType: AverageValue` กับ `sum(vllm:num_requests_waiting{namespace="ai-platform",pod=~"vllm-primary-.*"})` ที่ `threshold: "5"` $\implies \lceil \text{Sum} / 5 \rceil$
   - **Trigger 2 (`KV-Cache`):** กำหนด **`metricType: Value`** (บังคับ!) กับ `avg(vllm:kv_cache_usage_perc{namespace="ai-platform",pod=~"vllm-primary-.*"})` ที่ `threshold: "0.80"` $\implies \lceil N_{\text{current}} \times \text{avg} / 0.80 \rceil$ เพื่อป้องกันบั๊ก HPA สเกลลดพอดลงผิดพลาดเมื่อ $N \ge 2$ โดยกรองด้วย Label `pod=~"vllm-primary-.*"` ที่ใช้งานได้ทั้งกับ `mock_vllm_server` และพอด `vLLM` จริงบน GPU (ไม่ต้องพึ่ง Label `server_id` ที่ไม่มีใน Upstream)
3. **Cache Persistence & Graceful Shutdown:**
   - ทุกพอดของ `vllm-primary` ใช้ `hf-model-cache-pvc` (`HF_HOME=/cache/huggingface`, `VLLM_CACHE_ROOT=/tmp/vllm-cache`), `securityContext` แบบ Non-root (`UID 10001` + `readOnlyRootFilesystem: true`), `terminationGracePeriodSeconds: 60`, และ `preStop: sleep 5`

---

## 4. ผลกระทบและข้อควรระวัง (Consequences)

- **ข้อดี:** ป้องกัน Preemption Thrashing ได้ตั้งแต่คิวเริ่มสะสมเกิน 5 คำขอ/พอด หรือ KV-Cache เกิน 80%, ไม่ต้องเสียเวลาโหลดโมเดลซ้ำตอน Scale-out, และรองรับทั้ง local CPU/Mock verification และ Production Cloud GPU
- **ข้อควรระวัง / Trade-offs:**
  - `DCGM_FI_PROF_SM_ACTIVE` และ `DCGM_FI_PROF_DRAM_ACTIVE` ต้องใช้สิทธิ์ Profiling หรือ MIG/bare-metal GPU driver ที่รองรับบน Cloud VM (บน Time-Slicing บางผู้ให้บริการอาจต้องเปิด DCGM profiling feature flag)
  - `hf-model-cache-pvc` ต้องรองรับ `ReadWriteMany` เมื่อ KEDA ขยายพอดหลายตัวพร้อมกันบนหลาย Node (หรือจัด Node Affinity ในคลัสเตอร์ single-GPU)
