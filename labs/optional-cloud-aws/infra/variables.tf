variable "aws_region" {
  description = "AWS region for cost-optimized L4 GPU Spot availability (us-east-1 is cheapest)"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Resource naming prefix"
  type        = string
  default     = "ai-infra-handbook"
}

variable "alert_email" {
  description = "Email address for AWS Budgets cost threshold notifications ($5, $15, $25)"
  type        = string
  default     = "replace-with-your-email@example.com"

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be a valid email address."
  }
}

variable "monthly_budget_limit_usd" {
  description = "Monthly AWS budget cap in USD (enforced <= $30 by guardrail)"
  type        = number
  default     = 30

  validation {
    condition     = var.monthly_budget_limit_usd >= 5 && var.monthly_budget_limit_usd <= 30
    error_message = "monthly_budget_limit_usd must stay within $5 - $30 USD."
  }
}

variable "enable_gpu_ec2" {
  description = "Toggle provisioning of 1x g6.xlarge Spot NVIDIA L4 instance with Dead-Man's Switch"
  type        = bool
  default     = false
}

variable "gpu_instance_type" {
  description = "Approved EC2 GPU instance type (restricted to g6.xlarge 24GB L4)"
  type        = string
  default     = "g6.xlarge"

  validation {
    condition     = var.gpu_instance_type == "g6.xlarge"
    error_message = "Only g6.xlarge (1x NVIDIA L4 24GB) is allowed under the $10-$30 budget policy."
  }
}

variable "use_spot_instance" {
  description = "Use EC2 Spot pricing (~$0.45-$0.59/hr in us-east-1) instead of On-Demand"
  type        = bool
  default     = true
}

variable "auto_terminate_minutes" {
  description = "Dead-Man's Switch timeout (minutes) before OS triggers shutdown -> instance termination"
  type        = number
  default     = 180

  validation {
    condition     = var.auto_terminate_minutes >= 30 && var.auto_terminate_minutes <= 180
    error_message = "auto_terminate_minutes must be between 30 and 180 minutes."
  }
}

variable "enable_vpc_and_eks_blueprint" {
  description = "Documentation toggle only: keep false on $10-$30 budget (EKS Control Plane $0.10/hr + NAT GW drain credits fast)"
  type        = bool
  default     = false

  validation {
    condition     = var.enable_vpc_and_eks_blueprint == false
    error_message = "EKS + NAT Gateway exceeds the $10-$30 self-study budget; use EC2 g6.xlarge + k3s instead."
  }
}
