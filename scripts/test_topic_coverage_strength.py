import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.services.evidence.evidence_coverage import EvidenceCoverageEvaluator, CoverageRequirementSet, EvidenceCoverageResult, EvidenceTopicAttributor
from src.services.evidence.coverage_requirements import CoverageRequirement
from src.services.evidence.evidence_pipeline import EvidenceBundle, EvidenceItem
from src.services.evidence.topic_evidence_binding import TopicEvidenceBindingBuilder

def test_topic_coverage_strength():
    req_set = CoverageRequirementSet(
        task_id="test_task",
        required_topics=[
            CoverageRequirement(topic_role="topic_strong", required=True, description="Explain strong topic"),
            CoverageRequirement(topic_role="topic_adequate", required=True, description="Explain adequate topic"),
            CoverageRequirement(topic_role="topic_weak", required=True, description="Explain weak topic"),
            CoverageRequirement(topic_role="topic_unsupported", required=True, description="Explain unsupported topic")
        ],
        optional_topics=[],
        minimum_required_coverage_ratio=0.5
    )
    
    item1 = EvidenceItem(evidence_id="1", task_id="test_task", evidence_type="test", capability="knowledge", content="strong content")
    item2 = EvidenceItem(evidence_id="2", task_id="test_task", evidence_type="test", capability="knowledge", content="adequate content")
    item3 = EvidenceItem(evidence_id="3", task_id="test_task", evidence_type="test", capability="knowledge", content="weak content")
    
    # Mock EvidenceTopicAttributor
    class MockAttributorResult:
        def __init__(self, topics, scores):
            self.covered_topics = topics
            self.topic_scores = scores

    def mock_attribute(item, req_set):
        if item.evidence_id == "1":
            return MockAttributorResult(["topic_strong"], {"topic_strong": 0.8})
        elif item.evidence_id == "2":
            return MockAttributorResult(["topic_adequate"], {"topic_adequate": 0.5})
        elif item.evidence_id == "3":
            return MockAttributorResult(["topic_weak"], {"topic_weak": 0.3})
        return MockAttributorResult([], {})

    from src.services.evidence import evidence_coverage
    original_attribute = evidence_coverage.EvidenceTopicAttributor.attribute
    evidence_coverage.EvidenceTopicAttributor.attribute = mock_attribute

    try:
        bundle = EvidenceBundle(task_id="test_task", query="test query", query_plan=None, answer_type="default")
        bundle.primary_evidence = [item1, item2, item3]
        
        result = EvidenceCoverageEvaluator.evaluate(bundle, req_set)
        
        assert result.status == "INSUFFICIENT", f"Expected INSUFFICIENT, got {result.status}"
        assert "topic_strong" in result.strong_required_topics
        assert "topic_adequate" in result.adequate_required_topics
        assert "topic_weak" in result.weak_required_topics
        assert "topic_unsupported" in result.unsupported_required_topics
        assert result.topic_presence_ratio == 0.75
        assert result.required_supported_ratio == 0.75
        
        # Test Binding Builder
        binding_set, plan = TopicEvidenceBindingBuilder.build(bundle, req_set)
        assert plan.required_strong == 1
        assert plan.required_adequate == 1
        assert plan.required_weak == 0
        assert plan.required_unsupported == 2
        assert plan.required_total == 4
        print("All tests passed!")
    finally:
        evidence_coverage.EvidenceTopicAttributor.attribute = original_attribute

if __name__ == "__main__":
    test_topic_coverage_strength()


def _market_behavior_requirements():
    return CoverageRequirementSet(
        task_id="market_task",
        required_topics=[
            CoverageRequirement(
                topic_role="current_state",
                required=True,
                description="Current market state",
                min_usefulness=0.5,
            ),
            CoverageRequirement(
                topic_role="recent_market_behavior",
                required=True,
                description="Recent temporal market behavior",
                min_usefulness=0.5,
            ),
        ],
        optional_topics=[
            CoverageRequirement(
                topic_role="technical_context",
                required=False,
                description="Technical context",
                min_usefulness=0.5,
            ),
        ],
    )


