"""
Module 4 (M4): Mock vLLM V1 Streaming Server & AI Gateway Governance Components
===============================================================================
Designed for the No-GPU Local Path (<80MB RAM per pod) so learners can run
multi-replica failover (vllm-primary-svc:8000 & vllm-secondary-svc:8000),
KEDA autoscaling (M5), and Capstone chaos drills (M6) on a 16GB RAM laptop
without OOM-crashing the host.

Exposes exact vLLM V1 Prometheus metrics:
  - vllm:kv_cache_usage_perc (Gauge 0.0 - 1.0)
  - vllm:num_requests_running (Gauge)
  - vllm:num_requests_waiting (Gauge)
  - vllm:prefix_cache_hits_total (Counter, in tokens)
  - vllm:prefix_cache_queries_total (Counter, in tokens)
  - vllm:num_preemptions_total (Counter)
  - vllm:time_to_first_token_seconds_bucket (Histogram)
  - vllm:inter_token_latency_seconds_bucket (Histogram - Primary)
  - vllm:time_per_output_token_seconds_bucket (Histogram - Compat Alias)
  - vllm:generation_tokens_total (Counter)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

try:
    from .pdpa_guardrail import PDPAPIIMasker  # noqa: E402
except ImportError:  # pragma: no cover - direct script execution fallback
    from pdpa_guardrail import PDPAPIIMasker  # type: ignore # noqa: E402


# ==============================================================================
# 1. Mock vLLM V1 Server State & Prometheus Metrics Engine
# ==============================================================================
@dataclass
class MockVLLMServer:
    """
    Simulates a vLLM V1 OpenAI-compatible server with:
      - Automatic Prefix Caching (16-token block hash tracking)
      - Configurable TTFT & ITL latency and Chaos fault injection
      - Exact vLLM V1 Prometheus metrics exposition
    """

    server_id: str = field(default_factory=lambda: os.getenv("SERVER_ID", "vllm-primary-svc"))
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "mock-qwen2.5-7b"))
    block_size: int = 16

    # Live gauges & counters matching vLLM V1 metric names
    kv_cache_usage_perc: float = 0.18
    num_requests_running: int = 1
    num_requests_waiting: int = 0
    prefix_cache_hits_total: int = 0
    prefix_cache_queries_total: int = 0
    num_preemptions_total: int = 0
    generation_tokens_total: int = 0

    # Chaos / latency simulation knobs
    base_ttft_ms: float = 35.0
    base_itl_ms: float = 5.0
    inject_latency_ms: float = 0.0
    inject_http_503: bool = False

    # Internal prefix block cache (stores block SHA-256 hashes)
    _cached_prefix_blocks: set[str] = field(default_factory=set)
    _ttft_observations: List[float] = field(default_factory=list)
    _itl_observations: List[float] = field(default_factory=list)

    def configure_chaos(
        self,
        inject_latency_ms: Optional[float] = None,
        inject_http_503: Optional[bool] = None,
        kv_cache_usage_perc: Optional[float] = None,
        num_requests_waiting: Optional[int] = None,
    ) -> Dict[str, Any]:
        if inject_latency_ms is not None:
            self.inject_latency_ms = float(inject_latency_ms)
        if inject_http_503 is not None:
            self.inject_http_503 = bool(inject_http_503)
        if kv_cache_usage_perc is not None:
            self.kv_cache_usage_perc = max(0.0, min(1.0, float(kv_cache_usage_perc)))
        if num_requests_waiting is not None:
            self.num_requests_waiting = max(0, int(num_requests_waiting))
        return {
            "server_id": self.server_id,
            "inject_latency_ms": self.inject_latency_ms,
            "inject_http_503": self.inject_http_503,
            "kv_cache_usage_perc": self.kv_cache_usage_perc,
            "num_requests_waiting": self.num_requests_waiting,
        }

    def _update_prefix_cache_metrics(self, prompt_text: str) -> Tuple[int, int]:
        """
        Tokenizes roughly by whitespace/subwords and computes chained 16-token
        block hashes just like vLLM V1 Automatic Prefix Caching.
        """
        words = prompt_text.split()
        # Ensure at least 16 tokens for realistic prefix block accounting
        tokens = words if len(words) >= 16 else (words * 16)[: max(16, len(words))]
        num_tokens = len(tokens)
        self.prefix_cache_queries_total += num_tokens

        hits = 0
        parent_hash = "root"
        num_full_blocks = num_tokens // self.block_size
        for b in range(num_full_blocks):
            block_slice = " ".join(tokens[b * self.block_size : (b + 1) * self.block_size])
            block_hash = hashlib.sha256(f"{parent_hash}|{block_slice}".encode("utf-8")).hexdigest()
            if block_hash in self._cached_prefix_blocks:
                hits += self.block_size
            else:
                self._cached_prefix_blocks.add(block_hash)
            parent_hash = block_hash

        self.prefix_cache_hits_total += hits
        return num_tokens, hits

    async def handle_chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Processes an OpenAI-compatible /v1/chat/completions request."""
        if self.inject_http_503:
            raise RuntimeError(f"HTTP 503 Service Unavailable from {self.server_id}")

        total_delay_s = (self.base_ttft_ms + self.inject_latency_ms) / 1000.0
        if total_delay_s > 0:
            await asyncio.sleep(total_delay_s)

        messages = payload.get("messages", [])
        prompt_parts: List[str] = []
        for m in messages:
            content = m.get("content") if isinstance(m, dict) else m
            if isinstance(content, str):
                prompt_parts.append(content)
            elif isinstance(content, list):
                prompt_parts.extend(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
        prompt_text = " ".join(part for part in prompt_parts if part)
        prompt_tokens, prefix_hits = self._update_prefix_cache_metrics(prompt_text)

        output_tokens = int(payload.get("max_tokens", 32))
        self.generation_tokens_total += output_tokens
        self._ttft_observations.append(total_delay_s)
        self._itl_observations.append(self.base_itl_ms / 1000.0)

        if self.kv_cache_usage_perc >= 0.99:
            self.num_preemptions_total += 1

        reply_content = (
            f"[{self.server_id}] Processed prompt ({prompt_tokens} tok, "
            f"prefix_hits={prefix_hits} tok): {prompt_text[:160]}"
        )
        return {
            "id": f"chatcmpl-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", self.model_name),
            "routed_backend": self.server_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply_content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": prompt_tokens + output_tokens,
                "prefix_cache_hit_tokens": prefix_hits,
            },
        }

    async def stream_chat_completion(self, payload: Dict[str, Any]) -> AsyncIterator[str]:
        """Streams OpenAI-compatible Server-Sent Events (SSE) chunks."""
        resp = await self.handle_chat_completion(payload)
        text = resp["choices"][0]["message"]["content"]
        chunks = text.split(" ")
        for idx, token_str in enumerate(chunks):
            await asyncio.sleep(self.base_itl_ms / 1000.0)
            if idx > 0:
                self._itl_observations.append(self.base_itl_ms / 1000.0)
            event = {
                "id": resp["id"],
                "object": "chat.completion.chunk",
                "model": resp["model"],
                "routed_backend": self.server_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": (token_str + " ") if idx < len(chunks) - 1 else token_str},
                        "finish_reason": None if idx < len(chunks) - 1 else "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    def render_prometheus_metrics(self) -> str:
        """Exposes exact vLLM V1 Prometheus metrics format with true cumulative histogram buckets."""
        labels = f'model_name="{self.model_name}",server_id="{self.server_id}"'
        ttft_obs = self._ttft_observations if self._ttft_observations else [self.base_ttft_ms / 1000.0]
        itl_obs = self._itl_observations if self._itl_observations else [self.base_itl_ms / 1000.0]
        ttft_count = len(ttft_obs)
        ttft_sum = sum(ttft_obs)
        itl_count = len(itl_obs)
        itl_sum = sum(itl_obs)

        ttft_bounds = [("0.05", 0.05), ("0.1", 0.1), ("0.5", 0.5), ("0.75", 0.75), ("0.8", 0.8), ("2.0", 2.0)]
        itl_bounds = [("0.010", 0.010), ("0.015", 0.015), ("0.030", 0.030), ("0.050", 0.050)]

        lines = [
            "# HELP vllm:kv_cache_usage_perc Fraction of KV-cache blocks currently utilized (0.0 to 1.0).",
            "# TYPE vllm:kv_cache_usage_perc gauge",
            f"vllm:kv_cache_usage_perc{{{labels}}} {self.kv_cache_usage_perc:.4f}",
            "# HELP vllm:num_requests_running Number of requests currently in running batch.",
            "# TYPE vllm:num_requests_running gauge",
            f"vllm:num_requests_running{{{labels}}} {self.num_requests_running}",
            "# HELP vllm:num_requests_waiting Number of requests waiting in the scheduler queue.",
            "# TYPE vllm:num_requests_waiting gauge",
            f"vllm:num_requests_waiting{{{labels}}} {self.num_requests_waiting}",
            "# HELP vllm:prefix_cache_hits_total Total number of tokens that hit Automatic Prefix Cache.",
            "# TYPE vllm:prefix_cache_hits_total counter",
            f"vllm:prefix_cache_hits_total{{{labels}}} {self.prefix_cache_hits_total}",
            "# HELP vllm:prefix_cache_queries_total Total number of tokens queried against Automatic Prefix Cache.",
            "# TYPE vllm:prefix_cache_queries_total counter",
            f"vllm:prefix_cache_queries_total{{{labels}}} {self.prefix_cache_queries_total}",
            "# HELP vllm:num_preemptions_total Cumulative number of sequence preemptions (RECOMPUTE).",
            "# TYPE vllm:num_preemptions_total counter",
            f"vllm:num_preemptions_total{{{labels}}} {self.num_preemptions_total}",
            "# HELP vllm:generation_tokens_total Total number of generated output tokens.",
            "# TYPE vllm:generation_tokens_total counter",
            f"vllm:generation_tokens_total{{{labels}}} {self.generation_tokens_total}",
            "# HELP vllm:time_to_first_token_seconds Histogram of Time to First Token (TTFT).",
            "# TYPE vllm:time_to_first_token_seconds histogram",
            *[
                f'vllm:time_to_first_token_seconds_bucket{{{labels},le="{le_lbl}"}} '
                f"{sum(1 for v in ttft_obs if v <= upper)}"
                for le_lbl, upper in ttft_bounds
            ],
            f'vllm:time_to_first_token_seconds_bucket{{{labels},le="+Inf"}} {ttft_count}',
            f"vllm:time_to_first_token_seconds_sum{{{labels}}} {ttft_sum:.4f}",
            f"vllm:time_to_first_token_seconds_count{{{labels}}} {ttft_count}",
            "# HELP vllm:inter_token_latency_seconds Histogram of Inter-Token Latency (ITL).",
            "# TYPE vllm:inter_token_latency_seconds histogram",
            *[
                f'vllm:inter_token_latency_seconds_bucket{{{labels},le="{le_lbl}"}} '
                f"{sum(1 for v in itl_obs if v <= upper)}"
                for le_lbl, upper in itl_bounds
            ],
            f'vllm:inter_token_latency_seconds_bucket{{{labels},le="+Inf"}} {itl_count}',
            f"vllm:inter_token_latency_seconds_sum{{{labels}}} {itl_sum:.4f}",
            f"vllm:inter_token_latency_seconds_count{{{labels}}} {itl_count}",
            "# HELP vllm:time_per_output_token_seconds Compatibility alias of Inter-Token Latency (ITL).",
            "# TYPE vllm:time_per_output_token_seconds histogram",
            *[
                f'vllm:time_per_output_token_seconds_bucket{{{labels},le="{le_lbl}"}} '
                f"{sum(1 for v in itl_obs if v <= upper)}"
                for le_lbl, upper in itl_bounds
            ],
            f'vllm:time_per_output_token_seconds_bucket{{{labels},le="+Inf"}} {itl_count}',
            f"vllm:time_per_output_token_seconds_sum{{{labels}}} {itl_sum:.4f}",
            f"vllm:time_per_output_token_seconds_count{{{labels}}} {itl_count}",
        ]
        return "\n".join(lines) + "\n"


# ==============================================================================
# 3. Kubernetes Gateway API Inference Extension: Endpoint Picker (EPP) Scorer
# ==============================================================================
class EndpointPickerScorer:
    """
    Implements the KV-cache-aware and queue-aware scoring formula of the
    Kubernetes Gateway API Inference Extension Endpoint Picker (EPP):
      Score(i) = w_prefix * HitRatio_i - w_queue * (Q_i / Q_max) - w_kv * KV_i
    """

    def __init__(
        self,
        w_prefix: float = 2.0,
        w_queue: float = 3.0,
        w_kv: float = 2.5,
        q_max: float = 32.0,
        sheddable_kv_threshold: float = 0.85,
    ) -> None:
        self.w_prefix = w_prefix
        self.w_queue = w_queue
        self.w_kv = w_kv
        self.q_max = q_max
        self.sheddable_kv_threshold = sheddable_kv_threshold

    def score_backend(self, backend: MockVLLMServer, prefix_hit_ratio: float = 0.0) -> float:
        q_norm = backend.num_requests_waiting / self.q_max
        kv = backend.kv_cache_usage_perc
        return (
            (self.w_prefix * prefix_hit_ratio)
            - (self.w_queue * q_norm)
            - (self.w_kv * kv)
        )

    def pick_best_endpoint(
        self,
        backends: List[MockVLLMServer],
        prefix_hit_ratios: Optional[Dict[str, float]] = None,
        criticality: str = "Critical",
    ) -> MockVLLMServer:
        ratios = prefix_hit_ratios or {}
        # Load shedding for Sheddable batch workloads when all pods exceed KV threshold
        if criticality.lower() == "sheddable":
            healthy_for_batch = [
                b for b in backends if b.kv_cache_usage_perc < self.sheddable_kv_threshold
            ]
            if not healthy_for_batch:
                raise PermissionError(
                    "HTTP 429 Load Shedding: KV-cache utilization exceeds 85% threshold for Sheddable traffic"
                )
            candidates = healthy_for_batch
        else:
            candidates = backends

        best = max(
            candidates,
            key=lambda b: self.score_backend(b, ratios.get(b.server_id, 0.0)),
        )
        return best


# ==============================================================================
# 4. LiteLLM-Compatible Multi-Tenant Governance & Resilience Router
# ==============================================================================
class HTTP429RateLimitError(Exception):
    """Raised when a tenant virtual key exceeds its RPM or TPM quota."""

    def __init__(self, message: str, status_code: int = 429) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class GatewayResilienceRouter:
    """
    Simulates the LiteLLM Proxy Governance Control Plane on port 4000:
      1. Virtual Key Authentication & Per-Team RPM/TPM Rate Limiting
      2. Pre-Call PDPA PII Guardrail (Thai 13-digit ID & Phone Redaction)
      3. Exact Response Cache (Redis simulation)
      4. Stream Timeout & Automated Primary -> Secondary Failover
    """

    primary_backend: MockVLLMServer
    secondary_backend: MockVLLMServer
    stream_timeout_s: float = 3.0

    # Virtual key RPM quotas: sk-realtime-team (100 RPM) vs sk-batch-team (3 RPM for quick test)
    tenant_rpm_limits: Dict[str, int] = field(
        default_factory=lambda: {
            "sk-realtime-team": 100,
            "sk-batch-team": 3,
        }
    )
    _tenant_request_counts: Dict[str, int] = field(default_factory=dict)
    _response_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    async def chat_completions(
        self,
        api_key: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Step 1: Virtual Key & RPM Quota Check
        if api_key not in self.tenant_rpm_limits:
            raise PermissionError(f"HTTP 401 Invalid Virtual Key: {api_key}")

        current_count = self._tenant_request_counts.get(api_key, 0) + 1
        self._tenant_request_counts[api_key] = current_count
        if current_count > self.tenant_rpm_limits[api_key]:
            raise HTTP429RateLimitError(
                f"HTTP 429 Too Many Requests: Key '{api_key}' exceeded RPM quota ({self.tenant_rpm_limits[api_key]} RPM)",
                status_code=429,
            )

        # Step 2: Pre-call PDPA PII Redaction Guardrail (runs BEFORE cache & model routing!)
        raw_messages = payload.get("messages", [])
        sanitized_messages, redaction_count = PDPAPIIMasker.mask_messages(raw_messages)
        sanitized_payload = {**payload, "messages": sanitized_messages}

        # Step 3: Exact Response Cache Lookup (keyed by model + sanitized messages)
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "model": sanitized_payload.get("model", "qwen2.5-7b"),
                    "messages": sanitized_messages,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        if cache_key in self._response_cache:
            cached_resp = json.loads(json.dumps(self._response_cache[cache_key]))
            cached_resp["headers"] = {
                "X-Sim-Cache-Hit": "true",
                "X-Sim-Routed-Backend": cached_resp.get("routed_backend", "redis-cache"),
                "X-Sim-PDPA-Redactions": str(redaction_count),
            }
            return cached_resp

        # Step 4: Route to Primary Backend with stream_timeout_s; Fallback to Secondary on timeout/5xx
        try:
            response = await asyncio.wait_for(
                self.primary_backend.handle_chat_completion(sanitized_payload),
                timeout=self.stream_timeout_s,
            )
            routed = self.primary_backend.server_id
            fallback_triggered = False
        except (asyncio.TimeoutError, RuntimeError):
            response = await asyncio.wait_for(
                self.secondary_backend.handle_chat_completion(sanitized_payload),
                timeout=self.stream_timeout_s,
            )
            routed = self.secondary_backend.server_id
            fallback_triggered = True

        response["sanitized_messages"] = sanitized_messages
        response["headers"] = {
            "X-Sim-Cache-Hit": "false",
            "X-Sim-Routed-Backend": routed,
            "X-Sim-Fallback-Triggered": str(fallback_triggered).lower(),
            "X-Sim-PDPA-Redactions": str(redaction_count),
        }
        self._response_cache[cache_key] = json.loads(json.dumps(response))
        return response


# ==============================================================================
# 5. Optional FastAPI Application Binding (for container / uvicorn execution)
# ==============================================================================
default_mock_server = MockVLLMServer()

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import PlainTextResponse, StreamingResponse

    app = FastAPI(title="Mock vLLM V1 Server", version="1.0.0")

    @app.get("/health")
    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok", "server_id": default_mock_server.server_id}

    @app.get("/readyz")
    async def readyz() -> Dict[str, str]:
        if default_mock_server.inject_http_503:
            raise HTTPException(status_code=503, detail="Chaos 503 injected")
        return {
            "status": "ready",
            "model": default_mock_server.model_name,
            "server_id": default_mock_server.server_id,
        }

    @app.get("/v1/models")
    async def list_models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": default_mock_server.model_name,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": default_mock_server.server_id,
                }
            ],
        }

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        return default_mock_server.render_prometheus_metrics()

    @app.post("/admin/chaos")
    async def admin_chaos(req: Request) -> Dict[str, Any]:
        body = await req.json()
        return default_mock_server.configure_chaos(
            inject_latency_ms=body.get("inject_latency_ms"),
            inject_http_503=body.get("inject_http_503"),
            kv_cache_usage_perc=body.get("kv_cache_usage_perc"),
            num_requests_waiting=body.get("num_requests_waiting"),
        )

    @app.post("/v1/chat/completions")
    async def chat_completions_endpoint(req: Request) -> Any:
        if default_mock_server.inject_http_503:
            raise HTTPException(
                status_code=503,
                detail=f"HTTP 503 Service Unavailable from {default_mock_server.server_id}",
            )
        body = await req.json()
        if body.get("stream", False):
            return StreamingResponse(
                default_mock_server.stream_chat_completion(body),
                media_type="text/event-stream",
            )
        try:
            return await default_mock_server.handle_chat_completion(body)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

except ImportError:
    app = None  # FastAPI optional when running pure-Python unit tests
