import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.services.knowledge.manifest_reader import ManifestReader

CANONICAL_OWNER_SLUGS = {
    "ben_bernake": "ben_bernanke",
    "fed": "federal_reserve",
    "frb": "federal_reserve",
    "word_bank": "world_bank",
    "word_gold_council": "world_gold_council",
    "worldgoldcouncil": "world_gold_council",
}

ORGANIZATION_DISPLAY_NAMES = {
    "federal_reserve": "Federal Reserve",
    "bls": "BLS",
    "bea": "BEA",
    "imf": "IMF",
    "world_bank": "World Bank",
    "oecd": "OECD",
    "bis": "BIS",
    "world_gold_council": "World Gold Council",
}

REPORT_FILENAME_PATTERNS = [
    ("summary_of_economic_projections", "Summary Of Economic Projections", "SEP", "US"),
    ("fomc_minutes", "FOMC Minutes", "FOMC_MINUTES", "US"),
    ("minutes", "FOMC Minutes", "FOMC_MINUTES", "US"),
    ("fomc_statement", "FOMC Statement", "FOMC", "US"),
    ("fomc", "FOMC Statement", "FOMC", "US"),
    ("cpi", "US CPI Report", "CPI", "US"),
    ("nonfarm_payrolls", "US Nonfarm Payrolls", "NFP", "US"),
    ("nfp", "US Nonfarm Payrolls", "NFP", "US"),
    ("employment", "US Employment Report", "EMPLOYMENT", "US"),
    ("gdp", "US GDP Report", "GDP", "US"),
    ("world_economic_outlook", "World Economic Outlook", "GLOBAL_OUTLOOK", ""),
    ("commodity_markets_outlook", "Commodity Markets Outlook", "COMMODITY_MARKETS", ""),
    ("gold_market", "Gold Market Commentary", "GOLD_MARKET", ""),
]


@dataclass
class AutoManifestResult:
    manifest_path: str
    data: Dict[str, Any]
    created: bool = False
    updated: bool = False
    messages: List[str] = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []


