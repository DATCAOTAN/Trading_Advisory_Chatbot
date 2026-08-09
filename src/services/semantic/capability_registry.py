from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_name: str
    service_name: str
    operation_name: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_type: str = ""
    cacheable: bool = False
    default_freshness_seconds: int = 0
    latency_class: str = "medium"
    cost_class: str = "low"
    dependencies: List[str] = field(default_factory=list)
    enabled: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "service_name": self.service_name,
            "operation_name": self.operation_name,
            "input_schema": dict(self.input_schema),
            "output_type": self.output_type,
            "cacheable": self.cacheable,
            "default_freshness_seconds": self.default_freshness_seconds,
            "latency_class": self.latency_class,
            "cost_class": self.cost_class,
            "dependencies": list(self.dependencies),
            "enabled": self.enabled,
        }


class CapabilityRegistry:
    """Describe available capabilities and the existing services behind them."""

    def __init__(self, capabilities: Optional[Dict[str, CapabilityDefinition]] = None):
        self._capabilities = capabilities or self._default_capabilities()

    def get(self, capability_name: str) -> Optional[CapabilityDefinition]:
        return self._capabilities.get(capability_name)

    def is_enabled(self, capability_name: str) -> bool:
        definition = self.get(capability_name)
        return bool(definition and definition.enabled)

    def all(self) -> Dict[str, CapabilityDefinition]:
        return dict(self._capabilities)

    def register(self, definition: CapabilityDefinition) -> None:
        self._capabilities[definition.capability_name] = definition

    @classmethod
    def default(cls) -> "CapabilityRegistry":
        registry = cls()
        for capability in registry.all().values():
            print(
                "[CapabilityRegistry] "
                f"capability={capability.capability_name} "
                f"service={capability.service_name} "
                f"operation={capability.operation_name} "
                f"enabled={str(capability.enabled).lower()}"
            )
        return registry

    @staticmethod
    def _default_capabilities() -> Dict[str, CapabilityDefinition]:
        capabilities = [
            CapabilityDefinition(
                capability_name="official_report",
                service_name="KnowledgeV3",
                operation_name="retrieval_adapter.retrieve",
                input_schema={"target": "event_type/title/organization"},
                output_type="RetrievedKnowledgeContext",
                cacheable=True,
                default_freshness_seconds=86400,
                latency_class="medium",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="static_knowledge",
                service_name="KnowledgeV3",
                operation_name="retrieval_adapter.retrieve",
                input_schema={"target": "concept/domain/subdomain"},
                output_type="RetrievedKnowledgeContext",
                cacheable=True,
                default_freshness_seconds=86400,
                latency_class="medium",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="market_knowledge",
                service_name="KnowledgeV3",
                operation_name="retrieval_adapter.retrieve",
                input_schema={"target": "market topic"},
                output_type="RetrievedKnowledgeContext",
                cacheable=True,
                default_freshness_seconds=86400,
                latency_class="medium",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="market_snapshot",
                service_name="LiveDataService",
                operation_name="get_live_price",
                input_schema={"symbol": "str"},
                output_type="MarketSnapshot",
                cacheable=False,
                default_freshness_seconds=60,
                latency_class="low",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="ohlcv",
                service_name="LiveDataService",
                operation_name="get_historical_candles",
                input_schema={"symbol": "str", "timeframe": "str", "limit": "int"},
                output_type="list[OHLCV]",
                cacheable=False,
                default_freshness_seconds=300,
                latency_class="medium",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="economic_event",
                service_name="LiveDataService",
                operation_name="get_economic_calendar",
                input_schema={"impact": "str"},
                output_type="list[EconomicEventContext]",
                cacheable=False,
                default_freshness_seconds=900,
                latency_class="medium",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="technical_snapshot",
                service_name="ExistingTechnicalSnapshotAdapter",
                operation_name="build",
                input_schema={"market_snapshot": "MarketSnapshot", "candles": "list"},
                output_type="dict",
                cacheable=False,
                default_freshness_seconds=300,
                latency_class="low",
                cost_class="low",
                dependencies=["ohlcv"],
            ),
            CapabilityDefinition(
                capability_name="position_read",
                service_name="PositionReadModelService",
                operation_name="read_from_query_plan",
                input_schema={"query_plan": "QueryPlan"},
                output_type="PositionReadModel",
                cacheable=False,
                default_freshness_seconds=90,
                latency_class="low",
                cost_class="low",
            ),
            CapabilityDefinition(
                capability_name="account_state",
                service_name="Unavailable",
                operation_name="",
                output_type="RiskSnapshot",
                enabled=False,
            ),
            CapabilityDefinition(
                capability_name="instrument_spec",
                service_name="Unavailable",
                operation_name="",
                output_type="dict",
                enabled=False,
            ),
            CapabilityDefinition(
                capability_name="stop_distance",
                service_name="UserInput",
                operation_name="",
                output_type="float",
                enabled=False,
            ),
            CapabilityDefinition(
                capability_name="risk_limit",
                service_name="Unavailable",
                operation_name="",
                output_type="dict",
                enabled=False,
            ),
        ]
        return {definition.capability_name: definition for definition in capabilities}
