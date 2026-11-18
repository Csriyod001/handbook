"""
LiteLLM Proxy Pre-Call PDPA Guardrail Callback (`pdpa_guardrail.py`)
=====================================================================
Single Source of Truth for Thai PDPA PII masking:
  - 13-digit Thai National IDs (formatted or contiguous) -> <THAI_ID_REDACTED>
  - 10-digit Thai mobile phone numbers (06x/08x/09x) -> <THAI_PHONE_REDACTED>
  - Modulo-11 checksum validation helper (`validate_thai_id_checksum`)

Runs standalone inside Kubernetes LiteLLM Proxy (`/app/pdpa_guardrail.py` mounted via ConfigMap)
via `litellm_settings.callbacks: ["pdpa_guardrail.proxy_handler_instance"]`, and is also imported
by `mock_vllm_server.app` for zero-duplication resilience testing.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore
except ImportError:  # Standalone mode when running offline unit tests without litellm

    class CustomLogger:  # type: ignore[no-redef]
        """Minimal stub mirroring litellm.integrations.custom_logger.CustomLogger."""


class PDPAPIIMasker:
    """
    Pre-call PDPA Guardrail aligned with OWASP Top 10 for LLM Applications (2025):
      - LLM02:2025 Sensitive Information Disclosure
      - Redacts 13-digit Thai National IDs (formatted or unformatted) -> <THAI_ID_REDACTED>
      - Redacts 10-digit Thai mobile phone numbers -> <THAI_PHONE_REDACTED>
    """

    THAI_ID_PATTERN = re.compile(
        r"\b[1-8](?:[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d|\d{12})\b"
    )
    THAI_PHONE_PATTERN = re.compile(
        r"(?<![\d.])(?:0|\+?66[-\s]?)[689]\d[-\s]?\d{3}[-\s]?\d{4}(?!\d)"
    )

    @staticmethod
    def validate_thai_id_checksum(digits_only: str) -> bool:
        """
        Verifies the Modulo-11 check digit (13th digit) of a Thai National ID:
          S = sum(d_i * (14 - i) for i in 1..12)
          check_digit = (11 - (S % 11)) % 10
        """
        clean = re.sub(r"\D", "", digits_only)
        if len(clean) != 13 or clean[0] in ("0", "9"):
            return False
        total = sum(int(clean[i]) * (13 - i) for i in range(12))
        check_digit = (11 - (total % 11)) % 10
        return check_digit == int(clean[12])

    @classmethod
    def mask_text(cls, text: str, strict_checksum: bool = False) -> Tuple[str, int]:
        """Returns (masked_text, redaction_count).

        When strict_checksum=True, only 13-digit matches passing the Thai Modulo-11
        check digit are redacted (reducing false positives on bank/order IDs).
        When strict_checksum=False (default fail-safe mode), all structural matches
        are redacted to protect typoed customer IDs under PDPA.
        """
        redactions = 0

        def _replace_id(match: re.Match[str]) -> str:
            nonlocal redactions
            candidate = match.group(0)
            if strict_checksum and not cls.validate_thai_id_checksum(candidate):
                return candidate
            redactions += 1
            return "<THAI_ID_REDACTED>"

        def _replace_phone(match: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return "<THAI_PHONE_REDACTED>"

        masked = cls.THAI_ID_PATTERN.sub(_replace_id, text)
        masked = cls.THAI_PHONE_PATTERN.sub(_replace_phone, masked)
        return masked, redactions

    @classmethod
    def mask_messages(
        cls,
        messages: List[Dict[str, Any]],
        strict_checksum: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Returns deep-copied messages with string and multimodal text PII masked."""
        total_redactions = 0
        sanitized: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                sanitized.append(msg)
                continue
            content = msg.get("content")
            if content is None:
                sanitized.append({**msg, "content": None})
            elif isinstance(content, str):
                masked_content, count = cls.mask_text(content, strict_checksum=strict_checksum)
                total_redactions += count
                sanitized.append({**msg, "content": masked_content})
            elif isinstance(content, list):
                masked_parts: List[Any] = []
                for part in content:
                    if (
                        isinstance(part, dict)
                        and part.get("type") == "text"
                        and isinstance(part.get("text"), str)
                    ):
                        masked_text, count = cls.mask_text(
                            part["text"], strict_checksum=strict_checksum
                        )
                        total_redactions += count
                        masked_parts.append({**part, "text": masked_text})
                    else:
                        masked_parts.append(part)
                sanitized.append({**msg, "content": masked_parts})
            else:
                masked_content, count = cls.mask_text(
                    str(content), strict_checksum=strict_checksum
                )
                total_redactions += count
                sanitized.append({**msg, "content": masked_content})
        return sanitized, total_redactions


class PDPACustomGuardrail(CustomLogger):
    """Self-contained PDPA PII masking guardrail executing in LiteLLM pre-call phase."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: Dict[str, Any],
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
            "pass_through_endpoint",
            "rerank",
        ],
        **kwargs: Any,
    ) -> Optional[Union[Exception, str, Dict[str, Any]]]:
        """Masks Thai PII across chat `messages` or `prompt` before cache lookup or backend dispatch."""
        messages = data.get("messages")
        redactions = 0
        if isinstance(messages, list):
            sanitized_messages, redactions = PDPAPIIMasker.mask_messages(messages)
            data["messages"] = sanitized_messages
        elif isinstance(data.get("prompt"), str):
            sanitized_prompt, redactions = PDPAPIIMasker.mask_text(data["prompt"])
            data["prompt"] = sanitized_prompt

        metadata = data.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["pdpa_redactions"] = redactions
        return data


proxy_handler_instance = PDPACustomGuardrail()
