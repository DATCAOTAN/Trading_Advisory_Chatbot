from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Generic, Type, TypeVar

from src.config import Config
from src.services.trading.knowledge.models import MacroCard, MethodCard, RegimeMethodMap, StrategyPlaybook


T = TypeVar("T")


class JsonCardStore(Generic[T]):
    card_type: Type[T]
    default_subdir: str
    id_field: str

    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory) if directory else Config.BASE_DIR / "data" / "knowledge_compiled" / self.default_subdir
        self.warnings: list[str] = []

    def load_all(self) -> list[T]:
        self.warnings = []
        if not self.directory.exists():
            self.warnings.append(f"missing_directory:{self.directory}")
            return []
        items: list[T] = []
        seen: set[str] = set()
        for path in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                records = payload if isinstance(payload, list) else [payload]
                for record in records:
                    parsed = self._parse_record(record, path)
                    if parsed is None:
                        continue
                    item_id = str(getattr(parsed, self.id_field, ""))
                    if item_id in seen:
                        self.warnings.append(f"duplicate_id:{item_id}:{path.name}")
                        continue
                    seen.add(item_id)
                    items.append(parsed)
            except Exception as exc:
                self.warnings.append(f"invalid_json:{path.name}:{type(exc).__name__}")
        return items

    def _parse_record(self, record: Any, path: Path) -> T | None:
        if not isinstance(record, dict):
            self.warnings.append(f"invalid_record:{path.name}")
            return None
        required = _required_fields(self.card_type)
        missing = [name for name in required if _missing_value(record.get(name))]
        if missing:
            self.warnings.append(f"missing_required:{path.name}:{','.join(missing)}")
            return None
        allowed = {field.name for field in fields(self.card_type)}
        data = {key: value for key, value in record.items() if key in allowed}
        try:
            return self.card_type(**data)
        except Exception as exc:
            self.warnings.append(f"schema_error:{path.name}:{type(exc).__name__}")
            return None


class MethodCardStore(JsonCardStore[MethodCard]):
    card_type = MethodCard
    default_subdir = "method_cards"
    id_field = "method_id"


class MacroCardStore(JsonCardStore[MacroCard]):
    card_type = MacroCard
    default_subdir = "macro_cards"
    id_field = "macro_id"


class StrategyPlaybookStore(JsonCardStore[StrategyPlaybook]):
    card_type = StrategyPlaybook
    default_subdir = "strategy_playbooks"
    id_field = "playbook_id"


class RegimeMethodMapStore(JsonCardStore[RegimeMethodMap]):
    card_type = RegimeMethodMap
    default_subdir = "regime_method_map"
    id_field = "regime"


def _required_fields(card_type: Type[Any]) -> list[str]:
    if card_type is MethodCard:
        return ["method_id", "method_name", "source_type", "source_refs"]
    if card_type is MacroCard:
        return ["macro_id", "title", "source_type", "source_refs"]
    if card_type is StrategyPlaybook:
        return ["playbook_id", "method_id", "name", "compatible_regimes"]
    if card_type is RegimeMethodMap:
        return ["regime"]
    return []


def _missing_value(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False
