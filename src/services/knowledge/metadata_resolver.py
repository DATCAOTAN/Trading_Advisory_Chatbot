import os
from typing import Dict, Any

from src.services.knowledge.manifest_reader import ManifestReader
from src.services.knowledge.registry_loader import RegistryLoader
from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.auto_manifest_service import CANONICAL_OWNER_SLUGS


def canonical_owner_slug(value: str) -> str:
    slug = str(value or "").strip().lower()
    return CANONICAL_OWNER_SLUGS.get(slug, slug)

class MetadataResolver:
    """
    Kết hợp dữ liệu từ Thư mục, Manifest và Registry để tạo ra Metadata chuẩn.
    Bảo vệ chống Duplicate Knowledge (Nội dung trùng nhưng đổi tên file).
    """

    def __init__(self):
        self.registry = RegistryLoader()
        self.catalog = KnowledgeCatalog()

    def resolve(self, file_path: str) -> Dict[str, Any]:
        parts = os.path.normpath(file_path).split(os.sep)
        
        # 1. Path Strict Validation
        extension = os.path.splitext(file_path)[1].lower()
        if extension not in {".pdf", ".epub"}:
            return {"error": f"FATAL: Unsupported file extension '{extension}' for {file_path}", "lifecycle": "QUARANTINE"}

        try:
            repo_idx = parts.index("knowledge_repository")
        except ValueError:
            return {"error": "FATAL: Path does not contain 'knowledge_repository'", "lifecycle": "QUARANTINE"}
            
        if len(parts) < repo_idx + 6:
            return {"error": f"FATAL: Path convention violation (too short) for {file_path}", "lifecycle": "QUARANTINE"}
            
        knowledge_type = parts[repo_idx + 1]
        domain = parts[repo_idx + 2]
        subdomain = parts[repo_idx + 3]
        path_author_slug = parts[repo_idx + 4]
        author_slug = canonical_owner_slug(path_author_slug)

        # 2. Đọc Manifest
        manifest_path = ManifestReader.find_manifest_for_file(file_path)
        if not manifest_path:
             return {"error": f"FATAL: Missing .manifest.yaml for {file_path}", "lifecycle": "QUARANTINE"}           
        manifest_data = ManifestReader.read_manifest(manifest_path)

        knowledge_type = manifest_data.get("knowledge_type", knowledge_type)
        manifest_author_slug = str(manifest_data.get("author_slug", author_slug) or "").strip().lower()
        author_slug = canonical_owner_slug(manifest_author_slug)
        domain = manifest_data.get("domain", domain) 

        # 3. Registry Mapping
        author_info = self.registry.authors.get(author_slug, {})
        source_tier = manifest_data.get("source_tier") or author_info.get("source_tier", "tier3")
        organization_slug = str(manifest_data.get("organization_slug", "") or "").strip().lower()
        organization_info = self.registry.authors.get(organization_slug, {}) if organization_slug else {}
        organization_display_name = (
            organization_info.get("display_name")
            or manifest_data.get("organization")
            or ""
        )
        author_display_name = author_info.get("display_name", manifest_data.get("author", "Unknown"))
        if knowledge_type == "report":
            author_display_name = organization_display_name or author_display_name

        # 4. Sinh ID
        t_slug = manifest_data.get("title_slug", "unknown_title")
        version = manifest_data.get("version", "v1")
        doc_id = f"{knowledge_type}_{t_slug}_{author_slug}_{version}".lower()
        alternate_doc_ids = self._alternate_doc_ids(
            knowledge_type=knowledge_type,
            title_slug=t_slug,
            version=version,
            canonical_author_slug=author_slug,
            raw_author_slugs=[manifest_author_slug, path_author_slug],
        )

        # 5. Duplicate Knowledge Detection (Fingerprint check)
        checksum = manifest_data.get("checksum", "")
        replaces_doc_id = ""
        if checksum:
            existing_doc_id = self.catalog.find_doc_id_by_checksum(checksum)
            if existing_doc_id and existing_doc_id != doc_id:
                existing_doc = self.catalog.get_document(existing_doc_id) or {}
                existing_source = os.path.normpath(existing_doc.get("source_path") or "")
                current_source = os.path.normpath(file_path)
                if existing_source == current_source or existing_doc_id in alternate_doc_ids:
                    replaces_doc_id = existing_doc_id
                elif existing_source and not os.path.exists(existing_source):
                    replaces_doc_id = existing_doc_id
                else:
                    return {
                        "error": f"POSSIBLE_DUPLICATE: Checksum matches existing doc_id '{existing_doc_id}'", 
                        "lifecycle": "QUARANTINE"
                    }

        # 6. Routing Metadata
        tags = manifest_data.get("tags", {})
        routing_metadata = {
            "domain": domain,
            "subdomain": subdomain,
            "strategies": tags.get("strategies", []),
            "assets": tags.get("assets", []),
            "timeframe_focus": tags.get("timeframe_focus", []),
            "knowledge_type": knowledge_type,
            "source_tier": source_tier,
            "language": manifest_data.get("language", "en"),
            "event_type": manifest_data.get("event_type", ""),
            "country": manifest_data.get("country", ""),
            "period": manifest_data.get("period", ""),
            "asset_focus": manifest_data.get("asset_focus", ""),
        }

        # 7. Document Metadata
        document_metadata = {
            "doc_id": doc_id,
            "title": manifest_data.get("title", ""),
            "author": author_display_name,
            "organization": organization_display_name,
            "organization_slug": organization_slug,
            "publisher": manifest_data.get("publisher", ""),
            "edition": manifest_data.get("edition", ""),
            "publish_year": manifest_data.get("publish_year", 0),
            "original_filename": os.path.basename(file_path),
            "checksum": checksum,
            "document_type": extension.lstrip("."),
            "lifecycle": manifest_data.get("lifecycle", "ACTIVE"),
            "source_tier": source_tier,
            "country": manifest_data.get("country", ""),
            "event_type": manifest_data.get("event_type", ""),
            "published_date": manifest_data.get("published_date", ""),
            "period": manifest_data.get("period", ""),
            "release_time": manifest_data.get("release_time", ""),
            "revision": manifest_data.get("revision", ""),
            "asset_focus": manifest_data.get("asset_focus", ""),
        }

        return {
            "doc_id": doc_id,
            "lifecycle": manifest_data.get("lifecycle", "ACTIVE"),
            "routing_metadata": routing_metadata,
            "document_metadata": document_metadata,
            "chunking_override": manifest_data.get("chunking", {}),
            "parser": manifest_data.get("parser", {}),
            "replaces_doc_id": replaces_doc_id,
        }

    def _alternate_doc_ids(
        self,
        knowledge_type: str,
        title_slug: str,
        version: str,
        canonical_author_slug: str,
        raw_author_slugs: list,
    ) -> set:
        doc_ids = set()
        raw_candidates = set(raw_author_slugs)
        for alias, canonical in CANONICAL_OWNER_SLUGS.items():
            if canonical == canonical_author_slug:
                raw_candidates.add(alias)
        for raw_slug in raw_candidates:
            raw_slug = str(raw_slug or "").strip().lower()
            if raw_slug and raw_slug != canonical_author_slug:
                doc_ids.add(f"{knowledge_type}_{title_slug}_{raw_slug}_{version}".lower())
        return doc_ids
