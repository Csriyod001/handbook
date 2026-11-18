# Blameless Postmortem (Sample Reference): เหตุการณ์ Compound Batch Flood & Primary Replica Latency Spike บน `Project SiamShield AI` (`CAPSTONE-DOD-004B-SAMPLE`)

- **รหัสเหตุการณ์ (Incident ID):** `PM-SIAMSHIELD-2026-01`
- **สถานะ:** Worked Reference Sample (เปรียบเทียบหลังเขียน `docs/postmortems/capstone-postmortem.md` ด้วยตนเอง)
- **วันที่และเวลาเกิดเหตุ:** 2026-11-11 เวลา 14:00 – 14:09 น. (ระยะเวลารวม 9 นาที)
- **ระดับความรุนแรง (Severity):** `SEV-2` (ได้รับการป้องกันอัตโนมัติด้วยระบบ Failover และ Load Shedding ทำให้ `tier-realtime` มี Availability `100.0%` และไม่มีข้อมูลส่วนบุคคล PDPA รั่วไหล)

---

## 1. สรุปเหตุการณ์และผลกระทบ (Executive Summary & Impact)

ในระหว่างการประมวลผลสรุปกรมธรรม์สิ้นเดือน ไปป์ไลน์ของ `tier-batch` เกิดการส่งคำขอที่มีเอกสารยาว 3,500 โทเคนพร้อมเลขบัตรประชาชนลูกค้าเข้ามาพร้อมกันเกินโควตา 5 เท่า ประจวบเหมาะกับที่พอดตัวหนึ่งใน `vllm-primary-svc` เกิดอาการหน่วงชั่วขณะ (`> 5,000 ms`)
- **ผลกระทบต่อ `tier-realtime`:** Availability อยู่ที่ **`100.0%`** และ `TTFT p95 = 640.0 ms` (`< 800 ms` SLO) เนื่องจาก `LiteLLM Proxy` (`num_retries: 0`) สลับทราฟฟิกไปยัง `vllm-secondary-svc` ภายใน `3.0s` และ `KEDA` สเกลพอดเพิ่มเป็น 3 เรพลิกา (Mock Pod พร้อมใช้งานใน `8.5 วินาที`; Cloud L4 GPU ใช้เวลา ~45–75 วินาทีจาก PVC Cache)
- **ผลกระทบต่อ `tier-batch`:** คำขอส่วนเกินถูกบล็อกด้วย `HTTP 429` ตามที่ออกแบบไว้ (`10 RPM`) และเข้าคิว Retry ใหม่หลังพอดสเกลเสร็จ
- **ผลกระทบด้าน PDPA:** **`0 PII Leaks`** (`PDPAPIIMasker` แปลงเลขบัตรประชาชน 13 หลักเป็น `<THAI_ID_REDACTED>` และเบอร์โทรศัพท์เป็น `<THAI_PHONE_REDACTED>` ครบ 100%)

---

## 2. ลำดับเหตุการณ์ (Timeline of Events)

- **14:00:00 น.:** งาน Cron สิ้นเดือนของ `tier-batch` ยิงคำขอเข้ามา 50 RPM พร้อมข้อมูลลูกค้าที่ยังไม่ผ่านการกรอง PII
- **14:00:01 น.:** `PDPAPIIMasker` ที่ชั้น Pre-call ของ `litellm-gateway-svc:4000` สกัดกั้นและแปลงเลขบัตรประชาชน 13 หลักเป็น `<THAI_ID_REDACTED>` ทั้งหมด และตัวจำกัดโควตา RPM บล็อกคำขอส่วนเกินของ `batch-team` ด้วย `HTTP 429`
- **14:01:15 น.:** พอดหลักใน `vllm-primary-svc:8000` มีค่า `vllm:kv_cache_usage_perc` พุ่งแตะ `91.0%` และคิวรอ `vllm:num_requests_waiting = 18`
- **14:01:16 น.:** `Endpoint Picker (EPP)` สั่งตัดโหลด `Sheddable` ของ `tier-batch` ทันทีเพื่อสงวน KV-Cache ให้ `tier-realtime` (`Critical`)
- **14:01:20 น.:** `LiteLLM Proxy` ตรวจพบว่าพอดหลักตอบสนองช้าเกิน `stream_timeout: 3.0s` จึงสลับคำขอของ `tier-realtime` ไปยัง `vllm-secondary-svc:8000` อัตโนมัติทันที (`num_retries: 0`)
- **14:01:30 น.:** `KEDA ScaledObject` (`vllm-keda-scaler`) สั่งขยาย `deployment/vllm-primary` จาก 1 เป็น 3 พอด โดยพอดใหม่โหลดโมเดลจาก `hf-model-cache-pvc` (`HF_HOME=/cache/huggingface`) เสร็จใน `8.5 วินาที` (Mock Pod ในแล็บจำลอง; บน Cloud L4 GPU จริงประมาณ 45–75 วินาที)
- **14:09:00 น.:** คิวรอทั้งหมดถูกระบายจนหมด ค่า `vllm:kv_cache_usage_perc` ลดลงเหลือ `31.3%` ระบบกลับสู่สภาวะปกติ 100%

