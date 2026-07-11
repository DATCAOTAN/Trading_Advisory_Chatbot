from src.services.evidence.answer_coverage import AnswerCoverageValidator


def test_vietnamese_macro_answer_covers_report_and_scenario_roles():
    answer = (
        "Bao cao cho thay toc do tang cham lai so voi thang truoc, ap luc gia ha nhiet nhung chua bien mat. "
        "Du lieu moi nhat cong bo thuc te 0.3% so voi ky truoc 0.4%. "
        "Neu gia pha len tren khang cu sau khi loi suat suy yeu, kich ban tang duoc xac nhan; "
        "neu gia roi xuong duoi ho tro va dong USD manh len, kich ban bi vo hieu."
    )
    result = AnswerCoverageValidator.evaluate(
        answer,
        ["short_interpretation", "event_state", "confirmation_or_invalidation"],
    )

    assert result.status == "PASS"
    assert all(status == "COVERED" for status in result.topic_statuses.values())

