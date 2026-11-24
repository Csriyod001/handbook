# ==============================================================================
# Stage 1 OpenTofu: Provision Multi-Node Local Kind Cluster (`ai-platform-local`)
# Note: Separated from Kubernetes Provider resources (see `infra/k8s-bootstrap/`)
# so `tofu plan` & `tofu apply` run cleanly on first execution without provider
# bootstrap errors. `tehcyx/kind` writes `./ai-platform-local-config` by default
# (exposed via `output "kubeconfig_path"`). Cloud GPU IaC: `labs/optional-cloud-aws/`.
# ==============================================================================

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

      # tehcyx/kind assigns node labels via kubeadmConfigPatches
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

# Policy Check Guardrail for Cloud GPU profiles (real AWS L4 provisioning: labs/optional-cloud-aws/)
check "cloud_gpu_cost_guardrail" {
  assert {
    condition     = !var.enable_cloud_gpu_node || (var.auto_terminate_minutes <= 180 && contains(["NVIDIA-L4-24GB", "NVIDIA-A10G-24GB"], var.cloud_gpu_instance_type))
    error_message = "Cloud GPU budget guardrail violated: enforce auto_terminate_minutes <= 180 and approved 24GB SKUs."
  }
}
