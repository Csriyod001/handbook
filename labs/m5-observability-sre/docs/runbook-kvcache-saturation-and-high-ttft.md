# Production Incident Runbook (`RB-AI-005`): vLLM V1 KV-Cache Saturation, High TTFT & Preemption Thrashing

- **Runbook ID:** `RB-AI-005`
- **Service / Namespace:** `vllm-primary-svc:8000` (`namespace: ai-platform`)
- **Severity Classification:**
  - **SEV-2:** `p95 TTFT >= 0.8s` (800 ms) แต่ `< 2.0s` หรือ `avg(vllm:kv_cache_usage_perc) > 0.85` โดยยังไม่มีการตัดการเชื่อมต่อ
  - **SEV-1:** `p95 TTFT >= 2.0s`, เกิด `vllm:num_preemptions_total > 0` ต่อเนื่อง, หรือ SLO Burn Rate `> 14.4x` ทั้งหน้าต่าง `5m` และ `1h`
- **Triggering Prometheus Alerts (`prometheus-alert-rules.yaml`):**
  - `VLLMKVCacheSaturationWarning` (`avg(vllm:kv_cache_usage_perc) > 0.85` for `2m`)
  - `VLLMPreemptionThrashingCritical` (`sum(rate(vllm:num_preemptions_total[5m])) > 0` for `1m`)
  - `VLLMHighTTFTBurnRateCritical` (`5m` & `1h` multi-window breach rate `> 1.44%` / `B = 14.4` on `99.9%` TTFT 800ms SLO)
  - `VLLMPrefixCacheHitDropWarning` (`APC Hit Ratio < 0.50` while active queries `> 0`)

---

## 1. ขั้นตอนที่ 1: ประเมินสถานการณ์ใน 60 วินาทีแรก (Observe & Verify)

1. ตรวจสอบค่าคอขวด KV-Cache, คิวรอ และจำนวนการเกิด Preemption (`RECOMPUTE`) จากพอดจริง:
   ```bash
   kubectl exec -n ai-platform deploy/vllm-primary -- \
     curl -s http://localhost:8000/metrics | grep -E "vllm:(kv_cache_usage_perc|num_requests_waiting|num_preemptions_total|prefix_cache_hits_total|prefix_cache_queries_total)"
   ```
2. ตรวจสอบการทำงานของ `KEDA ScaledObject` (`vllm-keda-scaler`) และ HorizontalPodAutoscaler (`HPA`):
   ```bash
   kubectl get scaledobject,hpa,pods -n ai-platform -l app=vllm-serving
   kubectl describe scaledobject vllm-keda-scaler -n ai-platform
   ```
3. แยกแยะสาเหตุฮาร์ดแวร์บนแดชบอร์ด Grafana (`grafana-dashboard-vllm-v1.json`):
   - **Memory-Bandwidth Bound (Decode Bottleneck):** `DCGM_FI_PROF_DRAM_ACTIVE` สูง (> 0.70) ขณะที่ `DCGM_FI_PROF_SM_ACTIVE` ต่ำ -> โมเดลติดแบนด์วิดท์ HBM ระหว่างเฟส Decode
   - **Compute Bound / Prefill Saturation:** `DCGM_FI_PROF_SM_ACTIVE` สูงมาก -> มีคำขอ Prompt ยาวพร้อมกันสูง หรือ APC Cache Miss

---

## 2. ขั้นตอนที่ 2: บรรเทาผลกระทบเฉพาะหน้าภายใน 3 นาที (Immediate Traffic Mitigation)

- **กรณีที่ A — KEDA ขยายถึง `maxReplicaCount: 3` แล้วแต่คิวยังไม่ลด (Noisy Neighbor Batch Traffic):**
  1. ตรวจสอบว่า Endpoint Picker (`EPP`) ตัดโหลดทราฟฟิก `Sheddable` (`priority: -10`) ที่ `InferenceObjective` (`llm-d.ai/v1`) แล้วหรือไม่
  2. ลดโควตา `rpm` / `tpm` ของ Virtual Key ทีม `batch-team` ชั่วคราวผ่าน `LiteLLM Proxy` Admin API (`http://litellm-gateway-svc:4000/key/update`) เพื่อสงวนทรัพยากรให้ `realtime-team`
