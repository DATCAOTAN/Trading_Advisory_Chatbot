import hashlib
from typing import Dict, Any, List

from src.services.knowledge.registry_loader import RegistryLoader

class ValidationResult:
    def __init__(self, is_valid: bool, level: str, messages: List[str]):
        self.is_valid = is_valid
        self.level = level  # INFO, WARNING, ERROR, FATAL
        self.messages = messages

class Validator:
    """
    Tầng bảo vệ chặn rác dữ liệu trước khi xử lý sâu hơn.
    Gồm 3 lớp: Schema, Business, Integrity.
    """

    def __init__(self):
        self.registry = RegistryLoader()

    def validate(self, file_path: str, resolved_metadata: Dict[str, Any]) -> ValidationResult:
        messages = []
        highest_severity = "INFO"

        def add_msg(level: str, msg: str):
            nonlocal highest_severity
            messages.append(f"[{level}] {msg}")
            levels = ["INFO", "WARNING", "ERROR", "FATAL"]
            if levels.index(level) > levels.index(highest_severity):
                highest_severity = level

        # 1. Schema Validation
        rm = resolved_metadata.get("routing_metadata", {})
        dm = resolved_metadata.get("document_metadata", {})

        if not rm.get("domain") or rm.get("domain") == "unknown":
            add_msg("FATAL", "Thiếu 'domain' trong routing_metadata.")
        
        if not rm.get("knowledge_type") or rm.get("knowledge_type") == "unknown":
            add_msg("ERROR", "Thiếu 'knowledge_type' chuẩn.")
            
        if not dm.get("publisher"):
            add_msg("WARNING", "Thiếu 'publisher' trong document_metadata.")

        # 2. Business Validation
        if rm.get("domain") and rm.get("domain") != "unknown":
            if not self.registry.is_valid_domain(rm["domain"]):
                add_msg("ERROR", f"Domain '{rm['domain']}' không có trong registry.")
            
            subdomain = rm.get("subdomain")
            if subdomain and subdomain != "unknown":
                if not self.registry.is_valid_subdomain(rm["domain"], subdomain):
                    add_msg("WARNING", f"Subdomain '{subdomain}' không thuộc domain '{rm['domain']}'.")

        lifecycle = resolved_metadata.get("lifecycle", "DRAFT")
        if lifecycle in ["DEPRECATED", "ARCHIVED", "DRAFT"]:
            add_msg("INFO", f"Tài liệu bị bỏ qua do lifecycle là {lifecycle}.")

        # 3. Integrity Validation
        manifest_checksum = dm.get("checksum", "")
        if manifest_checksum:
            actual_checksum = self._calculate_checksum(file_path)
            if actual_checksum != manifest_checksum:
                add_msg("FATAL", f"Checksum không khớp! Manifest: {manifest_checksum}, Actual: {actual_checksum}")
        else:
            add_msg("WARNING", "Thiếu checksum trong manifest để kiểm tra tính toàn vẹn.")

        if not dm.get("doc_id"):
            add_msg("FATAL", "Không sinh được doc_id tĩnh.")

        is_valid = highest_severity not in ["FATAL"]
        
        # Patch 4: Normalize chuẩn chỉ áp dụng cho Routing, ID, Slug
        if is_valid:
            self._normalize_metadata(resolved_metadata)

        return ValidationResult(is_valid, highest_severity, messages)

    def _calculate_checksum(self, file_path: str) -> str:
        """Tính SHA-256 hash của file vật lý."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return ""

    def _normalize_metadata(self, metadata: Dict[str, Any]):
        """
        Patch 4: Chỉ chuẩn hóa routing_metadata, slug, enum, id.
        Không chạm vào document_metadata như title, author, publisher (vì liên quan UI hiển thị).
        """
        rm = metadata.get("routing_metadata", {})
        for key in ["strategies", "assets", "timeframe_focus"]:
            if isinstance(rm.get(key), list):
                rm[key] = [str(x).strip().lower() for x in rm[key]]
        
        for key in ["domain", "subdomain", "knowledge_type", "language", "source_tier"]:
            if key in rm and isinstance(rm[key], str):
                rm[key] = rm[key].strip().lower()

        # Doc ID cũng cần chuẩn hóa
        dm = metadata.get("document_metadata", {})
        if "doc_id" in dm:
            dm["doc_id"] = dm["doc_id"].strip().lower()
