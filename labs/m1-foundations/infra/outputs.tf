output "cluster_name" {
  description = "Provisioned Kind cluster name"
  value       = var.cluster_name
}

output "kubeconfig_path" {
  description = "Path to Kind cluster kubeconfig for Stage 2 k8s-bootstrap"
  value       = kind_cluster.ai_platform_local.kubeconfig_path
}

output "k8s_namespace" {
  description = "Primary AI platform namespace (provisioned in Stage 2 k8s-bootstrap)"
  value       = var.k8s_namespace
}

output "model_cache_pvc" {
  description = "Shared Hugging Face cache PersistentVolumeClaim name (provisioned in Stage 2)"
  value       = var.model_cache_pvc_name
}

output "cloud_gpu_profile" {
  description = "Active GPU execution policy guardrail profile (real Cloud GPU IaC: labs/optional-cloud-aws/)"
  value = {
    enabled                = var.enable_cloud_gpu_node
    gpu_sku                = var.cloud_gpu_instance_type
    auto_terminate_minutes = var.auto_terminate_minutes
  }
}
