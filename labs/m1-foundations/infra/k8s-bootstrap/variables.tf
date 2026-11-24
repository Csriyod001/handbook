variable "kubeconfig_path" {
  description = "Path to kubeconfig written by Stage 1 Kind cluster (defaults to ../ai-platform-local-config)"
  type        = string
  default     = "../ai-platform-local-config"
}

variable "kubeconfig_context" {
  description = "Kubeconfig context name for Kind cluster"
  type        = string
  default     = "kind-ai-platform-local"
}

variable "k8s_namespace" {
  description = "Canonical primary Kubernetes namespace"
  type        = string
  default     = "ai-platform"
}

variable "monitoring_namespace" {
  description = "Canonical monitoring namespace"
  type        = string
  default     = "monitoring"
}

variable "gpu_operator_namespace" {
  description = "Canonical GPU operator namespace"
  type        = string
  default     = "gpu-operator"
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