def test_current_price_alone_does_not_support_recent_market_behavior():
    req_set = _market_behavior_requirements()
    item = EvidenceItem(
        evidence_id="snapshot_only",
        task_id="market_task",
        evidence_type="market_snapshot",
        capability="market_snapshot",
        content="MarketSnapshot: price=2400.5; timestamp=2026-07-10T10:00:00Z",
        raw={"latest_price": 2400.5, "timestamp": "2026-07-10T10:00:00Z"},
    )

    attr = EvidenceTopicAttributor.attribute(item, req_set)

    assert "current_state" in attr.covered_topics
    assert "recent_market_behavior" not in attr.covered_topics


def test_ohlcv_with_multi_period_behavior_supports_recent_market_behavior():
    req_set = _market_behavior_requirements()
    item = EvidenceItem(
        evidence_id="ohlcv_behavior",
        task_id="market_task",
        evidence_type="ohlcv_summary",
        capability="ohlcv",
        content=(
            "OHLCV TEST: candles=3; latest_close=2412; first_close=2400; "
            "last_close=2412; direction=up; change_pct=0.5; range_pct=1.1"
        ),
        raw={
            "count": 3,
            "behavior": {
                "count": 3,
                "first_close": 2400,
                "last_close": 2412,
                "direction": "up",
                "change_pct": 0.5,
                "range_pct": 1.1,
            },
        },
    )

    attr = EvidenceTopicAttributor.attribute(item, req_set)

    assert "recent_market_behavior" in attr.covered_topics
    assert attr.topic_scores["recent_market_behavior"] >= 0.7


def test_ohlcv_latest_value_only_is_not_strong_recent_market_behavior():
    req_set = _market_behavior_requirements()
    item = EvidenceItem(
        evidence_id="ohlcv_latest_only",
        task_id="market_task",
        evidence_type="ohlcv_summary",
        capability="ohlcv",
        content="OHLCV TEST: candles=1; latest_close=2400; timeframe=1h",
        raw={"count": 1, "candles": [{"close": 2400}]},
    )

    attr = EvidenceTopicAttributor.attribute(item, req_set)

    assert "current_state" in attr.covered_topics
    assert "recent_market_behavior" not in attr.covered_topics


def test_technical_trend_snapshot_supports_recent_market_behavior():
    req_set = _market_behavior_requirements()
    item = EvidenceItem(
        evidence_id="technical_trend",
        task_id="market_task",
        evidence_type="technical_snapshot",
        capability="technical_snapshot",
        content="technical_snapshot={'trend': 'uptrend', 'momentum': 'bullish', 'volatility': 'elevated'}",
        raw={"trend": "uptrend", "momentum": "bullish", "volatility": "elevated"},
    )

    attr = EvidenceTopicAttributor.attribute(item, req_set)

    assert "recent_market_behavior" in attr.covered_topics
    assert attr.topic_scores["recent_market_behavior"] >= 0.7


def test_multiple_weak_items_do_not_aggregate_to_strong_support():
    req_set = CoverageRequirementSet(
        task_id="market_task",
        required_topics=[
            CoverageRequirement(
                topic_role="recent_market_behavior",
                required=True,
                description="Recent temporal market behavior",
                min_usefulness=0.5,
            )
        ],
    )
    item1 = EvidenceItem(
        evidence_id="weak_1",
        task_id="market_task",
        evidence_type="market_snapshot",
        capability="market_snapshot",
        content="MarketSnapshot: latest_price=2400",
        raw={"latest_price": 2400},
    )
    item1.topic_scores = {"recent_market_behavior": 0.3}
    item2 = EvidenceItem(
        evidence_id="weak_2",
        task_id="market_task",
        evidence_type="market_snapshot",
        capability="market_snapshot",
        content="MarketSnapshot: latest_price=2401",
        raw={"latest_price": 2401},
    )
    item2.topic_scores = {"recent_market_behavior": 0.35}
    bundle = EvidenceBundle(task_id="market_task", query="market state", query_plan=None, answer_type="market_analysis")
    bundle.primary_evidence = [item1, item2]

    _, plan = TopicEvidenceBindingBuilder.build(bundle, req_set)

    assert plan.required_strong == 0
    assert plan.required_unsupported == 1
