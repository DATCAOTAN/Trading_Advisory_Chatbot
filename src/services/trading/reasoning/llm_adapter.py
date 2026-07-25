from __future__ import annotations

import hashlib
import time
from typing import Any, Mapping, Protocol

from src.config import Config
from src.services.trading.reasoning.models import LLMReasoningRequest, LLMReasoningResponse
from src.services.trading.reasoning.output_parser import MethodReasoningOutputParser


class ReasoningProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        ...


class DisabledReasoningProvider:
    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        raise RuntimeError("trading_reasoning_llm_disabled")


class ProjectLLMReasoningProvider:
    def __init__(self, provider_name: str | None = None):
        self.provider_name = provider_name or getattr(Config, "TRADING_REASONING_LLM_PROVIDER", "") or None

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        from src.core.llm_client import LLMClient

        client = LLMClient(provider_override=self.provider_name)
        response = client.chat(
            [{"role": "user", "content": prompt}],
            stream=False,
            temperature=temperature,
        )
        return _response_text(response)


class LLMReasoningAdapter:
    def __init__(self, provider: ReasoningProvider | None = None, parser: MethodReasoningOutputParser | None = None):
        self.provider = provider
        self.parser = parser or MethodReasoningOutputParser()

    def complete(self, request: LLMReasoningRequest) -> LLMReasoningResponse:
        started = time.perf_counter()
        provider_name = request.provider_name or "disabled"
        if not bool(getattr(Config, "TRADING_REASONING_LLM_ENABLED", False)) and self.provider is None:
            return LLMReasoningResponse(
                response_id=_response_id(request.request_id, "disabled"),
                request_id=request.request_id,
                provider_name="disabled",
                parse_status="FAILED",
                warnings=["llm_disabled"],
                errors=["trading_reasoning_llm_disabled"],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        provider = self.provider or ProjectLLMReasoningProvider(provider_name)
        try:
            raw_text = provider.complete(request.compact_prompt, request.max_tokens, request.temperature)
            parsed = self.parser.parse(raw_text, request.mode, request.symbol, request.context_pack_id, [])
            status = "OK" if parsed else "FAILED"
            return LLMReasoningResponse(
                response_id=_response_id(request.request_id, raw_text),
                request_id=request.request_id,
                provider_name=provider_name,
                raw_text_redacted=_redact(raw_text),
                parsed_result=parsed,
                parse_status=status,
                warnings=[] if parsed else ["parse_failed"],
                errors=[] if parsed else ["invalid_json"],
                latency_ms=(time.perf_counter() - started) * 1000,
                token_usage_estimate=max(1, (len(request.compact_prompt) + len(str(raw_text))) // 4),
            )
        except Exception as exc:
            return LLMReasoningResponse(
                response_id=_response_id(request.request_id, type(exc).__name__),
                request_id=request.request_id,
                provider_name=provider_name,
                raw_text_redacted="",
                parse_status="FAILED",
                warnings=["provider_error"],
                errors=[type(exc).__name__],
                latency_ms=(time.perf_counter() - started) * 1000,
            )


class StubLLMReasoningAdapter(LLMReasoningAdapter):
    def __init__(self, raw_text: str):
        super().__init__(provider=_StaticProvider(raw_text))


class _StaticProvider:
    def __init__(self, raw_text: str):
        self.raw_text = raw_text

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        return self.raw_text


def _response_id(request_id: str, text: str) -> str:
    digest = hashlib.sha256(f"{request_id}|{text}".encode("utf-8")).hexdigest()[:16]
    return f"llm_reasoning_response_{digest}"


def _redact(text: str) -> str:
    raw = str(text or "")
    if len(raw) > 4000:
        raw = raw[:4000] + "...[truncated]"
    return raw.replace("api_key", "api_[redacted]").replace("password", "[redacted]")


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        message = response.get("message")
        if isinstance(message, Mapping) and isinstance(message.get("content"), str):
            return message["content"]
    raise RuntimeError("trading_reasoning_response_missing_content")
