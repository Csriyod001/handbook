output "s3_model_cache_bucket" {
  description = "Private S3 bucket for Hugging Face model weight caching"
  value       = aws_s3_bucket.model_cache.bucket
}

output "ecr_repository_urls" {
  description = "Private ECR repository URLs for container images"
  value = {
    ai_inference_service = aws_ecr_repository.ai_inference_service.repository_url
    mock_vllm_server     = aws_ecr_repository.mock_vllm_server.repository_url
  }
}

output "gpu_ec2_instance_id" {
  description = "Active g6.xlarge Spot instance ID (connect via: aws ssm start-session --target <id>)"
  value       = var.enable_gpu_ec2 ? aws_instance.l4_gpu_lab[0].id : "disabled (enable_gpu_ec2=false)"
}
