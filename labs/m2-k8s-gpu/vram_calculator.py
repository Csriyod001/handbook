#!/usr/bin/env python3
"""
GPU VRAM Sizing & Concurrency Calculator for GQA LLMs (Module 2)
================================================================
Implements the exact mathematical formulas from Chapter 2 & SPEC_AND_STYLE_GUIDE.md:
- Model Weights Memory: P * B_param
- Grouped-Query Attention (GQA) KV-Cache Memory:
  2 * L * H_kv * d_head * B_kv * S * C
- Per-Process CUDA Context & CUDA Graph Overhead (with `--enforce-eager` support)
- Maximum Concurrent Sequences Solver for target GPU VRAM (e.g., NVIDIA L4 24GB)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


PRECISION_BYTES: Dict[str, float] = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "fp8": 1.0,
    "int8": 1.0,
    # INT4-AWQ/GPTQ includes ~15% group scale/zero-point metadata overhead
    "int4_awq": 0.58,
    "int4_raw": 0.50,
}


@dataclass(frozen=True)
class ModelArchSpec:
    """Architectural specification for a Transformer LLM with GQA."""

    model_id: str
    params_billion: float
    num_layers: int
    num_query_heads: int
    num_kv_heads: int
    head_dim: int


@dataclass(frozen=True)
class VRAMBreakdown:
    """Detailed GPU VRAM sizing breakdown in decimal GB (10^9 bytes) and binary GiB."""

    model_id: str
    weight_precision: str
    kv_precision: str
    seq_len: int
    concurrent_seqs: int
    num_replicas: int
    enforce_eager: bool
    weights_gb: float
    kv_cache_bytes_per_token: int
    kv_cache_gb: float
    overhead_gb: float
    total_vram_gb: float
    total_vram_gib: float
    fits_gpu: bool
    max_concurrent_seqs_on_gpu: int

    @property
    def max_concurrent_per_replica(self) -> int:
        """Maximum concurrent sequences supported per replica under time-slicing."""
        return self.max_concurrent_seqs_on_gpu // max(1, self.num_replicas)


# Canonical Model Specs matching SPEC_AND_STYLE_GUIDE.md
MODEL_CATALOG: Dict[str, ModelArchSpec] = {
    "meta-llama/Llama-3.1-8B-Instruct": ModelArchSpec(
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        params_billion=8.03,
        num_layers=32,
        num_query_heads=32,
        num_kv_heads=8,
        head_dim=128,
    ),
    "Qwen/Qwen2.5-7B-Instruct": ModelArchSpec(
        model_id="Qwen/Qwen2.5-7B-Instruct",
        params_billion=7.615,
        num_layers=28,
        num_query_heads=28,
        num_kv_heads=4,
        head_dim=128,
    ),
    "Qwen/Qwen2.5-3B-Instruct": ModelArchSpec(
        model_id="Qwen/Qwen2.5-3B-Instruct",
        params_billion=3.09,
        num_layers=36,
        num_query_heads=16,
        num_kv_heads=2,
        head_dim=128,
    ),
    "Qwen/Qwen2.5-0.5B-Instruct": ModelArchSpec(
        model_id="Qwen/Qwen2.5-0.5B-Instruct",
        params_billion=0.494,
        num_layers=24,
        num_query_heads=14,
        num_kv_heads=2,
        head_dim=64,
    ),
}


def compute_kv_cache_bytes_per_token(
    spec: ModelArchSpec, kv_precision: str = "fp16"
) -> int:
    """
    Calculate KV-Cache footprint per token (in bytes) using the GQA formula:
    M_kv_token = 2 * L * H_kv * d_head * B_kv
    """
    if kv_precision not in PRECISION_BYTES:
        raise ValueError(f"Unsupported kv_precision: {kv_precision}")
    b_kv = PRECISION_BYTES[kv_precision]
    return int(2 * spec.num_layers * spec.num_kv_heads * spec.head_dim * b_kv)


def calculate_vram_sizing(
    spec: ModelArchSpec,
    weight_precision: str = "fp16",
    kv_precision: str = "fp16",
    seq_len: int = 4096,
    concurrent_seqs: int = 16,
    gpu_vram_gb: float = 24.0,
    gpu_memory_utilization: float = 0.92,
    num_replicas: int = 1,
    enforce_eager: bool = False,
) -> VRAMBreakdown:
    """
    Compute total VRAM required (in GB = 10^9 bytes) and solve for maximum
    concurrent sequences supported within `gpu_vram_gb * gpu_memory_utilization`.
    """
    if weight_precision not in PRECISION_BYTES:
        raise ValueError(f"Unsupported weight_precision: {weight_precision}")

    b_param = PRECISION_BYTES[weight_precision]

    # 1. Model weights memory (multiplied by num_replicas if running separate processes)
    weights_bytes_per_replica = spec.params_billion * 1e9 * b_param
    weights_gb = (weights_bytes_per_replica * num_replicas) / 1e9

    # 2. KV-Cache memory
    kv_bytes_per_token = compute_kv_cache_bytes_per_token(spec, kv_precision)
    kv_cache_bytes = kv_bytes_per_token * seq_len * concurrent_seqs * num_replicas
    kv_cache_gb = kv_cache_bytes / 1e9

    # 3. Runtime Overhead (CUDA Context + Activations + optional CUDA Graphs)
    # Without --enforce-eager, CUDA Graphs add ~1.5 GB per process.
    per_replica_overhead_gb = 0.70 if enforce_eager else 2.20
    if num_replicas == 1 and not enforce_eager:
        per_replica_overhead_gb = 2.50
    overhead_gb = per_replica_overhead_gb * num_replicas

    total_vram_gb = weights_gb + kv_cache_gb + overhead_gb
    total_vram_gib = (total_vram_gb * 1e9) / (1024**3)

    usable_vram_gb = gpu_vram_gb * gpu_memory_utilization
    fits_gpu = total_vram_gb <= usable_vram_gb

    # Solve for aggregate max concurrent sequences across all replicas on the GPU
    available_for_kv_gb = max(0.0, usable_vram_gb - weights_gb - overhead_gb)
    bytes_per_sequence = kv_bytes_per_token * seq_len
    max_concurrent = int((available_for_kv_gb * 1e9) // bytes_per_sequence)

    return VRAMBreakdown(
        model_id=spec.model_id,
        weight_precision=weight_precision,
        kv_precision=kv_precision,
        seq_len=seq_len,
        concurrent_seqs=concurrent_seqs,
        num_replicas=num_replicas,
        enforce_eager=enforce_eager,
        weights_gb=round(weights_gb, 2),
        kv_cache_bytes_per_token=kv_bytes_per_token,
        kv_cache_gb=round(kv_cache_gb, 2),
        overhead_gb=round(overhead_gb, 2),
        total_vram_gb=round(total_vram_gb, 2),
        total_vram_gib=round(total_vram_gib, 2),
        fits_gpu=fits_gpu,
        max_concurrent_seqs_on_gpu=max_concurrent,
    )


def print_sizing_table() -> None:
    """Print canonical GPU VRAM Sizing comparison table for NVIDIA L4 (24GB) and RTX 4050 (6GB)."""
    llama8b = MODEL_CATALOG["meta-llama/Llama-3.1-8B-Instruct"]
    qwen7b = MODEL_CATALOG["Qwen/Qwen2.5-7B-Instruct"]
    qwen3b = MODEL_CATALOG["Qwen/Qwen2.5-3B-Instruct"]
    qwen05b = MODEL_CATALOG["Qwen/Qwen2.5-0.5B-Instruct"]

    scenarios = [
        (
            "Llama-3.1-8B (FP16, S=8192, C=32)",
            calculate_vram_sizing(
                llama8b,
                weight_precision="fp16",
                kv_precision="fp16",
                seq_len=8192,
                concurrent_seqs=32,
                gpu_vram_gb=24.0,
                gpu_memory_utilization=1.0,
            ),
        ),
        (
            "Qwen2.5-7B (BF16, S=8192, C=16)",
            calculate_vram_sizing(
                qwen7b,
                weight_precision="bf16",
                kv_precision="fp16",
                seq_len=8192,
                concurrent_seqs=16,
                gpu_vram_gb=24.0,
                gpu_memory_utilization=0.85,
            ),
        ),
        (
            "Qwen2.5-7B-AWQ (INT4, S=4096, C=32)",
            calculate_vram_sizing(
                qwen7b,
                weight_precision="int4_awq",
                kv_precision="fp16",
                seq_len=4096,
                concurrent_seqs=32,
                gpu_vram_gb=24.0,
                gpu_memory_utilization=0.92,
            ),
        ),
        (
            "Qwen2.5-7B (FP8 W+KV, S=4096, C=32)",
            calculate_vram_sizing(
                qwen7b,
                weight_precision="fp8",
                kv_precision="fp8",
                seq_len=4096,
                concurrent_seqs=32,
                gpu_vram_gb=24.0,
                gpu_memory_utilization=0.92,
            ),
        ),
        (
            "Qwen2.5-3B-AWQ (RTX4050 6GB, FP8 KV)",
            calculate_vram_sizing(
                qwen3b,
                weight_precision="int4_awq",
                kv_precision="fp8",
                seq_len=2048,
                concurrent_seqs=8,
                gpu_vram_gb=6.0,
                gpu_memory_utilization=0.85,
                enforce_eager=True,
            ),
        ),
        (
            "4x Time-Sliced Qwen2.5-0.5B (Eager Mode)",
            calculate_vram_sizing(
                qwen05b,
                weight_precision="bf16",
                kv_precision="fp16",
                seq_len=2048,
                concurrent_seqs=8,
                gpu_vram_gb=24.0,
                gpu_memory_utilization=0.85,
                num_replicas=4,
                enforce_eager=True,
            ),
        ),
    ]

    print("=" * 92)
    print("  GPU VRAM Sizing & Capacity Report (NVIDIA L4 24GB & RTX 4050 6GB)")
    print("=" * 92)
    print(
        f"{'Scenario':<40} | {'Weights':>7} | {'KV-Cache':>8} | {'Overhead':>8} | {'Total VRAM':>10} | {'Fits GPU?'}"
    )
    print("-" * 92)
    for label, res in scenarios:
        if not res.fits_gpu:
            status = "NO (OOM)"
        elif res.num_replicas > 1:
            status = (
                f"YES (Max C={res.max_concurrent_per_replica}/rep, "
                f"{res.max_concurrent_seqs_on_gpu} total)"
            )
        else:
            status = f"YES (Max C={res.max_concurrent_seqs_on_gpu})"
        print(
            f"{label:<40} | {res.weights_gb:>5.2f}GB | {res.kv_cache_gb:>6.2f}GB | "
            f"{res.overhead_gb:>6.2f}GB | {res.total_vram_gb:>8.2f}GB | {status}"
        )
    print("=" * 92)


if __name__ == "__main__":
    print_sizing_table()
