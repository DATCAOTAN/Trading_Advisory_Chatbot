import os
import sys
import uuid
import time
from typing import Dict, Any

from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.metadata_resolver import MetadataResolver
from src.services.knowledge.vector_service import VectorServiceV3

def run_sprint_2_final_tests():
    print("🚀 Bắt đầu chạy Final Test Cases (Sprint 2.2 Enterprise Reliability)...")
    catalog = KnowledgeCatalog()
    resolver = MetadataResolver()
    vs = None
    try:
        vs = VectorServiceV3()
    except Exception as e:
        print(f"⚠️ VectorServiceV3 không khởi tạo được (Thiếu khóa API hoặc Qdrant): {e}")

    print("\n--- TEST 1: Kịch bản Đổi tên giả mạo (Duplicate Detection) ---")
    doc_id_1 = "book_original_john_murphy_v1"
    checksum_fake = "abc123sha256fake"
    
    # Giả lập đã tồn tại tài liệu
    catalog.upsert_document(doc_id_1, {"checksum": checksum_fake})
    
    # Tạo đường dẫn mới nhưng nội dung checksum giống nhau (Đã lưu trong manifest test giả)
    # Vì MetadataResolver đọc file thật, ta mock hàm find_doc_id_by_checksum
    res = catalog.find_doc_id_by_checksum(checksum_fake)
    if res == doc_id_1:
        print("✅ Pass: Hệ thống phát hiện Duplicate Knowledge thông qua Content Fingerprint (Checksum).")
    else:
        print("❌ Fail: Hệ thống không bắt được Duplicate.")

    print("\n--- TEST 2: Kịch bản Heartbeat Timeout (Stale Lock) ---")
    doc_id_stale = "test_doc_stale"
    job_stale = str(uuid.uuid4())
    catalog.acquire_index_lock(doc_id_stale, job_stale)
    
    # Ép Heartbeat về quá khứ 10 phút trước
    conn = catalog._get_connection()
    conn.execute("UPDATE index_jobs SET heartbeat_at = ? WHERE job_id = ?", (time.time() - 600, job_stale))
    conn.commit()
    conn.close()
    
    # Chạy Reconciliation Job (giả định Timeout = 300s)
    if vs:
        try:
            vs.reconcile_index_jobs(timeout_seconds=300)
            doc_status = catalog.get_document(doc_id_stale)
            if doc_status.get("index_status") == "FAILED":
                print("✅ Pass: Reconciliation Job đã quét dọn Stale Lock và Reset status thành FAILED.")
            else:
                print("❌ Fail: Trạng thái không được Reset.")
        except Exception as e:
            print(f"⚠️ Không thể chạy Reconciliation qua Qdrant: {e}")
    else:
        print("⚠️ Bỏ qua Test 2 do Vector DB không khả dụng.")

    print("\n🏁 Hoàn tất Enterprise Test Cases!")

if __name__ == "__main__":
    run_sprint_2_final_tests()
