# ADR-002: GPU Sharing Strategy, Three-Tier Kubernetes Probes, and Zero-Downtime Rollouts

- **Status:** Accepted
- **Date:** 2026-11-11
- **Owner:** AI Platform & Infrastructure Engineering Team
- **Related Namespace / Service:** `ai-platform` (`vllm-primary-svc` on Port `8000`)

---

## 1. Context & Problem Statement
องค์กรของเรามีคลัสเตอร์ที่มีโหนดการ์ดจอ **NVIDIA L4 (24GB VRAM)** จำกัด แต่ต้องรองรับทั้งการทดสอบโมเดลขนาดเล็กหลายตัว (`Qwen/Qwen2.5-0.5B-Instruct`) และการรันโมเดลหลัก (`Qwen/Qwen2.5-7B-Instruct-AWQ`) ปัญหาที่พบคือ:
1. การ์ดจอ NVIDIA L4 (สถาปัตยกรรม Ada Lovelace) ไม่รองรับการแบ่งฮาร์ดแวร์ด้วย MIG (ซึ่งมีเฉพาะบน A30/A100/H100) หากให้แต่ละพอดของโมเดลจิ๋วจอง `nvidia.com/gpu: 1` เต็มใบ จะเกิดการสูญเปล่าของ VRAM กว่า 80%
2. เมื่อทดลองเปิด GPU Time-Slicing (`replicas: 4`) บนการ์ด 24GB โดยใช้ค่าเริ่มต้นของ `vLLM` เกิดอาการ `CUDA out of memory` ตอนเริ่มทำงานเพราะทุกพอดสร้าง CUDA Graphs แยกกัน
3. การอัปเดตเวอร์ชันด้วย Helm ทำให้เกิด `CrashLoopBackOff` ตอนโหลดโมเดลและเกิด `502 Bad Gateway` ตอนสลับพอด

---

## 2. Options Considered for GPU Sharing on NVIDIA L4

| เกณฑ์การประเมิน | Option A: Dedicated GPU (1 Pod ต่อ 1 Physical GPU) | Option B: Hardware MIG (ต้องอัปเกรดเป็นการ์ด A100 80GB) | Option C (ที่เลือกสำหรับ L4): NVIDIA Device Plugin Time-Slicing (`replicas: 4`) + `--enforce-eager` |
| :--- | :--- | :--- | :--- |
| **ค่าใช้จ่ายฮาร์ดแวร์ต่อชั่วโมง** | สูง (ต้องเช่า L4 4 ใบสำหรับ 4 บริการย่อย) | สูงมาก (~\$1.80–\$2.50/ชม.) | **ต่ำที่สุด (~\$0.60–\$0.80/ชม. บนการ์ด L4 1 ใบ)** |
| **ความหนาแน่นของบริการย่อย** | 1 Pod / GPU | 7 Pods / A100 GPU | **4 Pods / L4 GPU** |
| **การป้องกัน CUDA Graph OOM** | ไม่จำเป็น | แยกระดับฮาร์ดแวร์ | **บังคับใส่ `--enforce-eager` และ `--gpu-memory-utilization 0.20`** |

---

## 3. Decision
1. **สำหรับการแชร์การ์ดจอ L4 (Dev/Multi-model):** ใช้ `nvidia-time-slicing-config` (`replicas: 4`) คู่กับแฟล็ก `--enforce-eager` และ `--gpu-memory-utilization 0.20` เพื่อตัดภาระหน่วยความจำของ CUDA Graphs ต่อโปรเซส (~1.5 GB/pod) ส่วนบนคลัสเตอร์ Local (`kind`) ใช้ Run:ai `fake-gpu-operator` จำลอง `gpuCount=4`
2. **สำหรับการรัน Production LLM หลัก (บทที่ 3–6):** มอบหมายการ์ด L4 เต็มใบให้พอด `Qwen/Qwen2.5-7B-Instruct-AWQ` (`values-cloud-gpu-7b-awq.yaml`, `--gpu-memory-utilization 0.92`, `--enforce-eager` ปิดอยู่เพื่อใช้ CUDA Graph) เพื่อให้ได้พื้นที่ KV-Cache และ Decode Speed สูงสุด
3. **มาตรฐาน Helm Chart (`charts/ai-inference-service/`):**
   - บังคับแยก `startupProbe` (`periodSeconds: 5, failureThreshold: 36` = 180s), `readinessProbe`, และ `livenessProbe`
   - บังคับใส่ `lifecycle.preStop.exec.command: ["sh", "-c", "sleep 5"]` และ `terminationGracePeriodSeconds: 60`
   - บังคับใช้ `PriorityClass` (`ai-production-high-priority` เหนือกว่า `ai-batch-low-priority`) และผูกโวลุ่ม `hf-model-cache-pvc` เข้าที่ `HF_HOME=/cache/huggingface` (พร้อม `VLLM_CACHE_ROOT=/tmp/vllm-cache`, `createPvc: false` เมื่อใช้งานร่วมกับ OpenTofu ในบทที่ 1 หรือ `createPvc: true` + `ReadWriteOnce` บน k3s Cloud VM)
