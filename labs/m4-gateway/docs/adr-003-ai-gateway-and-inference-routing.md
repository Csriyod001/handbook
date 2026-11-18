# ADR-003: การเลือกใช้ `LiteLLM Proxy` ร่วมกับ Kubernetes Gateway API Inference Extension สำหรับระบบ AI Gateway หลายผู้เช่า

- **สถานะ (Status):** Accepted
- **วันที่ (Date):** 2026-11-11
- **ผู้รับผิดชอบ (Owners):** AI Platform & Governance Engineering Team
- **โมดูลที่เกี่ยวข้อง:** M4 (AI Gateway & Governance), เชื่อมต่อจาก M3 (`vLLM` V1 Engine) และส่งมอบสู่ M5 (Observability & KEDA Autoscaling)

---

## 1. บริบทและปัญหา (Context & Problem Statement)

ในการนำคลัสเตอร์ `vLLM` V1 (`vllm-primary-svc:8000` และ `vllm-secondary-svc:8000`) ขึ้นให้บริการแก่ผู้ใช้งานหลายแผนกในองค์กร ได้แก่:
1. **`realtime-team`:** แอปพลิเคชันแชตบอตบริการลูกค้าที่ต้องการเวลาตอบสนองเร็ว (`TTFT p95 < 800 ms`) และความพร้อมใช้งานสูง
2. **`batch-team`:** ไปป์ไลน์สรุปเอกสารหลังบ้านที่ส่งคำขอจำนวนมากพร้อมกัน

เราพบว่าการใช้ Kubernetes `Service` มาตรฐาน (Round-Robin) หรือ Ingress ทั่วไปทำให้เกิดปัญหาคอขวดและความเสี่ยงด้านความปลอดภัย 4 ประการ:
- **KV-Cache Blindness:** Load Balancer แบบดั้งเดิมไม่ทราบว่า Pod ใดมี `vllm:kv_cache_usage_perc` เกือบเต็มหรือมี Prefix Cache ของ System Prompt ชุดนั้นอยู่แล้ว
- **Noisy Neighbor Starvation:** งาน Batch สามารถแย่งโควตาโทเคนและคิว `vllm:num_requests_waiting` จนทำให้ลูกค้าฝั่ง Realtime ค้าง
- **PDPA PII Compliance Risk:** ผู้ใช้ในประเทศไทยอาจส่งเลขประจำตัวประชาชน 13 หลัก หรือเบอร์โทรศัพท์เข้ามาใน Prompt ซึ่งต้องถูกแปลงเป็น `<THAI_ID_REDACTED>` และ `<THAI_PHONE_REDACTED>` ตั้งแต่อยู่ในขั้น Pre-call ก่อนบันทึกลงแคชหรือส่งเข้าโมเดล ตามมาตรฐาน **OWASP LLM Top 10 (2025)**
- **Single Point of Failure:** เมื่อเรพลิกาหลักค้างเกินกว่า 3 วินาที ต้องมีระบบตัดการเชื่อมต่อ (`stream_timeout: 3.0s`) และสลับไปใช้ `vllm-secondary-svc:8000` โดยไม่ก่อให้เกิดพายุการลองซ้ำ (Retry Storm)

---

## 2. ทางเลือกที่พิจารณา (Considered Options)

| เกณฑ์การประเมิน | Option 1: NGINX / Envoy Ingress มาตรฐาน | Option 2: พัฒนา Custom Gateway เองทั้งหมด | Option 3 (ที่เลือก): `LiteLLM Proxy` + K8s Gateway API Inference Extension (`EPP`) |
| :--- | :---: | :---: | :---: |
| **Multi-tenant Virtual Keys & RPM/TPM Limits** | ไม่รองรับ (นับโทเคนไม่ได้) | ต้องเขียนโค้ดและดูแลฐานข้อมูลเอง | **รองรับในตัว (ผ่าน PostgreSQL + Redis)** |
| **PDPA PII Masking (Thai 13-digit ID)** | ไม่รองรับในระดับ Payload JSON | รองรับแต่ต้องเขียนไปป์ไลน์เองทั้งหมด | **รองรับผ่าน Pre-call Guardrail Hook** |
| **KV-Cache & Prefix-Cache Aware Routing** | ไม่รองรับ (Round-Robin/Least-Conn) | ซับซ้อนมากในการดึง Metrics เอง | **รองรับผ่าน `InferencePool`, `InferenceModel`, และ `EPP`** |
| **Automated Stream Timeout & Failover** | จับได้เฉพาะ TCP/HTTP Timeout รวม | ต้องเขียน SSE Stream Wrapper เอง | **รองรับ `stream_timeout: 3.0s` + Fallback Group** |

