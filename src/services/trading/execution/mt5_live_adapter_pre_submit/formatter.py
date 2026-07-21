from __future__ import annotations


class MT5LiveAdapterPreSubmitFormatter:
    def to_card(self, report, adapter_receipt=None, journal_record=None) -> dict:
        return {
            "pre_submit_status": report.status,
            "valid": report.valid,
            "controlled_demo_integration_workflow_allowed": report.controlled_demo_integration_workflow_allowed,
            "live_submission_allowed": False,
            "adapter_status": getattr(adapter_receipt, "adapter_status", ""),
            "bridge_write_skeleton_reachable": report.bridge_write_skeleton_reachable,
            "bridge_write_skeleton_status": report.bridge_write_skeleton_status,
            "kill_switch_engaged": report.kill_switch_engaged,
            "idempotency_status": report.idempotency_status,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "ticket": None,
            "deal": None,
            "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            "latency_ms": getattr(adapter_receipt, "latency_ms", 0.0),
        }

    def to_markdown_summary(self, report, adapter_receipt=None, journal_record=None) -> str:
        card = self.to_card(report, adapter_receipt, journal_record)
        return "\n".join(f"- `{key}`: {str(value).lower() if isinstance(value, bool) else value}" for key, value in card.items())
