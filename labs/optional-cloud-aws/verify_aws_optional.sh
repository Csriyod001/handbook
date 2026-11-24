#!/usr/bin/env bash
# ==============================================================================
# Optional AWS Cloud Track Verification (labs/optional-cloud-aws/verify_aws_optional.sh)
# Validates Non-GPU S3/ECR/Budgets + g6.xlarge Spot Dead-Man's Switch HCL Guardrails
# ==============================================================================
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_MODE="${VERIFY_MODE:-static}"
cd "$LAB_DIR"

echo "================================================================================"
echo "  Optional AWS Cloud Verification (MODE=${VERIFY_MODE}): S3, ECR, Budgets & g6.xlarge"
echo "================================================================================"

for f in \
  "README.md" \
  "infra/versions.tf" \
  "infra/variables.tf" \
  "infra/main.tf" \
  "infra/outputs.tf"; do
  if [ ! -f "$f" ]; then
    echo "  [FAIL] Missing required file: $f" >&2
    exit 1
  fi
  echo "  [OK] Found $f"
done

grep -q 'default     = "g6.xlarge"' infra/variables.tf
grep -q 'default     = false' infra/variables.tf
grep -q 'aws_s3_bucket_public_access_block' infra/main.tf
grep -q 'aws_ecr_repository' infra/main.tf
grep -q 'aws_budgets_budget' infra/main.tf
grep -q 'filter {}' infra/main.tf
grep -q 'instance_interruption_behavior = "terminate"' infra/main.tf
grep -q 'findmnt -no SOURCE /' infra/main.tf
grep -q 'instance_initiated_shutdown_behavior = "terminate"' infra/main.tf
grep -q 'shutdown -h +' infra/main.tf
grep -q 'check "aws_gpu_budget_guardrail"' infra/main.tf
echo "  [OK] AWS S3, ECR, Budgets & g6.xlarge Dead-Man's Switch guardrails verified"

if command -v tofu >/dev/null 2>&1; then
  (cd infra && tofu fmt -check && tofu init -backend=false >/dev/null && tofu validate)
  echo "  [OK] OpenTofu fmt & validate passed"
elif [ "$VERIFY_MODE" = "cluster" ]; then
  echo "  [FAIL] VERIFY_MODE=cluster requires 'tofu' CLI" >&2
  exit 1
else
  echo "  [SKIP] 'tofu' CLI not installed; static HCL check only"
fi

echo "================================================================================"
echo "  [SUCCESS] Optional AWS Cloud Track Verification Passed!"
echo "================================================================================"
