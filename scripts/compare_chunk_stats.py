import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def make_isolated_resolver(temp_dir: str):
    from src.services.knowledge.catalog_manager import KnowledgeCatalog
    from src.services.knowledge.metadata_resolver import MetadataResolver
    from src.services.knowledge.registry_loader import RegistryLoader

    resolver = MetadataResolver.__new__(MetadataResolver)
    resolver.registry = RegistryLoader()
    resolver.catalog = KnowledgeCatalog(str(Path(temp_dir) / "catalog.sqlite"))
    return resolver


def collect_stats(file_path: str, resolver: Optional[Any] = None) -> Dict[str, Any]:
    try:
        from src.services.knowledge.chunk_builder import ChunkBuilder
        from src.services.knowledge.validator import Validator
    except ImportError as exc:
        return {
            "status": "FAILED",
            "input_file_path": file_path,
            "error": f"Missing dependency for chunk stats: {exc}",
        }

    with tempfile.TemporaryDirectory() as temp_dir:
        resolver = resolver or make_isolated_resolver(temp_dir)
        metadata = resolver.resolve(file_path)

        if metadata.get("lifecycle") == "QUARANTINE":
            return {
                "status": "QUARANTINE",
                "input_file_path": file_path,
                "error": metadata.get("error", "QUARANTINE"),
            }

        validation = Validator().validate(file_path, metadata)
        if not validation.is_valid:
            return {
                "status": "FAILED",
                "input_file_path": file_path,
                "validation_level": validation.level,
                "messages": validation.messages,
            }

        chunk_result = ChunkBuilder().build_chunks(file_path, metadata)
        stats = dict(chunk_result.get("chunk_stats", {}))
        stats["status"] = chunk_result.get("status", "")
        stats["doc_id"] = metadata.get("doc_id", "")
        stats["domain"] = metadata.get("routing_metadata", {}).get("domain", "")
        stats["subdomain"] = metadata.get("routing_metadata", {}).get("subdomain", "")
        stats["knowledge_type"] = metadata.get("routing_metadata", {}).get("knowledge_type", "")
        stats["validation_level"] = validation.level
        stats["messages"] = validation.messages
        return stats


def print_stats(stats: Dict[str, Any]) -> None:
    print("[chunk-stats]")
    ordered_keys = [
        "input_file_path",
        "status",
        "doc_id",
        "knowledge_type",
        "domain",
        "subdomain",
        "parser_type",
        "extracted_char_count",
        "extracted_word_count",
        "selected_chunk_policy",
        "parent_chunk_count",
        "indexed_chunk_count",
        "average_chunk_size",
        "ocr_status",
        "total_pages",
        "empty_pages",
        "parent_size",
        "parent_overlap",
        "child_size",
        "child_overlap",
        "chunk_size_unit",
        "token_estimate_unit",
        "parent_size_chars",
        "child_size_chars",
        "child_overlap_chars",
        "parent_target_tokens",
        "child_target_tokens",
        "overlap_tokens",
        "validation_level",
    ]
    for key in ordered_keys:
        if key in stats:
            print(f"{key}: {stats[key]}")
    if stats.get("error"):
        print(stats["error"])
    for message in stats.get("messages", []) or []:
        print(message)
    for warning in stats.get("policy_warnings", []) or []:
        print(f"[WARNING] {warning}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Knowledge Platform V3 chunk statistics without indexing."
    )
    parser.add_argument("file_path")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    stats = collect_stats(args.file_path)
    print_stats(stats)
    return 0 if stats.get("status") not in {"QUARANTINE", "FAILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
