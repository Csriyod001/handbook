# ==============================================================================
# OpenTofu Variables — Must match SPEC_AND_STYLE_GUIDE.md Canonical Values
# ==============================================================================

variable "cluster_name" {
  description = "Canonical Kind Kubernetes cluster name for local AI platform labs"
  type        = string
  default     = "ai-platform-local"

  validation {
    condition     = var.cluster_name == "ai-platform-local"
    error_message = "cluster_name must be 'ai-platform-local' to match SPEC_AND_STYLE_GUIDE.md."
  }
}

variable "k8s_namespace" {
  description = "Primary Kubernetes namespace for AI inference & gateway workloads"
  type        = string
  default     = "ai-platform"

  validation {
    condition     = var.k8s_namespace == "ai-platform"
    error_message = "k8s_namespace must be 'ai-platform' to match SPEC_AND_STYLE_GUIDE.md."
  }
}

variable "monitoring_namespace" {
  description = "Kubernetes namespace for Prometheus, Grafana, and DCGM Exporter"
  type        = string
  default     = "monitoring"
}

variable "gpu_operator_namespace" {
  description = "Kubernetes namespace for Run:ai fake-gpu-operator or NVIDIA GPU Operator"
  type        = string
  default     = "gpu-operator"
}

variable "host_hf_cache_path" {
  description = "Host directory mounted into Kind nodes for persistent Hugging Face model caching"
  type        = string
  default     = "/tmp/ai-infra-hf-cache"
}

variable "container_hf_home_path" {
  description = "Container mount path for HF_HOME inside Kind worker nodes and non-root pods"
  type        = string
  default     = "/cache/huggingface"
}

variable "model_cache_pvc_name" {
  description = "Canonical PersistentVolumeClaim name for shared Hugging Face model weights"
  type        = string
  default     = "hf-model-cache-pvc"
}

variable "enable_cloud_gpu_node" {
  description = "Toggle on-demand Cloud L4 GPU execution path (keep false for $0 Local Path)"
  type        = bool
  default     = false
}

variable "cloud_gpu_instance_type" {
  description = "Allowed Cloud GPU SKU for benchmark validation (restricted for budget control)"
  type        = string
  default     = "NVIDIA-L4-24GB"

  validation {
    condition     = contains(["NVIDIA-L4-24GB", "NVIDIA-A10G-24GB"], var.cloud_gpu_instance_type)
    error_message = "Only NVIDIA-L4-24GB or NVIDIA-A10G-24GB are allowed by cost governance policy."
  }
}

variable "auto_terminate_minutes" {
  description = "Mandatory auto-termination timer (minutes) for Cloud GPU instances to prevent runaway billing"
  type        = number
  default     = 120

  validation {
    condition     = var.auto_terminate_minutes >= 15 && var.auto_terminate_minutes <= 180
    error_message = "auto_terminate_minutes must be between 15 and 180 minutes to protect the <$10 course budget."
  }
}
