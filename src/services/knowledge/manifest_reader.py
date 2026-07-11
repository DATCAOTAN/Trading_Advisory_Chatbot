import os
import yaml
from typing import Dict, Any, Optional

class ManifestReader:
    """
    Đọc file .manifest.yaml đi kèm với mỗi tài liệu gốc (PDF, DOCX).
    """

    @staticmethod
    def read_manifest(manifest_path: str) -> Dict[str, Any]:
        """
        Đọc nội dung file manifest. Trả về dict rỗng nếu lỗi.
        """
        if not os.path.exists(manifest_path):
            print(f"⚠️ [ManifestReader] Manifest không tồn tại: {manifest_path}")
            return {}
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data if data is not None else {}
        except Exception as e:
            print(f"❌ [ManifestReader] Lỗi đọc file {manifest_path}: {e}")
            return {}

    @staticmethod
    def find_manifest_for_file(file_path: str) -> Optional[str]:
        """
        Tìm file manifest tương ứng với file tài liệu gốc.
        Ví dụ: book.pdf -> book.manifest.yaml
        """
        base_name = os.path.splitext(file_path)[0]
        manifest_path = f"{base_name}.manifest.yaml"
        if os.path.exists(manifest_path):
            return manifest_path
        return None
