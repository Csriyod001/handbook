"""
Unit & Resilience Tests for Module 1 FastAPI Bounded Queue Service (`ai-inference-service`)
======================================================================================
Verifies:
1. Liveness probe (`/healthz`) always returns 200 OK.
2. Readiness probe (`/readyz`) verifies `HF_HOME` writability under `readOnlyRootFilesystem`.
3. Normal inference request (`/v1/predict`) returns 200 OK with expected schema.
4. Bounded Semaphore Queue sheds excess concurrent load with HTTP 429 + Retry-After header.
5. Prometheus `/metrics` endpoint exposes `ai_service_shed_requests_total` and gauges.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from app.main import BoundedInferenceEngine, ServiceConfig


def test_liveness_probe() -> None:
    """Liveness probe must return HTTP 200 and service name ai-inference-service."""
    with tempfile.TemporaryDirectory() as tmp_hf:
        cfg = ServiceConfig(hf_home=tmp_hf)
        eng = BoundedInferenceEngine(cfg)
        status, body = asyncio.run(eng.liveness_check())
        assert status == 200
        assert body["status"] == "alive"
        assert body["service"] == "ai-inference-service"
        assert body["namespace"] == "ai-platform"
        assert cfg.port == 8000


def test_readiness_probe_and_hf_home() -> None:
    """Readiness probe must succeed when HF_HOME is writable and return 503 when unwritable."""
    with tempfile.TemporaryDirectory() as tmp_hf:
        cfg = ServiceConfig(hf_home=tmp_hf)
        eng = BoundedInferenceEngine(cfg)
        status, body = asyncio.run(eng.readiness_check())
        assert status == 200
        assert body["status"] == "ready"
        assert body["hf_home_writable"] is True

    # Simulate read-only rootfs failure by pointing HF_HOME to an invalid file path
    with tempfile.NamedTemporaryFile() as blocker_file:
        invalid_hf_home = os.path.join(blocker_file.name, "cannot_mkdir_inside_file")
        cfg_bad = ServiceConfig(hf_home=invalid_hf_home)
        eng_bad = BoundedInferenceEngine(cfg_bad)
        status_bad, body_bad = asyncio.run(eng_bad.readiness_check())
        assert status_bad == 503
        assert body_bad["status"] == "not_ready"
        assert body_bad["hf_home_writable"] is False


def test_predict_normal_request() -> None:
    """Normal inference request within queue bounds must return 200 OK."""
    with tempfile.TemporaryDirectory() as tmp_hf:
        cfg = ServiceConfig(
            hf_home=tmp_hf,
            max_concurrent_requests=4,
            simulated_inference_sec=0.01,
        )
        eng = BoundedInferenceEngine(cfg)
        status, body, _ = asyncio.run(
            eng.predict(
                {
                    "transaction_id": "tx-1001",
                    "amount_thb": 45000.0,
                    "prompt": "Analyze transaction risk",
                }
            )
        )
        assert status == 200
        assert body["transaction_id"] == "tx-1001"
        assert body["model"] == "Qwen/Qwen2.5-0.5B-Instruct"
        assert body["decision"] == "APPROVE"
        assert body["cached_artifact_used"] is True


def test_bounded_queue_load_shedding_429() -> None:
    """
    When concurrent requests exceed max_concurrent_requests and cannot acquire
    the semaphore within queue_acquire_timeout_sec, excess requests must fail-fast
    with HTTP 429 Too Many Requests and Retry-After header.
    """
    with tempfile.TemporaryDirectory() as tmp_hf:
        cfg = ServiceConfig(
            hf_home=tmp_hf,
            enable_bounded_queue=True,
            max_concurrent_requests=3,
            queue_acquire_timeout_sec=0.02,
            simulated_inference_sec=0.12,
        )
        eng = BoundedInferenceEngine(cfg)

        async def _burst() -> list[tuple[int, dict, dict]]:
            tasks = [
                eng.predict({"transaction_id": f"tx-{i}", "amount_thb": 10000.0})
                for i in range(10)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.run(_burst())
        status_codes = [r[0] for r in results]
        ok_count = status_codes.count(200)
        shed_count = status_codes.count(429)

        assert ok_count == 3, f"Expected 3 requests to succeed, got {ok_count}"
        assert shed_count == 7, f"Expected 7 requests to be shed with 429, got {shed_count}"
        assert eng.shed_requests_total == 7

        # Verify Retry-After header on 429 responses
        for code, body, headers in results:
            if code == 429:
                assert headers.get("Retry-After") == "1"
                assert body["error"] == "too_many_requests"


def test_default_hf_home_is_non_root_cache() -> None:
    """Default HF_HOME must point to /cache/huggingface for non-root UID 10001 compatibility."""
    prev = os.environ.pop("HF_HOME", None)
    try:
        cfg = ServiceConfig()
        assert cfg.hf_home == "/cache/huggingface"
    finally:
        if prev is not None:
            os.environ["HF_HOME"] = prev


def test_concurrent_readiness_probes() -> None:
    """Concurrent /readyz checks must not collide on shared probe filenames."""
    with tempfile.TemporaryDirectory() as tmp_hf:
        cfg = ServiceConfig(hf_home=tmp_hf)
        eng = BoundedInferenceEngine(cfg)

        async def _check_many() -> list[tuple[int, dict]]:
            return await asyncio.gather(*(eng.readiness_check() for _ in range(10)))

        results = asyncio.run(_check_many())
        assert all(code == 200 and body["hf_home_writable"] is True for code, body in results)


def test_prometheus_metrics_exposed() -> None:
    """Prometheus metrics exposition must include request and load-shedding counters."""
    with tempfile.TemporaryDirectory() as tmp_hf:
        cfg = ServiceConfig(hf_home=tmp_hf, simulated_inference_sec=0.005)
        eng = BoundedInferenceEngine(cfg)
        asyncio.run(eng.predict({"transaction_id": "tx-99", "amount_thb": 5000.0}))
        metrics_text = eng.render_prometheus_metrics()
        assert 'ai_service_requests_total{service="ai-inference-service"} 1' in metrics_text
        assert 'ai_service_completed_requests_total{service="ai-inference-service"} 1' in metrics_text
        assert 'ai_service_shed_requests_total{service="ai-inference-service"} 0' in metrics_text


def test_fastapi_http_endpoints_if_available() -> None:
    """Exercise live FastAPI routes via TestClient when fastapi+httpx are installed."""
    try:
        from fastapi.testclient import TestClient  # type: ignore
        import app.main as app_mod
    except ImportError:
        print("  [SKIP] FastAPI/httpx not installed; HTTP TestClient check skipped")
        return

    if app_mod.app is None:
        return

    with tempfile.TemporaryDirectory() as tmp_hf:
        app_mod.engine = BoundedInferenceEngine(
            ServiceConfig(hf_home=tmp_hf, simulated_inference_sec=0.005)
        )
        client = TestClient(app_mod.app)
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        pred = client.post(
            "/v1/predict",
            json={"transaction_id": "tx-http", "amount_thb": 25000.0},
        )
        assert pred.status_code == 200
        assert pred.json()["transaction_id"] == "tx-http"
        assert "ai_service_requests_total" in client.get("/metrics").text
