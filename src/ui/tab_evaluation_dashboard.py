"""Evaluation Dashboard tab.

Read-only review UI over EvaluationRegistry view models.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import streamlit as st

from src.services.agents.evaluation_dashboard import (
    EvaluationDashboardFilters,
    EvaluationDashboardService,
    replay_view_from_result,
)
from src.services.agents.evaluation_persistence import EvaluationPersistenceStore
from src.ui.theme import render_section_heading


def render(orchestrator=None):
    render_section_heading(
        "Evaluation",
        "Read-only registry review, quality signals, and diagnostic evidence.",
    )
    st.caption("No provider, retrieval, MT5, broker, or account calls.")

    service = _dashboard_service_from_state()
    filters = _filters_from_ui()
    summary, rows = service.load(filters)
    _render_persistence_panel(service, filters)
    _render_system_health_panel(service)

    if summary.total_entries == 0:
        st.info("No persisted evaluation records found. Run evaluations or save current registry records first.")
        return

    _render_summary(summary)
    st.markdown("---")
    _render_filters_note()
    _render_table_and_detail(service, rows)
    st.markdown("---")
    _render_chain_view(service)
    st.markdown("---")
    _render_replay_panel()
    st.markdown("---")
    _render_analytics_panel(service, filters)
    st.markdown("---")
    _render_export_panel(service)


def _dashboard_service_from_state() -> EvaluationDashboardService:
    store = EvaluationPersistenceStore()
    artifacts = st.session_state.get("latest_runtime_artifacts") or {}
    registry_artifact = st.session_state.get("evaluation_registry") or artifacts.get("evaluation_registry") or {}
    if registry_artifact:
        service = EvaluationDashboardService.from_runtime_artifacts({"evaluation_registry": registry_artifact})
        service.persistence_store = store
        return service
    return EvaluationDashboardService.from_persistence_store(store)


def _render_persistence_panel(service: EvaluationDashboardService, filters: EvaluationDashboardFilters):
    with st.expander("Persistence / Dataset Versioning", expanded=False):
        st.caption("Local JSONL + manifest storage. No provider, retrieval, MT5, broker, or account calls.")
        col1, col2, col3 = st.columns(3)
        if col1.button("Save current evaluation records", key="eval_persist_save"):
            result = service.save_current_records()
            st.session_state.evaluation_persistence_status = result.as_dict()
            st.success(f"Saved={result.saved}, duplicates={result.duplicates}, rejected={result.rejected}")
        if col2.button("Load persisted records", key="eval_persist_load"):
            _, persisted_rows = service.load_persisted_records()
            st.session_state.evaluation_registry = service.registry.as_runtime_artifact()
            st.session_state.evaluation_persistence_status = {"status": "LOADED", "entries": len(persisted_rows)}
            st.rerun()
        if col3.button("Refresh registry from disk", key="eval_persist_refresh"):
            _, persisted_rows = service.load_persisted_records()
            st.session_state.evaluation_registry = service.registry.as_runtime_artifact()
            st.session_state.evaluation_persistence_status = {"status": "REFRESHED", "entries": len(persisted_rows)}
            st.rerun()

        col4, col5, col6 = st.columns(3)
        if col4.button("Validate store", key="eval_persist_validate"):
            st.session_state.evaluation_persistence_status = service.validate_persistence_store().as_dict()
        version_name = col5.text_input("Dataset version name", value="review-dataset", key="eval_version_name")
        version_desc = col6.text_input("Description", value="", key="eval_version_description")
        if st.button("Create dataset version", key="eval_version_create"):
            version = service.create_dataset_version(version_name, version_desc, filters)
            st.session_state.evaluation_dataset_version_status = version.as_dict()
            st.success(f"Created {version.version_id} entries={version.entries_count}")

        versions = service.list_dataset_versions()
        selected_version = st.selectbox(
            "Dataset versions",
            [""] + [version.version_id for version in versions],
            key="eval_selected_dataset_version",
        )
        col7, col8, col9 = st.columns(3)
        if selected_version and col7.button("Export selected version JSON", key="eval_version_export_json"):
            st.session_state.evaluation_dataset_export_status = service.export_dataset_version(selected_version, "json").as_dict()
        if selected_version and col8.button("Export selected version CSV", key="eval_version_export_csv"):
            st.session_state.evaluation_dataset_export_status = service.export_dataset_version(selected_version, "csv").as_dict()
        import_path = col9.text_input("Import/validate dataset path", key="eval_import_path")
        validate_only = st.checkbox("Validate imported dataset only", value=True, key="eval_import_validate_only")
        if import_path and st.button("Validate imported dataset", key="eval_import_validate"):
            st.session_state.evaluation_dataset_import_status = service.import_dataset_export(import_path, validate_only=validate_only).as_dict()

        st.json(
            {
                "storage_path": str(service.persistence_store.registry_path),
                "manifest_path": str(service.persistence_store.manifest_path),
                "exports_dir": str(service.persistence_store.export_dir),
                "last_persistence": st.session_state.get("evaluation_persistence_status", {}),
                "last_version": st.session_state.get("evaluation_dataset_version_status", {}),
                "last_export": st.session_state.get("evaluation_dataset_export_status", {}),
                "last_import": st.session_state.get("evaluation_dataset_import_status", {}),
            },
            expanded=False,
        )


def _render_system_health_panel(service: EvaluationDashboardService):
    with st.expander("System Health / Recovery", expanded=False):
        st.caption("Validate-only defensive checks. No provider, retrieval, MT5, broker, account, delete, or compact action is run.")
        selected_registry_id = st.session_state.get("eval_selected_registry_id", "")
        artifacts = st.session_state.get("latest_runtime_artifacts") or {}
        col1, col2 = st.columns(2)
        if col1.button("Validate system health", key="eval_health_validate"):
            report, plan = service.system_health_report(selected_registry_id=selected_registry_id, runtime_artifacts=artifacts)
            st.session_state.evaluation_health_report = report.as_dict()
            st.session_state.evaluation_health_plan = plan.as_dict()
        if col2.button("Export diagnostic report", key="eval_health_export"):
            report_data = st.session_state.get("evaluation_health_report")
            plan_data = st.session_state.get("evaluation_health_plan", {})
            if report_data:
                diagnostic = service.export_system_diagnostic(report_data, plan_data)
                st.session_state.evaluation_health_diagnostic = diagnostic.as_dict()
                st.success(f"Diagnostic exported: {diagnostic.diagnostics_path}")
            else:
                st.warning("Run validation before exporting diagnostics.")

        report = st.session_state.get("evaluation_health_report", {})
        plan = st.session_state.get("evaluation_health_plan", {})
        diagnostic = st.session_state.get("evaluation_health_diagnostic", {})
        if report:
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Integrity", report.get("status", "UNKNOWN"))
            col_b.metric("Issues", len(report.get("issues", [])))
            col_c.metric("Corrupt", report.get("corrupt_records_count", 0))
            col_d.metric("Unsafe", report.get("unsafe_artifacts_count", 0))
            st.json(
                {
                    "issue_counts_by_severity": report.get("issue_counts_by_severity", {}),
                    "issue_counts_by_category": report.get("issue_counts_by_category", {}),
                    "recovery_plan": {
                        "plan_id": plan.get("plan_id", ""),
                        "actions": plan.get("actions", []),
                        "can_auto_apply": plan.get("can_auto_apply", False),
                        "requires_confirmation": plan.get("requires_confirmation", False),
                        "execution_allowed": plan.get("execution_allowed", False),
                    },
                    "diagnostic": diagnostic,
                },
                expanded=False,
            )
        else:
            st.info("No health report yet. Run validate-only health check when needed.")


def _filters_from_ui() -> EvaluationDashboardFilters:
    with st.expander("Bộ lọc", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        request_id = col1.text_input("Request ID", key="eval_filter_request_id")
        record_type = col2.selectbox(
            "Record type",
            ["", "journal_review", "backtest_evaluation", "paper_trading_evaluation"],
            key="eval_filter_record_type",
        )
        symbol = col3.text_input("Symbol", key="eval_filter_symbol")
        status = col4.text_input("Status", key="eval_filter_status")

        col5, col6, col7, col8 = st.columns(4)
        quality = col5.text_input("Quality", key="eval_filter_quality")
        task_id = col6.text_input("Task ID", key="eval_filter_task_id")
        intent = col7.text_input("Intent family", key="eval_filter_intent")
        needs = col8.checkbox("Needs review only", key="eval_filter_needs_review")

        col9, col10, col11, col12 = st.columns(4)
        safety_flag = col9.text_input("Safety flag", key="eval_filter_safety")
        priority = col10.selectbox("Priority", ["", "HIGH", "MEDIUM", "LOW"], key="eval_filter_priority")
        review_status = col11.selectbox(
            "Review status",
            ["", "UNREVIEWED", "IN_REVIEW", "APPROVED", "APPROVED_WITH_NOTES", "NEEDS_FIX", "REJECTED", "NOT_APPLICABLE"],
            key="eval_filter_review_status",
        )
        severity = col12.selectbox("Severity", ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"], key="eval_filter_severity")
        limit = st.number_input("Limit", min_value=1, max_value=500, value=100, step=10, key="eval_filter_limit")

    return EvaluationDashboardFilters(
        request_id=request_id,
        record_type=record_type,
        symbol=symbol,
        status=status,
        quality_label=quality,
        task_id=task_id,
        intent_family=intent,
        needs_review_only=needs,
        safety_flag=safety_flag,
        review_priority=priority,
        review_status=review_status,
        severity=severity,
        limit=int(limit),
    )


def _render_summary(summary):
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total", summary.total_entries)
    col2.metric("Needs review", summary.needs_review_count)
    col3.metric("Safety flags", summary.safety_flag_count)
    col4.metric("High quality", summary.by_quality_label.get("high_quality", 0) + summary.by_quality_label.get("useful_for_review", 0))
    warn_fail = sum(summary.by_status.get(status, 0) for status in ["WARN", "FAIL", "DEGRADED", "EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"])
    col5.metric("Warn/Fail", warn_fail)
    st.caption(f"Symbols: {', '.join(summary.symbols) if summary.symbols else 'none'} | execution_allowed={str(summary.execution_allowed).lower()}")


def _render_filters_note():
    st.caption("Rows exclude raw prompts, full final answers, secrets, account data, broker data, MT5 data, and order data.")


def _render_table_and_detail(service: EvaluationDashboardService, rows):
    st.markdown("#### Registry table")
    table = [row.as_dict() for row in rows]
    st.dataframe(table, use_container_width=True, hide_index=True)
    if not rows:
        st.info("No rows match current filters.")
        return
    selected = st.selectbox("Detail registry id", [row.registry_id for row in rows], key="eval_selected_registry_id")
    detail = service.detail(selected)
    if detail:
        st.markdown("#### Detail")
        col1, col2 = st.columns(2)
        with col1:
            st.json(
                {
                    "registry_id": detail.registry_id,
                    "record_type": detail.record_type,
                    "request_id": detail.request_id,
                    "final_answer_sha256": detail.final_answer_sha256,
                    "chain_status": detail.chain_status,
                    "replay_available": detail.replay_available,
                    "export_safe": detail.export_safe,
                },
                expanded=False,
            )
            st.markdown("**Source refs**")
            st.write(detail.source_refs or [])
        with col2:
            st.markdown("**Safety / Evaluation**")
            st.json({"safety_index": detail.safety_index, "evaluation_index": detail.evaluation_index}, expanded=False)
            st.markdown("**Limitations**")
            st.write(detail.limitations or [])
        st.markdown("**Task index**")
        st.dataframe(detail.task_index, use_container_width=True, hide_index=True)
        _render_human_review_section(service, detail)


def _render_human_review_section(service: EvaluationDashboardService, detail):
    st.markdown("#### Human Review")
    batch = service.review_batch_summary()
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Reviewed", batch.reviewed_count)
    col2.metric("Approved", batch.approved_count)
    col3.metric("Needs fix", batch.needs_fix_count)
    col4.metric("Rejected", batch.rejected_count)
    col5.metric("Unsafe", batch.unsafe_count)
    col6.metric("Locked", batch.locked_count)

    state = service.workflow_state(detail.registry_id)
    history = service.review_history(detail.registry_id)
    st.json({"workflow_state": state.as_dict()}, expanded=False)
    if history:
        st.markdown("**Review history**")
        st.dataframe([item.as_dict() for item in history], use_container_width=True, hide_index=True)

    task_ids = [task.get("task_id") for task in detail.task_index if task.get("task_id")]
    if not task_ids:
        task_ids = [""]
    with st.form(f"human_review_form_{detail.registry_id}"):
        st.markdown("**Annotation form**")
        col_a, col_b, col_c = st.columns(3)
        reviewer_id = col_a.text_input("Reviewer ID", value="reviewer", key=f"reviewer_{detail.registry_id}")
        task_id = col_b.selectbox("Task", task_ids, key=f"review_task_{detail.registry_id}")
        severity = col_c.selectbox("Severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], key=f"review_severity_{detail.registry_id}")

        col_d, col_e, col_f = st.columns(3)
        review_status = col_d.selectbox("Review status", ["IN_REVIEW", "APPROVED", "APPROVED_WITH_NOTES", "NEEDS_FIX", "REJECTED", "NOT_APPLICABLE"], key=f"review_status_{detail.registry_id}")
        quality_decision = col_e.selectbox("Quality", ["HIGH_QUALITY", "ACCEPTABLE", "ACCEPTABLE_WITH_WARNINGS", "LOW_QUALITY", "INVALID", "UNSAFE", "NOT_APPLICABLE"], key=f"review_quality_{detail.registry_id}")
        correctness_label = col_f.selectbox("Correctness", ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT", "UNSUPPORTED", "UNCLEAR", "NOT_APPLICABLE"], key=f"review_correctness_{detail.registry_id}")

        col_g, col_h, col_i = st.columns(3)
        grounding_label = col_g.selectbox("Grounding", ["WELL_GROUNDED", "PARTIALLY_GROUNDED", "POORLY_GROUNDED", "MISSING_SOURCE", "NOT_APPLICABLE"], key=f"review_grounding_{detail.registry_id}")
        safety_label = col_h.selectbox("Safety", ["SAFE", "WARNING", "UNSAFE", "NOT_APPLICABLE"], key=f"review_safety_{detail.registry_id}")
        task_scope_label = col_i.selectbox("Task scope", ["TASK_SCOPE_OK", "POSSIBLE_LEAKAGE", "TASK_SCOPE_FAIL", "NOT_APPLICABLE"], key=f"review_scope_{detail.registry_id}")

        reason_options = [item["code"] for item in service.reason_codes()]
        reason_codes = st.multiselect("Reason codes", reason_options, key=f"review_reasons_{detail.registry_id}")
        reviewer_note = st.text_area("Reviewer note", key=f"review_note_{detail.registry_id}")
        suggested_fix_summary = st.text_area("Suggested fix summary", key=f"review_fix_{detail.registry_id}")
        submitted = st.form_submit_button("Save annotation")
        if submitted:
            result = service.save_review_annotation(
                detail.registry_id,
                task_id=task_id,
                reviewer_id=reviewer_id,
                review_status=review_status,
                quality_decision=quality_decision,
                correctness_label=correctness_label,
                grounding_label=grounding_label,
                safety_label=safety_label,
                task_scope_label=task_scope_label,
                reason_codes=reason_codes,
                reviewer_note=reviewer_note,
                suggested_fix_summary=suggested_fix_summary,
                severity=severity,
            )
            st.session_state.human_review_status = result.as_dict()
            st.success(f"Annotation status={result.status} redactions={result.redactions}")

    col_lock, col_version, col_export = st.columns(3)
    if col_lock.button("Lock review", key=f"lock_review_{detail.registry_id}"):
        lock_result = service.lock_registry_review(detail.registry_id)
        st.session_state.human_review_lock_status = {"status": lock_result.status, "registry_id": lock_result.registry_id}
    annotated_name = col_version.text_input("Annotated version name", value="annotated-review", key=f"annotated_version_{detail.registry_id}")
    if col_version.button("Create annotated version", key=f"create_annotated_{detail.registry_id}"):
        version = service.create_annotated_dataset_version(annotated_name, locked=False)
        st.session_state.human_review_annotated_version = version.as_dict()
        st.success(f"Annotated version={version.version_id}")
    versions = service.list_annotated_dataset_versions()
    selected = col_export.selectbox("Annotated versions", [""] + [version.version_id for version in versions], key=f"annotated_select_{detail.registry_id}")
    if selected and col_export.button("Export annotated JSON", key=f"export_annotated_json_{detail.registry_id}"):
        st.session_state.human_review_export_status = service.export_annotated_dataset(selected, "json").as_dict()
    if selected and col_export.button("Export annotated CSV", key=f"export_annotated_csv_{detail.registry_id}"):
        st.session_state.human_review_export_status = service.export_annotated_dataset(selected, "csv").as_dict()

    st.json(
        {
            "last_annotation": st.session_state.get("human_review_status", {}),
            "last_lock": st.session_state.get("human_review_lock_status", {}),
            "last_annotated_version": st.session_state.get("human_review_annotated_version", {}),
            "last_annotated_export": st.session_state.get("human_review_export_status", {}),
        },
        expanded=False,
    )


def _render_chain_view(service: EvaluationDashboardService):
    st.markdown("#### Chain view")
    request_id = st.text_input("Chain request id", key="eval_chain_request_id")
    chains = service.chain_view(request_id=request_id)
    if not chains:
        st.info("No chains match current request id.")
        return
    for chain in chains:
        with st.expander(f"{chain.request_id or 'unknown'} / {chain.final_answer_sha256[:12]} / {chain.review_priority}", expanded=False):
            st.json(
                {
                    "chain_completeness": chain.chain_completeness,
                    "journal_records": chain.journal_records,
                    "backtest_records": chain.backtest_records,
                    "paper_records": chain.paper_records,
                    "review_priority": chain.review_priority,
                },
                expanded=False,
            )
            st.dataframe(chain.task_chain, use_container_width=True, hide_index=True)


def _render_replay_panel():
    st.markdown("#### Replay result")
    replay_result = st.session_state.get("latest_replay_result")
    if not replay_result:
        st.caption("No replay result in session. Deterministic ReplayHarness results can be displayed here.")
        return
    view = replay_view_from_result(replay_result)
    col1, col2, col3 = st.columns(3)
    col1.metric("Replay", view.status)
    col2.metric("Mismatches", len(view.mismatches))
    col3.metric("Latency ms", view.latency_ms)
    st.json(
        {
            "compared_fields": view.compared_fields,
            "mismatches": view.mismatches,
            "safety_summary": view.safety_summary,
            "generated_records_summary": view.generated_records_summary,
        },
        expanded=False,
    )


def _render_analytics_panel(service: EvaluationDashboardService, filters: EvaluationDashboardFilters):
    st.markdown("#### Review Analytics")
    report = service.analytics_report(filters)
    if report.coverage.total_registry_entries == 0:
        st.info("No evaluation records are available for analytics.")
        return

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Dataset health", report.dataset_quality.dataset_health_label)
    col2.metric("Quality score", report.quality.quality_score)
    col3.metric("Coverage", report.coverage.annotation_coverage_rate)
    col4.metric("Safety issue rate", report.safety.safety_issue_rate)
    col5.metric("Task leakage rate", report.task_scope.task_leakage_rate)
    st.caption(f"Grounding issue rate={report.grounding.grounding_issue_rate} | execution_allowed={str(report.execution_allowed).lower()}")

    with st.expander("Analytics details", expanded=False):
        left, right = st.columns(2)
        with left:
            st.markdown("**Review coverage**")
            st.json(report.coverage.as_dict(), expanded=False)
            st.markdown("**Label distribution**")
            st.json(
                {
                    "quality": report.quality.quality_distribution,
                    "correctness": report.correctness.as_dict(),
                    "grounding": report.grounding.as_dict(),
                    "safety": report.safety.as_dict(),
                    "task_scope": report.task_scope.as_dict(),
                },
                expanded=False,
            )
        with right:
            st.markdown("**Reason code analysis**")
            st.json(report.reason_codes.as_dict(), expanded=False)
            st.markdown("**Evaluation consistency**")
            st.json(report.evaluation_consistency.as_dict(), expanded=False)

        st.markdown("**Task / intent / symbol breakdown**")
        st.json(
            {
                "task_breakdown": report.task_breakdown,
                "intent_family_breakdown": report.intent_family_breakdown,
                "symbol_breakdown": report.symbol_breakdown,
            },
            expanded=False,
        )
        st.markdown("**Reviewer activity**")
        st.json(report.reviewer_activity.as_dict(), expanded=False)
        st.markdown("**System-quality recommendations**")
        st.write(report.recommendations or [])

    metrics_payload = report.to_json()
    st.download_button(
        "Download metrics JSON",
        data=metrics_payload,
        file_name="quality_metrics_report.json",
        mime="application/json",
        disabled=False,
    )
    st.caption(f"Metrics payload chars={len(metrics_payload)} | export status=READY")


def _render_export_panel(service: EvaluationDashboardService):
    st.markdown("#### Safe export")
    preview = service.export_preview(_filters_from_state())
    st.write(
        {
            "export_id": preview.export_id,
            "rows_count": preview.rows_count,
            "redactions": preview.redactions,
            "payload_chars": preview.payload_chars,
            "safe_to_download": preview.safe_to_download,
        }
    )
    st.dataframe(preview.rows[:20], use_container_width=True, hide_index=True)
    st.download_button(
        "Download JSON",
        data=preview.to_json(),
        file_name="evaluation_review_dataset.json",
        mime="application/json",
        disabled=not preview.safe_to_download,
    )
    st.download_button(
        "Download CSV",
        data=preview.to_csv(),
        file_name="evaluation_review_dataset.csv",
        mime="text/csv",
        disabled=not preview.safe_to_download,
    )


def _filters_from_state() -> EvaluationDashboardFilters:
    return EvaluationDashboardFilters(
        request_id=st.session_state.get("eval_filter_request_id", ""),
        record_type=st.session_state.get("eval_filter_record_type", ""),
        symbol=st.session_state.get("eval_filter_symbol", ""),
        status=st.session_state.get("eval_filter_status", ""),
        quality_label=st.session_state.get("eval_filter_quality", ""),
        task_id=st.session_state.get("eval_filter_task_id", ""),
        intent_family=st.session_state.get("eval_filter_intent", ""),
        needs_review_only=bool(st.session_state.get("eval_filter_needs_review", False)),
        safety_flag=st.session_state.get("eval_filter_safety", ""),
        review_priority=st.session_state.get("eval_filter_priority", ""),
        review_status=st.session_state.get("eval_filter_review_status", ""),
        severity=st.session_state.get("eval_filter_severity", ""),
        limit=int(st.session_state.get("eval_filter_limit", 100)),
    )
