"""
Ingestion Tracker — Bộ máy quản lý trạng thái kho tri thức (State Machine).

Design Pattern: State Pattern + Idempotency
  - Theo dõi SHA-256 hash của từng file PDF đã nạp vào Qdrant.
  - So sánh trạng thái hiện tại vs. trạng thái đã lưu để phân loại:
    NEW      → File chưa từng nạp  → Cần parse + encode + upsert
    MODIFIED → File đã sửa đổi    → Xóa points cũ + upsert mới
    DELETED  → File bị xóa        → Xóa points khỏi Qdrant
    UNCHANGED→ File không đổi     → Bỏ qua hoàn toàn

  - Tính Idempotent: Bấm nút cập nhật 100 lần mà file không đổi
    → Qdrant DB giữ nguyên, không sinh dữ liệu thừa, không tốn tài nguyên.

File trạng thái: data/ingestion_state.json
  Cấu trúc:
  {
    "files": {
      "filename.pdf": {
        "sha256": "abc123...",
        "indexed_at": "2026-06-07T04:00:00",
        "chunk_count": 42,
        "file_path": "/absolute/path/to/file.pdf"
      }
    }
  }
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Config


# =============================================================================
# DATA CLASSES — Kết quả phân tích khác biệt
# =============================================================================
@dataclass
class IngestionDiff:
    """Kết quả so sánh trạng thái kho tri thức hiện tại vs. đã lưu."""
    new_files: List[str]        = field(default_factory=list)  # File mới cần nạp
    modified_files: List[str]   = field(default_factory=list)  # File sửa đổi cần re-index
    deleted_files: List[str]    = field(default_factory=list)  # File bị xóa cần dọn Qdrant
    unchanged_files: List[str]  = field(default_factory=list)  # File không đổi → bỏ qua

    @property
    def has_changes(self) -> bool:
        """Có bất kỳ thay đổi nào cần xử lý không?"""
        return bool(self.new_files or self.modified_files or self.deleted_files)

    def summary(self) -> str:
        """Báo cáo tóm tắt dạng text."""
        return (
            f"📊 Kết quả quét kho tri thức:\n"
            f"   🆕 Mới:       {len(self.new_files)} file\n"
            f"   ✏️ Sửa đổi:   {len(self.modified_files)} file\n"
            f"   🗑️ Đã xóa:    {len(self.deleted_files)} file\n"
            f"   ✅ Không đổi:  {len(self.unchanged_files)} file"
        )


@dataclass
class IngestionReport:
    """Báo cáo kết quả sau khi đồng bộ xong."""
    added: int       = 0   # Số chunks đã thêm mới
    updated: int     = 0   # Số chunks đã cập nhật (xóa cũ + thêm mới)
    deleted: int     = 0   # Số file đã xóa khỏi Qdrant
    unchanged: int   = 0   # Số file bỏ qua
    total_chunks: int = 0  # Tổng chunks hiện có trong Qdrant


# =============================================================================
# INGESTION TRACKER — State Machine quản lý trạng thái
# =============================================================================
class IngestionTracker:
    """
    Bộ theo dõi trạng thái nạp dữ liệu — lõi của Smart Incremental Ingestion.

    Sử dụng SHA-256 hash để nhận diện file thay đổi.
    State file: data/ingestion_state.json
    """

    def __init__(self, state_file: Path = None):
        self.state_file = state_file or Config.INGESTION_STATE_FILE
        self._state: Dict = self._load_state()

    # =========================================================================
    # LOAD / SAVE STATE
    # =========================================================================
    def _load_state(self) -> Dict:
        """Đọc file trạng thái. Trả về dict rỗng nếu chưa có file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    print(f"📋 [Tracker] Đã load state: {len(data.get('files', {}))} file đã index")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ [Tracker] Lỗi đọc state file: {e} → khởi tạo mới")
        return {"files": {}}

    def _save_state(self):
        """Ghi file trạng thái ra đĩa."""
        os.makedirs(self.state_file.parent, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)
        print(f"💾 [Tracker] Đã lưu state: {len(self._state['files'])} file")

    # =========================================================================
    # SHA-256 HASH — Fingerprint của file
    # =========================================================================
    @staticmethod
    def _compute_sha256(file_path: str) -> str:
        """Tính SHA-256 hash của file. Đọc theo block 64KB để tiết kiệm RAM."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
        return sha256.hexdigest()

    # =========================================================================
    # QUÉT THƯ MỤC PDF
    # =========================================================================
    @staticmethod
    def _scan_pdf_files(folder_path: str = None) -> Dict[str, str]:
        """
        Quét thư mục PDF và trả về dict {filename: absolute_path}.
        Quét cả thư mục con (static/, dynamic/).
        """
        if folder_path is None:
            folder_path = str(Config.RAW_PDF_DIR)

        pdf_map = {}
        for root, _, files in os.walk(folder_path):
            for fname in files:
                if fname.lower().endswith(".pdf"):
                    full_path = os.path.join(root, fname)
                    pdf_map[fname] = full_path
        return pdf_map

    # =========================================================================
    # COMPUTE DIFF — So sánh trạng thái hiện tại vs. đã lưu
    # =========================================================================
    def compute_diff(self, folder_path: str = None) -> IngestionDiff:
        """
        So sánh trạng thái kho PDF hiện tại với trạng thái đã index.

        Returns:
            IngestionDiff chứa danh sách file new/modified/deleted/unchanged
        """
        current_files = self._scan_pdf_files(folder_path)
        saved_files   = self._state.get("files", {})

        diff = IngestionDiff()

        # 1. Kiểm tra file hiện có trên đĩa
        for fname, fpath in current_files.items():
            current_hash = self._compute_sha256(fpath)

            if fname not in saved_files:
                # File mới — chưa từng index
                diff.new_files.append(fname)
            elif saved_files[fname].get("sha256") != current_hash:
                # File đã sửa đổi — hash khác
                diff.modified_files.append(fname)
            else:
                # File không đổi — bỏ qua
                diff.unchanged_files.append(fname)

        # 2. Kiểm tra file đã bị xóa khỏi thư mục
        for fname in saved_files:
            if fname not in current_files:
                diff.deleted_files.append(fname)

        print(diff.summary())
        return diff

    # =========================================================================
    # CẬP NHẬT STATE SAU KHI INDEX
    # =========================================================================
    def mark_indexed(self, filename: str, file_path: str, chunk_count: int):
        """Đánh dấu file đã được index thành công."""
        self._state["files"][filename] = {
            "sha256":      self._compute_sha256(file_path),
            "indexed_at":  datetime.now().isoformat(),
            "chunk_count": chunk_count,
            "file_path":   file_path,
        }

    def mark_deleted(self, filename: str):
        """Xóa file khỏi state (đã xóa khỏi Qdrant)."""
        self._state["files"].pop(filename, None)

    def commit(self):
        """Lưu toàn bộ thay đổi state ra đĩa."""
        self._save_state()

    def reset(self):
        """Xóa sạch state (dùng cho Force Re-index)."""
        self._state = {"files": {}}
        self._save_state()
        print("🗑️ [Tracker] Đã reset toàn bộ state")
