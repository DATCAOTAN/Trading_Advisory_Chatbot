from src.services.evidence.answer_coverage import AnswerCoverageValidator


def test_minimum_event_state_actual_and_previous_is_covered():
    answer = "Du lieu moi nhat cong bo CPI thuc te tang 0.3%, so voi ky truoc 0.2%."
    result = AnswerCoverageValidator.evaluate(answer, ["event_state"])

    assert result.status == "PASS"
    assert result.topic_statuses["event_state"] == "COVERED"


def test_surprise_event_state_requires_forecast_when_contract_demands_it():
    answer = "The release reported actual CPI at 0.3%, while the previous value was 0.2%."
    result = AnswerCoverageValidator.evaluate(answer, ["event_state_surprise_analysis"])

    assert result.status == "WARN"
    assert result.topic_statuses["event_state_surprise_analysis"] == "PARTIAL"
    assert "forecast" in result.topic_reasons["event_state_surprise_analysis"]


def test_event_name_alone_is_uncertain_not_covered():
    result = AnswerCoverageValidator.evaluate("CPI is important for markets.", ["event_state"])

    assert result.status == "WARN"
    assert result.topic_statuses["event_state"] == "UNCERTAIN"