---

## 3. การตัดสินใจ (Decision)

เราตัดสินใจเลือก **Option 3** โดยมีรายละเอียดสถาปัตยกรรมดังนี้:
1. ติดตั้ง **`LiteLLM Proxy`** ที่ `litellm-gateway-svc.ai-platform.svc.cluster.local:4000` เชื่อมต่อกับ `redis-svc:6379` (สำหรับ Rate Limit Counters และ Exact Response Cache) และ `postgres-svc:5432` (สำหรับเก็บ Virtual Keys และ Spend Logs)
2. บังคับใช้ **Pre-call PDPA PII Guardrail (`PDPAPIIMasker`)** เพื่อตรวจจับและปิดบังเลขบัตรประชาชนไทย 13 หลัก (`<THAI_ID_REDACTED>`) และหมายเลขโทรศัพท์มือถือไทย (`<THAI_PHONE_REDACTED>`) ก่อนขั้นตอน Cache Lookup และ Model Routing
3. ตั้งค่า **`stream_timeout: 3.0s`**, `num_retries: 0`, และ `fallbacks: [{"qwen2.5-7b": ["qwen2.5-7b-secondary"]}, {"qwen2.5-7b-batch": ["qwen2.5-7b-secondary"]}]` เพื่อสลับจาก `vllm-primary-svc:8000` ไปยัง `vllm-secondary-svc:8000` ทันทีภายใน `< 3.5 วินาที` โดยไม่เสียเวลารอ Timeout ซ้ำอีกรอบก่อน Fallback
4. กำหนดนิยาม **`InferencePool` (`vllm-qwen-pool`)** และ **`InferenceModel`** แยกระดับความสำคัญระหว่าง `Critical` (`realtime-team`) และ `Sheddable` (`batch-team`) เพื่อให้ **Endpoint Picker (EPP)** จัดเส้นทางตามค่า `vllm:kv_cache_usage_perc` และ `vllm:num_requests_waiting` โดยแยก Label ของ Warm-Standby (`vllm-secondary`) ออกจาก Pool หลักเพื่อป้องกันไม่ให้ EPP ผสมทราฟฟิกลงเครื่องสำรอง DR โดยพลการ
5. จัดการ Secret (`LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `DATABASE_URL`) นอก Git ผ่าน `labs/m4-gateway/.env.example` → `kubectl create secret` และใช้ Kubernetes Init Job (`litellm-init-virtual-keys`) เพื่อออก Virtual Keys ของ `realtime-team` และ `batch-team` อย่างอัตโนมัติ

---

## 4. ผลกระทบและการส่งมอบงาน (Consequences & M4 → M5 Handoff)

- **ข้อดี:** ป้องกันข้อมูลส่วนบุคคลรั่วไหลตามกฎหมาย PDPA ได้ 100%, ลดภาระ GPU ด้วย Redis Cache, และรับประกันว่าเมื่อเรพลิกาหลักล่ม ทราฟฟิกจะสลับไปยังเรพลิกาสำรองภายในเวลา `< 3.5 วินาที`
- **ข้อควรระวัง:** ต้องมอนิเตอร์ความพร้อมใช้งานของ `redis-svc:6379` และตั้งค่าให้ Gateway ทำงานต่อได้หาก Redis ล่มชั่วคราว (Fail-open สำหรับ Cache แต่ยังบังคับใช้ In-memory Rate Limit สำรอง)
