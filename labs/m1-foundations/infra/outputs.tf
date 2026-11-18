output "cluster_name" {
  description = "Provisioned Kind cluster name"
  value       = var.cluster_name
}

output "k8s_namespace" {
  description = "Primary AI platform namespace"
  value       = var.k8s_namespace
}

output "model_cache_pvc" {
  description = "Shared Hugging Face cache PersistentVolumeClaim name"
  value       = var.model_cache_pvc_name
}

output "cloud_gpu_profile" {
  description = "Active GPU execution profile and cost guardrail settings"
  value = {
    enabled                = var.enable_cloud_gpu_node
    gpu_sku                = var.cloud_gpu_instance_type
    auto_terminate_minutes = var.auto_terminate_minutes
  }
}
