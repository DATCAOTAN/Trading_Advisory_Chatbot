from src.services.evidence.answer_coverage import AnswerCoverageValidator


def test_comparative_report_synthesis_is_covered_without_literal_heading():
    answer = (
        "Bao cao cho thay toc do tang cham lai so voi thang truoc, "
        "nhung ap luc gia van dai dang va cac thanh phan dien bien khong dong deu."
    )
    result = AnswerCoverageValidator.evaluate(answer, ["short_interpretation"])

    assert result.status == "PASS"
    assert result.topic_statuses["short_interpretation"] == "COVERED"


def test_raw_numbers_alone_do_not_satisfy_interpretation():
    answer = "CPI 3.4%, previous 3.1%, core CPI 3.2%."
    result = AnswerCoverageValidator.evaluate(answer, ["short_interpretation"])

    assert result.status == "WARN"
    assert result.topic_statuses["short_interpretation"] in {"PARTIAL", "UNCERTAIN"}

