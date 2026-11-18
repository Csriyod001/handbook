"""
Module 4 (M4): Automated Resilience & Governance Test Suite
===========================================================
Verifies:
  1. Mock vLLM V1 Prometheus metrics exposition (exact V1 metric names)
  2. PDPA PII Masking (13-digit Thai National ID checksum & redaction + phone numbers)
  3. Multi-tenant RPM Rate Limiting (HTTP 429 on quota flood while isolating other tenants)
  4. Gateway Exact Response Cache Hit (X-Sim-Cache-Hit: true)
  5. Automated Primary -> Secondary Failover when Primary injects latency spike / HTTP 503
  6. Kubernetes Gateway API Inference Extension Endpoint Picker (EPP) KV-cache-aware scoring
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure labs/m4-gateway is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LAB_M4_ROOT = os.path.dirname(CURRENT_DIR)
if LAB_M4_ROOT not in sys.path:
    sys.path.insert(0, LAB_M4_ROOT)

from mock_vllm_server.app import (  # noqa: E402
    EndpointPickerScorer,
    GatewayResilienceRouter,
    HTTP429RateLimitError,
    MockVLLMServer,
    PDPAPIIMasker,
)
from mock_vllm_server.pdpa_guardrail import proxy_handler_instance  # noqa: E402


def test_mock_vllm_v1_prometheus_metrics() -> None:
    """Verifies that mock_vllm_server exposes all canonical vLLM V1 Prometheus metrics."""
    server = MockVLLMServer(server_id="vllm-primary-svc", model_name="mock-qwen2.5-7b")
    shared_prefix = " ".join(f"system_tok_{i}" for i in range(32))
    payload = {
        "model": "mock-qwen2.5-7b",
        "messages": [{"role": "user", "content": f"{shared_prefix} question_one"}],
        "max_tokens": 16,
    }
    # First request populates prefix cache blocks
    asyncio.run(server.handle_chat_completion(payload))
    # Second request with identical 32-token prefix triggers prefix cache hits
    resp2 = asyncio.run(server.handle_chat_completion(payload))
    assert resp2["usage"]["prefix_cache_hit_tokens"] >= 32

    metrics_text = server.render_prometheus_metrics()
    required_metrics = [
        "vllm:kv_cache_usage_perc",
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
        "vllm:prefix_cache_hits_total",
        "vllm:prefix_cache_queries_total",
        "vllm:num_preemptions_total",
        "vllm:time_to_first_token_seconds_bucket",
        "vllm:inter_token_latency_seconds_bucket",
        "vllm:time_per_output_token_seconds_bucket",
        "vllm:generation_tokens_total",
    ]
    for metric_name in required_metrics:
        assert metric_name in metrics_text, f"Missing required V1 metric: {metric_name}"


def test_pdpa_thai_id_and_phone_redaction() -> None:
    """Verifies Thai 13-digit National ID Modulo-11 checksum and <THAI_ID_REDACTED> masking."""
    # Valid 13-digit Thai ID: 1-1007-01234-56-1
    assert PDPAPIIMasker.validate_thai_id_checksum("1-1007-01234-56-1") is True
    assert PDPAPIIMasker.validate_thai_id_checksum("1100701234561") is True
    assert PDPAPIIMasker.validate_thai_id_checksum("1100701234569") is False

    raw_prompt = (
        "ตรวจสอบสินเชื่อของเลขบัตร 1-1007-01234-56-1 และเลขติดกัน 3100598765432 "
        "ติดต่อกลับที่เบอร์ 081-234-5678 หรือ +66 89-999-8888 ครับ"
    )
    masked_text, count = PDPAPIIMasker.mask_text(raw_prompt)
    assert count == 4
    assert "1-1007-01234-56-1" not in masked_text
    assert "3100598765432" not in masked_text
    assert "081-234-5678" not in masked_text
    assert "+66 89-999-8888" not in masked_text
    assert masked_text.count("<THAI_ID_REDACTED>") == 2
    assert masked_text.count("<THAI_PHONE_REDACTED>") == 2

    # strict_checksum=True should only redact valid Modulo-11 Thai IDs (ignores random 13-digit order IDs)
    strict_text, strict_count = PDPAPIIMasker.mask_text(
        "Order 1100701234569 vs Citizen 1-1007-01234-56-1",
        strict_checksum=True,
    )
    assert strict_count == 1
    assert "1100701234569" in strict_text
    assert "1-1007-01234-56-1" not in strict_text

    # mask_messages must preserve None content and redact multimodal text parts
    sanitized_msgs, msg_count = PDPAPIIMasker.mask_messages(
        [
            {"role": "assistant", "content": None},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "ID 1100701234561"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/0812345678.png"}},
                ],
            },
        ]
    )
    assert sanitized_msgs[0]["content"] is None
    assert msg_count == 1
    assert sanitized_msgs[1]["content"][0]["text"] == "ID <THAI_ID_REDACTED>"
    assert sanitized_msgs[1]["content"][1]["image_url"]["url"].endswith("0812345678.png")


def test_tenant_rate_limiting_http_429() -> None:
    """Verifies that batch-team receives HTTP 429 upon exceeding RPM quota while realtime-team is unaffected."""
    primary = MockVLLMServer(server_id="vllm-primary-svc", base_ttft_ms=1.0)
    secondary = MockVLLMServer(server_id="vllm-secondary-svc", base_ttft_ms=1.0)
    router = GatewayResilienceRouter(
        primary_backend=primary,
        secondary_backend=secondary,
        tenant_rpm_limits={"sk-realtime-team": 50, "sk-batch-team": 2},
    )

    # First 2 requests for sk-batch-team succeed
    for i in range(2):
        res = asyncio.run(
            router.chat_completions(
                "sk-batch-team",
                {"model": "qwen2.5-7b", "messages": [{"role": "user", "content": f"batch job {i}"}]},
            )
        )
        assert res["routed_backend"] == "vllm-primary-svc"

    # 3rd request for sk-batch-team must raise HTTP 429
    got_429 = False
    try:
        asyncio.run(
            router.chat_completions(
                "sk-batch-team",
                {"model": "qwen2.5-7b", "messages": [{"role": "user", "content": "batch job overflow"}]},
            )
        )
    except HTTP429RateLimitError as exc:
        got_429 = True
        assert exc.status_code == 429

    assert got_429 is True, "Expected HTTP 429 Too Many Requests when exceeding tenant RPM limit"

    # Meanwhile, sk-realtime-team continues to succeed without noisy-neighbor interference
    rt_res = asyncio.run(
        router.chat_completions(
            "sk-realtime-team",
            {"model": "qwen2.5-7b", "messages": [{"role": "user", "content": "urgent customer query"}]},
        )
    )
    assert rt_res["routed_backend"] == "vllm-primary-svc"


def test_gateway_exact_cache_hit() -> None:
    """Verifies that identical sanitized prompts hit the Gateway response cache."""
    primary = MockVLLMServer(server_id="vllm-primary-svc", base_ttft_ms=2.0)
    secondary = MockVLLMServer(server_id="vllm-secondary-svc", base_ttft_ms=2.0)
    router = GatewayResilienceRouter(primary_backend=primary, secondary_backend=secondary)

    payload = {
        "model": "qwen2.5-7b",
        "messages": [{"role": "user", "content": "รบกวนเช็กยอดเลขบัตร 1-1007-01234-56-1"}],
    }
    first = asyncio.run(router.chat_completions("sk-realtime-team", payload))
    assert first["headers"]["X-Sim-Cache-Hit"] == "false"
    assert first["headers"]["X-Sim-PDPA-Redactions"] == "1"
    assert "<THAI_ID_REDACTED>" in first["choices"][0]["message"]["content"]

    # Second call with a DIFFERENT Thai ID that normalizes to the exact same <THAI_ID_REDACTED> prompt!
    payload_same_structure = {
        "model": "qwen2.5-7b",
        "messages": [{"role": "user", "content": "รบกวนเช็กยอดเลขบัตร 3-1005-98765-43-2"}],
    }
    second = asyncio.run(router.chat_completions("sk-realtime-team", payload_same_structure))
    assert second["headers"]["X-Sim-Cache-Hit"] == "true"


def test_automated_failover_on_primary_latency_spike() -> None:
    """Verifies automatic failover from vllm-primary-svc to vllm-secondary-svc on timeout/chaos."""
    primary = MockVLLMServer(server_id="vllm-primary-svc", base_ttft_ms=5.0)
    secondary = MockVLLMServer(server_id="vllm-secondary-svc", base_ttft_ms=5.0)
    router = GatewayResilienceRouter(
        primary_backend=primary,
        secondary_backend=secondary,
        stream_timeout_s=0.05,  # 50ms stream timeout for fast deterministic test execution
    )

    # Inject 250ms latency spike on primary (> 50ms stream_timeout_s)
    primary.configure_chaos(inject_latency_ms=250.0, kv_cache_usage_perc=0.99)

    resp = asyncio.run(
        router.chat_completions(
            "sk-realtime-team",
            {"model": "qwen2.5-7b", "messages": [{"role": "user", "content": "test failover routing"}]},
        )
    )
    assert resp["headers"]["X-Sim-Fallback-Triggered"] == "true"
    assert resp["headers"]["X-Sim-Routed-Backend"] == "vllm-secondary-svc"
    assert resp["routed_backend"] == "vllm-secondary-svc"


def test_epp_kv_cache_aware_scoring() -> None:
    """Verifies Kubernetes Gateway API Inference Extension EPP scoring and Sheddable load shedding."""
    pod_hot = MockVLLMServer(server_id="vllm-pod-1")
    pod_hot.configure_chaos(kv_cache_usage_perc=0.90, num_requests_waiting=16)

    pod_cool = MockVLLMServer(server_id="vllm-pod-2")
    pod_cool.configure_chaos(kv_cache_usage_perc=0.20, num_requests_waiting=0)

    epp = EndpointPickerScorer()
    chosen = epp.pick_best_endpoint(
        [pod_hot, pod_cool],
        prefix_hit_ratios={"vllm-pod-1": 0.80, "vllm-pod-2": 0.80},
        criticality="Critical",
    )
    assert chosen.server_id == "vllm-pod-2"

    # When both pods exceed 85% KV-cache utilization, Sheddable batch requests must be shed
    pod_cool.configure_chaos(kv_cache_usage_perc=0.92, num_requests_waiting=8)
    shed_triggered = False
    try:
        epp.pick_best_endpoint([pod_hot, pod_cool], criticality="Sheddable")
    except PermissionError:
        shed_triggered = True
    assert shed_triggered is True


def test_cumulative_histogram_buckets_and_routes() -> None:
    """Verifies true cumulative TTFT/ITL histogram buckets plus /health, /v1/models, and PDPA hook."""
    import re

    server = MockVLLMServer(server_id="vllm-primary-svc", base_ttft_ms=5.0, base_itl_ms=2.0)
    # 1 fast observation (~5ms) + 1 slow observation (~205ms)
    asyncio.run(
        server.handle_chat_completion(
            {"messages": [{"role": "user", "content": "fast request"}], "max_tokens": 8}
        )
    )
    server.configure_chaos(inject_latency_ms=200.0)
    asyncio.run(
        server.handle_chat_completion(
            {"messages": [{"role": "user", "content": "slow request"}], "max_tokens": 8}
        )
    )
    server.configure_chaos(inject_latency_ms=0.0)

    metrics_text = server.render_prometheus_metrics()

    def _bucket(metric: str, le: str) -> int:
        match = re.search(rf'{metric}\{{[^}}]*le="{re.escape(le)}"\}}\s+(\d+)', metrics_text)
        assert match is not None, f"Missing bucket {metric} le={le}"
        return int(match.group(1))

    b_005 = _bucket("vllm:time_to_first_token_seconds_bucket", "0.05")
    b_010 = _bucket("vllm:time_to_first_token_seconds_bucket", "0.1")
    b_050 = _bucket("vllm:time_to_first_token_seconds_bucket", "0.5")
    b_inf = _bucket("vllm:time_to_first_token_seconds_bucket", "+Inf")
    assert b_005 == 1, f"Only 1 fast observation <= 50ms expected, got {b_005}"
    assert b_010 == 1
    assert b_050 == 2, f"Both <= 500ms expected, got {b_050}"
    assert b_inf == 2

    assert _bucket("vllm:inter_token_latency_seconds_bucket", "0.010") >= 2
    assert _bucket("vllm:inter_token_latency_seconds_bucket", "+Inf") >= 2

    # Verify standalone LiteLLM pre-call hook
    hook_payload = {
        "messages": [{"role": "user", "content": "เช็กสิทธิ์ 1-1007-01234-56-1 เบอร์ 081-234-5678"}]
    }
    res = asyncio.run(proxy_handler_instance.async_pre_call_hook(None, None, hook_payload, "completion"))
    assert res["metadata"]["pdpa_redactions"] == 2
    assert "<THAI_ID_REDACTED>" in res["messages"][0]["content"]
    assert "<THAI_PHONE_REDACTED>" in res["messages"][0]["content"]

    # Verify FastAPI /health and /v1/models route registration and HTTP 503 pre-stream check when available
    try:
        from fastapi.testclient import TestClient  # type: ignore
        from mock_vllm_server.app import app as fastapi_app, default_mock_server
    except ImportError:
        fastapi_app = None
        TestClient = None  # type: ignore
    if fastapi_app is not None:
        paths = {getattr(r, "path", "") for r in fastapi_app.routes}
        assert "/health" in paths
        assert "/v1/models" in paths
        assert "/metrics" in paths
        assert "/v1/chat/completions" in paths
        if TestClient is not None:
            client = TestClient(fastapi_app)
            default_mock_server.configure_chaos(inject_http_503=True)
            r503 = client.post(
                "/v1/chat/completions",
                json={"model": "mock-qwen2.5-7b", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
            )
            default_mock_server.configure_chaos(inject_http_503=False)
            assert r503.status_code == 503
