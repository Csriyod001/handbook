#!/usr/bin/env python3
"""
Module 5 (M5): Chaos Traffic Surge & KEDA Autoscaling Incident Simulator / Live Driver
======================================================================================
Supports two modes:
  1. `--simulate` (default): Deterministic offline simulation verifying KEDA dual-trigger
     math and PrometheusRule alert evaluation without requiring a live cluster.
  2. `--live`: Drives real HTTP chaos injection (`POST /admin/chaos`), concurrent traffic,
     and live Prometheus `/metrics` scraping against a running Kind/K8s cluster (ideal
     on HP Victus 32GB RAM where Prometheus, Grafana, LiteLLM, and KEDA run together).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ClusterTelemetrySnapshot:
    replicas: int
    num_requests_waiting: int
    kv_cache_usage_perc: float
    ttft_p95_ms: float
    preemptions_total: int


def calculate_keda_desired_replicas(
    current_replicas: int,
    waiting_queue: int,
    kv_cache_usage: float,
    queue_threshold: float = 5.0,
    kv_threshold: float = 0.80,
    min_replicas: int = 1,
    max_replicas: int = 3,
) -> Tuple[int, int, int]:
    """
    Computes desired replicas using KEDA's dual Prometheus triggers:
      - Trigger 1: ceil(waiting_queue / queue_threshold)
      - Trigger 2: ceil(current_replicas * (kv_cache_usage / kv_threshold))
    Returns (desired_replicas, trigger1_replicas, trigger2_replicas).
    """
    t1 = math.ceil(waiting_queue / queue_threshold) if waiting_queue > 0 else min_replicas
    t2 = math.ceil(current_replicas * (kv_cache_usage / kv_threshold)) if kv_cache_usage > 0 else min_replicas
    desired = min(max_replicas, max(min_replicas, t1, t2))
    return desired, t1, t2


def evaluate_prometheus_alerts(snapshot: ClusterTelemetrySnapshot) -> List[str]:
    """Evaluates PrometheusRule alerts from prometheus-alert-rules.yaml."""
    fired: List[str] = []
    if snapshot.kv_cache_usage_perc > 0.85:
        fired.append("VLLMKVCacheSaturationWarning")
    if snapshot.preemptions_total > 0:
        fired.append("VLLMPreemptionThrashingCritical")
    if snapshot.ttft_p95_ms > 800.0:
        fired.append("VLLMHighTTFTBurnRateCritical")
    return fired


def run_simulation() -> int:
    print("================================================================================")
    print(" [M5 CHAOS DRILL] Simulating 10x Long-Context Traffic Surge on vllm-primary")
    print("================================================================================")

    baseline = ClusterTelemetrySnapshot(
        replicas=1,
        num_requests_waiting=1,
        kv_cache_usage_perc=0.22,
        ttft_p95_ms=380.0,
        preemptions_total=0,
    )
    print(
        f"[T+00s] Baseline State  : Replicas={baseline.replicas} | "
        f"WaitingQueue={baseline.num_requests_waiting:<2} | "
        f"KV_Usage={baseline.kv_cache_usage_perc * 100:.1f}% | "
        f"TTFT_p95={baseline.ttft_p95_ms:.0f}ms | Alerts=NONE"
    )

    surge = ClusterTelemetrySnapshot(
        replicas=1,
        num_requests_waiting=18,
        kv_cache_usage_perc=0.94,
        ttft_p95_ms=2950.0,
        preemptions_total=6,
    )
    print(
        f"[T+15s] Traffic Surge!  : Replicas={surge.replicas} | "
        f"WaitingQueue={surge.num_requests_waiting:<2} | "
        f"KV_Usage={surge.kv_cache_usage_perc * 100:.1f}% | "
        f"TTFT_p95={surge.ttft_p95_ms:.0f}ms | Preemptions={surge.preemptions_total}"
    )

    alerts = evaluate_prometheus_alerts(surge)
    for alert in alerts:
        if alert == "VLLMKVCacheSaturationWarning":
            print(f"[ALERT FIRED] {alert} (kv_cache_usage_perc={surge.kv_cache_usage_perc:.2f} > 0.85)")
        elif alert == "VLLMPreemptionThrashingCritical":
            print(f"[ALERT FIRED] {alert} (preemptions_total={surge.preemptions_total} > 0)")
        elif alert == "VLLMHighTTFTBurnRateCritical":
            print(f"[ALERT FIRED] {alert} (ttft_p95_ms={surge.ttft_p95_ms:.0f}ms > 800ms)")

    desired, t1, t2 = calculate_keda_desired_replicas(
        current_replicas=surge.replicas,
        waiting_queue=surge.num_requests_waiting,
        kv_cache_usage=surge.kv_cache_usage_perc,
    )
    q_ratio = surge.num_requests_waiting / 5.0
    kv_ratio = surge.replicas * (surge.kv_cache_usage_perc / 0.80)
    print(f"[KEDA SCALER] Trigger 1 (WaitingQueue={surge.num_requests_waiting} / threshold=5 -> ceil({q_ratio:.2f})={t1}, capped={desired})")
    print(f"[KEDA SCALER] Trigger 2 (KV_Usage={surge.replicas} * {surge.kv_cache_usage_perc:.2f} / 0.80 -> ceil({kv_ratio:.2f})={t2})")
    print(
        f"[KEDA ACTION] Scaling deployment/vllm-primary: {surge.replicas} -> {desired} replicas "
        f"(Mounting PVC: hf-model-cache-pvc at HF_HOME=/cache/huggingface)"
    )

    post_scale = ClusterTelemetrySnapshot(
        replicas=desired,
        num_requests_waiting=2,
        kv_cache_usage_perc=0.313,
        ttft_p95_ms=490.0,
        preemptions_total=0,
    )
    print(f"[T+25s] Pods Ready (<10s simulated/mock warm cache start; ~35-75s on Cloud L4 GPU PVC): Replicas={post_scale.replicas} | Load balanced across {post_scale.replicas} pods")
    print(
        f"[T+40s] Post-Scale State: Replicas={post_scale.replicas} | "
        f"WaitingQueue={post_scale.num_requests_waiting:<2} | "
        f"KV_Usage={post_scale.kv_cache_usage_perc * 100:.1f}% | "
        f"TTFT_p95={post_scale.ttft_p95_ms:.0f}ms | Preemptions={post_scale.preemptions_total}"
    )
    print("[RECOVERY] All SLOs restored (TTFT p95 490ms < 800ms SLA). Zero dropped streaming requests!")
    print("================================================================================")

    assert desired == 3
    assert "VLLMKVCacheSaturationWarning" in alerts
    assert "VLLMPreemptionThrashingCritical" in alerts
    assert evaluate_prometheus_alerts(post_scale) == []
    return 0


def _http_post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None, timeout: float = 10.0) -> Tuple[int, str]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")


def run_live_chaos(
    vllm_url: str,
    gateway_url: str,
    api_key: str,
    concurrency: int = 12,
    reset: bool = False,
    dry_run: bool = False,
) -> int:
    vllm_base = vllm_url.rstrip("/")
    gw_base = gateway_url.rstrip("/")
    chaos_payload = (
        {"inject_latency_ms": 0, "inject_http_503": False, "kv_cache_usage_perc": 0.18, "num_requests_waiting": 0}
        if reset
        else {"inject_latency_ms": 950, "inject_http_503": False, "kv_cache_usage_perc": 0.94, "num_requests_waiting": 18}
    )

    print("================================================================================")
    print(f" [M5 LIVE CHAOS] Target vLLM={vllm_base} | Gateway={gw_base} | reset={reset}")
    print("================================================================================")
    print(f"[PLAN] POST {vllm_base}/admin/chaos payload={json.dumps(chaos_payload)}")
    if not reset:
        print(f"[PLAN] Burst {concurrency} concurrent POST {gw_base}/v1/chat/completions")
        print(f"[PLAN] Scrape GET {vllm_base}/metrics and verify KEDA with: kubectl get scaledobject,hpa -n ai-platform")

    if dry_run:
        print("[DRY-RUN] Skipping live HTTP calls.")
        return 0

    code, body = _http_post_json(f"{vllm_base}/admin/chaos", chaos_payload)
    print(f"[CHAOS API] HTTP {code}: {body}")
    if code >= 400:
        return 1

    if not reset:
        def _send_one(idx: int) -> int:
            status, _ = _http_post_json(
                f"{gw_base}/v1/chat/completions",
                {
                    "model": "qwen2.5-7b",
                    "messages": [{"role": "user", "content": f"live chaos surge check #{idx}"}],
                    "max_tokens": 24,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return status

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(concurrency, 16)) as pool:
            statuses = list(pool.map(_send_one, range(concurrency)))
        print(f"[TRAFFIC BURST] Sent {concurrency} requests -> HTTP statuses: {statuses}")

        with urllib.request.urlopen(f"{vllm_base}/metrics", timeout=10.0) as mresp:
            metrics_text = mresp.read().decode("utf-8", errors="replace")
        for line in metrics_text.splitlines():
            if not line.startswith("#") and any(
                m in line for m in ("vllm:kv_cache_usage_perc", "vllm:num_requests_waiting", "vllm:num_preemptions_total")
            ):
                print(f"[LIVE METRIC] {line}")

    print("[NEXT] Run `kubectl get scaledobject,hpa,pods -n ai-platform` to observe real KEDA scale-out (and `--reset` when done).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Module 5 Chaos Surge & KEDA Autoscaling Driver")
    parser.add_argument("--simulate", action="store_true", help="Run deterministic offline simulation (default)")
    parser.add_argument("--live", action="store_true", help="Drive live HTTP chaos & traffic against cluster endpoints")
    parser.add_argument("--vllm-url", default="http://localhost:8000", help="Port-forwarded vllm-primary-svc URL")
    parser.add_argument("--gateway-url", default="http://localhost:4000", help="Port-forwarded litellm-gateway-svc URL")
    parser.add_argument("--api-key", default="sk-realtime-team", help="LiteLLM Virtual Key for live load burst")
    parser.add_argument("--concurrency", type=int, default=12, help="Concurrent requests for live traffic burst")
    parser.add_argument("--reset", action="store_true", help="Reset injected chaos state back to healthy baseline")
    parser.add_argument("--dry-run", action="store_true", help="Print live HTTP actions without sending traffic")
    return parser


def test_keda_scaling_and_alert_evaluation() -> None:
    """Pytest entry point verifying KEDA math, alert rules, and live CLI dry-run."""
    desired, t1, t2 = calculate_keda_desired_replicas(
        current_replicas=1,
        waiting_queue=18,
        kv_cache_usage=0.94,
    )
    assert desired == 3
    assert t1 == 4
    assert t2 == 2
    assert run_simulation() == 0
    assert run_live_chaos("http://localhost:8000", "http://localhost:4000", "sk-test", dry_run=True) == 0


def main() -> int:
    args = build_parser().parse_args()
    if args.live:
        return run_live_chaos(
            vllm_url=args.vllm_url,
            gateway_url=args.gateway_url,
            api_key=args.api_key,
            concurrency=args.concurrency,
            reset=args.reset,
            dry_run=args.dry_run,
        )
    return run_simulation()


if __name__ == "__main__":
    sys.exit(main())
