import os
import fitz  # PyMuPDF
from typing import List, Dict, Any, Tuple
from src.config import Config


class PDFParserService:
    """
    Dịch vụ bóc tách và cắt nhỏ văn bản PDF theo chiến lược Parent-Child Chunking.

    Chiến lược hai cấp:
    ┌─────────────────────────────────────────────┐
    │ PARENT chunk (~2000 ký tự)                  │
    │ → Lưu vào payload, BƠM vào LLM khi truy vấn│
    │   ├─ CHILD chunk (~400 ký tự)               │
    │   │  → Lập index Vector, dùng để TÌM KIẾM  │
    │   ├─ CHILD chunk (overlap 80 ký tự)         │
    │   └─ CHILD chunk ...                        │
    └─────────────────────────────────────────────┘
    """

    @staticmethod
    def _extract_full_text(pdf_path: str) -> str:
        """Bóc tách toàn bộ văn bản từ 1 file PDF."""
        try:
            doc = fitz.open(pdf_path)
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()
            return "\n".join(pages_text)
        except Exception as e:
            print(f"❌ Lỗi khi đọc file PDF '{pdf_path}': {e}")
            return ""

    @staticmethod
    def _make_sliding_chunks(text: str, chunk_size: int, overlap: int) -> List[Tuple[int, str]]:
        """
        Cắt văn bản thành các đoạn bằng Sliding Window.
        Trả về list[(start_idx, chunk_text)] để tra vị trí.
        """
        chunks = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = start + chunk_size
            chunk_text = text[start:end].strip()
            if len(chunk_text) > 50:  # Bỏ qua đoạn quá ngắn, không có nghĩa
                chunks.append((start, chunk_text))
            start += (chunk_size - overlap)
        return chunks

    @staticmethod
    def extract_parent_child_chunks(
        folder_path: str = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Quét thư mục PDF và trả về 2 danh sách:
        - parents: Các đoạn lớn (~2000 ký tự) chứa ngữ cảnh đầy đủ cho LLM
        - children: Các đoạn nhỏ (~400 ký tự) để lập index tìm kiếm, có parent_id

        Returns:
            (parents_list, children_list)
        """
        if folder_path is None:
            folder_path = str(Config.RAW_PDF_DIR)

        all_parents: List[Dict[str, Any]] = []
        all_children: List[Dict[str, Any]] = []
        parent_id_counter = 0

        # Quét tất cả PDF trong thư mục và thư mục con
        pdf_files = []
        for root, _, files in os.walk(folder_path):
            for file_name in files:
                if file_name.lower().endswith(".pdf"):
                    pdf_files.append((root, file_name))

        if not pdf_files:
            print(f"⚠️ [Parser] Không tìm thấy file PDF nào trong: {folder_path}")
            return [], []

        for root, file_name in pdf_files:
            pdf_path = os.path.join(root, file_name)
            parents, children = PDFParserService.extract_single_file(
                pdf_path, file_name, parent_id_start=parent_id_counter,
            )
            parent_id_counter += len(parents)
            all_parents.extend(parents)
            all_children.extend(children)

        print(f"✅ [Parser] Hoàn thành: {len(all_parents)} parent chunks, {len(all_children)} child chunks")
        return all_parents, all_children

    @staticmethod
    def extract_single_file(
        pdf_path: str,
        file_name: str = None,
        parent_id_start: int = 0,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Bóc tách và cắt nhỏ MỘT file PDF duy nhất.

        Được thiết kế cho Incremental Ingestion — chỉ xử lý file cần thiết,
        không cần quét lại toàn bộ thư mục.

        Args:
            pdf_path:         Đường dẫn tuyệt đối đến file PDF
            file_name:        Tên file (dùng trong metadata). Nếu None, tự trích từ path.
            parent_id_start:  ID khởi đầu cho parent chunks (tránh trùng khi batch)

        Returns:
            (parents_list, children_list) cho file này
        """
        if file_name is None:
            file_name = os.path.basename(pdf_path)

        print(f"📖 [Parser] Đang bóc tách: {file_name}")

        full_text = PDFParserService._extract_full_text(pdf_path)
        if not full_text.strip():
            print(f"⚠️ [Parser] File rỗng hoặc lỗi: {file_name}")
            return [], []

        # Xác định loại tài liệu (static/dynamic)
        doc_type = "dynamic" if "dynamic" in pdf_path else "static"

        # Lấy tên thư mục mẹ để áp dụng Adaptive Chunking
        folder_name = os.path.basename(os.path.dirname(pdf_path))
        chunk_cfg = Config.ADAPTIVE_CHUNK_CONFIG.get(folder_name, Config.ADAPTIVE_CHUNK_CONFIG["default"])

        parents: List[Dict[str, Any]]  = []
        children: List[Dict[str, Any]] = []
        parent_id_counter = parent_id_start

        # Bước 1: Tạo Parent chunks theo cấu hình thích ứng
        parent_chunks_raw = PDFParserService._make_sliding_chunks(
            full_text,
            chunk_size=chunk_cfg["parent_size"],
            overlap=chunk_cfg["parent_overlap"],
        )

        for parent_start, parent_text in parent_chunks_raw:
            current_parent_id = parent_id_counter
            parent_id_counter += 1

            parents.append({
                "parent_id": current_parent_id,
                "text": parent_text,
                "metadata": {
                    "source": file_name,
                    "doc_type": doc_type,
                    "char_start": parent_start,
                }
            })

            # Bước 2: Tạo Child chunks từ văn bản của Parent theo cấu hình thích ứng
            child_chunks_raw = PDFParserService._make_sliding_chunks(
                parent_text,
                chunk_size=chunk_cfg["child_size"],
                overlap=chunk_cfg["child_overlap"],
            )

            for _, child_text in child_chunks_raw:
                children.append({
                    "parent_id": current_parent_id,
                    "text": child_text,
                    "metadata": {
                        "source": file_name,
                        "doc_type": doc_type,
                    }
                })

        print(f"   ↳ {file_name}: {len(parents)} parents, {len(children)} children")
        return parents, children

    @staticmethod
    def extract_chunks_from_folder() -> List[Dict[str, Any]]:
        """Backward-compatible: Trả về flat list children cho các script test cũ."""
        _, children = PDFParserService.extract_parent_child_chunks()
        return children


if __name__ == "__main__":
    print("=== SMOKE TEST: PARENT-CHILD PDF PARSER ===")
    parents, children = PDFParserService.extract_parent_child_chunks()

    if parents:
        print(f"\n📊 Tổng: {len(parents)} parents | {len(children)} children")
        print(f"📐 Tỷ lệ: ~{len(children) // max(len(parents), 1)} children/parent")
        print("\n🔍 MẪU PARENT #0:")
        print(f"   Source: {parents[0]['metadata']['source']}")
        print(f"   Text ({len(parents[0]['text'])} ký tự): {parents[0]['text'][:200]}...")
        print(f"\n🔍 MẪU CHILD #0 (→ parent_id={children[0]['parent_id']}):")
        print(f"   Text ({len(children[0]['text'])} ký tự): {children[0]['text'][:200]}...")
    else:
        print("❌ Chưa có PDF nào. Hãy bỏ file vào data/raw_pdfs/")