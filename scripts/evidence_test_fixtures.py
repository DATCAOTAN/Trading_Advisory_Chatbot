from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.context_acquisition import TaskContextView
from src.services.semantic.context_execution import ContextAcquisitionResult


def query_plan(
    primary_intent: str = "book_concept_explanation",
    task_id: str = "task_1",
    query: str = "Al Brooks noi gi ve price action?",
    authors: List[str] | None = None,
    books: List[str] | None = None,
    concepts: List[str] | None = None,
    symbols: List[str] | None = None,
    macro_events: List[str] | None = None,
    organizations: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "original_query": query,
        "normalized_query": query,
        "primary_intent": primary_intent,
        "secondary_intents": [],
        "entities": {
            "symbols": symbols or [],
            "macro_events": macro_events or [],
            "organizations": organizations or [],
            "authors": authors or [],
            "books": books or [],
            "concepts": concepts or [],
            "strategies": [],
            "timeframes": [],
            "countries": [],
        },
        "temporal_scope": "timeless",
        "requested_analysis": [],
        "user_action_intent": "explanation",
        "requires_execution": False,
        "confidence": 0.9,
    }


def task_view(plan: Dict[str, Any], task_id: str | None = None) -> TaskContextView:
    return TaskContextView(
        task_id=task_id or plan.get("task_id", "task_1"),
        subquery=plan.get("original_query", ""),
        query_plan=plan,
        sufficiency_status="COMPLETE",
        confidence_ceiling="high",
    )


def knowledge_result(
    capability: str = "static_knowledge",
    target: str = "price_action",
    content: str = (
        "Price action reading focuses on what bars reveal about trader behavior, trend, "
        "breakouts, pullbacks, and failed attempts. The trader studies context before acting."
    ),
    title: str = "Reading Price Charts Bar by Bar",
    author: str = "Al Brooks",
    organization: str = "",
    event_type: str = "",
    task_ids: List[str] | None = None,
    freshness: str = "acceptable",
) -> ContextAcquisitionResult:
    doc = {
        "content": content,
        "metadata": {
            "title": title,
            "author": author,
            "organization": organization,
            "knowledge_type": "report" if capability == "official_report" else "book",
            "event_type": event_type,
            "section": "content",
            "chunk_id": f"{title}:{target}:1",
        },
        "score": 0.91,
    }
    return ContextAcquisitionResult(
        capability=capability,
        target=target,
        status="success",
        required=True,
        requested_by_tasks=task_ids or ["task_1"],
        data=[doc],
        source="Knowledge V3",
        operation="retrieve",
        provenance={
            "title": title,
            "author": author,
            "organization": organization,
            "event_type": event_type,
            "provider": "knowledge_current",
        },
        fetched_at=datetime.now(timezone.utc).isoformat(),
        freshness_status=freshness,
    )


def cpi_report_result(task_ids: List[str] | None = None) -> ContextAcquisitionResult:
    return knowledge_result(
        capability="official_report",
        target="CPI",
        content=(
            "The Consumer Price Index report discusses inflation pressure across headline "
            "and core CPI components, including shelter, services, prices, rates, and "
            "how those categories affect inflation assessment for the current period."
        ),
        title="US CPI Report",
        author="",
        organization="BLS",
        event_type="CPI",
        task_ids=task_ids or ["task_1"],
    )


def event_result(task_ids: List[str] | None = None) -> ContextAcquisitionResult:
    return ContextAcquisitionResult(
        capability="economic_event",
        target="CPI",
        status="success",
        required=True,
        requested_by_tasks=task_ids or ["task_1"],
        data={
            "event_name": "US CPI",
            "country": "US",
            "actual": "3.4%",
            "forecast": "3.2%",
            "previous": "3.1%",
            "surprise": "higher_than_forecast",
            "release_time": "2026-07-01T12:30:00Z",
            "source": "existing_calendar_api",
        },
        source="existing_calendar_api",
        operation="get_economic_calendar",
        provenance={"event_type": "CPI", "provider": "existing_calendar_api"},
        freshness_status="fresh",
    )


def market_result(task_ids: List[str] | None = None, freshness: str = "fresh") -> ContextAcquisitionResult:
    return ContextAcquisitionResult(
        capability="market_snapshot",
        target="XAUUSD",
        status="success",
        required=True,
        requested_by_tasks=task_ids or ["task_1"],
        data={
            "symbol": "XAUUSD",
            "timeframe": "1m",
            "latest_price": 2345.67,
            "recent_trend": "mixed",
            "volatility_note": "event driven",
            "timestamp": "2026-07-06T03:00:00Z",
            "source": "existing_live_data",
        },
        source="existing_live_data",
        operation="get_live_price",
        provenance={"symbol": "XAUUSD", "provider": "existing_live_data"},
        freshness_status=freshness,
    )


def ohlcv_result(task_ids: List[str] | None = None, freshness: str = "fresh") -> ContextAcquisitionResult:
    return ContextAcquisitionResult(
        capability="ohlcv",
        target="XAUUSD",
        status="success",
        required=True,
        requested_by_tasks=task_ids or ["task_1"],
        normalized_parameters={"timeframe": "15m", "lookback": 100},
        data=[
            {"timestamp": "2026-07-06T02:45:00Z", "open": 2340, "high": 2348, "low": 2338, "close": 2345.67}
        ],
        source="existing_live_data",
        operation="get_historical_candles",
        provenance={"symbol": "XAUUSD", "timeframe": "15m", "provider": "existing_live_data"},
        freshness_status=freshness,
    )


def technical_result(task_ids: List[str] | None = None) -> ContextAcquisitionResult:
    return ContextAcquisitionResult(
        capability="technical_snapshot",
        target="XAUUSD",
        status="success",
        required=False,
        requested_by_tasks=task_ids or ["task_1"],
        data={"RSI": 54.2, "EMA50": 2341.0, "interpretation": "neutral momentum"},
        source="ExistingTechnicalSnapshotAdapter",
        operation="build_snapshot",
        provenance={"symbol": "XAUUSD", "timeframe": "15m"},
        freshness_status="fresh",
    )