---

## 3. การวิเคราะห์หาสาเหตุรากเหง้า 5 ทำไม (5 Whys Root Cause Analysis)

1. **ทำไม `vllm:kv_cache_usage_perc` บนเรพลิกาหลักจึงพุ่งขึ้นแตะ 91% อย่างรวดเร็ว?**
   เพราะมีคำขอสรุปเอกสารขนาดยาวของ `tier-batch` เข้ามาพร้อมกับโหลดพีคของ `tier-realtime` ขณะที่เริ่มต้นรันอยู่เพียง 1 เรพลิกา
2. **ทำไมสคริปต์ของ `tier-batch` จึงยิงคำขอเข้ามาพร้อมกัน 50 RPM ทั้งที่โควตากำหนดไว้ 10 RPM?**
   เพราะผู้พัฒนาสคริปต์ฝั่ง Batch ใช้ `asyncio.gather()` ยิงขนานโดยไม่ได้ใส่ Client-side Rate Limiter และไม่ได้ใช้ Exponential Backoff เมื่อได้รับ `HTTP 429`
3. **ทำไมข้อความที่มีเลขบัตรประชาชนไทย 13 หลักจึงถูกส่งมาจากฝั่ง Batch?**
   เพราะไปป์ไลน์ดึงข้อมูลดิบจากตารางใบคำขอสินเชื่อโดยตรง โชคดีที่ชั้น Pre-call `PDPAPIIMasker` บน `litellm-gateway-svc` ทำงานเป็นด่านบังคับสำหรับทุก Virtual Key จึงไม่มีข้อมูลหลุดรอด
4. **ทำไมพอดใหม่ที่ KEDA สเกลขึ้นมาถึงไม่ต้องรอ 3–4 นาทีเพื่อดาวน์โหลดโมเดลซ้ำ?**
   เพราะเราผูกโวลุ่ม `hf-model-cache-pvc` เข้ากับ `HF_HOME=/cache/huggingface` ไว้ล่วงหน้าตามมาตรฐาน `ADR-001` และ `ADR-002`
5. **ทำไมผู้ใช้ฝั่ง `tier-realtime` จึงไม่พบข้อผิดพลาด HTTP 5xx เลยแม้แต่รายการเดียว?**
   เพราะการตั้งค่า `num_retries: 0` + `stream_timeout: 3.0s` ร่วมกับ Fallback Group ไปยัง `vllm-secondary-svc:8000` และการตัดโหลด Batch ของ `EPP` ทำงานประสานกันอย่างสมบูรณ์

---

## 4. รายการแนวทางป้องกันและพัฒนาต่อยอด (Action Items)

| ลำดับ | การดำเนินการ (Action Item) | ผู้รับผิดชอบ | สถานะ |
| :---: | :--- | :--- | :---: |
| 1 | เพิ่ม SDK Wrapper มาตรฐานให้ทีม `batch-team` มีระบบ Token-Bucket Rate Limiter และ Exponential Backoff + Jitter เมื่อได้รับ `HTTP 429` | Platform SDK Team | Completed |
| 2 | ตั้งค่า Cron Schedule ใน KEDA ให้ Pre-warm เรพลิกาของ `vllm-primary` เป็น 2 พอดล่วงหน้า 10 นาทีก่อนเวลา 14:00 น. ของวันสิ้นเดือน | AI SRE Team | Completed |
