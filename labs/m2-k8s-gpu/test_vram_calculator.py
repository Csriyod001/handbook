"""
Pytest Unit Tests for Module 2 GPU VRAM Sizing Calculator (`vram_calculator.py`)
================================================================================
Verifies:
1. Exact GQA KV-Cache per token for `meta-llama/Llama-3.1-8B-Instruct` (128 KiB = 131,072 bytes).
2. Worked Example 1: Llama-3.1-8B (FP16, S=8192, C=32) requires ~52.92 GB and exceeds 24GB L4.
3. Worked Example 2: Qwen2.5-7B-Instruct-AWQ (INT4, S=4096, C=32) fits comfortably on 24GB L4
   with >3x KV-Cache capacity compared to BF16 baseline.
4. Time-Slicing 4 replicas with `--enforce-eager` saves >= 5 GB of CUDA Graph VRAM overhead.
5. Max concurrent sequences solver accurately computes capacity bounds.
"""

from __future__ import annotations

from vram_calculator import (
    MODEL_CATALOG,
    calculate_vram_sizing,
    compute_kv_cache_bytes_per_token,
)


def test_llama3_8b_fp16_kv_cache_per_token() -> None:
    """Llama-3.1-8B (L=32, H_kv=8, d_head=128, FP16=2B) must equal 131,072 bytes (128 KiB) per token."""
    llama8b = MODEL_CATALOG["meta-llama/Llama-3.1-8B-Instruct"]
    kv_bytes = compute_kv_cache_bytes_per_token(llama8b, kv_precision="fp16")
    assert kv_bytes == 131072, f"Expected 131072 bytes (128 KiB), got {kv_bytes}"
    assert kv_bytes // 1024 == 128


def test_llama3_8b_fp16_exceeds_l4_24gb() -> None:
    """Llama-3.1-8B FP16 at S=8192, C=32 must require ~52.92 GB and fail to fit on a 24GB L4."""
    llama8b = MODEL_CATALOG["meta-llama/Llama-3.1-8B-Instruct"]
    res = calculate_vram_sizing(
        llama8b,
        weight_precision="fp16",
        kv_precision="fp16",
        seq_len=8192,
        concurrent_seqs=32,
        gpu_vram_gb=24.0,
        gpu_memory_utilization=0.92,
    )
    assert res.weights_gb == 16.06
    assert res.kv_cache_gb == 34.36
    assert res.total_vram_gb == 52.92
    assert res.fits_gpu is False


def test_qwen25_7b_awq_fits_l4_24gb() -> None:
    """
    Qwen2.5-7B-Instruct-AWQ at S=4096, C=32 with gpu_memory_utilization=0.92
    must fit on an NVIDIA L4 (24GB) and expand KV-Cache concurrency capacity >3x vs BF16.
    """
    qwen7b = MODEL_CATALOG["Qwen/Qwen2.5-7B-Instruct"]

    baseline_bf16 = calculate_vram_sizing(
        qwen7b,
        weight_precision="bf16",
        kv_precision="fp16",
        seq_len=4096,
        concurrent_seqs=32,
        gpu_vram_gb=24.0,
        gpu_memory_utilization=0.85,
    )
    optimized_awq = calculate_vram_sizing(
        qwen7b,
        weight_precision="int4_awq",
        kv_precision="fp16",
        seq_len=4096,
        concurrent_seqs=32,
        gpu_vram_gb=24.0,
        gpu_memory_utilization=0.92,
    )

    assert baseline_bf16.fits_gpu is False
    assert optimized_awq.fits_gpu is True
    assert optimized_awq.weights_gb < 5.0
    assert (
        optimized_awq.max_concurrent_seqs_on_gpu
        >= baseline_bf16.max_concurrent_seqs_on_gpu * 3
    )


def test_time_slicing_enforce_eager_savings() -> None:
    """
    Running 4 time-sliced replicas of Qwen2.5-0.5B with --enforce-eager must save
    at least 5.0 GB of CUDA Graph VRAM overhead compared to non-eager mode.
    """
    qwen05b = MODEL_CATALOG["Qwen/Qwen2.5-0.5B-Instruct"]
    with_cuda_graphs = calculate_vram_sizing(
        qwen05b,
        weight_precision="bf16",
        seq_len=2048,
        concurrent_seqs=4,
        num_replicas=4,
        enforce_eager=False,
    )
    with_enforce_eager = calculate_vram_sizing(
        qwen05b,
        weight_precision="bf16",
        seq_len=2048,
        concurrent_seqs=4,
        num_replicas=4,
        enforce_eager=True,
    )
    vram_saved = with_cuda_graphs.total_vram_gb - with_enforce_eager.total_vram_gb
    assert vram_saved >= 5.5
    assert with_enforce_eager.fits_gpu is True
    assert with_enforce_eager.max_concurrent_per_replica == (
        with_enforce_eager.max_concurrent_seqs_on_gpu // 4
    )


def test_max_concurrent_sequences_solver() -> None:
    """Max concurrent sequences solver must return 0 when weights alone exceed usable VRAM."""
    llama8b = MODEL_CATALOG["meta-llama/Llama-3.1-8B-Instruct"]
    res = calculate_vram_sizing(
        llama8b,
        weight_precision="fp32",  # 32.12 GB weights > 24.0 GB L4
        seq_len=2048,
        concurrent_seqs=1,
        gpu_vram_gb=24.0,
    )
    assert res.fits_gpu is False
    assert res.max_concurrent_seqs_on_gpu == 0


def test_qwen25_3b_awq_fits_rtx4050_6gb() -> None:
    """Qwen2.5-3B-AWQ with FP8 KV-Cache and --enforce-eager must fit on 6GB RTX 4050."""
    qwen3b = MODEL_CATALOG["Qwen/Qwen2.5-3B-Instruct"]
    res = calculate_vram_sizing(
        qwen3b,
        weight_precision="int4_awq",
        kv_precision="fp8",
        seq_len=2048,
        concurrent_seqs=8,
        gpu_vram_gb=6.0,
        gpu_memory_utilization=0.85,
        enforce_eager=True,
    )
    assert res.fits_gpu is True
    assert res.weights_gb < 2.0
    assert res.max_concurrent_seqs_on_gpu >= 30


def test_qwen25_7b_fp8_doubles_kv_capacity_per_token() -> None:
    """FP8 KV-Cache halves bytes/token vs FP16 and fits 24GB L4 with FP8 weights."""
    qwen7b = MODEL_CATALOG["Qwen/Qwen2.5-7B-Instruct"]
    fp16_kv = compute_kv_cache_bytes_per_token(qwen7b, kv_precision="fp16")
    fp8_kv = compute_kv_cache_bytes_per_token(qwen7b, kv_precision="fp8")
    assert fp8_kv * 2 == fp16_kv
    res = calculate_vram_sizing(
        qwen7b,
        weight_precision="fp8",
        kv_precision="fp8",
        seq_len=4096,
        concurrent_seqs=32,
        gpu_vram_gb=24.0,
        gpu_memory_utilization=0.92,
    )
    assert res.fits_gpu is True
    assert res.max_concurrent_seqs_on_gpu >= 100
