import os
import fitz  # Thư viện PyMuPDF chuyên xử lý file PDF tốc độ cao
from typing import List, Dict, Any
from src.config import Config

class PDFParserService:
    @staticmethod
    def extract_chunks_from_folder() -> List[Dict[str, Any]]:
        """
        Quét thư mục raw_pdfs, trích xuất văn bản thô từ PDF 
        và thực hiện chia nhỏ văn bản kèm theo thông tin nguồn (Metadata).
        """
        all_chunks = []
        folder_path = str(Config.RAW_PDF_DIR)
        
        if not os.path.exists(folder_path) or not os.listdir(folder_path):
            print(f"⚠️ Cảnh báo: Thư mục {folder_path} trống hoặc không tồn tại. Hãy bỏ file PDF vào!")
            return []

        # Quét qua từng file trong thư mục dữ liệu thô
        for file_name in os.listdir(folder_path):
            if not file_name.endswith('.pdf'):
                continue  # Bỏ qua các file ẩn hoặc file không phải định dạng PDF
                
            pdf_path = os.path.join(folder_path, file_name)
            print(f"📖 Đang bóc tách dữ liệu file: {file_name}")
            
            try:
                # Mở tài liệu PDF bằng PyMuPDF
                doc = fitz.open(pdf_path)
                full_text = ""
                
                # Gộp toàn bộ chữ của tất cả các trang trong file thành 1 chuỗi văn bản lớn
                for page in doc:
                    full_text += page.get_text() + "\n"
                doc.close()
                
                # Thực hiện kỹ thuật Sliding Window Chunking
                start = 0
                text_length = len(full_text)
                
                while start < text_length:
                    end = start + Config.CHUNK_SIZE
                    chunk_text = full_text[start:end].strip()
                    
                    # Chỉ lưu đoạn chunk nếu nó chứa ký tự chữ thực sự hợp lệ
                    if chunk_text:
                        all_chunks.append({
                            "text": chunk_text,
                            "metadata": {"source": file_name}
                        })
                    
                    # Dịch chuyển cửa sổ trượt theo cấu hình overlap đã định nghĩa
                    start += (Config.CHUNK_SIZE - Config.CHUNK_OVERLAP)
                    
            except Exception as e:
                print(f"❌ Gặp lỗi nghiêm trọng khi xử lý file {file_name}: {str(e)}")
                
        return all_chunks

if __name__ == "__main__":
    # Khung kiểm thử độc lập (Isolate Testing) để xác thực chức năng của lớp Parser
    print("=== KIỂM THỬ KHÓI (SMOKE TEST) LỚP PDF PARSER ===")
    chunks = PDFParserService.extract_chunks_from_folder()
    
    if chunks:
        print(f"\n✅ Kiểm thử thành công!")
        print(f"📊 Tổng số đoạn văn bản (Chunks) được tạo ra: {len(chunks)}")
        print("-" * 50)
        print("🔍 BẢN IN THỬ ĐOẠN CHUNK ĐẦU TIÊN ĐỂ KIỂM TRA MẮT THƯỜNG:")
        print(f"📄 Nguồn gốc file: {chunks[0]['metadata']['source']}")
        print(f"📝 Nội dung chữ trích xuất:\n{chunks[0]['text'][:350]}...")
        print("-" * 50)
    else:
        print("\n❌ Kiểm thử thất bại: Chưa bóc tách được dữ liệu. Anh hãy kiểm tra lại file PDF đầu vào.")