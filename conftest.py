import os


collect_ignore = ["run_manual_test.py", "test_reranker_manual.py"]

# Must run before pytest imports application settings or loads the local .env.
os.environ["TRADING_TEST_HERMETIC"] = "true"
os.environ["TRADING_REASONING_LLM_ENABLED"] = "false"
os.environ["MT5_SYMBOL_MAP_XAUUSD"] = "XAUUSDm"
os.environ["MARKET_BROKER_SYMBOL_XAUUSD"] = "XAUUSDm"
os.environ["MT5_SYMBOL_MAP_BTCUSD"] = "BTCUSDm"
os.environ["MARKET_BROKER_SYMBOL_BTCUSD"] = "BTCUSDm"
