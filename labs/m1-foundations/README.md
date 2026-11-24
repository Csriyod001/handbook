# Module 1: Reproducible AI Foundations — `ai-inference-service`

Production-hardened FastAPI inference wrapper with:
- Multi-stage Astral `uv` build reading dependencies directly from `pyproject.toml`
- Non-root execution (`UID 10001`) compatible with `readOnlyRootFilesystem: true`
- Canonical Hugging Face cache path `HF_HOME=/cache/huggingface` and `VLLM_CACHE_ROOT=/tmp/vllm-cache`
- Bounded concurrency queue (`asyncio.Semaphore`) with fail-fast `HTTP 429` load shedding
- Two-stage OpenTofu IaC (`infra/` for Kind cluster -> `infra/k8s-bootstrap/` for namespaces & `hf-model-cache-pvc`)

## Quick Verification
```bash
VERIFY_MODE=static bash verify_m1.sh
```
