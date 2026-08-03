import os

from src.config import Config
from src.services.trading.decision.offline_candidate_acceptance import (
    run_offline_candidate_acceptance,
)
from src.services.trading.market.timeframes import broker_symbol_for, resolve_symbol


def test_pytest_bootstrap_uses_committed_symbol_aliases_without_local_env():
    assert os.environ["TRADING_TEST_HERMETIC"] == "true"
    assert Config.MARKET_BROKER_SYMBOL_XAUUSD == "XAUUSDm"
    assert Config.MARKET_BROKER_SYMBOL_BTCUSD == "BTCUSDm"
    assert broker_symbol_for("XAUUSD") == "XAUUSDm"
    assert broker_symbol_for("BTCUSD") == "BTCUSDm"
    assert resolve_symbol("XAUUSDm").canonical_symbol == "XAUUSD"
    assert resolve_symbol("BTCUSDm").canonical_symbol == "BTCUSD"
    assert resolve_symbol("UNKNOWNUSDx").status == "UNRESOLVED"


def test_offline_acceptance_uses_typed_metadata_without_external_providers():
    result = run_offline_candidate_acceptance("fresh_market")

    assert result["candidate_admission_count"] == 1
    assert result["candidate_integrity_result"] == "VALID"
    assert result["external_proposal_provider_invocation_count"] == 0
    assert result["broker_mutation_count"] == 0
