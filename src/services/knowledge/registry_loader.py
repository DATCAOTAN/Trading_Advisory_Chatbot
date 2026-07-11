import os
import yaml
from typing import Dict, Any, List

class RegistryLoader:
    """
    Đọc và cache cấu trúc Registry từ các file YAML trong src/metadata/.
    """
    _instance = None
    _is_initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RegistryLoader, cls).__new__(cls)
        return cls._instance

    def __init__(self, metadata_dir: str = "src/metadata"):
        if self._is_initialized:
            return
        
        self.metadata_dir = metadata_dir
        self.authors: Dict[str, Any] = {}
        self.domains: Dict[str, Any] = {}
        self.assets: List[str] = []
        self.strategies: List[str] = []
        self.knowledge_types: List[str] = []
        self.languages: List[str] = []
        
        self.load_all()
        self.__class__._is_initialized = True

    def _load_yaml(self, filename: str) -> Any:
        path = os.path.join(self.metadata_dir, filename)
        if not os.path.exists(path):
            print(f"⚠️ [RegistryLoader] File not found: {path}")
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"❌ [RegistryLoader] Error loading {filename}: {e}")
            return {}

    def load_all(self):
        self.authors = self._load_yaml("authors.yaml")
        self.domains = self._load_yaml("domains.yaml")
        
        assets_data = self._load_yaml("assets.yaml")
        self.assets = assets_data.get("assets", []) if isinstance(assets_data, dict) else []
        
        strategies_data = self._load_yaml("strategies.yaml")
        self.strategies = strategies_data.get("strategies", []) if isinstance(strategies_data, dict) else []
        
        types_data = self._load_yaml("knowledge_types.yaml")
        self.knowledge_types = types_data.get("types", []) if isinstance(types_data, dict) else []
        
        lang_data = self._load_yaml("languages.yaml")
        self.languages = lang_data.get("languages", []) if isinstance(lang_data, dict) else []

    def get_source_tier(self, author_name: str) -> str:
        """Lấy source_tier của tác giả, mặc định là tier3 nếu không tìm thấy."""
        author_info = self.authors.get(author_name, {})
        return author_info.get("source_tier", "tier3")

    def is_valid_domain(self, domain: str) -> bool:
        return domain in self.domains

    def is_valid_subdomain(self, domain: str, subdomain: str) -> bool:
        if domain not in self.domains:
            return False
        subdomains = self.domains[domain].get("subdomains", [])
        return subdomain in subdomains
