from src.services.evidence.answer_coverage import AnswerCoverageValidator


def test_observable_confirmation_conditions_are_covered():
    answer = (
        "Neu gia pha len tren vung khang cu va loi suat suy yeu, kich ban tang duoc xac nhan. "
        "Neu gia pha xuong duoi ho tro trong khi dong USD manh len, kich ban nay bi vo hieu."
    )
    result = AnswerCoverageValidator.evaluate(answer, ["confirmation_or_invalidation"])

    assert result.status == "PASS"
    assert result.topic_statuses["confirmation_or_invalidation"] == "COVERED"


def test_vague_watch_market_phrase_is_not_strong_confirmation_logic():
    result = AnswerCoverageValidator.evaluate(
        "Can theo doi thi truong can than trong cac phien toi.",
        ["confirmation_or_invalidation"],
    )

    assert result.status == "WARN"
    assert result.topic_statuses["confirmation_or_invalidation"] in {"UNCERTAIN", "PARTIAL"}

