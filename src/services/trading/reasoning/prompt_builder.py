from __future__ import annotations

import hashlib
import json
from typing import Any

from src.config import Config
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.models import LLMReasoningRequest, now_utc_iso


class MethodReasoningPromptBuilder:
    def build(
        self,
        context_pack: RuntimeContextPack,
        mode: str | None = None,
        user_selected_method_id: str | None = None,
    ) -> LLMReasoningRequest:
        selected_mode = mode or context_pack.mode
        payload = {
            "role": "method_reasoning_only",
            "instructions": [
                "Compare only the method candidates present in the supplied RuntimeContextPack.",
                "Return strict JSON matching MethodSelectionResult fields.",
                "Do not create executable instructions or a final market action.",
                "Do not use raw books, raw reports, raw candles, account data, credentials, or external tools.",
            ],
            "forbidden_outputs": [
                "BUY",
                "SELL",
                "entry",
                "stop loss",
                "take profit",
                "lot",
                "account risk",
                "order" + "_send",
                "trade decision",
            ],
            "mode": selected_mode,
            "user_selected_method_id": user_selected_method_id or "",
            "symbol": context_pack.symbol,
            "broker_symbol": context_pack.broker_symbol,
            "context_pack_id": context_pack.context_pack_id,
            "feature_summary": context_pack.feature_snapshot_summary,
            "calendar_summary": context_pack.calendar_context_summary,
            "market_regime_summary": context_pack.market_regime_summary,
            "selected_method_cards": context_pack.selected_method_cards,
            "selected_macro_cards": context_pack.selected_macro_cards,
            "selected_playbooks": context_pack.selected_playbooks,
            "rejected_or_blocked_knowledge": context_pack.rejected_or_blocked_knowledge,
            "source_refs": context_pack.source_refs,
            "required_json_schema": _result_schema(),
        }
        compact_prompt = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        created_at = now_utc_iso()
        return LLMReasoningRequest(
            request_id=_request_id(context_pack.context_pack_id, selected_mode, created_at),
            created_at=created_at,
            mode=selected_mode,
            symbol=context_pack.symbol,
            context_pack_id=context_pack.context_pack_id,
            compact_prompt=compact_prompt,
            max_tokens=int(getattr(Config, "TRADING_REASONING_MAX_TOKENS", 1200)),
            temperature=float(getattr(Config, "TRADING_REASONING_TEMPERATURE", 0.1)),
            provider_name=str(getattr(Config, "TRADING_REASONING_LLM_PROVIDER", "") or "disabled"),
            metadata={
                "prompt_size_chars": len(compact_prompt),
                "token_estimate": max(1, len(compact_prompt) // 4),
                "source": "RuntimeContextPack",
            },
        )


def _result_schema() -> dict[str, Any]:
    return {
        "primary_method_id": "string",
        "supporting_method_ids": ["string"],
        "rejected_method_ids": ["string"],
        "selected_playbook_ids": ["string"],
        "relevant_macro_ids": ["string"],
        "overall_context_fit": "number_0_to_1",
        "confidence": "number_0_to_1",
        "blockers": ["string"],
        "warnings": ["string"],
        "reasoning_summary": "string",
        "candidate_assessments": [
            {
                "method_id": "string",
                "role": "PRIMARY_CANDIDATE|SUPPORTING_CONFIRMATION|REJECTED|RISK_ONLY",
                "compatibility_score": "number_0_to_1",
                "reasons": ["string"],
                "conflicts": ["string"],
                "source_refs": ["string"],
            }
        ],
    }


def _request_id(context_pack_id: str, mode: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{context_pack_id}|{mode}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"llm_reasoning_request_{digest}"
