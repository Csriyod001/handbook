# Optional AWS Cloud Platform & GPU Track (งบ \$10–\$30 USD)

โมดูลเสริมนี้ช่วยให้คุณนำทักษะ OpenTofu และ AI Infrastructure ที่ฝึกบนเครื่อง Local ไปใช้งานจริงบน **AWS Cloud** ภายใต้งบประมาณ **\$10–\$30 USD** โดยแบ่งการทำงานเป็น 2 โหมดที่สลับได้ในโค้ดชุดเดียว:
1. **Mode 1 (`enable_gpu_ec2 = false` — ค่าเริ่มต้น, ~\$0):** สร้างโครงสร้างพื้นฐานกลาง ได้แก่ Private **S3 Model Cache Bucket** (Encrypted + Block Public Access), Private **ECR Repositories**, Least-Privilege **IAM Role / SSM**, และ **AWS Budgets Alarm**
2. **Mode 2 (`enable_gpu_ec2 = true` — 1× `g6.xlarge` Spot L4):** เปิดเครื่อง **`g6.xlarge` Spot (`us-east-1`, 1× NVIDIA L4 24GB VRAM, 4 vCPU, 16 GiB RAM, ฟรี 250 GB NVMe)** พร้อม **Dead-Man's Switch** (`shutdown -h +180` + `instance_initiated_shutdown_behavior = "terminate"`) เพื่อรัน `k3s` + `vLLM` จริงได้ครบทั้ง M2, M3, M5 และ M6 ด้วยค่าใช้จ่ายรวมเพียง **~\$7–\$12 USD**

---

## 1. เหตุใดจึงใช้ `g6.xlarge` Spot + `k3s` + S3 + SSM แทน EKS?
- **EKS + NAT Gateway** มีค่า Control Plane (\$0.10/ชม.) และ NAT Gateway (\$0.045/ชม. + Data Processing) ซึ่งเปิดทิ้งไว้แค่ไม่กี่วันก็กินงบ \$10–\$20 โดยยังไม่ได้รัน GPU เลย
- **1× EC2 `g6.xlarge` Spot (`us-east-1`) + `k3s` + 250 GB NVMe Instance Store:**
  - ราคา Spot ใน `us-east-1` เฉลี่ย **~\$0.45–\$0.59/ชม.** (งบ \$10–\$30 รันได้ถึง **18–55 ชั่วโมง**)
  - เชื่อมต่อผ่าน **AWS SSM Session Manager** (ไม่ต้องเปิด Port 22 และไม่ต้องสร้าง Elastic IP ค้างบิล)
  - ดึง Model Weights จาก S3 เข้า EC2 ใน Region เดียวกันผ่าน Network ภายในได้ฟรีและเร็วกว่าโหลดจากอินเทอร์เน็ตทุกครั้ง

---

## 2. ขั้นตอนเตรียมบัญชี AWS และยื่นขอ GPU Service Quota ล่วงหน้า
> [!WARNING]
> **ข้อควรทราบเรื่อง AWS Free Plan / GCP \$300 Trial:**
> บัญชี AWS ใหม่ (ต้องเลือก **Paid Plan** เพื่อขอเพิ่ม Quota ได้; Promotional Credit ยังใช้หักยอดได้ตามเงื่อนไข) และบัญชี GCP \$300 Trial ต่างตั้งค่า **Default GPU Quota = 0** หากจะรัน `g6.xlarge` ให้ยื่นขอ Quota ตั้งแต่วันแรกใน Region `us-east-1`:

1. เปิด **AWS Budgets** แล้วตั้งงบเตือนที่ **\$5**, **\$15**, และ **\$25** (OpenTofu ของเรามี `aws_budgets_budget` ให้ด้วย)
2. เข้าหน้า **Service Quotas → Amazon EC2** (`us-east-1`) แล้วยื่นขอเพิ่มเพียง `4 vCPUs` (`g6.xlarge` 1 เครื่อง):
   - **`All G and VT Spot Instance Requests`** → ขอเพิ่มเป็น **`4`**
   - **`Running On-Demand G and VT instances`** → ขอเพิ่มเป็น **`4`** *(เผื่อ Spot ขาดตลาด)*
3. หากโดน Auto-Deny ในบัญชีใหม่ ให้ใช้งาน S3/EC2 เล็กๆ (`t3.micro`) 2–3 วัน หรือตอบ Support Case อธิบายว่า: *"Running single g6.xlarge (1x L4) for self-paced Kubernetes and vLLM inference benchmarking lab (~10-15 hours total, non-mining workload)."*

---

## 3. ตารางเทียบ Service ระหว่าง AWS กับ GCP (AWS ↔ GCP Equivalence)

| หน้าที่ใน AI Platform | AWS Service (หลักในโมดูลนี้) | GCP Service เทียบเท่า |
| :--- | :--- | :--- |
| **Model Weights Object Cache** | Amazon S3 (`Private Bucket`) | Cloud Storage (GCS) |
| **Container Registry** | Amazon ECR (`scan_on_push = true`) | Artifact Registry |
| **24GB NVIDIA L4 VM** | EC2 `g6.xlarge` (Spot, 250GB NVMe) | Compute Engine `g2-standard-8` (Spot) |
| **Workload Identity & Remote Access** | IAM Role (`IRSA` / Instance Profile) + SSM | Workload Identity + IAP Tunnel |
| **Managed Kubernetes (ระดับองค์กร)** | Amazon EKS + Karpenter | Google Kubernetes Engine (GKE Autopilot) |

---

## 4. คำสั่งใช้งาน OpenTofu
```bash
cd labs/optional-cloud-aws/infra
tofu fmt -check
tofu init -backend=false
tofu validate

# 1. สร้างเฉพาะ Non-GPU Platform Infra (S3 + ECR + IAM + Budgets)
tofu plan -var="alert_email=you@example.com"

# 2. เปิดเครื่อง GPU g6.xlarge Spot (Dead-Man's Switch 180 นาที) เมื่อ Quota อนุมัติแล้ว
tofu plan \
  -var="alert_email=you@example.com" \
  -var="enable_gpu_ec2=true" \
  -var="auto_terminate_minutes=180"

# 3. ทำลายทรัพยากรทันทีหลังเก็บผล Benchmark เสร็จ
tofu destroy -auto-approve
```
