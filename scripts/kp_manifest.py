import os
import sys
import hashlib
import yaml

def calculate_checksum(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def init_manifest(pdf_path: str):
    if not pdf_path.endswith('.pdf'):
        print("Vui lòng cung cấp file .pdf")
        return
    
    manifest_path = pdf_path.replace('.pdf', '.manifest.yaml')
    if os.path.exists(manifest_path):
        print(f"Manifest đã tồn tại: {manifest_path}")
        return

    checksum = calculate_checksum(pdf_path)
    base_name = os.path.basename(pdf_path).replace('.pdf', '')
    
    # Trích xuất mặc định từ Convention Path
    # data/knowledge_repository/{knowledge_type}/{domain}/{subdomain}/{author_slug}/{file.pdf}
    parts = os.path.normpath(pdf_path).split(os.sep)
    try:
        repo_idx = parts.index("knowledge_repository")
        knowledge_type = parts[repo_idx + 1] if len(parts) > repo_idx + 1 else "book"
        domain = parts[repo_idx + 2] if len(parts) > repo_idx + 2 else "unknown"
        subdomain = parts[repo_idx + 3] if len(parts) > repo_idx + 3 else "unknown"
        author_slug = parts[repo_idx + 4] if len(parts) > repo_idx + 4 else "unknown_author"
    except ValueError:
        knowledge_type = "book"
        domain = "unknown"
        subdomain = "unknown"
        author_slug = "unknown_author"

    title_display = base_name.replace('_', ' ').title()

    manifest_data = {
        "title_slug": base_name,
        "author_slug": author_slug,
        "version": "v1",
        "title": title_display,
        "author": "Auto Generated",
        "edition": "1st Edition",
        "publish_year": 2024,
        "language": "en",
        "knowledge_type": knowledge_type,
        "lifecycle": "ACTIVE",
        "checksum": checksum,
        "tags": {
            "strategies": [],
            "assets": [],
            "timeframe_focus": []
        }
    }

    with open(manifest_path, 'w', encoding='utf-8') as f:
        yaml.dump(manifest_data, f, allow_unicode=True, sort_keys=False)
    
    print(f"✅ Đã tạo manifest skeleton kèm checksum: {manifest_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python kp_manifest.py [init|checksum] <pdf_path>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    path = sys.argv[2]
    
    if cmd == "init":
        init_manifest(path)
    elif cmd == "checksum":
        print(calculate_checksum(path))
