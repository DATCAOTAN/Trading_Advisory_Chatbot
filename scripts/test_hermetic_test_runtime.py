from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from src.config import Config
from src.core.llm_client import LLMClient
from src.services.trading.decision import offline_candidate_acceptance as offline


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_pytest_bootstrap_disables_external_reasoning():
    assert os.environ["TRADING_TEST_HERMETIC"] == "true"
    assert os.environ["TRADING_REASONING_LLM_ENABLED"] == "false"
    assert Config.TRADING_REASONING_LLM_ENABLED is False


def test_simulated_local_dotenv_cannot_override_pytest_bootstrap(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("TRADING_REASONING_LLM_ENABLED=true\n", encoding="utf-8")
    before = dotenv.read_bytes()
    command = (
        "from dotenv import load_dotenv; "
        "load_dotenv('.env'); "
        "from src.config import Config; "
        "import json, os; "
        "print(json.dumps({'configured': True, "
        "'effective': Config.TRADING_REASONING_LLM_ENABLED, "
        "'hermetic': os.environ.get('TRADING_TEST_HERMETIC')}))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout) == {
        "configured": True,
        "effective": False,
        "hermetic": "true",
    }
    assert dotenv.read_bytes() == before


@pytest.mark.parametrize("provider", ["groq", "google", "openrouter"])
def test_external_provider_fails_before_client_construction(monkeypatch, provider):
    counts = {"groq": 0, "openai": 0}

    class FakeGroq:
        def __init__(self, **_kwargs):
            counts["groq"] += 1

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            counts["openai"] += 1

    groq_module = ModuleType("groq")
    groq_module.Groq = FakeGroq
    openai_module = ModuleType("openai")
    openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "groq", groq_module)
    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.setattr(Config, "GROQ_API_KEY", "fixture-key")
    monkeypatch.setattr(Config, "GOOGLE_API_KEY", "fixture-key")
    monkeypatch.setattr(Config, "OPENROUTER_API_KEY", "fixture-key")

    with pytest.raises(RuntimeError, match="^OFFLINE_EXTERNAL_PROVIDER_FORBIDDEN$"):
        LLMClient(provider_override=provider)

    assert counts == {"groq": 0, "openai": 0}


def test_guard_is_inactive_in_normal_runtime_with_fake_provider(monkeypatch):
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs["base_url"])

    openai_module = ModuleType("openai")
    openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.delenv("TRADING_TEST_HERMETIC", raising=False)
    monkeypatch.delenv("TRADING_OFFLINE_ACCEPTANCE", raising=False)
    monkeypatch.setattr(Config, "OPENROUTER_API_KEY", "fixture-key")

    client = LLMClient(provider_override="openrouter")

    assert client.provider == "openrouter"
    assert calls == ["https://openrouter.ai/api/v1"]


def test_offline_harness_uses_only_deterministic_adapter_when_env_enables_llm(
    monkeypatch,
):
    monkeypatch.setenv("TRADING_REASONING_LLM_ENABLED", "true")
    monkeypatch.setattr(Config, "TRADING_REASONING_LLM_ENABLED", True)

    result = offline.run_offline_candidate_acceptance("fresh_pending")

    assert result["deterministic_proposal_adapter_invocation_count"] == 1
    assert result["external_proposal_provider_invocation_count"] == 0
    assert result["generation_count"] == 1
    assert result["protected_export_count"] == 0
    assert result["submission_count"] == 0
    assert result["broker_mutation_count"] == 0


def test_offline_harness_does_not_modify_local_env():
    dotenv = PROJECT_ROOT / ".env"
    before = (
        dotenv.exists(),
        hashlib.sha256(dotenv.read_bytes()).hexdigest() if dotenv.exists() else "",
    )

    offline.run_offline_candidate_acceptance("fresh_market")

    after = (
        dotenv.exists(),
        hashlib.sha256(dotenv.read_bytes()).hexdigest() if dotenv.exists() else "",
    )
    assert after == before
