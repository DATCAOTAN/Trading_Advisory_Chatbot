"""
Launcher cho Trading Advisory Chatbot — Fix crash pyarrow DLL trên Windows.

NGUYÊN NHÂN CRASH:
  Streamlit chạy script trên ScriptRunner thread (không phải main thread).
  Khi sentence_transformers → datasets → pyarrow cố load DLL trên thread phụ
  → Windows báo "access violation" (segfault).

GIẢI PHÁP:
  Script này chạy trên MAIN THREAD, pre-import tất cả thư viện native
  TRƯỚC khi Streamlit tạo ScriptRunner thread. Khi ScriptRunner import lại,
  Python trả về module đã cache → không load DLL mới → không crash.

CÁCH DÙNG:
  python launcher.py          (thay cho streamlit run src/app.py)
"""
import os
import sys

# ── Env vars chống crash OpenMP/MKL ──────────────────────────────────────────
os.environ["KMP_DUPLICATE_LIB_OK"]  = "TRUE"
os.environ["OMP_NUM_THREADS"]       = "1"
os.environ["MKL_NUM_THREADS"]       = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ── Thêm project root vào sys.path ──────────────────────────────────────────
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# =============================================================================
# PRE-IMPORT: Load tất cả native DLLs trên MAIN THREAD
# =============================================================================
print("🔧 [Launcher] Pre-loading native libraries trên main thread...")

# 1. PyArrow (thủ phạm chính)
try:
    import pyarrow
    import pyarrow.lib
    # Cố load thêm các submodule native gây crash
    try:
        import pyarrow.dataset
    except Exception:
        pass
    try:
        import pyarrow.parquet
    except Exception:
        pass
    print(f"   ✅ pyarrow {pyarrow.__version__}")
except ImportError:
    print("   ⚠️ pyarrow chưa cài")

# 2. Torch
try:
    import torch
    print(f"   ✅ torch {torch.__version__}")
except ImportError:
    print("   ⚠️ torch chưa cài")

# 3. Sentence Transformers (kéo theo datasets, transformers, tokenizers)
try:
    from sentence_transformers import SentenceTransformer
    print("   ✅ sentence_transformers")
except ImportError:
    print("   ⚠️ sentence_transformers chưa cài")

# 4. Các thư viện native khác
for lib_name in ["sklearn", "pandas", "numpy"]:
    try:
        __import__(lib_name)
    except ImportError:
        pass

print("🔧 [Launcher] Pre-load hoàn tất. Khởi động Streamlit...\n")

# =============================================================================
# KHỞI ĐỘNG STREAMLIT
# =============================================================================
from streamlit.web.cli import main as st_main

# Giả lập lệnh: streamlit run src/app.py
sys.argv = ["streamlit", "run", os.path.join(project_root, "src", "app.py"),
            "--server.fileWatcherType", "none"]

st_main()
