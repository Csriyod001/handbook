# Blameless Postmortem (`PM-2026-1111`): เหตุการณ์ TTFT p95 พุ่งสูงช่วงพีคจากการทำลาย Prefix Cache

- **รหัสเหตุการณ์:** `PM-2026-1111`
- **ชื่อเหตุการณ์:** ค่าความหน่วง TTFT p95 พุ่งสูงถึง `2,950 ms` จากการแทรก Dynamic Timestamp ที่ส่วนต้นของ System Prompt ร่วมกับทราฟฟิกพุ่งกระชาก 3 เท่า
- **วันที่เกิดเหตุ:** `2026-11-11` เวลา `10:12 – 10:26 น.` (รวมระยะเวลา `14 นาที`)
- **ระดับความรุนแรง:** `SEV-2` (มี Latency SLO Breach แต่ Error Rate คงที่ `0%` ด้วย Gateway Fallback)
- **ผู้จัดทำ:** AI Platform SRE Team (Blameless Review)
- **Runbook ที่ใช้งาน:** [RB-AI-005](runbook-kvcache-saturation-and-high-ttft.md)

---

## 1. สรุปผลกระทบ (Executive Summary & Customer Impact)

ระหว่างเวลา `10:12 – 10:26 น.` คำขอจากกลุ่มผู้ใช้งานเรียลไทม์ (`realtime-team`) จำนวน **8.4%** ประสบปัญหาค่า Time-to-First-Token (**TTFT p95**) พุ่งสูงถึง **2,950 ms** (เกินเพดาน SLO `< 800 ms`) และมีการเผาผลาญ Error Budget ชั่วคราวที่อัตรา Burn Rate สูงกว่า `14.4x` ส่งผลให้เกิด `VLLMPreemptionThrashingCritical` บนคลัสเตอร์ `vllm-primary-svc` อย่างไรก็ตาม **ไม่มีคำขอที่ล้มเหลวเป็น HTTP 5xx** เนื่องจาก:
1. `LiteLLM Proxy` ตัดสตรีมเกินเวลาและ Failover ไปยัง `vllm-secondary-svc` ได้ทันตามนโยบาย `stream_timeout: 3.0s`
2. `KEDA ScaledObject` สเกลพอดจาก `1 -> 3` ตัวได้อย่างรวดเร็วด้วย Shared Volume Cache (`hf-model-cache-pvc` -> `HF_HOME=/cache/huggingface`)

---

## 2. ลำดับเหตุการณ์โดยละเอียด (Timeline of Events)

| เวลา (ICT) | เหตุการณ์ (Event) | สัญญาณตรวจวัด (Telemetry / Action) |
| :--- | :--- | :--- |
| **10:12:00** | ทีม AI App Deploy โค้ดเวอร์ชันใหม่ที่แทรก `Current Time: 2026-11-11 10:12:01.492` ไว้ที่ **บรรทัดแรกสุด** ของ System Prompt (ความยาว 2,048 โทเคน) | Production Deployment Rollout Completed |
| **10:14:00** | อัตรา Prefix Cache Hit (`sum(rate(vllm:prefix_cache_hits_total[5m])) / clamp_min(sum(rate(vllm:prefix_cache_queries_total[5m])), 1e-9)`) ร่วงจาก `89.4%` เหลือ **`0.0%`** ทันที | Alert `VLLMPrefixCacheHitDropWarning` pending |
| **10:15:00** | GPU ต้องคำนวณ Prefill เต็ม 2,048 โทเคนทุกคำขอ ทำให้ `vllm:kv_cache_usage_perc` พุ่งจาก `0.32` แตะ **`0.94`**, คิวรอ (`vllm:num_requests_waiting`) พุ่งเป็น `14`, และเกิด Recompute (`vllm:num_preemptions_total`) | `p95 TTFT = 2,950 ms`, `VLLMKVCacheSaturationWarning` Firing |
| **10:15:30** | KEDA ประเมินจากสูตร $\max(1, \lceil 14/5 \rceil, \lceil 1 \times 0.94/0.80 \rceil) = 3$ สั่งขยาย `deployment/vllm-primary` เป็น **3 พอด** ทันที | `kubectl get hpa` Target Replicas `1 -> 3` |
| **10:15:40** | พอดใหม่ทั้ง 2 ตัวเมานต์แคชน้ำหนักโมเดลจาก `hf-model-cache-pvc` (`HF_HOME=/cache/huggingface`) พร้อมรับทราฟฟิกโดยไม่ต้องโหลดจาก Hub ซ้ำ (~9s บน Mock/Sim; ~35–75s บน Cloud L4 GPU) | Pods Ready; Queue drain begins |
| **10:22:00** | วิศวกรเวรปฏิบัติตาม `RB-AI-005` ตรวจกราฟ Grafana Panel 5 (APC Hit Ratio) และแจ้งทีม AI App ให้ย้าย Timestamp ไปท้าย User Message | Mitigation Rollout (`Prompt Order Fix`) |
| **10:26:00** | อัตรา Prefix Cache Hit ฟื้นกลับมาที่ **`89.1%`**, KV-Cache เฉลี่ยลดลงเหลือ **`0.41`**, และ `TTFT p95` กลับสู่ `440 ms` | Incident Resolved |

