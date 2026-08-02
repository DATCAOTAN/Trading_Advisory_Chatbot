from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.config import Config
from src.services.trading.decision.autonomous_candidate_monitor import (
    AutonomousCandidateMonitor,
    AutonomousCandidateMonitorError,
    AutonomousCandidateMonitorJournal,
    monitor_profile_id,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionRunResult,
)
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
)


class FeatureService:
    def __init__(self, bar_time="2026-08-02T01:00:00+00:00", quality="COMPLETE"):
        self.bar_time = bar_time
        self.quality = quality
        self.calls = 0

    def build_features(self, symbol, timeframes, candle_count):
        self.calls += 1
        bars = [SimpleNamespace(timestamp=self.bar_time)] if self.bar_time else []
        snapshots = {
            timeframe: SimpleNamespace(bars=bars) for timeframe in timeframes
        }
        return SimpleNamespace(
            quality_report=SimpleNamespace(status=self.quality),
            bundle=SimpleNamespace(broker_symbol=symbol + "m", timeframes=snapshots),
        )


class Assembler:
    def __init__(self, blocker=""):
        self.blocker = blocker
        self.calls = 0

    def build(self, **kwargs):
        self.calls += 1
        if self.blocker:
            raise OperatorCandidateInputError(self.blocker)
        return SimpleNamespace(request=kwargs)


class Orchestrator:
    def __init__(self):
        self.calls = 0

    def run_once(self, inputs):
        self.calls += 1
        return AutonomousDecisionRunResult(
            candidate=SimpleNamespace(
                candidate_reference=f"candidate-{self.calls}", intent="OPEN_POSITION"
            ),
            validation=SimpleNamespace(valid=True, issues=()),
            journal_appended=True,
            persistence_safe=True,
        )


def monitor(tmp_path, *, feature=None, assembler=None, orchestrator=None):
    return AutonomousCandidateMonitor(
        feature_service=feature or FeatureService(),
        input_assembler=assembler or Assembler(),
        decision_orchestrator=orchestrator or Orchestrator(),
        journal=AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl"),
    )


def test_one_generation_per_completed_bar_and_next_bar_runs(tmp_path):
    feature, assembler, orchestrator = FeatureService(), Assembler(), Orchestrator()
    subject = monitor(
        tmp_path, feature=feature, assembler=assembler, orchestrator=orchestrator
    )

    first = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))
    duplicate = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))
    feature.bar_time = "2026-08-02T01:01:00+00:00"
    second = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))

    assert (first.status, duplicate.status, second.status) == (
        "GENERATED",
        "NO_NEW_BAR",
        "GENERATED",
    )
    assert assembler.calls == orchestrator.calls == 2
    assert first.execution_authority is first.submission_called is first.order_send_called is False
    assert len(subject.journal.records()) == 4


def test_natural_no_action_is_terminal_for_the_bar(tmp_path):
    assembler = Assembler("STRUCTURED_PROPOSAL_NOT_AVAILABLE")
    subject = monitor(tmp_path, assembler=assembler)

    first = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))
    duplicate = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))

    assert first.status == first.intent == "NO_ACTION"
    assert duplicate.status == "NO_NEW_BAR"
    assert assembler.calls == 1


def test_incomplete_started_attempt_is_never_retried(tmp_path):
    journal = AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl")
    profile = monitor_profile_id("BTCUSD", ("M1", "H1", "H4"))
    assert journal.claim(
        profile_id=profile,
        symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        timeframes=("M1", "H1", "H4"),
        closed_bar_time="2026-08-02T01:00:00+00:00",
    )
    assembler = Assembler()
    subject = AutonomousCandidateMonitor(
        feature_service=FeatureService(),
        input_assembler=assembler,
        decision_orchestrator=Orchestrator(),
        journal=journal,
    )

    result = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))

    assert result.status == "RESULT_UNKNOWN"
    assert result.blocker == "MONITOR_PREVIOUS_ATTEMPT_INCOMPLETE"
    assert assembler.calls == 0


def test_stale_market_blocks_before_claim_and_generation(tmp_path):
    assembler = Assembler()
    subject = monitor(
        tmp_path, feature=FeatureService(quality="STALE"), assembler=assembler
    )

    result = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))

    assert result.status == "BLOCKED"
    assert result.blocker == "MONITOR_MARKET_INPUT_NOT_FRESH"
    assert assembler.calls == 0
    assert subject.journal.records() == []


def test_execution_permission_blocks_before_market_or_generation(tmp_path, monkeypatch):
    feature, assembler = FeatureService(), Assembler()
    monkeypatch.setattr(Config, "TRADING_EXECUTION_LIVE_ENABLED", True)
    subject = monitor(tmp_path, feature=feature, assembler=assembler)

    result = subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))

    assert result.blocker == "MONITOR_EXECUTION_PERMISSION_ENABLED"
    assert feature.calls == assembler.calls == 0


def test_corrupt_monitor_journal_fails_closed(tmp_path):
    path = tmp_path / "monitor.jsonl"
    path.write_text('{"status":"GENERATED"}\n', encoding="utf-8")
    journal = AutonomousCandidateMonitorJournal(path)

    with pytest.raises(AutonomousCandidateMonitorError, match="MONITOR_JOURNAL_CORRUPT"):
        journal.records()


def test_monitor_journal_detects_tampering(tmp_path):
    subject = monitor(tmp_path)
    subject.run_once(symbol="BTCUSD", timeframes=("M1", "H1", "H4"))
    rows = subject.journal.path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[-1])
    payload["status"] = "NO_ACTION"
    rows[-1] = json.dumps(payload)
    subject.journal.path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(AutonomousCandidateMonitorError, match="MONITOR_JOURNAL_CORRUPT"):
        subject.journal.records()


def test_dashboard_only_reads_monitor_and_has_no_monitor_execution_button():
    source = open("src/ui/tab_dashboard.py", encoding="utf-8").read()
    assert "AutonomousCandidateMonitorJournal" in source
    assert "Start Candidate Monitor" not in source
    assert "Submit Monitored Candidate" not in source
