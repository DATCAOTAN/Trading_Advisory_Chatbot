from src.services.evidence.evidence_pipeline import TopicRepairDecision


def test_uncertain_required_topic_with_strong_evidence_allows_repair():
    decision = TopicRepairDecision.evaluate(
        task_id="task_1",
        topic_role="short_interpretation",
        answer_status="UNCERTAIN",
        evidence_strength="STRONG",
        repair_attempt_count=0,
    )

    assert decision.repair_allowed is True


def test_uncertain_required_topic_with_weak_evidence_does_not_repair():
    decision = TopicRepairDecision.evaluate(
        task_id="task_1",
        topic_role="event_state",
        answer_status="UNCERTAIN",
        evidence_strength="WEAK",
        repair_attempt_count=0,
    )

    assert decision.repair_allowed is False
    assert decision.reason_code == "insufficient_evidence_strength"


def test_maximum_one_repair_attempt_is_enforced():
    decision = TopicRepairDecision.evaluate(
        task_id="task_1",
        topic_role="confirmation_or_invalidation",
        answer_status="MISSING",
        evidence_strength="ADEQUATE",
        repair_attempt_count=1,
    )

    assert decision.repair_allowed is False
    assert decision.reason_code == "max_attempts_reached"

