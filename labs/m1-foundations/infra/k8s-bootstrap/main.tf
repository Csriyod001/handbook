# ==============================================================================
# Stage 2 OpenTofu: Bootstrap Canonical Namespaces & Shared HF_HOME PVC
# Run AFTER Stage 1 (`../`) creates `kind_cluster.ai_platform_local`.
# ==============================================================================

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kubeconfig_context
}

resource "kubernetes_namespace" "ai_platform" {
  metadata {
    name = var.k8s_namespace
    labels = {
      "app.kubernetes.io/part-of"    = "ai-infra-handbook"
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = var.monitoring_namespace
    labels = {
      "app.kubernetes.io/part-of"    = "ai-infra-handbook"
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "kubernetes_namespace" "gpu_operator" {
  metadata {
    name = var.gpu_operator_namespace
    labels = {
      "app.kubernetes.io/part-of"    = "ai-infra-handbook"
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "kubernetes_persistent_volume" "hf_model_cache_pv" {
  metadata {
    name = "hf-model-cache-pv"
  }
  spec {
    capacity = {
      storage = "20Gi"
    }
    access_modes                     = ["ReadWriteMany"]
    persistent_volume_reclaim_policy = "Retain"
    storage_class_name               = "standard"
    persistent_volume_source {
      host_path {
        path = var.container_hf_home_path
        type = "DirectoryOrCreate"
      }
    }
  }
}

resource "kubernetes_persistent_volume_claim" "hf_model_cache_pvc" {
  metadata {
    name      = var.model_cache_pvc_name
    namespace = kubernetes_namespace.ai_platform.metadata[0].name
  }
  spec {
    access_modes       = ["ReadWriteMany"]
    storage_class_name = "standard"
    volume_name        = kubernetes_persistent_volume.hf_model_cache_pv.metadata[0].name
    resources {
      requests = {
        storage = "20Gi"
      }
    }
  }
}
