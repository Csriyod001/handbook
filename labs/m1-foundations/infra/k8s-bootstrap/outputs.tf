output "namespaces" {
  description = "Bootstrapped Kubernetes namespaces"
  value = [
    kubernetes_namespace.ai_platform.metadata[0].name,
    kubernetes_namespace.monitoring.metadata[0].name,
    kubernetes_namespace.gpu_operator.metadata[0].name,
  ]
}

output "model_cache_pvc" {
  description = "Provisioned Hugging Face shared cache PVC"
  value       = kubernetes_persistent_volume_claim.hf_model_cache_pvc.metadata[0].name
}
