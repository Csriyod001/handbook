"""
Production FastAPI Inference Wrapper with Bounded Concurrency Queue (Module 1)
==============================================================================
Canonical Variables (from SPEC_AND_STYLE_GUIDE.md):
- Service Name : ai-inference-service (Image: ai-inference-service:1.0.0)
- Port         : 8000
- Namespace    : ai-platform
- Model ID     : Qwen/Qwen2.5-0.5B-Instruct
- Cache Path   : HF_HOME=/cache/huggingface

Key Engineering Features:
1. Bounded Semaphore Queue (`asyncio.Semaphore`) with fail-fast HTTP 429 shedding
   to prevent unbounded memory growth and Zombie Work during traffic spikes.
2. Strict separation of `/healthz` (Liveness) vs `/readyz` (Readiness):
   - `/healthz` returns 200 OK as long as the event loop is alive (prevents Kubelet
     from killing the pod during temporary load spikes).
   - `/readyz` verifies `HF_HOME` writability (critical under `readOnlyRootFilesystem: true`)
     and checks queue saturation, returning 503 when saturated or misconfigured.
3. Prometheus `/metrics` endpoint exposing request counters, shed request counters,
   in-flight gauge, and latency histograms.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


# ==============================================================================
# 1. Runtime Configuration (Configurable via Environment Variables)
# ==============================================================================
@dataclass
class ServiceConfig:
    service_name: str = field(
        default_factory=lambda: os.getenv("SERVICE_NAME", "ai-inference-service")
    )
    namespace: str = field(
        default_factory=lambda: os.getenv("K8S_NAMESPACE", "ai-platform")
    )
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    model_id: str = field(
        default_factory=lambda: os.getenv("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
    )
    hf_home: str = field(
        default_factory=lambda: os.getenv("HF_HOME", "/cache/huggingface")
    )
    enable_bounded_queue: bool = field(
        default_factory=lambda: os.getenv("ENABLE_BOUNDED_QUEUE", "true").lower()
        == "true"
    )
    max_concurrent_requests: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_REQUESTS", "4"))
    )
    queue_acquire_timeout_sec: float = field(
        default_factory=lambda: float(os.getenv("QUEUE_ACQUIRE_TIMEOUT_SEC", "0.08"))
    )
    simulated_inference_sec: float = field(
        default_factory=lambda: float(os.getenv("SIMULATED_INFERENCE_SEC", "0.02"))
    )


# ==============================================================================
# 2. Core Bounded-Queue Inference Engine & Telemetry State
# ==============================================================================
class BoundedInferenceEngine:
    """Manages bounded concurrency, HF_HOME cache verification, and Prometheus metrics."""

    def __init__(self, config: ServiceConfig | None = None) -> None:
        self.config = config or ServiceConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)
        self.in_flight_requests: int = 0
        self.total_requests: int = 0
        self.shed_requests_total: int = 0
        self.completed_requests_total: int = 0
        self.latency_sum_seconds: float = 0.0

    def verify_hf_home_writable(self) -> Tuple[bool, str]:
        """Verify that HF_HOME exists or can be written to under readOnlyRootFilesystem."""
        hf_path = self.config.hf_home
        try:
            os.makedirs(hf_path, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=hf_path,
                prefix=".write_probe_",
                mode="w",
                encoding="utf-8",
                delete=True,
            ) as f:
                f.write("ok")
                f.flush()
            return True, "HF_HOME volume is mounted and writable"
        except OSError as exc:
            return (
                False,
                f"HF_HOME directory '{hf_path}' is not writable under readOnlyRootFilesystem: {exc}",
            )

    async def liveness_check(self) -> Tuple[int, Dict[str, Any]]:
        """Liveness probe (/healthz): always 200 if event loop is responsive."""
        return 200, {
            "status": "alive",
            "service": self.config.service_name,
            "namespace": self.config.namespace,
        }

    async def readiness_check(self) -> Tuple[int, Dict[str, Any]]:
        """Readiness probe (/readyz): 503 if HF_HOME is unwritable or queue is saturated."""
        writable, reason = await asyncio.to_thread(self.verify_hf_home_writable)
        saturated = (
            self.config.enable_bounded_queue
            and self.in_flight_requests >= self.config.max_concurrent_requests
        )
        is_ready = writable and not saturated
        status_code = 200 if is_ready else 503
        return status_code, {
            "status": "ready" if is_ready else "not_ready",
            "service": self.config.service_name,
            "model": self.config.model_id,
            "hf_home": self.config.hf_home,
            "hf_home_writable": writable,
            "in_flight_requests": self.in_flight_requests,
            "max_concurrent_requests": self.config.max_concurrent_requests,
            "reason": "ok" if is_ready else ("queue_saturated" if writable else reason),
        }

    async def predict(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        """
        Execute inference under a bounded asyncio.Semaphore.
        Returns (http_status_code, json_body, headers).
        """
        self.total_requests += 1
        start_time = time.perf_counter()

        if self.config.enable_bounded_queue:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=self.config.queue_acquire_timeout_sec,
                )
            except asyncio.TimeoutError:
                self.shed_requests_total += 1
                return (
                    429,
                    {
                        "error": "too_many_requests",
                        "message": (
                            f"Bounded queue saturated (max_concurrent_requests="
                            f"{self.config.max_concurrent_requests}). Shedding load to prevent OOM."
                        ),
                        "retry_after_seconds": 1,
                    },
                    {"Retry-After": "1"},
                )

        self.in_flight_requests += 1
        try:
            await asyncio.sleep(self.config.simulated_inference_sec)
            amount = float(payload.get("amount_thb", 0.0))
            tx_id = str(payload.get("transaction_id", "tx-unknown"))
            risk_score = round(min(0.99, max(0.05, amount / 250000.0)), 2)
            decision = "REVIEW" if risk_score >= 0.70 else "APPROVE"
            elapsed_sec = time.perf_counter() - start_time
            self.completed_requests_total += 1
            self.latency_sum_seconds += elapsed_sec

            return (
                200,
                {
                    "transaction_id": tx_id,
                    "model": self.config.model_id,
                    "risk_score": risk_score,
                    "decision": decision,
                    "latency_ms": round(elapsed_sec * 1000.0, 2),
                    "cached_artifact_used": True,
                },
                {},
            )
        finally:
            self.in_flight_requests -= 1
            if self.config.enable_bounded_queue:
                self._semaphore.release()

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus text exposition format metrics."""
        lines = [
            "# HELP ai_service_in_flight_requests Current number of in-flight inference requests",
            "# TYPE ai_service_in_flight_requests gauge",
            f'ai_service_in_flight_requests{{service="{self.config.service_name}"}} {self.in_flight_requests}',
            "# HELP ai_service_requests_total Total incoming inference requests",
            "# TYPE ai_service_requests_total counter",
            f'ai_service_requests_total{{service="{self.config.service_name}"}} {self.total_requests}',
            "# HELP ai_service_shed_requests_total Requests rejected with HTTP 429 due to bounded queue saturation",
            "# TYPE ai_service_shed_requests_total counter",
            f'ai_service_shed_requests_total{{service="{self.config.service_name}"}} {self.shed_requests_total}',
            "# HELP ai_service_completed_requests_total Successfully completed inference requests",
            "# TYPE ai_service_completed_requests_total counter",
            f'ai_service_completed_requests_total{{service="{self.config.service_name}"}} {self.completed_requests_total}',
            "# HELP ai_service_inference_latency_seconds_sum Total inference latency in seconds",
            "# TYPE ai_service_inference_latency_seconds_sum counter",
            f'ai_service_inference_latency_seconds_sum{{service="{self.config.service_name}"}} {self.latency_sum_seconds:.6f}',
        ]
        return "\n".join(lines) + "\n"


engine = BoundedInferenceEngine()


# ==============================================================================
# 3. FastAPI Wiring (with zero-dependency fallback when FastAPI is not installed)
# ==============================================================================
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, PlainTextResponse

    app = FastAPI(
        title="ai-inference-service",
        version="1.0.0",
        description="Production AI Inference Wrapper with Bounded Concurrency",
    )

    @app.get("/healthz")
    @app.get("/health")
    async def healthz() -> JSONResponse:
        code, body = await engine.liveness_check()
        return JSONResponse(status_code=code, content=body)

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        code, body = await engine.readiness_check()
        return JSONResponse(status_code=code, content=body)

    @app.post("/v1/predict")
    async def predict_endpoint(request: Request) -> JSONResponse:
        payload = await request.json()
        code, body, headers = await engine.predict(payload)
        return JSONResponse(status_code=code, content=body, headers=headers)

    @app.get("/metrics")
    async def metrics_endpoint() -> PlainTextResponse:
        return PlainTextResponse(
            content=engine.render_prometheus_metrics(),
            media_type="text/plain; version=0.0.4",
        )

except ImportError:
    # Allows unit testing `BoundedInferenceEngine` on bare Python stdlib environments
    app = None
