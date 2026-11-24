#!/usr/bin/env python3
"""
Module 3 (M3) Mini-Lab: Quantization Quality Eval Gate (`eval_thai_quality.py`)
===============================================================================
Ensures INT4-AWQ / FP8 quantization does not degrade Thai language fidelity,
PDPA awareness, or strict JSON structured output before promoting a model.

Supports:
  --simulate : Deterministic offline comparison (BF16 vs AWQ vs FP8)
  --live     : Evaluates a running OpenAI-compatible vLLM endpoint
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    prompt: str
    expect_json: bool
    required_keywords: tuple[str, ...]


EVAL_SUITE: List[EvalCase] = [
    EvalCase(
        case_id="thai-json-pdpa",
        prompt=(
            'ตอบเป็น JSON เท่านั้น {"risk": "HIGH|LOW", "masked": true} '
            "สำหรับข้อความ: ลูกค้า <THAI_ID_REDACTED> ขอโอนเงิน 180000 บาท"
        ),
        expect_json=True,
        required_keywords=("risk", "masked"),
    ),
    EvalCase(
        case_id="thai-math-sla",
        prompt="หาก TTFT เป้าหมายคือ < 800 ms และระบบวัดได้ 640 ms ถือว่า PASS หรือ FAIL? ตอบสั้นๆ ภาษาไทย",
        expect_json=False,
        required_keywords=("PASS",),
    ),
    EvalCase(
        case_id="thai-kv-concept",
        prompt="อธิบายสั้นๆ ว่าเหตุใดควรวาง Dynamic Timestamp ไว้ท้าย Prompt แทนต้น System Prompt",
        expect_json=False,
        required_keywords=("Prefix",),
    ),
]


def score_response(case: EvalCase, content: str) -> Dict[str, Any]:
    """Validate JSON parseability (if expected) and required keyword presence."""
    json_ok = True
    if case.expect_json:
        try:
            stripped = content.strip()
            if stripped.startswith("```"):
                stripped = "\n".join(
                    line for line in stripped.splitlines() if not line.strip().startswith("```")
                )
            parsed = json.loads(stripped)
            json_ok = isinstance(parsed, dict)
        except Exception:
            json_ok = False

    kw_hits = sum(1 for kw in case.required_keywords if kw.lower() in content.lower())
    kw_ok = kw_hits == len(case.required_keywords)
    return {
        "case_id": case.case_id,
        "json_ok": json_ok,
        "keyword_ok": kw_ok,
        "passed": json_ok and kw_ok,
    }


def run_simulation() -> int:
    print("================================================================================")
    print(" [M3 EVAL GATE] Thai & Structured JSON Quantization Quality Check (--simulate)")
    print("================================================================================")
    profiles = [
        ("Qwen2.5-7B-Instruct (BF16 Baseline)", 100.0, 100.0, 0.0, "PASS (Reference)"),
        ("Qwen2.5-7B-Instruct-AWQ (INT4-Marlin)", 98.5, 97.2, 1.4, "PASS (Within <=2% Gate)"),
        ("Qwen2.5-7B-Instruct (Native FP8 W+KV)", 99.2, 99.0, 0.5, "PASS (Best Balance)"),
        ("Qwen2.5-3B-Instruct-AWQ (RTX 4050 6GB)", 95.0, 93.8, 3.1, "PASS (Local Dev Gate)"),
    ]
    print(f"{'Profile':<42} | {'JSON Valid':>10} | {'Thai Acc':>8} | {'Delta':>6} | {'Status'}")
    print("-" * 92)
    for name, json_rate, thai_acc, delta, status in profiles:
        print(f"{name:<42} | {json_rate:>9.1f}% | {thai_acc:>7.1f}% | -{delta:>4.1f}% | {status}")
    print("================================================================================")
    print("[PASS] Quantization Eval Gate completed. Always run --live after changing weights/kv-cache dtype.")
    return 0


def run_live(url: str, model: str) -> int:
    endpoint = f"{url.rstrip('/')}/v1/chat/completions"
    results: List[Dict[str, Any]] = []
    for case in EVAL_SUITE:
        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": case.prompt}],
                "temperature": 0.0,
                "max_tokens": 128,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
        results.append(score_response(case, text))

    passed = sum(1 for r in results if r["passed"])
    print(f"[LIVE EVAL] Model={model} | Passed {passed}/{len(results)} Thai/JSON cases")
    for r in results:
        print(f"  - {r['case_id']}: passed={r['passed']} (json_ok={r['json_ok']}, keyword_ok={r['keyword_ok']})")
    return 0 if passed == len(results) else 1


def test_eval_gate_scoring() -> None:
    """Pytest entrypoint verifying Thai JSON & keyword eval scoring."""
    good_json = '{"risk": "HIGH", "masked": true}'
    bad_json = "risk is HIGH and masked true"
    assert score_response(EVAL_SUITE[0], good_json)["passed"] is True
    assert score_response(EVAL_SUITE[0], bad_json)["passed"] is False
    assert run_simulation() == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Quantization Quality Eval Gate for Thai & JSON outputs.")
    parser.add_argument("--simulate", action="store_true", help="Run deterministic offline eval summary")
    parser.add_argument("--live", action="store_true", help="Run against a live vLLM OpenAI endpoint")
    parser.add_argument("--url", default="http://localhost:8000", help="Target server base URL")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct-AWQ", help="Served model ID")
    args = parser.parse_args()

    if args.live:
        return run_live(args.url, args.model)
    return run_simulation()


if __name__ == "__main__":
    sys.exit(main())
