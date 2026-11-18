# ==============================================================================
# Declarative AI Infrastructure Foundation (Module 1 OpenTofu Configuration)
# Uses Guided Local State (no S3/DynamoDB lock overhead required in Week 2)
# ==============================================================================

# 1. Provision Multi-Node Local Kind Cluster with Host Model Cache extraMounts
resource "kind_cluster" "ai_platform_local" {
  name           = var.cluster_name
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
      extra_port_mappings {
        container_port = 30080
        host_port      = 8000
        protocol       = "TCP"
      }
      extra_port_mappings {
        container_port = 30400
        host_port      = 4000
        protocol       = "TCP"
      }
    }

    node {
      role = "worker"

      # tehcyx/kind assigns node labels via kubeadmConfigPatches (node.labels is not a Terraform schema field)
      kubeadm_config_patches = [
        <<-EOT
        kind: JoinConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ai.platform/node-pool=gpu-inference,run.ai/simulated-gpu-node-pool=default"
        EOT
      ]

      extra_mounts {
        host_path      = var.host_hf_cache_path
        container_path = var.container_hf_home_path
      }
    }

    node {
      role = "worker"

      kubeadm_config_patches = [
        <<-EOT
        kind: JoinConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ai.platform/node-pool=general-services"
        EOT
      ]

      extra_mounts {
        host_path      = var.host_hf_cache_path
        container_path = var.container_hf_home_path
      }
    }
  }
}

# 2. Configure Kubernetes Provider against the provisioned Kind Cluster
provider "kubernetes" {
  host                   = kind_cluster.ai_platform_local.endpoint
  client_certificate     = kind_cluster.ai_platform_local.client_certificate
  client_key             = kind_cluster.ai_platform_local.client_key
  cluster_ca_certificate = kind_cluster.ai_platform_local.cluster_ca_certificate
}

# 3. Create Canonical Namespaces (`ai-platform`, `monitoring`, `gpu-operator`)
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

# 4. Provision PersistentVolume & PersistentVolumeClaim (`hf-model-cache-pvc`)
#    wiring `/cache/huggingface` (`HF_HOME`) into non-root pods in `ai-platform`.
#    Note: On local Kind, both worker nodes mount host_hf_cache_path so ReadWriteMany
#    matches the shared node hostPath. On Multi-Node Cloud, Helm overrides/uses
#    ReadWriteOnce (node-local NVMe) or a true RWX filesystem (EFS/Filestore).
#    Module 1 OpenTofu owns this PVC; Module 2 Helm defaults modelCache.createPvc=false.
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

# 5. Cloud GPU Cost Guardrail Check (Local Kind remains free when enable_cloud_gpu_node = false;
#    Cloud L4 VM/Pod provisioning uses Ch02 Path B / Ch03 on-demand scripts guarded by this SLA)
check "cloud_gpu_cost_guardrail" {
  assert {
    condition     = !var.enable_cloud_gpu_node || (var.auto_terminate_minutes <= 180 && contains(["NVIDIA-L4-24GB", "NVIDIA-A10G-24GB"], var.cloud_gpu_instance_type))
    error_message = "Cloud GPU budget guardrail violated: enforce auto_terminate_minutes <= 180 and approved 24GB SKUs."
  }
}
