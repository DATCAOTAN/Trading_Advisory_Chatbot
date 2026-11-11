from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_execution_permission_contract import (
    _enable_execution_ready_config,
)
from src.config import Config
from src.services.trading.decision.autonomous_candidate_monitor import (
    AutonomousCandidateMonitor,
    AutonomousCandidateMonitorError,
    AutonomousCandidateMonitorJournal,
    monitor_profile_id,
    _record_hash,
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


class Handler:
    def __init__(self, assembler, orchestrator):
        self.assembler = assembler
        self.orchestrator = orchestrator

    def __call__(self, **kwargs):
        try:
            inputs = self.assembler.build(
                symbol=kwargs["symbol"], timeframes=kwargs["timeframes"]
            )
            run_result = self.orchestrator.run_once(inputs)
            return _monitor_result(
                "GENERATED",
                kwargs,
                candidate_reference=run_result.candidate.candidate_reference,
                intent=run_result.candidate.intent,
                validation_valid=True,
            )
        except OperatorCandidateInputError as exc:
            no_action = exc.blockers == ("STRUCTURED_PROPOSAL_NOT_AVAILABLE",)
            return _monitor_result(
                "NO_ACTION" if no_action else "BLOCKED",
                kwargs,
                intent="NO_ACTION" if no_action else "",
                blocker=str(exc),
            )


def monitor(tmp_path, *, feature=None, assembler=None, orchestrator=None):
    return AutonomousCandidateMonitor(
        feature_service=feature or FeatureService(),
        completed_bar_handler=Handler(
            assembler or Assembler(), orchestrator or Orchestrator()
        ),
        journal=AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl"),
    )


def test_one_generation_per_completed_bar_and_next_bar_runs(tmp_path):
    feature, assembler, orchestrator = FeatureService(), Assembler(), Orchestrator()
    subject = monitor(
        tmp_path, feature=feature, assembler=assembler, orchestrator=orchestrator
    )

    first = _run(subject)
    duplicate = _run(subject)
    feature.bar_time = "2026-08-02T01:01:00+00:00"
    second = _run(subject)

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

    first = _run(subject)
    duplicate = _run(subject)

    assert first.status == first.intent == "NO_ACTION"
    assert duplicate.status == "NO_NEW_BAR"
    assert assembler.calls == 1


@pytest.mark.parametrize("replayed", ["2026-08-02T00:59:00+00:00", "2026-08-02T08:00:00+07:00"])
def test_restart_cannot_replay_an_older_or_equivalent_completed_bar(tmp_path, replayed):
    feature = FeatureService()
    assert _run(monitor(tmp_path, feature=feature)).status == "GENERATED"
    feature.bar_time = replayed
    assembler = Assembler()
    restarted = monitor(tmp_path, feature=feature, assembler=assembler)
    assert _run(restarted).status == "NO_NEW_BAR"
    assert assembler.calls == 0


def test_incomplete_started_attempt_is_never_retried(tmp_path):
    journal = AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl")
    profile = monitor_profile_id("BTCUSD", ("M1", "H1", "H4"), "account-a")
    assert journal.claim(
        profile_id=profile,
        account_scope="account-a",
        symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        timeframes=("M1", "H1", "H4"),
        closed_bar_time="2026-08-02T01:00:00+00:00",
    )
    assembler = Assembler()
    subject = AutonomousCandidateMonitor(
        feature_service=FeatureService(),
        completed_bar_handler=Handler(assembler, Orchestrator()),
        journal=journal,
    )

    result = _run(subject)

    assert result.status == "RESULT_UNKNOWN"
    assert result.blocker == "MONITOR_PREVIOUS_ATTEMPT_INCOMPLETE"
    assert assembler.calls == 0


def test_stale_market_blocks_before_claim_and_generation(tmp_path):
    assembler = Assembler()
    subject = monitor(
        tmp_path, feature=FeatureService(quality="STALE"), assembler=assembler
    )

    result = _run(subject)

    assert result.status == "BLOCKED"
    assert result.blocker == "MONITOR_MARKET_INPUT_NOT_FRESH"
    assert assembler.calls == 0
    assert subject.journal.records() == []


def test_mixed_execution_permission_blocks_before_market_or_generation(
    tmp_path, monkeypatch
):
    feature, assembler = FeatureService(), Assembler()
    monkeypatch.setattr(Config, "TRADING_EXECUTION_LIVE_ENABLED", True)
    subject = monitor(tmp_path, feature=feature, assembler=assembler)

    result = _run(subject)

    assert result.blocker == "MONITOR_PERMISSION_STATE_INCOHERENT"
    assert feature.calls == assembler.calls == 0


def test_execution_ready_permissions_reach_completed_bar_and_candidate(
    tmp_path, monkeypatch
):
    _enable_execution_ready_config(monkeypatch)
    feature, assembler, orchestrator = FeatureService(), Assembler(), Orchestrator()
    subject = monitor(
        tmp_path, feature=feature, assembler=assembler, orchestrator=orchestrator
    )

    result = _run(subject)

    assert result.status == "GENERATED"
    assert result.candidate_reference == "candidate-1"
    assert feature.calls == assembler.calls == orchestrator.calls == 1


def test_corrupt_monitor_journal_fails_closed(tmp_path):
    path = tmp_path / "monitor.jsonl"
    path.write_text('{"status":"GENERATED"}\n', encoding="utf-8")
    journal = AutonomousCandidateMonitorJournal(path)

    with pytest.raises(AutonomousCandidateMonitorError, match="MONITOR_JOURNAL_CORRUPT"):
        journal.records()


def test_monitor_journal_detects_tampering(tmp_path):
    subject = monitor(tmp_path)
    _run(subject)
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


def test_unresolved_attempt_blocks_next_bar_and_accounts_are_independent(tmp_path):
    journal = AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl")
    profile_a = monitor_profile_id("BTCUSD", ("M1", "H1", "H4"), "account-a")
    assert journal.claim(
        profile_id=profile_a,
        account_scope="account-a",
        symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        timeframes=("M1", "H1", "H4"),
        closed_bar_time="2026-08-02T01:00:00+00:00",
    )
    feature = FeatureService("2026-08-02T01:01:00+00:00")
    blocked = AutonomousCandidateMonitor(
        feature_service=feature,
        completed_bar_handler=Handler(Assembler(), Orchestrator()),
        journal=journal,
    )

    assert _run(blocked).status == "RESULT_UNKNOWN"
    other = blocked.run_once(
        symbol="BTCUSD", timeframes=("M1", "H1", "H4"), account_scope="account-b"
    )
    assert other.status == "GENERATED"


def test_legacy_unscoped_started_record_blocks_retry_after_upgrade(tmp_path):
    path = tmp_path / "monitor.jsonl"
    legacy = {
        "event_id": "legacy-event",
        "created_at": "2026-08-02T01:00:01+00:00",
        "profile_id": monitor_profile_id("BTCUSD", ("M1", "H1", "H4")),
        "symbol": "BTCUSD",
        "broker_symbol": "BTCUSDm",
        "timeframes": ["M1", "H1", "H4"],
        "closed_bar_time": "2026-08-02T01:00:00+00:00",
        "phase": "STARTED",
        "status": "STARTED",
        "candidate_reference": "",
        "intent": "",
        "blocker": "",
        "validation_valid": False,
        "generation_count": 0,
        "execution_authority": False,
        "export_called": False,
        "submission_called": False,
        "order_send_called": False,
        "metadata_redacted": True,
    }
    legacy["record_hash"] = _record_hash(legacy)
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    subject = AutonomousCandidateMonitor(
        feature_service=FeatureService("2026-08-02T01:01:00+00:00"),
        completed_bar_handler=Handler(Assembler(), Orchestrator()),
        journal=AutonomousCandidateMonitorJournal(path),
    )

    result = _run(subject)

    assert result.status == "RESULT_UNKNOWN"
    assert result.blocker == "MONITOR_PREVIOUS_ATTEMPT_INCOMPLETE"


def _run(subject):
    return subject.run_once(
        symbol="BTCUSD", timeframes=("M1", "H1", "H4"), account_scope="account-a"
    )


def _monitor_result(status, values, **changes):
    from src.services.trading.decision.autonomous_candidate_monitor import (
        AutonomousCandidateMonitorResult,
    )

    return AutonomousCandidateMonitorResult(
        status=status,
        symbol=values["symbol"],
        broker_symbol=values["broker_symbol"],
        timeframes=values["timeframes"],
        closed_bar_time=values["closed_bar_time"],
        account_scope=values["account_scope"],
        generation_count=1,
        proposal_provider_max_invocations=1,
        **changes,
    )
