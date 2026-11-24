# Portability, Offline Reading & Quickstart Guide

คู่มือนี้ช่วยให้คุณเปิดอ่านหนังสือและรันชุดแล็บของ **AI Infrastructure & Platform Engineering Handbook (2026 Edition)** ได้ทันทีในทุกสภาพแวดล้อม ไม่ว่าจะเป็น **Offline Reading Bundle** (`.tar.gz` / `.zip`), **VS Code DevContainer**, **Docker Compose**, หรือ **WSL2 บนเครื่อง HP Victus (32GB RAM + RTX 4050 6GB)**

---

## 1. Portable Offline Reading Packages (`.tar.gz` & `.zip`)

คุณสามารถสร้างชุดหนังสือแบบพกพาที่รวม [`index.html`](./index.html), [`dist/AI_Infra_Interactive_Handbook.html`](./dist/AI_Infra_Interactive_Handbook.html) (พร้อม asset แบบ offline ใน [`dist/assets/tailwindcss.min.js`](./dist/assets/tailwindcss.min.js)), [`dist/FULL_MANUSCRIPT.md`](./dist/FULL_MANUSCRIPT.md), และชุดแล็บทั้งหมดไว้ในไฟล์เดียว:

```bash
python3 scripts/make package
python3 scripts/make verify-archive
```

### 1.1 การแตกไฟล์และเปิดอ่านแบบ Offline ตามระบบปฏิบัติการ

#### Linux / WSL2
```bash
tar -xzf dist/ai-infra-handbook-portable.tar.gz -C ~/ai-infra-offline
cd ~/ai-infra-offline
xdg-open index.html
```

#### macOS
```bash
tar -xzf dist/ai-infra-handbook-portable.tar.gz -C ~/ai-infra-offline
cd ~/ai-infra-offline
open index.html
```

#### Windows PowerShell
```powershell
Expand-Archive -Path .\dist\ai-infra-handbook-portable.zip -DestinationPath $HOME\ai-infra-offline -Force
Start-Process "$HOME\ai-infra-offline\index.html"
```

---

## 2. Containerized Lab Environment (DevContainer & Docker Compose)

หากไม่ต้องการติดตั้งเครื่องมือ (`uv`, `kubectl`, `kind`, `helm`, `tofu`, `trivy`, `promtool`) ลงบนเครื่องหลักทีละตัว สามารถใช้สภาพแวดล้อมแบบคอนเทนเนอร์ที่เราเตรียมไว้ใน [`.devcontainer/devcontainer.json`](./.devcontainer/devcontainer.json) และ [`docker-compose.lab.yml`](./docker-compose.lab.yml) ซึ่งเชื่อมต่อ Docker Daemon ผ่าน `/var/run/docker.sock` (Docker-outside-of-Docker) และแชร์แคชโมเดล `/tmp/ai-infra-hf-cache` เข้าไปยัง `/cache/huggingface` อัตโนมัติ

### 2.1 รันผ่าน VS Code DevContainer
1. เปิดโฟลเดอร์โปรเจกต์ใน VS Code พร้อมส่วนขยาย Dev Containers
2. เลือก **Reopen in Container** (ระบบจะรัน `python3 scripts/make verify-static` ให้อัตโนมัติหลังสร้างคอนเทนเนอร์เสร็จ)

### 2.2 รันผ่าน Docker Compose
```bash
mkdir -p /tmp/ai-infra-hf-cache
docker compose -f docker-compose.lab.yml run --rm --service-ports lab
```

ตรวจสอบความถูกต้องของคอนฟิกคอนเทนเนอร์แบบออฟไลน์ได้ตลอดเวลา:
```bash
python3 scripts/make verify-container
```

---

## 3. Standard Ports & Shared Cache Volumes

บริการทุกตัวในชุดแล็บใช้พอร์ตและโวลุ่มแคชมาตรฐานตาม [`SPEC_AND_STYLE_GUIDE.md`](./SPEC_AND_STYLE_GUIDE.md):

| Component | Port | Host Volume / Socket Mount | หน้าที่หลัก |
| :--- | :---: | :--- | :--- |
| **vLLM / Inference Service** | `8000` | `/tmp/ai-infra-hf-cache` → `/cache/huggingface` | ให้บริการ `/v1/chat/completions`, `/healthz`, `/readyz`, `/metrics` |
| **LiteLLM AI Gateway** | `4000` | — | Virtual Keys, Rate Limit, PDPA Masking, Auto Failover |
| **Grafana Dashboard** | `3000` | — | แดชบอร์ด vLLM V1 & DCGM GPU Telemetry |
| **Prometheus Server** | `9090` | — | จัดเก็บ Metrics และประเมิน Alert Rules / KEDA Queries |
| **Docker Socket (DooD)** | — | `/var/run/docker.sock` → `/var/run/docker.sock` | ให้คอนเทนเนอร์ DevContainer/Compose สร้าง `kind` cluster ได้ |

---

## 4. Portable Verification Commands (`Makefile` & `scripts/make`)

บนเครื่อง Linux/WSL2 ที่ยังไม่ได้ติดตั้ง GNU `make` สามารถใช้ตัวรันสำรอง `scripts/make` แทนคำสั่ง `make` ได้ทุกคำสั่ง:

```bash
python3 scripts/make help
python3 scripts/make check-env
python3 scripts/make verify-structure
python3 scripts/make verify-static
python3 scripts/make build-handbook
```

---

## 5. Troubleshooting (การแก้ปัญหาที่พบบ่อย)

1. **WSL2 มองเห็น RAM น้อยกว่า 16GB หรือ OOM ระหว่างรัน Kind:**
   ตรวจสอบ `%UserProfile%\.wslconfig` ฝั่ง Windows (สำหรับเครื่อง 32GB เช่น HP Victus ตั้ง `memory=22GB`, `processors=10`, `swap=4GB`) แล้วรัน `wsl --shutdown` ตามขั้นตอนใน [`chapters/00-onboarding-and-setup.md`](./chapters/00-onboarding-and-setup.md)
2. **Permission Denied ที่ `/var/run/docker.sock` หรือ `/tmp/ai-infra-hf-cache`:**
   ตรวจสอบสิทธิ์กลุ่ม Docker (`sudo usermod -aG docker "$USER"`) และรัน `python3 scripts/make init-cache`
3. **เปิด `index.html` แล้วสไตล์ไม่ขึ้นเมื่อไม่มีอินเทอร์เน็ต:**
   ตรวจสอบว่าแตกไฟล์ครบทั้งโฟลเดอร์ `dist/assets/tailwindcss.min.js` (ห้ามคัดลอกเฉพาะไฟล์ `.html` ออกมาเดี่ยวๆ)
