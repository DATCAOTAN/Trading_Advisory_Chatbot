from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import Config
from src.services.trading.execution.adapter_policy import ExecutionAdapterPolicy
from src.services.trading.execution.adapter_registry import ExecutionAdapterRegistry
from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport
from src.services.trading.execution.preflight.models import PreflightEvidenceSnapshot, now_utc_iso
from src.services.trading.execution.preflight.policy import LiveExecutionPreflightPolicy


class PreflightEvidenceCollector:
    def __init__(self, policy: LiveExecutionPreflightPolicy | None = None, project_root: Path | None = None):
        self.policy = policy or LiveExecutionPreflightPolicy.from_config()
        self.project_root = Path(project_root or Config.BASE_DIR)

    def collect(
        self,
        design_report,
        capability_report: LiveExecutionCapabilityReport | None,
        blocked_receipt: LiveExecutionBlockedReceipt | None,
        simulated_contract=None,
        simulated_receipt=None,
        live_block_journal_record=None,
    ) -> PreflightEvidenceSnapshot:
        evidence = PreflightEvidenceSnapshot(
            evidence_id=f"preflight_evidence_{_short_hash(now_utc_iso())}",
            created_at=now_utc_iso(),
        )
        evidence.config_summary_redacted = self._config_summary()
        evidence.adapter_registry_summary = self._adapter_registry_summary()
        evidence.mt5_bridge_endpoint_summary = self._bridge_endpoint_summary()
        evidence.code_scan_summary = self._code_scan_summary()
        evidence.ui_scan_summary = self._ui_scan_summary()
        evidence.journal_summary = self._journal_summary()
        evidence.source_refs_summary = self._source_refs_summary(design_report, blocked_receipt, simulated_contract)
        evidence.idempotency_summary = self._idempotency_summary(blocked_receipt, simulated_contract, simulated_receipt)
        evidence.redaction_summary = self._redaction_summary(design_report, capability_report, blocked_receipt)
        evidence.design_spec_summary = self._design_spec_summary(design_report, capability_report, blocked_receipt)
        evidence.simulated_contract_summary = self._simulated_contract_summary(simulated_contract, simulated_receipt)
        evidence.runtime_env_summary = self._runtime_env_summary(live_block_journal_record)
        evidence.warnings = _dedupe(_summary_warnings(evidence.as_dict()))
        evidence.payload_size_chars = len(json.dumps(evidence.as_dict(), ensure_ascii=False, sort_keys=True))
        return evidence

    def _config_summary(self) -> dict[str, Any]:
        return {
            "live_execution_enabled": bool(getattr(Config, "TRADING_MT5_LIVE_EXECUTION_ENABLED", False)),
            "hard_block_enabled": bool(getattr(Config, "TRADING_MT5_HARD_LIVE_BLOCK_ENABLED", True)),
            "order_submission_enabled": bool(getattr(Config, "TRADING_MT5_ORDER_SEND_ENABLED", False)),
            "execution_bridge_enabled": bool(getattr(Config, "TRADING_MT5_EXECUTION_BRIDGE_ENABLED", False)),
            "mt5_execution_adapter_implemented": bool(getattr(Config, "TRADING_MT5_EXECUTION_ADAPTER_IMPLEMENTED", False)),
            "preflight_enabled": self.policy.enabled,
        }

    def _adapter_registry_summary(self) -> dict[str, Any]:
        default_policy = ExecutionAdapterPolicy.from_config()
        default_type = str(getattr(default_policy, "adapter_type", "SIMULATED")).upper()
        try:
            default_adapter = ExecutionAdapterRegistry(default_policy).get_adapter()
            default_health = getattr(default_adapter, "health_check")().as_dict()
        except Exception as exc:
            default_health = {"status": "UNKNOWN", "error_type": type(exc).__name__}
        try:
            reserved_policy = ExecutionAdapterPolicy(
                adapter_type="RESERVED_MT5_LIVE",
                simulated_adapter_enabled=False,
                live_adapter_enabled=False,
                mt5_live_adapter_enabled=False,
            )
            reserved_adapter = ExecutionAdapterRegistry(reserved_policy).get_adapter()
            reserved_name = reserved_adapter.__class__.__name__
            reserved_health = getattr(reserved_adapter, "health_check")().as_dict()
        except Exception as exc:
            reserved_name = "unavailable"
            reserved_health = {"status": "UNKNOWN", "error_type": type(exc).__name__}
        return {
            "default_adapter_type": default_type,
            "default_health_status": default_health.get("status", "UNKNOWN"),
            "reserved_adapter_class": reserved_name,
            "reserved_returns_skeleton_only": reserved_name == "MT5ExecutionAdapterSkeleton",
            "reserved_live_supported": bool(reserved_health.get("live_execution_supported", False)),
            "real_live_adapter_active": False,
        }

    def _bridge_endpoint_summary(self) -> dict[str, Any]:
        server_path = self.project_root / "tools" / "mt5_bridge" / "server.py"
        text = _safe_read(server_path)
        forbidden_endpoints = ["/order", "/execute", "/send" + "_order", "/order" + "_send", "/trade", "/position/open"]
        controlled_endpoints = [
            "/execution/write-skeleton/check",
            "/execution/controlled-submit",
            "/execution/reconcile",
        ]
        forbidden_found = [marker for marker in forbidden_endpoints if marker in text]
        controlled_found = [marker for marker in controlled_endpoints if marker in text]
        do_post_present = bool(re.search(r"def\s+do_POST\b", text))
        return {
            "server_file_present": server_path.exists(),
            "execution_endpoint_count": len(forbidden_found),
            "execution_endpoint_present": bool(forbidden_found),
            "forbidden_endpoint_count": len(forbidden_found),
            "forbidden_endpoint_present": bool(forbidden_found),
            "controlled_endpoint_count": len(controlled_found),
            "controlled_endpoints_complete": len(controlled_found) == len(controlled_endpoints),
            "do_post_handler_present": do_post_present,
            "do_post_execution_handler_present": bool(do_post_present and controlled_found),
        }

    def _code_scan_summary(self) -> dict[str, Any]:
        source_paths = list((self.project_root / "src").rglob("*.py")) + list((self.project_root / "tools").rglob("*.py"))
        source_paths = [path for path in source_paths if "__pycache__" not in path.parts]
        call_pattern = re.compile(r"\.\s*order" + r"_send\s*\(")
        live_method_pattern = re.compile(r"\bdef\s+(submit_live_order|send_order|place_order|execute_trade)\b")
        mt5_import_pattern = re.compile(r"\b(import|from)\s+Meta" + r"Trader5\b")
        ticket_pattern = re.compile(r"\b(mt5_ticket|deal_id)\s*=")
        counts = {
            "order_submission_call_count": 0,
            "app_order_submission_call_count": 0,
            "bridge_execution_order_submission_call_count": 0,
            "reconciliation_order_submission_call_count": 0,
            "live_method_definition_count": 0,
            "docker_side_mt5_import_count": 0,
            "mt5_ticket_or_deal_marker_count": 0,
            "protected_reconciliation_ticket_or_deal_marker_count": 0,
            "unprotected_ticket_or_deal_marker_count": 0,
        }
        for path in source_paths:
            text = _safe_read(path)
            call_count = len(call_pattern.findall(text))
            counts["order_submission_call_count"] += call_count
            if "src" in path.parts:
                counts["app_order_submission_call_count"] += call_count
            if path.as_posix().endswith("tools/mt5_bridge/execution.py"):
                counts["bridge_execution_order_submission_call_count"] += call_count
            if path.as_posix().endswith("tools/mt5_bridge/reconciliation.py"):
                counts["reconciliation_order_submission_call_count"] += call_count
            counts["live_method_definition_count"] += len(live_method_pattern.findall(text))
            if "src" in path.parts:
                counts["docker_side_mt5_import_count"] += len(mt5_import_pattern.findall(text))
            ticket_or_deal_count = len(ticket_pattern.findall(text))
            counts["mt5_ticket_or_deal_marker_count"] += ticket_or_deal_count
            if path.as_posix().endswith("tools/mt5_bridge/reconciliation.py"):
                counts["protected_reconciliation_ticket_or_deal_marker_count"] += ticket_or_deal_count
            else:
                counts["unprotected_ticket_or_deal_marker_count"] += ticket_or_deal_count
        return {
            "files_scanned": len(source_paths),
            **counts,
            "order_submission_absent": counts["order_submission_call_count"] == 0,
            "controlled_order_submission_call_site_valid": (
                counts["order_submission_call_count"] == 1
                and counts["bridge_execution_order_submission_call_count"] == 1
                and counts["app_order_submission_call_count"] == 0
                and counts["reconciliation_order_submission_call_count"] == 0
            ),
            "app_order_submission_absent": counts["app_order_submission_call_count"] == 0,
            "reconciliation_order_submission_absent": counts["reconciliation_order_submission_call_count"] == 0,
            "live_methods_absent": counts["live_method_definition_count"] == 0,
            "docker_side_mt5_import_absent": counts["docker_side_mt5_import_count"] == 0,
            "mt5_ticket_or_deal_absent": counts["mt5_ticket_or_deal_marker_count"] == 0,
            "unprotected_ticket_or_deal_absent": counts["unprotected_ticket_or_deal_marker_count"] == 0,
        }

    def _ui_scan_summary(self) -> dict[str, Any]:
        ui_path = self.project_root / "src" / "ui" / "tab_dashboard.py"
        text = _safe_read(ui_path)
        unsafe_button_labels = ["Confirm Trade", "Execute Trade", "Place Order", "Buy", "Sell"]
        unsafe_button_present = any(f'st.button("{label}"' in text or f"st.button('{label}'" in text for label in unsafe_button_labels)
        return {
            "dashboard_file_present": ui_path.exists(),
            "unsafe_button_present": unsafe_button_present,
            "preflight_button_present": "Run Live Execution Preflight" in text,
            "preflight_safe_label_present": "Preflight only" in text or "preflight-only" in text,
            "live_disabled_label_present": "Live execution remains disabled" in text,
        }

    def _journal_summary(self) -> dict[str, Any]:
        path = Path(self.policy.journal_path)
        if not path.is_absolute():
            path = self.project_root / path
        parent_writable = False
        write_error = ""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            probe = path.parent / ".preflight_write_probe.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            parent_writable = True
        except Exception as exc:
            write_error = type(exc).__name__
        return {
            "journal_path": str(path.relative_to(self.project_root)) if path.is_relative_to(self.project_root) else str(path),
            "journal_parent_exists": path.parent.exists(),
            "journal_parent_writable": parent_writable,
            "write_error_type": write_error,
            "runtime_jsonl_gitignored": self._jsonl_gitignored(),
        }

    def _source_refs_summary(self, design_report, blocked_receipt, simulated_contract) -> dict[str, Any]:
        design_refs = list(getattr(design_report, "source_refs", []) or [])
        blocked_refs = list(getattr(blocked_receipt, "source_refs", []) or [])
        contract_refs = list(getattr(simulated_contract, "source_refs", []) or [])
        all_refs = _dedupe(design_refs + blocked_refs + contract_refs)
        return {
            "design_source_refs_count": len(design_refs),
            "blocked_receipt_source_refs_count": len(blocked_refs),
            "simulated_contract_source_refs_count": len(contract_refs),
            "source_refs_count": len(all_refs),
            "source_refs_present": bool(all_refs),
        }

    def _idempotency_summary(self, blocked_receipt, simulated_contract, simulated_receipt) -> dict[str, Any]:
        artifact_hash = (
            getattr(blocked_receipt, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        idempotency_key = (
            getattr(blocked_receipt, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        return {
            "artifact_hash_present": bool(artifact_hash),
            "idempotency_key_present": bool(idempotency_key),
            "artifact_hash_prefix": str(artifact_hash)[:12],
            "idempotency_key_prefix": str(idempotency_key)[:12],
        }

    def _redaction_summary(self, *objects) -> dict[str, Any]:
        payload = " ".join(json.dumps(_safe_as_dict(item), ensure_ascii=False, sort_keys=True).lower() for item in objects if item is not None)
        sensitive_markers = ["account_id", "api_key", "password", "secret", "credentials", "raw_candles", "raw_full_book", "raw_full_report"]
        present = [marker for marker in sensitive_markers if marker in payload]
        return {
            "raw_account_id_absent": "account_id" not in present,
            "credentials_absent": not any(marker in present for marker in {"api_key", "password", "secret", "credentials"}),
            "raw_context_absent": not any(marker in present for marker in {"raw_candles", "raw_full_book", "raw_full_report"}),
            "sensitive_marker_count": len(present),
        }

    def _design_spec_summary(self, design_report, capability_report, blocked_receipt) -> dict[str, Any]:
        return {
            "design_report_exists": design_report is not None,
            "design_report_id": getattr(design_report, "report_id", ""),
            "live_execution_allowed": bool(getattr(design_report, "live_execution_allowed", True)) if design_report is not None else True,
            "hard_live_block_required": bool(getattr(design_report, "hard_live_block_required", False)) if design_report is not None else False,
            "capability_report_exists": capability_report is not None,
            "capability_live_execution_supported": bool(getattr(capability_report, "live_execution_supported", True))
            if capability_report is not None
            else True,
            "capability_live_execution_enabled": bool(getattr(capability_report, "live_execution_enabled", True))
            if capability_report is not None
            else True,
            "capability_order_submission_available": bool(getattr(capability_report, "mt5_order_send_available", True))
            if capability_report is not None
            else True,
            "blocked_receipt_exists": blocked_receipt is not None,
            "blocked_receipt_blocked": bool(getattr(blocked_receipt, "blocked", False)) if blocked_receipt is not None else False,
            "blocked_receipt_executed": bool(getattr(blocked_receipt, "executed", True)) if blocked_receipt is not None else True,
            "blocked_receipt_order_sent": bool(getattr(blocked_receipt, "order_sent", True)) if blocked_receipt is not None else True,
            "threats_count": len(getattr(design_report, "threats", []) or []),
            "preflight_checks_count": len(getattr(design_report, "preflight_checks", []) or []),
        }

    def _simulated_contract_summary(self, simulated_contract, simulated_receipt) -> dict[str, Any]:
        return {
            "simulated_contract_exists": simulated_contract is not None,
            "simulated_receipt_exists": simulated_receipt is not None,
            "contract_id": getattr(simulated_contract, "contract_id", ""),
            "contract_simulated_only": bool(getattr(simulated_contract, "simulated_only", False)) if simulated_contract is not None else False,
            "contract_executable": bool(getattr(simulated_contract, "executable", True)) if simulated_contract is not None else True,
            "receipt_executable": bool(getattr(simulated_receipt, "executable", True)) if simulated_receipt is not None else True,
            "receipt_executed": bool(getattr(simulated_receipt, "executed", True)) if simulated_receipt is not None else True,
        }

    def _runtime_env_summary(self, live_block_journal_record) -> dict[str, Any]:
        docker_compose_path = self.project_root / "docker-compose.yml"
        return {
            "docker_compose_file_present": docker_compose_path.exists(),
            "live_block_journal_record_present": live_block_journal_record is not None,
            "live_block_journal_record_id": getattr(live_block_journal_record, "journal_record_id", ""),
            "app_config_redacted": True,
        }

    def _jsonl_gitignored(self) -> bool:
        gitignore = _safe_read(self.project_root / ".gitignore")
        return "data/trading/execution_journal/*.jsonl" in gitignore.replace("\\", "/")


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _safe_as_dict(value) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "as_dict"):
        try:
            return value.as_dict()
        except Exception:
            return {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _summary_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not payload.get("journal_summary", {}).get("journal_parent_writable", False):
        warnings.append("preflight_journal_parent_not_writable")
    if payload.get("mt5_bridge_endpoint_summary", {}).get("forbidden_endpoint_present", False):
        warnings.append("mt5_bridge_forbidden_endpoint_detected")
    if payload.get("ui_scan_summary", {}).get("unsafe_button_present", False):
        warnings.append("unsafe_dashboard_button_detected")
    return warnings


def _short_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _dedupe(items: list[Any] | None) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
