# Blameless Postmortem: เหตุการณ์ Compound Batch Flood & Primary Replica Latency Spike บน `Project SiamShield AI` (`CAPSTONE-DOD-004B`)

- **รหัสเหตุการณ์ (Incident ID):** `PM-SIAMSHIELD-2026-01`
- **วันที่และเวลาเกิดเหตุ:** `<TODO: วันที่และช่วงเวลาที่จำลองเหตุการณ์>`
- **ระดับความรุนแรง (Severity):** `<TODO: e.g., SEV-2 พร้อมสรุป Availability & PDPA Status>`

> **คำแนะนำสำหรับผู้เรียน:** รันสถานการณ์ Incident Simulation แล้วสรุปเหตุการณ์, Timeline, การวิเคราะห์ **5 Whys**, และ Action Items ด้านล่างให้ครบถ้วนโดยยึดหลัก Blameless Postmortem แล้วลบ `<TODO:...>` ทั้งหมด (ดูตัวอย่างหลังเขียนเสร็จได้ที่ `examples/capstone-postmortem-sample.md`)

---

## 1. สรุปเหตุการณ์และผลกระทบ (Executive Summary & Impact)
- **ภาพรวมเหตุการณ์:** `<TODO: สรุปสาเหตุของ Compound Batch Flood + Primary Latency Spike>`
- **ผลกระทบต่อ `tier-realtime`:** `<TODO: ระบุ Availability, TTFT p95, และเวลา Failover ไป vllm-secondary-svc>`
- **ผลกระทบต่อ `tier-batch`:** `<TODO: ระบุพฤติกรรม HTTP 429 และ EPP Load Shedding>`
- **ผลกระทบด้าน PDPA:** `<TODO: ระบุผลการคัดกรอง <THAI_ID_REDACTED> / <THAI_PHONE_REDACTED>>`

---

## 2. ลำดับเหตุการณ์ (Timeline of Events)
- `<TODO: 14:00:00 — เหตุการณ์เริ่มต้นและการตรวจจับ PDPA / RPM>`
- `<TODO: 14:01:xx — KV-Cache saturation, EPP Load Shedding และ LiteLLM Failover (num_retries: 0)>`
- `<TODO: 14:01:xx — KEDA Scale-out พร้อมโหลดจาก hf-model-cache-pvc (HF_HOME=/cache/huggingface)>`
- `<TODO: 14:09:00 — การฟื้นตัวสู่สภาวะปกติ>`

---

## 3. การวิเคราะห์หาสาเหตุรากเหง้า 5 ทำไม (5 Whys Root Cause Analysis)
1. **Why 1:** `<TODO: ทำไม KV-Cache บน vllm-primary จึงเต็มอย่างรวดเร็ว?>`
2. **Why 2:** `<TODO: ทำไมฝั่ง batch-team จึงยิงเกิน 10 RPM?>`
3. **Why 3:** `<TODO: ทำไม PII 13 หลักจึงหลุดเข้า Prompt ก่อนถึง Gateway?>`
4. **Why 4:** `<TODO: ทำไมพอดที่ KEDA สเกลขึ้นมาไม่ต้องดาวน์โหลดโมเดลซ้ำ 3–4 นาที (อ้างอิง HF_HOME=/cache/huggingface)?>`
5. **Why 5:** `<TODO: ทำไมทราฟฟิก tier-realtime จึงไม่พบ HTTP 5xx เลย?>`

---

## 4. รายการแนวทางป้องกันและพัฒนาต่อยอด (Action Items)

| ลำดับ | การดำเนินการ (Action Item) | ผู้รับผิดชอบ | สถานะ |
| :---: | :--- | :--- | :---: |
| 1 | `<TODO: มาตรการฝั่ง Client SDK / Batch Rate Limiting>` | `<TODO>` | `<TODO>` |
| 2 | `<TODO: มาตรการฝั่ง SRE / KEDA Pre-warming หรือ Alert Tuning>` | `<TODO>` | `<TODO>` |