class AutoManifestService:
    """Create and repair sidecar manifests for zero-touch V3 updates."""

    def ensure_manifest(
        self,
        file_path: str,
        mutate: bool = True,
        update_checksum: bool = True,
        metadata_hints: Optional[Dict[str, Any]] = None,
    ) -> AutoManifestResult:
        path = Path(file_path)
        manifest_path = Path(f"{path.with_suffix('')}.manifest.yaml")
        path_metadata = self._metadata_from_path(path)
        data: Dict[str, Any] = {}
        created = False
        updated = False
        messages: List[str] = []

        if manifest_path.exists():
            data = ManifestReader.read_manifest(str(manifest_path))
        else:
            created = True
            updated = True
            messages.append("manifest_created")

        hints = metadata_hints or {}
        defaults = self._default_manifest(path, path_metadata, hints)
        for key, value in defaults.items():
            if not self._has_value(data.get(key)) and self._has_value(value):
                data[key] = value
                updated = True

        if path_metadata.get("knowledge_type") == "report":
            updated = self._apply_report_canonical_fields(data, defaults) or updated

        canonical_author_slug = self._canonical_owner_slug(data.get("author_slug"))
        if canonical_author_slug and canonical_author_slug != data.get("author_slug"):
            data["author_slug"] = canonical_author_slug
            path_author = self.title_from_slug(path_metadata.get("path_owner_slug", ""))
            if not self._has_value(data.get("author")) or data.get("author") == path_author:
                data["author"] = self.title_from_slug(canonical_author_slug)
            updated = True
            messages.append(f"author_slug_canonicalized:{canonical_author_slug}")

        tags = data.get("tags")
        if not isinstance(tags, dict):
            data["tags"] = {"strategies": [], "assets": [], "timeframe_focus": []}
            updated = True

        checksum = str(hints.get("checksum") or hints.get("content_sha256") or "")
        if not checksum:
            checksum = self.calculate_checksum(str(path))
        if checksum and (not data.get("checksum") or update_checksum and data.get("checksum") != checksum):
            data["checksum"] = checksum
            updated = True
            messages.append("checksum_updated")

        if mutate and updated:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)

        return AutoManifestResult(
            manifest_path=str(manifest_path),
            data=data,
            created=created,
            updated=updated,
            messages=messages,
        )

    def _default_manifest(
        self,
        path: Path,
        path_metadata: Dict[str, str],
        metadata_hints: Dict[str, Any],
    ) -> Dict[str, Any]:
        title_slug = self.slugify(path.stem)
        title = metadata_hints.get("title") or self.title_from_slug(path.stem)
        author_slug = path_metadata.get("owner_slug", "unknown")
        author = metadata_hints.get("author") or self.title_from_slug(author_slug)
        report_defaults = {}
        if path_metadata.get("knowledge_type") == "report":
            report_defaults = self._report_defaults(path, path_metadata, metadata_hints)
            title = report_defaults.get("title") or title
            author = report_defaults.get("organization") or author

        defaults = {
            "title": title,
            "title_slug": title_slug,
            "author": author,
            "author_slug": author_slug,
            "knowledge_type": path_metadata.get("knowledge_type", "unknown"),
            "domain": path_metadata.get("domain", "unknown"),
            "subdomain": path_metadata.get("subdomain", "unknown"),
            "document_type": path.suffix.lower().lstrip("."),
            "version": "v1",
            "lifecycle": "ACTIVE",
            "language": "en",
            "source_tier": "tier3",
            "publisher": "",
            "edition": "",
            "publish_year": 0,
            "tags": {"strategies": [], "assets": [], "timeframe_focus": []},
        }
        defaults.update(report_defaults)
        return defaults

    def _metadata_from_path(self, path: Path) -> Dict[str, str]:
        parts = list(path.parts)
        try:
            repo_idx = parts.index("knowledge_repository")
        except ValueError:
            return {}

        if len(parts) < repo_idx + 6:
            return {}

        return {
            "knowledge_type": parts[repo_idx + 1],
            "domain": parts[repo_idx + 2],
            "subdomain": parts[repo_idx + 3],
            "owner_slug": self._canonical_owner_slug(parts[repo_idx + 4]),
            "path_owner_slug": parts[repo_idx + 4],
        }

    @staticmethod
    def calculate_checksum(file_path: str) -> str:
        digest = hashlib.sha256()
        try:
            with open(file_path, "rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        except Exception:
            return ""

    @staticmethod
    def slugify(value: str) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return text.strip("_") or "unknown"

    @staticmethod
    def title_from_slug(value: str) -> str:
        text = re.sub(r"[_\-]+", " ", str(value or "")).strip()
        return text.title() if text else "Unknown"

    def _report_defaults(
        self,
        path: Path,
        path_metadata: Dict[str, str],
        metadata_hints: Dict[str, Any],
    ) -> Dict[str, Any]:
        stem = self.slugify(path.stem)
        organization_slug = path_metadata.get("owner_slug", "unknown")
        organization = ORGANIZATION_DISPLAY_NAMES.get(
            organization_slug,
            self.title_from_slug(organization_slug),
        )
        title, event_type, country = self._infer_report_type(stem, path_metadata)
        period = self._infer_period(stem)
        published_date = self._infer_published_date(stem)
        asset_focus = self._infer_asset_focus(path_metadata, stem)

        title_slug_source = " ".join(part for part in [metadata_hints.get("title") or title, period] if part)
        defaults = {
            "organization_slug": organization_slug,
            "organization": metadata_hints.get("organization") or organization,
            "author": metadata_hints.get("author") or organization,
            "author_slug": organization_slug,
            "title": metadata_hints.get("title") or title,
            "title_slug": self.slugify(title_slug_source),
            "source_tier": "tier1" if organization_slug in ORGANIZATION_DISPLAY_NAMES else "tier3",
            "country": country,
            "event_type": event_type,
            "published_date": published_date,
            "period": period,
            "release_time": "",
            "revision": self._infer_revision(stem),
            "asset_focus": asset_focus,
        }
        return {key: value for key, value in defaults.items() if self._has_value(value)}

    def _infer_report_type(self, stem: str, path_metadata: Dict[str, str]) -> tuple[str, str, str]:
        for token, title, event_type, country in REPORT_FILENAME_PATTERNS:
            if token in stem:
                return title, event_type, country
        title = self.title_from_slug(stem)
        event_type = self.slugify(path_metadata.get("subdomain", "")).upper()
        return title, event_type, ""

    @staticmethod
    def _infer_period(stem: str) -> str:
        date_match = re.search(r"(20\d{2})[_\-](0[1-9]|1[0-2])[_\-](0[1-9]|[12]\d|3[01])", stem)
        if date_match:
            return "-".join(date_match.groups())
        month_match = re.search(r"(20\d{2})[_\-](0[1-9]|1[0-2])", stem)
        if month_match:
            return "-".join(month_match.groups())
        quarter_match = re.search(r"(20\d{2})[_\-]q([1-4])", stem)
        if quarter_match:
            return f"{quarter_match.group(1)}-Q{quarter_match.group(2)}"
        return ""

    def _infer_published_date(self, stem: str) -> str:
        period = self._infer_period(stem)
        return period if len(period) == 10 else ""

    @staticmethod
    def _infer_revision(stem: str) -> str:
        for revision in ["advance", "second_estimate", "third_estimate", "final"]:
            if revision in stem:
                return revision
        return ""

    @staticmethod
    def _infer_asset_focus(path_metadata: Dict[str, str], stem: str) -> str:
        if path_metadata.get("subdomain") == "gold" or "gold" in stem:
            return "gold"
        if path_metadata.get("subdomain") == "commodities" or "commodity" in stem:
            return "commodities"
        return ""

    def _apply_report_canonical_fields(self, data: Dict[str, Any], defaults: Dict[str, Any]) -> bool:
        updated = False
        canonical_keys = {
            "organization_slug",
            "organization",
            "author",
            "author_slug",
            "knowledge_type",
            "domain",
            "subdomain",
            "document_type",
            "title",
            "title_slug",
            "source_tier",
            "country",
            "event_type",
            "published_date",
            "period",
            "revision",
            "asset_focus",
        }
        for key in canonical_keys:
            value = defaults.get(key)
            if self._has_value(value) and data.get(key) != value:
                data[key] = value
                updated = True
        return updated

    @staticmethod
    def _canonical_owner_slug(value: Any) -> str:
        slug = str(value or "").strip().lower()
        return CANONICAL_OWNER_SLUGS.get(slug, slug)

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True
