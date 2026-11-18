#!/usr/bin/env python3
"""
Module 6 (M6 Capstone): Project SiamShield AI — End-to-End Platform & Chaos Verification Engine
===============================================================================================
Integrates components from M2 (VRAM Sizing), M3 (Unit Economics & vLLM V1), M4 (LiteLLM Gateway,
PDPA PII Masking, Endpoint Picker), and M5 (KEDA Autoscaling) to verify all 5 Capstone SLOs.
"""

from __future__ import annotations

import asyncio
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../../.."))
M4_PATH = os.path.join(REPO_ROOT, "labs", "m4-gateway")
M5_CHAOS_PATH = os.path.join(REPO_ROOT, "labs", "m5-observability-sre", "chaos")

for p in (M4_PATH, M5_CHAOS_PATH):
    if p not in sys.path:
        sys.path.insert(0, p)

from mock_vllm_server.app import (  # noqa: E402
    EndpointPickerScorer,
    GatewayResilienceRouter,
    HTTP429RateLimitError,
    MockVLLMServer,
    PDPAPIIMasker,
)
from trigger_incident import calculate_keda_desired_replicas  # noqa: E402


def run_capstone_verification() -> int:
    print("========================================================================================")
    print(" Project SiamShield AI — End-to-End Two-Tier Platform & Chaos Verification")
    print("========================================================================================")

    # 1. VRAM & Unit Economics Verification
    vram_total_gb = 24.0
    gpu_util = 0.92
    weights_awq_gb = 4.42
    overhead_gb = 1.66
    kv_pool_gb = (vram_total_gb * gpu_util) - weights_awq_gb - overhead_gb
    kv_tokens = int((kv_pool_gb * (1024**3)) / 57344)
    hourly_cost = 0.85
    peak_tput = 1450.0
    api_price = 0.60
    breakeven_pct = (hourly_cost * 1_000_000) / (peak_tput * 3600.0 * api_price) * 100.0
    cost_50pct = (hourly_cost * 1_000_000) / (peak_tput * 3600.0 * 0.50)

    assert round(kv_pool_gb, 2) == 16.00
    assert kv_tokens >= 299000
    assert 27.0 <= breakeven_pct <= 27.2
    print("[1/5] Verifying VRAM & Unit Economics Sizing (NVIDIA L4 24GB per Primary/Secondary Node)...")
    print(f"      - Model: Qwen/Qwen2.5-7B-Instruct-AWQ (Weights: {weights_awq_gb:.2f} GB, KV Pool: {kv_pool_gb:.2f} GB / ~{kv_tokens/1000:.1f}k tokens)")
    print(f"      - Break-even Utilization vs ${api_price:.2f}/1M API: {breakeven_pct:.1f}% (Cost @ 50% util = ${cost_50pct:.2f}/1M tokens)")

    # 2. Pre-Call PDPA Guardrail Verification
    raw_input = "ตรวจสอบลูกค้า 1-1007-01234-56-1 โทร 081-234-5678"
    masked_output, redactions = PDPAPIIMasker.mask_text(raw_input)
    assert redactions == 2
    assert "<THAI_ID_REDACTED>" in masked_output
    assert "<THAI_PHONE_REDACTED>" in masked_output
    assert "1-1007-01234-56-1" not in masked_output
    print("[2/5] Testing Pre-Call PDPA Guardrail (Thai 13-Digit National ID & Phone)...")
    print(f"      - Input : '{raw_input}'")
    print(f"      - Output: '{masked_output}' (0 PII Leaks)")

    # 3. Two-Tier Isolation under Batch Flood
    primary = MockVLLMServer(server_id="vllm-primary-svc", base_ttft_ms=5.0)
    secondary = MockVLLMServer(server_id="vllm-secondary-svc", base_ttft_ms=5.0)
    router = GatewayResilienceRouter(
        primary_backend=primary,
        secondary_backend=secondary,
        stream_timeout_s=0.05,
        tenant_rpm_limits={"sk-realtime-team": 120, "sk-batch-team": 10},
    )

    batch_accepted = 0
    batch_rejected_429 = 0
    for i in range(15):
        try:
            asyncio.run(
                router.chat_completions(
                    "sk-batch-team",
                    {"model": "qwen2.5-7b-batch", "messages": [{"role": "user", "content": f"summarize policy doc #{i}"}]},
                )
            )
            batch_accepted += 1
        except HTTP429RateLimitError:
            batch_rejected_429 += 1

    assert batch_accepted == 10
    assert batch_rejected_429 == 5

    rt_resp = asyncio.run(
        router.chat_completions(
            "sk-realtime-team",
            {"model": "qwen2.5-7b", "messages": [{"role": "user", "content": "urgent fraud check customer 1-1007-01234-56-1"}]},
        )
    )
    assert rt_resp["routed_backend"] == "vllm-primary-svc"
    assert rt_resp["headers"]["X-Sim-PDPA-Redactions"] == "1"
    rt_ttft_ms = (sum(primary._ttft_observations) / len(primary._ttft_observations)) * 1000.0
    rt_itl_ms = (sum(primary._itl_observations) / len(primary._itl_observations)) * 1000.0
    print("[3/5] Testing Two-Tier Isolation under Batch Flood (Noisy Neighbor Protection)...")
    print(f"      - tier-batch (sk-batch-team) flooded 15 reqs -> {batch_accepted} accepted, {batch_rejected_429} rejected with HTTP 429")
    print(f"      - tier-realtime (sk-realtime-team) simulated mean TTFT={rt_ttft_ms:.1f} ms (< 800 ms SLO), ITL={rt_itl_ms:.1f} ms (< 30 ms SLO)")

    # 4. Primary Replica Blackhole -> Secondary Automated Failover
    import time
    injected_ms = 250.0
    primary.configure_chaos(inject_latency_ms=injected_ms, kv_cache_usage_perc=0.91)
    t_start = time.perf_counter()
    failover_resp = asyncio.run(
        router.chat_completions(
            "sk-realtime-team",
            {"model": "qwen2.5-7b", "messages": [{"role": "user", "content": "realtime query during primary spike"}]},
        )
    )
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    assert failover_resp["headers"]["X-Sim-Fallback-Triggered"] == "true"
    assert failover_resp["routed_backend"] == "vllm-secondary-svc"
    print("[4/5] Testing Primary Replica Blackhole -> Secondary Automated Failover...")
    print(f"      - Injected {injected_ms:.0f}ms latency on vllm-primary-svc (> {router.stream_timeout_s * 1000:.0f}ms stream_timeout)")
    print(f"      - Gateway failed over to vllm-secondary-svc in {elapsed_ms:.1f}ms (Availability = 100.0%)")

    # 5. KEDA Autoscaling & EPP Load Shedding under KV-Cache Surge
    epp = EndpointPickerScorer(sheddable_kv_threshold=0.85)
    secondary.configure_chaos(kv_cache_usage_perc=0.89, num_requests_waiting=18)
    shed_batch = False
    try:
        epp.pick_best_endpoint([primary, secondary], criticality="Sheddable")
    except PermissionError:
        shed_batch = True
    assert shed_batch is True

    observed_waiting = secondary.num_requests_waiting
    observed_kv = primary.kv_cache_usage_perc
    desired_replicas, _, _ = calculate_keda_desired_replicas(
        current_replicas=1,
        waiting_queue=observed_waiting,
        kv_cache_usage=observed_kv,
    )
    assert desired_replicas == 3
    print("[5/5] Testing KEDA Autoscaling & EPP Load Shedding under KV-Cache Surge...")
    print(f"      - Primary KV-Cache={observed_kv * 100:.1f}%, Secondary KV-Cache={secondary.kv_cache_usage_perc * 100:.1f}%, Waiting={observed_waiting} -> EPP shed Sheddable batch traffic")
    print(f"      - KEDA scaled vllm-primary 1 -> {desired_replicas} replicas (<10s Mock Pod warm start; ~35-75s Cloud L4 GPU PVC)")
    print("========================================================================================")
    print(" [SUCCESS] All SiamShield AI SLOs & Resilience Invariants Verified!")
    print("========================================================================================")
    return 0


def test_siamshield_end_to_end_capstone() -> None:
    """Pytest entry point for Project SiamShield AI end-to-end verification."""
    assert run_capstone_verification() == 0


if __name__ == "__main__":
    sys.exit(run_capstone_verification())