- **กรณีที่ B — พอดใหม่ค้างสถานะ `Pending` เนื่องจากสล็อต GPU ในคลัสเตอร์เต็ม:**
  1. ตรวจสอบสถานะ Spillover Routing ใน `litellm-gateway-svc:4000` ให้กระจายคำขอไปยัง `vllm-secondary-svc:8000` (`fallbacks: [{"qwen2.5-7b": ["qwen2.5-7b-secondary"]}]`)
  2. ยืนยันว่าไม่ได้ปิด Shared Cache Volume (`hf-model-cache-pvc` -> `HF_HOME=/cache/huggingface`) จนทำให้พอดใหม่เสียเวลาโหลดน้ำหนักโมเดลซ้ำ

---

## 3. ขั้นตอนที่ 3: แก้ไขที่ต้นเหตุ (Root-Cause Remediation)

1. **หากพบค่า `APC Hit Ratio` ร่วงผิดปกติ (`VLLMPrefixCacheHitDropWarning`):**
   - ตรวจสอบฝั่ง Prompt Builder ของทีมแอปพลิเคชันทันทีว่ามีการแทรกตัวแปรพลวัต (เช่น Timestamp, UUID, Request ID, User ID) ไว้ที่ส่วนต้นของ System Prompt หรือไม่ เนื่องจาก SHA-256 Prefix Hash เป็นแบบลูกโซ่ บล็อกแรกที่เปลี่ยนจะทำลายแคชทั้งห่วงโซ่
2. **หากพบคำขอยาวผูกขาดบล็อก PagedAttention:**
   - ตรวจสอบพารามิเตอร์ Startup ของ `vLLM` V1 ให้จำกัดขอบเขตที่ `--max-model-len 4096` และ `--max-num-seqs 64` พร้อมเปิด Unified Chunked Prefill (`--max-num-batched-tokens 2048`) ตามมาตรฐานบทที่ 3

---

## 4. ขั้นตอนที่ 4: ยืนยันการฟื้นตัวก่อนปิดเหตุการณ์ (Recovery Verification & Sign-Off)

ห้ามปิด Incident จนกว่าจะผ่านเกณฑ์ทั้ง 3 ข้อต่อเนื่องอย่างน้อย **10 นาที**:
1. `sum(rate(vllm:num_preemptions_total[5m])) == 0` (ไม่มีการยึดบล็อก KV-Cache เพื่อ Recompute เพิ่มเติม)
2. `histogram_quantile(0.95, sum(rate(vllm:time_to_first_token_seconds_bucket[5m])) by (le)) < 0.8` (`p95 TTFT < 800 ms`, และ `1 - sum(rate(vllm:time_to_first_token_seconds_bucket{le="0.75"}[5m])) / clamp_min(sum(rate(vllm:time_to_first_token_seconds_bucket{le="+Inf"}[5m])), 1e-9)` ต่ำกว่า Burn-Rate Alert)
3. `avg(vllm:kv_cache_usage_perc{namespace="ai-platform",pod=~"vllm-primary-.*"}) < 0.75` และ `KEDA` คงเสถียรภาพจำนวน Pod โดยไม่มีการ Scale Flap

---

## 5. เอกสารอ้างอิงที่เกี่ยวข้อง

- **Postmortem ตัวอย่าง:** [postmortem-001-peak-hour-latency-outage.md](postmortem-001-peak-hour-latency-outage.md)
- **ADR ที่เกี่ยวข้อง:** [adr-004-observability-and-keda-autoscaling.md](adr-004-observability-and-keda-autoscaling.md)
- **Alert Rules:** [prometheus-alert-rules.yaml](../prometheus-alert-rules.yaml)
- **KEDA Manifest:** [keda-vllm-scaledobject.yaml](../keda-vllm-scaledobject.yaml)
