from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_workspace_shell_uses_shared_theme_and_compact_navigation():
    source = _source("src/app.py")

    assert "apply_workspace_theme()" in source
    assert 'page_title="Trading Advisory Workspace"' in source
    assert 'initial_sidebar_state="auto"' in source
    assert '["Advisory", "Operations", "Evaluation", "Settings"]' in source
    assert "main-header" not in source
    assert "linear-gradient" not in source


def test_workspace_theme_is_operational_and_responsive():
    source = _source("src/ui/theme.py")

    assert "--workspace-bg: #f4f7fb" in source
    assert "@media (max-width: 900px)" in source
    assert "@media (max-width: 640px)" in source
    assert '[data-testid="stChatMessage"]' in source
    assert '[data-testid="stMetric"]' in source
    assert 'border-radius: 6px' in source
    assert "linear-gradient" not in source


def test_primary_tabs_share_consistent_section_hierarchy():
    chat = _source("src/ui/tab_chatbot.py")
    dashboard = _source("src/ui/tab_dashboard.py")
    evaluation = _source("src/ui/tab_evaluation_dashboard.py")
    settings = _source("src/ui/tab_settings.py")

    for source, title in (
        (chat, '"Advisory"'),
        (dashboard, '"Operations"'),
        (evaluation, '"Evaluation"'),
        (settings, '"Settings"'),
    ):
        assert "render_section_heading(" in source
        assert title in source


def test_execution_diagnostics_are_collapsed_without_removing_boundaries():
    source = _source("src/ui/tab_dashboard.py")
    expander = source.index(
        'with st.expander("Execution boundary diagnostics", expanded=False):'
    )
    first_boundary = source.index("_render_dry_run_execution_gate_status()")
    final_boundary = source.index(
        "_render_mt5_live_adapter_disabled_pre_submit_status()"
    )

    assert expander < first_boundary < final_boundary
    assert '"Generate Candidate"' in source
    assert '"Clear Current Candidate"' in source


def test_workspace_redesign_keeps_runtime_widget_contracts():
    dashboard = _source("src/ui/tab_dashboard.py")

    for contract in (
        'key="autonomous_candidate_symbol"',
        'key=f"{key_prefix}generate_autonomous_candidate"',
        'key=f"{key_prefix}clear_autonomous_candidate"',
        "OperatorCandidateGenerationController(",
        "TradingAuthorityOperatorService(",
    ):
        assert contract in dashboard
