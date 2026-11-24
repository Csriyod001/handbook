# Production Incident Runbook: `Project SiamShield AI` Multi-Tier Platform (`CAPSTONE-DOD-004A`)

- **รหัสคู่มือ (Runbook ID):** `RB-SIAMSHIELD-001`
- **ระบบที่ครอบคลุม:** `litellm-gateway-svc:4000`, `vllm-primary-svc:8000`, `vllm-secondary-svc:8000`, `vllm-keda-scaler`
- **สัญญาณเตือนที่เรียกใช้คู่มือนี้:** `VLLMKVCacheSaturationWarning`, `VLLMPreemptionThrashingCritical`, `VLLMHighTTFTBurnRateCritical`, `VLLMHighITLWarning`

> **คำแนะนำสำหรับผู้เรียน:** เขียนคำสั่งตรวจสอบและขั้นตอนแก้ปัญหาให้ครบทั้ง 4 ขั้นตอนด้านล่าง โดยตรวจสอบชื่อ Metric (`vllm:kv_cache_usage_perc`, `vllm:num_requests_waiting`), KEDA/Prometheus Labels (`pod=~"vllm-primary-.*"`), Path PVC (`HF_HOME=/cache/huggingface`), และการ Failover (`num_retries: 0`) จากไฟล์ในคลัง จากนั้นลบแท็ก `<TODO:...>` ทั้งหมด (ดูตัวอย่างเปรียบเทียบหลังทำได้ที่ `examples/capstone-runbook-sample.md`)

---

## ขั้นตอนปฏิบัติการกู้คืนระบบ 4 ขั้น (4-Step SRE Mitigation Playbook)

### ขั้นที่ 1: ตรวจสอบและระบุชั้นที่เกิดคอขวดภายใน 60 วินาที (Triage & Pinpoint)
1. คำสั่งตรวจสอบเมทริกซ์ `vLLM` (`vllm:kv_cache_usage_perc`, `vllm:num_requests_waiting`, `vllm:prefix_cache_hits_total`, `vllm:num_preemptions_total`):
   ```bash
   <TODO: ใส่คำสั่ง kubectl exec / curl ตรวจเมทริกซ์บน vllm-primary>
   ```
2. คำสั่งตรวจสถานะ KEDA `ScaledObject`, `HPA`, และ Pods ในเนมสเปซ `ai-platform` (พร้อมตรวจ Query label `pod=~"vllm-primary-.*"`):
   ```bash
   <TODO: ใส่คำสั่ง kubectl get ...>
   ```

### ขั้นที่ 2: ปกป้องทราฟฟิก `tier-realtime` ทันทีภายใน 3 นาที (Immediate Isolation & Failover)
1. **กรณี `vllm:kv_cache_usage_perc > 0.85` หรือ `vllm:num_requests_waiting > 5`:**
   - `<TODO: ระบุวิธีตรวจว่า EPP ทำ Load Shedding ให้ InferenceObjective/siamshield-tier-batch (priority -10 / Sheddable) และวิธีลดโควตา batch-team>`
2. **กรณีพอด `vllm-primary` ค้างหรือไม่ตอบสนอง:**
   - `<TODO: ระบุวิธีตรวจ Gateway Failover (num_retries: 0, stream_timeout: 3.0s) ไปยัง vllm-secondary-svc จาก Gateway Log / Response Header (`X-Sim-Fallback-Triggered: true` ในโหมด Simulator)>`

### ขั้นที่ 3: แก้ไขที่ต้นเหตุและตรวจสอบแคชโวลุ่ม (Root-Cause Remediation)
1. `<TODO: ระบุการตรวจ hf-model-cache-pvc ที่เมาต์เข้า HF_HOME=/cache/huggingface และเปรียบเทียบเวลาพร้อมใช้งาน (Mock Pod vs Cloud L4 GPU)>`
2. `<TODO: ระบุการตรวจ VLLMPrefixCacheHitDropWarning และผลของ PDPA Redaction (<THAI_ID_REDACTED>)>`

### ขั้นที่ 4: ยืนยันการฟื้นตัวและถอนสถานะวิกฤต (Recovery & Scale-In Verification)
1. `<TODO: ระบุค่า SLO ที่ต้องตรวจยืนยัน (TTFT p95, ITL p95, Preemptions) ก่อนปิด Incident>`
2. `<TODO: ระบุการตรวจ Graceful Drain (preStop: sleep 5 และ terminationGracePeriodSeconds: 60) ระหว่าง Scale-in>`
