# Production Incident Runbook (Sample Reference): `Project SiamShield AI` Multi-Tier Platform (`CAPSTONE-DOD-004A-SAMPLE`)

- **รหัสคู่มือ (Runbook ID):** `RB-SIAMSHIELD-001`
- **สถานะ:** Worked Reference Sample (เปรียบเทียบหลังเขียน `docs/runbooks/capstone-runbook.md` ด้วยตนเอง)
- **ระบบที่ครอบคลุม:** `litellm-gateway-svc:4000`, `vllm-primary-svc:8000`, `vllm-secondary-svc:8000`, `vllm-keda-scaler`
- **สัญญาณเตือนที่เรียกใช้คู่มือนี้:** `VLLMKVCacheSaturationWarning`, `VLLMPreemptionThrashingCritical`, `VLLMHighTTFTBurnRateCritical`, `VLLMHighITLWarning`

---

## ขั้นตอนปฏิบัติการกู้คืนระบบ 4 ขั้น (4-Step SRE Mitigation Playbook)

### ขั้นที่ 1: ตรวจสอบและระบุชั้นที่เกิดคอขวดภายใน 60 วินาที (Triage & Pinpoint)
1. ตรวจสอบเมทริกซ์ `vLLM` V1 จากพอดหลักและพอดสำรอง:
   ```bash
   kubectl exec -n ai-platform deploy/vllm-primary -- curl -s http://localhost:8000/metrics | grep -E "vllm:(kv_cache_usage_perc|num_requests_waiting|prefix_cache_hits_total|num_preemptions_total)"
   ```
2. ตรวจสอบสถานะของ KEDA `ScaledObject` และ Prometheus Query ที่ใช้ Label จริง (`pod=~"vllm-primary-.*"`):
   ```bash
   kubectl get scaledobject,hpa,pods -n ai-platform
   ```

### ขั้นที่ 2: ปกป้องทราฟฟิก `tier-realtime` ทันทีภายใน 3 นาที (Immediate Isolation & Failover)
1. **หาก `vllm:kv_cache_usage_perc > 0.85` หรือ `vllm:num_requests_waiting > 5` จากการไหลทะลักของงาน Batch:**
   - ยืนยันว่า Endpoint Picker (EPP) ทำการ Shed ทราฟฟิก `InferenceModel/siamshield-tier-batch` (`criticality: Sheddable`) แล้ว
   - หากจำเป็น ให้ปรับลดโควตา RPM ของ `batch-team` (`qwen2.5-7b-batch`) ลงชั่วคราวที่ `litellm-gateway-svc:4000`
2. **หากพอดใน `vllm-primary-svc` ค้างหรือเกิด ECC Error:**
   - ยืนยันว่า `LiteLLM Proxy` (`num_retries: 0`) สลับทราฟฟิกไปยัง `vllm-secondary-svc:8000` ภายใน `stream_timeout: 3.0s` (สังเกตจาก Log ของ `deploy/litellm-gateway` / Response Header `x-litellm-api-base` บน Gateway จริง หรือ Header `X-Sim-Fallback-Triggered: true` ในโหมด Simulator)

### ขั้นที่ 3: แก้ไขที่ต้นเหตุและตรวจสอบแคชโวลุ่ม (Root-Cause Remediation)
1. ตรวจสอบว่าพอดที่สเกลเพิ่มโดย KEDA เมานต์โวลุ่ม `hf-model-cache-pvc` ที่พาธ `HF_HOME=/cache/huggingface` (`VLLM_CACHE_ROOT=/tmp/vllm-cache`, Non-root UID 10001) สำเร็จและพร้อมใช้งาน (`< 10 วินาที` บน Mock Pod หรือ `~35–75 วินาที` บน Cloud L4 GPU)
2. หาก `VLLMPrefixCacheHitDropWarning` ดังขึ้น (อัตรา `rate(vllm:prefix_cache_hits_total[5m]) / rate(vllm:prefix_cache_queries_total[5m]) < 0.50`) ให้ตรวจสอบว่าไม่มีการแทรก Dynamic Timestamp หรือข้อมูลไม่คงที่ไว้ต้น System Prompt และยืนยันว่า `PDPAPIIMasker` ทำงานแปลง `<THAI_ID_REDACTED>` ก่อนชั้น Cache

### ขั้นที่ 4: ยืนยันการฟื้นตัวและถอนสถานะวิกฤต (Recovery & Scale-In Verification)
1. ยืนยันว่า `TTFT p95 < 800 ms`, `ITL p95 < 30 ms`, และ `rate(vllm:num_preemptions_total[5m]) == 0` ติดต่อกัน 10 นาที
2. เมื่อโหลดลดลงและ KEDA สั่ง Scale-in กลับสู่ `minReplicaCount: 1` ให้ยืนยันว่า `terminationGracePeriodSeconds: 60` และ `preStop: sleep 5` ทำงานโดยไม่มีคำขอสตรีมมิ่งหลุด (`0 dropped requests`)
