# ADR-001: Container Packaging, Runtime Security, and Model Weight Caching Strategy

- **Status:** Accepted
- **Date:** 2026-11-11
- **Owner:** AI Platform & Infrastructure Engineering Team
- **Related Namespace / Cluster:** `ai-platform` on `ai-platform-local` (and Cloud L4 Production)

---

## 1. Context & Problem Statement
ทีมของเรากำลังสร้างแพลตฟอร์มกลางสำหรับรันบริการ AI (`ai-inference-service:1.0.0` และ `vLLM` serving pods บนพอร์ต `8000`) บน Kubernetes ปัญหาที่พบจากรูปแบบเดิมคือ:
1. การรวมไฟล์ไลบรารีขนาดใหญ่และไฟล์โมเดลไว้ใน Single-stage Docker Image ทำให้อิมเมจมีขนาด >1.1 GB ถึง 15 GB ส่งผลให้เวลา Cold-start ตอนขยายจำนวนพอดช้าเกิน 3 นาที
2. คอนเทนเนอร์เดิมรันด้วยสิทธิ์ `root` (`UID 0`) และเขียนไฟล์แคชลงใน Root Filesystem ซึ่งไม่ผ่านเกณฑ์ความปลอดภัยของสถาบันการเงิน (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`)
3. เมื่อเกิดโหลดพุ่งสูงพร้อมกัน เซิร์ฟเวอร์ไม่มีการจำกัดคิวทำให้เกิดอาการค้างและล่มแบบลูกโซ่ (Cascading Timeout & OOM Failure)

---

## 2. Options Considered

| เกณฑ์การประเมิน | Option A: Monolithic Image (Bake โมเดลและ Dependencies ใน Stage เดียว) | Option B: InitContainer ดึงโมเดลจาก Object Storage ทุกครั้งที่สร้าง Pod | Option C (ที่เลือก): Multi-Stage `uv` Image + Shared `HF_HOME` Volume Cache (`PVC`/`HostPath`) |
| :--- | :--- | :--- | :--- |
| **ขนาด Container Image** | 1.1 GB – 16.5 GB (ใหญ่มาก) | ~215 MB | **~215 MB** |
| **เวลา Cold-Start เมื่อรีสตาร์ท/Scale-up** | 180–240 วินาที (เมื่อโหนดยังไม่มีอิมเมจ) | 45–90 วินาที (โหลดผ่านเครือข่ายทุกครั้ง) | **~9 วินาที (ดึง Image + อ่านไฟล์) / ~35–75 วินาที (รวมเวลา init vLLM CUDA Graph)** |
| **เวลา Rebuild เมื่อแก้โค้ด Python** | ~28.4 วินาที | ~2.0 วินาที | **~1.8 วินาที** (`uv` + Layer Caching) |
| **ความเข้ากันได้กับ `readOnlyRootFilesystem`** | พังตอนรัน (`OSError: Read-only file system`) | ต้องตั้งค่า Volume เพิ่ม | **รองรับ 100%** (แยก `/tmp` และ `/cache/huggingface`) |

---

## 3. Decision
เราตัดสินใจเลือก **Option C** โดยกำหนดมาตรฐานบังคับสำหรับทุกบริการใน Namespace `ai-platform` ดังนี้:
1. ใช้ **Multi-stage `Dockerfile`** ร่วมกับ **`uv`** (`UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`) คัดลอกเฉพาะ `pyproject.toml` ก่อนซอร์สโค้ดสร้างอิมเมจ `ai-inference-service:1.0.0` (พอร์ต `8000`) และรันด้วยผู้ใช้ `appuser` (`UID 10001`)
2. กำหนด `HF_HOME=/cache/huggingface` (และ `VLLM_CACHE_ROOT=/tmp/vllm-cache`) เสมอ เพื่อให้ทำงานได้ภายใต้ `readOnlyRootFilesystem: true` โดยไม่ต้องแก้ไขสิทธิ์ใน `/root` และผูกเข้ากับ `PersistentVolumeClaim` ชื่อ `hf-model-cache-pvc` (เชื่อมโยงกับ `/tmp/ai-infra-hf-cache` บน Local Kind หรือ Host NVMe / RWX Storage บน Cloud)
3. บังคับใช้ **Bounded Semaphore Queue** ที่คืนค่า `HTTP 429 Too Many Requests` เมื่อคิวเต็ม และแยก `/healthz` (Liveness) ออกจาก `/readyz` (Readiness)

---

## 4. Consequences (ข้อดีและสิ่งที่ต้องแลก)
- **ข้อดี (Positive):** ลดขนาดอิมเมจลง >80%, ลดเวลา Cold-start เหลือระดับวินาที, ผ่านการสแกนความปลอดภัยด้วย `Trivy` (0 Critical CVEs), และป้องกันพอดล่มเมื่อโหลดพุ่ง
- **ข้อเสีย/สิ่งที่ต้องจัดการเพิ่ม (Negative & Mitigation):** ต้องมีขั้นตอนจัดการพื้นที่ของโวลุ่มแคช (`hf-model-cache-pvc`) ไม่ให้เต็มเมื่อมีการเปลี่ยนเวอร์ชันโมเดลหลายรุ่น ซึ่งเราจัดการด้วยการสร้างโครงสร้างโวลุ่มผ่านโค้ด OpenTofu ให้ตรวจสอบและล้างแคชรุ่นเก่าได้