---

## 3. การวิเคราะห์หาสาเหตุรากเหง้า (5 Whys Root Cause Analysis)

1. **ทำไม `TTFT p95` ถึงพุ่งทะลุเกณฑ์ 800 ms จนแตะ 2,950 ms?**  
   เพราะ GPU ต้องเสียเวลาทำ Compute Prefill ซ้ำทั้ง 2,048 โทเคนของ System Prompt ในทุกคำขอ จนคิวรอสะสม (`14 requests`) และ KV-Cache เต็ม `94%` จนเกิด Preemption (`RECOMPUTE`)
2. **ทำไม GPU ต้องคำนวณ Prefill System Prompt ใหม่ทุกครั้งทั้งที่เปิด Automatic Prefix Caching (APC)?**  
   เพราะ `vLLM` V1 Prefix Cache Hit Rate ร่วงลงเหลือ `0.0%`
3. **ทำไม Prefix Cache Hit ถึงเป็น `0.0%` ทั้งที่ข้อความหลักของ System Prompt เหมือนเดิมทุกประการ?**  
   เพราะการแฮชบล็อกใน `vLLM` V1 คำนวณแบบลูกโซ่ ($\text{Hash}_i = \text{SHA256}(\text{Hash}_{i-1} \parallel \text{Tokens}_i)$) ทันทีที่โทเคนแรกใน `Block 0` เปลี่ยนแปลง ค่าแฮชของทุกบล็อกที่ตามมา (ทั้ง 128 บล็อก) จะไม่ตรงกับแคชเดิมอีกเลย
4. **ทำไมโทเคนใน `Block 0` จึงเปลี่ยนทุกคำขอ?**  
   เพราะการอัปเดตฝั่งแอปพลิเคชันนำสตริง `Current Time` ที่มีค่าระดับมิลลิวินาทีไปวางต่อหัว (Prepend) ไว้ก่อนข้อความ System Prompt มาตรฐาน
5. **ทำไมข้อผิดพลาดนี้จึงหลุดรอดการตรวจสอบก่อนขึ้น Production?**  
   เพราะการทดสอบใน CI เดิมตรวจเฉพาะ Functional Accuracy ของคำตอบ ไม่ได้รัน Regression Assert ว่า `prefix_cache_hit_tokens > 0` บน Prompt ที่มี System Prompt ร่วมกัน

---

## 4. สิ่งที่ทำได้ดี vs จุดที่ต้องปรับปรุง (What Went Well / Lessons Learned)

- **What Went Well:**
  - `KEDA ScaledObject` ตอบสนองด้วย dual-trigger (`vllm:num_requests_waiting` & `vllm:kv_cache_usage_perc`) ภายในไม่ถึง 30 วินาที
  - การผูก `hf-model-cache-pvc` (`HF_HOME=/cache/huggingface`) ทำให้พอดใหม่ข้ามการดาวน์โหลดจาก Hub 100% (`<10s` บน Mock / `~35–75s` บน GPU vs `~195s+` เมื่อโหลดซ้ำ)
  - `LiteLLM` failover + `EPP` load shedding ช่วยให้ `realtime-team` ไม่ได้รับ HTTP 5xx
- **Where We Got Lucky / Gaps Closed:**
  - เดิม Alert `VLLMHighTTFTBurnRateCritical` เช็กเฉพาะหน้าต่าง 5 นาทีเดียว และ `clamp_min(..., 1)` ทำให้ค่า Hit Ratio เพี้ยนเมื่อทราฟฟิกเบาบาง ปัจจุบันแก้ไขใน [prometheus-alert-rules.yaml](../prometheus-alert-rules.yaml) ให้ใช้ Multi-Window (`5m` & `1h`) + `clamp_min(..., 1e-9)` แล้ว

---

## 5. แผนดำเนินการป้องกันไม่ให้เกิดซ้ำ (Action Items)

| ลำดับ | แนวทางแก้ไข (Action Item) | ผู้รับผิดชอบ | สถานะ |
| :---: | :--- | :--- | :--- |
| 1 | กำหนดมาตรฐาน **Static Prefix First:** ห้ามวางตัวแปร Timestamp, UUID, Session ID ไว้ก่อน System Prompt (ต้องต่อท้าย User Turn เท่านั้น) | AI App Team | **Completed** |
| 2 | เปิดใช้งาน Alert `VLLMPrefixCacheHitDropWarning` พร้อมเงื่อนไข active traffic guard (`queries > 0`) และ Multi-Window Burn-Rate Alerts | AI SRE Team | **Completed** |
| 3 | เพิ่มการทดสอบ Automated APC Cache Hit (`prefix_cache_hit_tokens > 0`) ใน CI Pipeline ทุกครั้งที่มีการแก้ไข Prompt Template | Platform QA | **In Progress** |
