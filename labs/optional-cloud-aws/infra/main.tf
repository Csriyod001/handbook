# ==============================================================================
# Optional AWS Cloud Track: Non-GPU Platform Infra + Optional g6.xlarge Spot L4
# Default (enable_gpu_ec2 = false): Private S3 Model Cache + ECR + IAM + Budgets
# GPU Mode (enable_gpu_ec2 = true): 1x g6.xlarge Spot + SSM + 250GB NVMe + k3s
#                                   + Dead-Man's Switch (auto-terminate <= 180m)
# ==============================================================================

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "ai-infra-handbook"
      ManagedBy = "opentofu"
    }
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# 1. Private S3 Model Weights Cache (eliminates repeated Hugging Face downloads)
resource "aws_s3_bucket" "model_cache" {
  bucket        = "${var.project_prefix}-hf-cache-${random_id.bucket_suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "model_cache" {
  bucket                  = aws_s3_bucket.model_cache.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "model_cache" {
  bucket = aws_s3_bucket.model_cache.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "model_cache" {
  bucket = aws_s3_bucket.model_cache.id
  rule {
    id     = "expire-old-cache"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}

# 2. Private ECR Repositories (with image scan on push and retention cap)
resource "aws_ecr_repository" "ai_inference_service" {
  name                 = "${var.project_prefix}/ai-inference-service"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "mock_vllm_server" {
  name                 = "${var.project_prefix}/mock-vllm-server"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "keep_last_five" {
  for_each = toset([
    aws_ecr_repository.ai_inference_service.name,
    aws_ecr_repository.mock_vllm_server.name,
  ])
  repository = each.value
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 5 images to stay within free/low-cost storage"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# 3. Least-Privilege IAM Role for SSM Session Manager + S3 Model Cache + ECR Pull
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gpu_node_role" {
  name               = "${var.project_prefix}-gpu-node-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.gpu_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  role       = aws_iam_role.gpu_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

data "aws_iam_policy_document" "s3_cache_rw" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.model_cache.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.model_cache.arn}/*"]
  }
}

resource "aws_iam_role_policy" "s3_cache_access" {
  name   = "${var.project_prefix}-s3-cache-policy"
  role   = aws_iam_role.gpu_node_role.id
  policy = data.aws_iam_policy_document.s3_cache_rw.json
}

resource "aws_iam_instance_profile" "gpu_node_profile" {
  name = "${var.project_prefix}-gpu-node-profile"
  role = aws_iam_role.gpu_node_role.name
}

# 4. AWS Budgets Cost Alerting ($5 / $15 / $25 thresholds on $30 cap)
resource "aws_budgets_budget" "monthly_cap" {
  name         = "${var.project_prefix}-monthly-cap"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 17
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 83
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

# 5. Optional 1x g6.xlarge Spot NVIDIA L4 Node (enabled only when enable_gpu_ec2 = true)
data "aws_ssm_parameter" "dlami_ubuntu_gpu" {
  count = var.enable_gpu_ec2 ? 1 : 0
  name  = "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-24.04/latest/ami-id"
}

resource "aws_security_group" "gpu_ssm_only" {
  count       = var.enable_gpu_ec2 ? 1 : 0
  name        = "${var.project_prefix}-gpu-ssm-only"
  description = "Zero inbound SSH ports; access via AWS SSM Session Manager + port-forwarding"

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "l4_gpu_lab" {
  count                                = var.enable_gpu_ec2 ? 1 : 0
  ami                                  = data.aws_ssm_parameter.dlami_ubuntu_gpu[0].value
  instance_type                        = var.gpu_instance_type
  iam_instance_profile                 = aws_iam_instance_profile.gpu_node_profile.name
  vpc_security_group_ids               = [aws_security_group.gpu_ssm_only[0].id]
  instance_initiated_shutdown_behavior = "terminate"

  dynamic "instance_market_options" {
    for_each = var.use_spot_instance ? [1] : []
    content {
      market_type = "spot"
      spot_options {
        spot_instance_type             = "one-time"
        instance_interruption_behavior = "terminate"
      }
    }
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 60
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  user_data = <<-EOF
    #!/usr/bin/env bash
    set -euo pipefail
    # 1. Dead-Man's Switch: trigger OS shutdown -> AWS terminates instance automatically
    shutdown -h +${var.auto_terminate_minutes} "Auto-terminate guardrail triggered"

    # 2. Format & mount free 250GB NVMe instance store at /cache/huggingface (Nitro-safe root detection)
    mkdir -p /cache/huggingface
    ROOT_SRC=$(findmnt -no SOURCE /)
    ROOT_DISK="/dev/$(lsblk -no PKNAME "$ROOT_SRC" 2>/dev/null | head -n 1)"
    NVME_DEV=$(lsblk -dpno NAME,TYPE,FSTYPE,MOUNTPOINT | awk -v root="$ROOT_DISK" '$2=="disk" && $1!=root && $3=="" && $4=="" {print $1; exit}')
    if [ -n "$NVME_DEV" ]; then
      mkfs.ext4 -F "$NVME_DEV"
      mount "$NVME_DEV" /cache/huggingface
    fi
    chown -R 10001:10001 /cache/huggingface
    chmod 0775 /cache/huggingface

    # 3. Sync cached weights from S3 (if pre-populated)
    aws s3 sync "s3://${aws_s3_bucket.model_cache.bucket}/hf-cache/" /cache/huggingface/ || true

    # 4. Install lightweight k3s + NVIDIA k8s-device-plugin for M2/M5/M6 Kubernetes GPU labs
    curl -sfL https://get.k3s.io | sh -
    until kubectl get nodes >/dev/null 2>&1; do sleep 3; done
    kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.1/deployments/static/nvidia-device-plugin.yml || true
  EOF

  tags = {
    Name = "${var.project_prefix}-l4-spot-lab"
  }
}

check "alert_email_configured" {
  assert {
    condition     = var.alert_email != "replace-with-your-email@example.com"
    error_message = "Set -var=\"alert_email=you@example.com\" before tofu apply so AWS Budgets alerts reach your inbox."
  }
}

check "aws_gpu_budget_guardrail" {
  assert {
    condition     = !var.enable_gpu_ec2 || (var.gpu_instance_type == "g6.xlarge" && var.auto_terminate_minutes <= 180 && var.monthly_budget_limit_usd <= 30)
    error_message = "AWS GPU budget guardrail violated: enforce g6.xlarge, auto_terminate_minutes <= 180, and monthly_budget_limit_usd <= 30."
  }
}
