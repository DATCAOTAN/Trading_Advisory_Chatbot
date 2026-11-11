"""Immutable research records. Callers supply trusted scope and evidence verification."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Callable, Literal, Protocol, TYPE_CHECKING, runtime_checkable

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, ValidationError, ValidationInfo, model_serializer, model_validator

from src.services.semantic.structured_semantics import ComputationalParameter, ComputationalSpecification, ResearchGoal, SpecText
from ..market.timeframes import SUPPORTED_TIMEFRAMES, timeframe_duration_seconds
from ..reasoning.strategy_evidence import ConversationalStrategyRequest, validate_strategy
from .historical_dataset import canonical_bytes, checksum, utc

if TYPE_CHECKING:
    from src.services.semantic.query_plan import QueryPlan


Ref = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")]
UtcTime = Annotated[datetime, BeforeValidator(utc)]
Origin = Literal["AI_RESEARCHED", "USER_DEFINED"]
Author = Literal["AI_SUGGESTED", "USER_AUTHORED"]
Decision = Literal["ACCEPTED_FOR_NEXT_RESEARCH_STAGE", "REJECTED"]
_PINNED_READINESS_REPLAY = object()


class _Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class ResearchScope(_Record):
    trading_scope: Annotated[str, Field(pattern=r"^trading_scope_[a-f0-9]{24}$")]
    # Use a trusted opaque account reference, never a broker login.
    account_ref: Annotated[str, Field(pattern=r"^account_[a-f0-9]{24,64}$")] | None = None


class BriefReference(_Record):
    request_id: Ref
    goal: ResearchGoal
    requested_mode: Literal["", "advisory_only", "human_confirmed_live", "autonomous_live"]
    account_scope: Literal["", "DEMO", "REAL"]
    symbols: tuple[Ref, ...]
    requested_sources: tuple[Ref, ...]
    missing_information: tuple[str, ...]
    field_sources: tuple[tuple[str, str], ...]


class EvidenceReference(_Record):
    source_ref: Ref
    evidence_ref: Ref
    kind: Literal["KNOWLEDGE", "MARKET_OBSERVATION", "MT5_TESTER", "HISTORICAL_MARKET_DATA"]
    stance: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT"]
    status: Literal["PENDING", "UNSUITABLE", "VALIDATED"] = "PENDING"
    data_quality: Ref = "UNKNOWN"
    evaluation_version: Ref | None = None
    window_start: UtcTime | None = None
    window_end: UtcTime | None = None

    @model_validator(mode="after")
    def check_evidence(self):
        if (self.window_start is None) != (self.window_end is None) or (
            self.window_start is not None and self.window_start >= self.window_end
        ):
            raise ValueError("RESEARCH_EVIDENCE_WINDOW_INVALID")
        if self.status == "VALIDATED" and (
            self.kind == "MT5_TESTER" or self.data_quality == "UNKNOWN" or not self.evaluation_version
            or (self.kind == "MARKET_OBSERVATION" and self.window_start is None)
        ):
            raise ValueError("RESEARCH_EVIDENCE_NOT_VALIDATABLE")
        return self


@runtime_checkable
class RevisionEvidenceVerifier(Protocol):
    def verify_revision(
        self, proposal: ResearchProposal, revision: ResearchRevision, item: EvidenceReference,
    ) -> bool: ...


EvidenceVerifier = Callable[[ResearchScope, EvidenceReference, str], bool] | RevisionEvidenceVerifier


def _read_strategy(value) -> ConversationalStrategyRequest:
    if isinstance(value, ConversationalStrategyRequest):
        value = value.as_dict()
    if not isinstance(value, dict):
        raise ValueError("RESEARCH_STRATEGY_INVALID")
    try:
        strategy = ConversationalStrategyRequest.from_dict(value)
        if canonical_bytes(value) != canonical_bytes(strategy.as_dict()):
            raise ValueError("noncanonical strategy")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("RESEARCH_STRATEGY_INVALID") from exc
    if not strategy.entry_rules or validate_strategy(strategy):
        raise ValueError("RESEARCH_STRATEGY_NOT_ESTABLISHED")
    return strategy


StrategySpec = Annotated[
    ConversationalStrategyRequest, BeforeValidator(_read_strategy),
    PlainSerializer(lambda strategy: strategy.as_dict(), return_type=dict),
]


class HistoricalEvaluationWindow(_Record):
    start: UtcTime | None = None
    end: UtcTime | None = None
    split: UtcTime | None = None
    session_policy: Literal["UTC_WEEKDAYS_CONSERVATIVE_V1", "CONTINUOUS_UTC_V1"] | None = None

    @model_validator(mode="after")
    def check_window(self):
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("RESEARCH_EVALUATION_WINDOW_INVALID")
        if self.split is not None and (
            self.start is None or self.end is None or not self.start < self.split < self.end
        ):
            raise ValueError("RESEARCH_IS_OOS_SPLIT_INVALID")
        return self


class ResearchSignalCondition(_Record):
    """Typed operands only; unknown operators/references remain unresolved, never parsed."""

    operator: Ref | None = None
    left: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    right: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    constants: tuple[Annotated[float, Field(allow_inf_nan=False)], ...] = Field(default=(), max_length=2)


class ResearchSignalRule(_Record):
    name: Ref
    action: Literal["ENTRY", "EXIT"]
    conditions: tuple[ResearchSignalCondition, ...] = Field(default=(), max_length=16)
    combination: Literal["ALL", "ANY"] | None = None
    timing: Ref | None = None
    evaluation_timeframe: Ref | None = None


class ResearchDevelopment(_Record):
    """Inert G1 specification plus research-design fields, never an executable strategy."""

    specification: ComputationalSpecification
    in_sample: SpecText | None = None
    out_of_sample: SpecText | None = None
    transaction_costs: tuple[ComputationalParameter, ...] = Field(default=(), max_length=12)
    evaluation_criteria: tuple[SpecText, ...] = Field(default=(), max_length=12)
    rejection_criteria: tuple[SpecText, ...] = Field(default=(), max_length=12)
    missing_information: tuple[SpecText, ...] = Field(default=(), max_length=12)
    historical_window: HistoricalEvaluationWindow | None = None
    signal_rules: tuple[ResearchSignalRule, ...] = Field(default=(), max_length=16)

    @model_serializer(mode="wrap")
    def preserve_legacy_identity(self, serialize):
        payload = serialize(self)
        if self.historical_window is None:
            payload.pop("historical_window", None)
        if not self.signal_rules:
            payload.pop("signal_rules", None)
        return payload

    @classmethod
    def from_editor_json(cls, payload: str):
        try:
            return cls.model_validate_json(payload)
        except ValidationError as exc:
            error = exc.errors(include_input=False, include_url=False)[0]
            reason = str(error.get("ctx", {}).get("error", ""))
            if reason in {"RESEARCH_EVALUATION_WINDOW_INVALID", "RESEARCH_IS_OOS_SPLIT_INVALID",
                          "UTC_AWARE_DATETIME_REQUIRED", "RESEARCH_HISTORICAL_WINDOW_NOT_ALIGNED"}:
                raise ValueError(reason) from None
            if error["loc"] and error["loc"][0] == "historical_window":
                raise ValueError("RESEARCH_HISTORICAL_WINDOW_INVALID") from None
            if reason == "RESEARCH_SIGNAL_RULE_NAME_CONFLICT" or (error["loc"] and error["loc"][0] == "signal_rules"):
                raise ValueError("RESEARCH_SIGNAL_RULE_DEFINITION_INVALID") from None
            raise ValueError("RESEARCH_SPECIFICATION_INVALID") from None
        except (ValueError, TypeError):
            raise ValueError("RESEARCH_SPECIFICATION_INVALID") from None

    @model_validator(mode="after")
    def check_authority(self):
        config = self.specification.configuration
        if config is not None and (
            config.strategy_origin not in {None, "AI_RESEARCHED"}
            or config.authorization_mode not in {None, "ADVISORY"}
            or config.adaptation_policy is not None
        ):
            raise ValueError("RESEARCH_SPECIFICATION_AUTHORITY_CONFLICT")
        window = self.historical_window
        if len({rule.name for rule in self.signal_rules}) != len(self.signal_rules):
            raise ValueError("RESEARCH_SIGNAL_RULE_NAME_CONFLICT")
        if window is not None:
            for requirement in self.specification.data_requirements:
                step = timeframe_duration_seconds(requirement.timeframe) if requirement.timeframe else 0
                if step and any(value.timestamp() % step for value in (window.start, window.split, window.end) if value):
                    raise ValueError("RESEARCH_HISTORICAL_WINDOW_NOT_ALIGNED")
        return self

    def review(self) -> dict:
        from src.services.semantic.query_plan import QueryPlanAssembler

        spec = self.specification
        required, conflicts = QueryPlanAssembler.computational_requirements(spec)
        missing = [*self.missing_information, *required]
        for name in ("entry", "exit"):
            if not getattr(spec, name):
                missing.append("specification." + name)
        for index, data in enumerate(spec.data_requirements):
            for field in ("dataset", "symbol", "timeframe", "lookback_bars", "warmup_bars", "completeness"):
                if getattr(data, field) is None:
                    missing.append(f"data_requirements[{index}].{field}")
            if data.usage != "RESEARCH_ONLY":
                missing.append(f"data_requirements[{index}].research_only_usage")
        for name in ("in_sample", "out_of_sample", "transaction_costs", "evaluation_criteria", "rejection_criteria"):
            if not getattr(self, name):
                missing.append(name)
        for index, cost in enumerate(self.transaction_costs):
            if cost.name is None or cost.value is None or cost.unit is None:
                missing.append(f"transaction_costs[{index}].name_value_unit")
        return {"status": "NEEDS_CLARIFICATION" if missing or conflicts or spec.conflicts else "NEEDS_REVIEW",
                "missing_information": list(dict.fromkeys(missing)), "conflicts": [*conflicts, *spec.conflicts],
                "unsupported": list(spec.unsupported), "data_status": "NOT_CHECKED",
                "execution_allowed": False, "runtime_status": "UNSUPPORTED_DYNAMIC_COMPUTATION"}


class ResearchContent(_Record):
    hypothesis: str = Field(default="", max_length=500)
    strategy: StrategySpec | None = None
    timeframes: tuple[Ref, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    limitations: tuple[Annotated[str, Field(max_length=240)], ...] = ()
    development: ResearchDevelopment | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_identity(self, serialize):
        payload = serialize(self)
        # Existing pinned R1 hashes must not change when this optional field is absent.
        if self.development is None:
            payload.pop("development", None)
        return payload

    @model_validator(mode="after")
    def check_content(self):
        if any(timeframe not in SUPPORTED_TIMEFRAMES for timeframe in self.timeframes):
            raise ValueError("RESEARCH_TIMEFRAME_INVALID")
        refs = {(item.source_ref, item.evidence_ref) for item in self.evidence}
        if len(refs) != len(self.evidence):
            raise ValueError("RESEARCH_EVIDENCE_CONFLICT")
        if self.strategy and self.timeframes and set(self.timeframes) != set(self.strategy.timeframes):
            raise ValueError("RESEARCH_TIMEFRAME_CONFLICT")
        return self

    def hypothesis_fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json", exclude={"evidence", "limitations"}))


def _fingerprint(value) -> str:
    return checksum(canonical_bytes(value))


def generate_research_hypothesis(brief: BriefReference, provider) -> ResearchContent:
    """One explicit suggestion call; the provider cannot supply evidence or authority."""
    properties = ResearchContent.model_json_schema()["properties"]
    schema = {"type": "object", "additionalProperties": False,
              "required": ["hypothesis", "timeframes", "limitations"],
              "properties": {name: properties[name] for name in ("hypothesis", "timeframes", "limitations")}}
    schema["properties"]["timeframes"] = {"type": "array", "items": {"type": "string", "enum": sorted(SUPPORTED_TIMEFRAMES)}}
    prompt = (
        "Propose ONE bounded, falsifiable historical research hypothesis for this canonical brief. "
        "Return only JSON with hypothesis (nonempty, at most 500 characters), timeframes (array), "
        "and limitations (array, each at most 240 characters). Use the brief's language. "
        "Specify an observable comparison and how it could be disproven, not a profitability promise. "
        "No research has run. Do not claim observed prices, statistics, experiments, returns or evidence. "
        "Preserve explicit constraints. Unknown risk, horizon or other missing facts stay unknown; "
        "identify missing prerequisites in limitations. Any proposed timeframe is an AI suggestion. "
        "Use only the exact supported timeframe enum tokens; use [] if no timeframe is justified. "
        "No strategy code, trading instruction, approval, evidence record or execution authority. JSON schema: "
        + canonical_bytes(schema).decode("utf-8") + " Brief: "
        + canonical_bytes(brief.model_dump(mode="json")).decode("utf-8")
    )
    raw = provider.complete(prompt, max_tokens=1200, temperature=0.2)
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 8192:
        raise ValueError("RESEARCH_HYPOTHESIS_INVALID")
    import json

    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {"hypothesis", "timeframes", "limitations"}:
        raise ValueError("RESEARCH_HYPOTHESIS_INVALID")
    try:
        content = ResearchContent.model_validate_json(raw)
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_url=False)[0]
        field = error["loc"][0] if error["loc"] and error["loc"][0] in payload else "content"
        # Schema-only diagnostics: never return input values, raw text or validator context.
        codes = {"string_too_long": "TOO_LONG", "string_type": "TYPE", "tuple_type": "TYPE",
                 "string_pattern_mismatch": "FORMAT", "value_error": "VALUE"}
        code = codes.get(error["type"], "SCHEMA")
        raise ValueError(f"RESEARCH_HYPOTHESIS_INVALID_{field.upper()}_{code}") from None
    if not content.hypothesis.strip():
        raise ValueError("RESEARCH_HYPOTHESIS_EMPTY")
    return content


def develop_research_strategy(proposal: ResearchProposal, provider) -> ResearchDevelopment:
    """One explicit provider suggestion, validated as inert G1/R1 content only."""
    prompt = (
        "Develop this saved research hypothesis into ONE testable, non-executable specification. "
        "Return ONLY JSON matching this schema: "
        + canonical_bytes(ResearchDevelopment.model_json_schema()).decode("utf-8")
        + " The specification object permits ONLY these keys: "
        + ", ".join(ComputationalSpecification.model_fields)
        + ". Put market/symbol/timeframe ONLY in data_requirements objects. Describe calculations in formula/steps, "
        "and declare derived outputs in data_requirements[].computations using the typed schema. "
        "fields contains raw MT5 bar fields or exact declared output names, never an undeclared indicator label. "
        "For registered indicators provide exact canonical indicator_id and explicit parameters, not defaults. "
        "For new formulas declare typed RAW_MT5/DERIVED inputs, output type, definition and total lookback/warmup "
        "only when known; otherwise leave unresolved. Do not infer parameters from a name or claim an implementation. "
        "Never add unrecognized top-level indicator keys. SL/TP rules belong in "
        "exit, sizing rules in management, not separate risk/stop_loss/take_profit/sizing fields. "
        "Use the root in_sample/out_of_sample strings for split scope, root transaction_costs as an array of "
        "name/value/unit parameter objects. All rule arrays contain STRINGS, never objects. "
        "Keep the entire response concise, below 3000 tokens. "
        "Use formula/steps, parameters, entry/exit, reentry/management and temporal_requirements for "
        "explicitly defined calculations and rules. Preserve custom formulas as inert text; list unsupported "
        "runtime requirements. Specify needed data fields, symbol, timeframe, lookback, warmup, completeness, "
        "RESEARCH_ONLY usage; never claim data is available. Specify chronological disjoint IS/OOS scopes, "
        "cost definitions/units and falsifiable evaluation/rejection criteria only when justified. "
        "Unknown values remain null or empty and must be listed in missing_information. No invented market "
        "observations, results, profitability, evidence or approval. Preserve the canonical goal constraints; "
        "risk/sizing budgets belong ONLY to the immutable brief, not new numeric parameter suggestions. "
        "SL/TP and sizing rules may reference those constraints, but never invent unknown risk or broker values. "
        "All new rules are AI suggestions, not confirmed user facts. Configuration may only be AI_RESEARCHED/ADVISORY "
        "with adaptation_policy=null, never execution permission. No code. Develop the current revision, "
        "preserving existing user edits unless explicitly identified as conflicting. Brief: "
        + canonical_bytes(proposal.brief.model_dump(mode="json")).decode("utf-8")
        + " Current revision: " + canonical_bytes(proposal.head.content.model_dump(mode="json")).decode("utf-8")
    )
    raw = provider.complete(prompt, max_tokens=5000, temperature=0.2)
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 48000:
        raise ValueError("RESEARCH_SPECIFICATION_INVALID")
    try:
        return ResearchDevelopment.model_validate_json(raw)
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_url=False)[0]
        field = error["loc"][0] if error["loc"] and error["loc"][0] in ResearchDevelopment.model_fields else "content"
        codes = {"string_too_long": "TOO_LONG", "tuple_type": "TYPE", "model_type": "TYPE",
                 "literal_error": "VALUE", "extra_forbidden": "EXTRA", "json_invalid": "JSON"}
        raise ValueError(f"RESEARCH_SPECIFICATION_INVALID_{field.upper()}_{codes.get(error['type'], 'SCHEMA')}") from None


class ResearchRevision(_Record):
    execution_allowed: Literal[False] = False
    revision_id: Ref
    parent_revision_id: Ref | None
    author: Author
    created_at: UtcTime
    content: ResearchContent
    content_fingerprint: str

    def evidence_status(self) -> str:
        statuses = {item.status for item in self.content.evidence}
        if not statuses:
            return "ABSENT"
        if "UNSUITABLE" in statuses:
            return "UNSUITABLE"
        return "PENDING" if "PENDING" in statuses else "VALIDATED"

    def review_readiness(self) -> str:
        if not self.content.hypothesis.strip() and self.content.strategy is None:
            return "DRAFT"
        return "READY_FOR_REVIEW" if self.evidence_status() == "VALIDATED" else "EVIDENCE_PENDING"


class ResearchReview(_Record):
    revision_id: Ref
    decision: Decision
    reviewed_at: UtcTime


def _revision(proposal_id, parent, author, now, content):
    fingerprint = _fingerprint(content.model_dump(mode="json"))
    return ResearchRevision(
        revision_id="revision_" + _fingerprint([proposal_id, parent, author, fingerprint]),
        parent_revision_id=parent, author=author, created_at=now,
        content=content, content_fingerprint=fingerprint,
    )


class ResearchProposal(_Record):
    schema_version: Literal["research-proposal/v1"] = "research-proposal/v1"
    execution_allowed: Literal[False] = False
    proposal_id: Ref
    scope: ResearchScope
    brief: BriefReference
    origin: Origin
    revisions: tuple[ResearchRevision, ...] = Field(min_length=1)
    reviews: tuple[ResearchReview, ...] = ()

    @classmethod
    def from_plan(
        cls, plan: QueryPlan, *, scope: ResearchScope, origin: Origin,
        content: ResearchContent, created_at: datetime, verify_evidence: EvidenceVerifier | None = None,
    ) -> ResearchProposal:
        brief = plan.constraints.get("research_brief")
        if (
            plan.primary_intent != "strategy_research_brief" or plan.requires_execution
            or plan.constraints.get("trading_scope") != scope.trading_scope
            or not isinstance(brief, dict) or brief.get("execution_allowed") is not False
            or brief.get("effective_mode") != "advisory_only"
            or brief.get("strategy_status") != "STRATEGY_NOT_ESTABLISHED"
            or brief.get("request_id") != plan.plan_id
        ):
            raise ValueError("RESEARCH_BRIEF_SCOPE_OR_CONTRACT_INVALID")
        reference = BriefReference(
            request_id=plan.plan_id, goal=ResearchGoal.model_validate(brief["goal"]),
            requested_mode=brief["requested_mode"], account_scope=brief["account_scope"],
            symbols=tuple(brief["symbols"]), requested_sources=tuple(brief["requested_sources"]),
            missing_information=tuple(brief["missing_information"]),
            field_sources=tuple(sorted(brief["field_sources"].items())),
        )
        author = "AI_SUGGESTED" if origin == "AI_RESEARCHED" else "USER_AUTHORED"
        proposal_id = cls._identity(scope, reference, origin, content)
        return cls.model_validate({
            "proposal_id": proposal_id, "scope": scope, "brief": reference, "origin": origin,
            "revisions": (_revision(proposal_id, None, author, created_at, content),),
        }, context={"scope": scope, "verify_evidence": verify_evidence})

    @staticmethod
    def _identity(scope, brief, origin, content):
        return "proposal_" + _fingerprint([
            scope.model_dump(mode="json"), brief.model_dump(mode="json"), origin,
            content.model_dump(mode="json"),
        ])

    @property
    def head(self) -> ResearchRevision:
        return self.revisions[-1]

    def _require_scope(self, scope: ResearchScope) -> None:
        if self.scope != scope:
            raise ValueError("RESEARCH_SCOPE_MISMATCH")

    def _verify(self, revision: ResearchRevision, verify_evidence: EvidenceVerifier | None) -> None:
        for item in revision.content.evidence:
            if item.status != "VALIDATED":
                continue
            if isinstance(verify_evidence, RevisionEvidenceVerifier):
                verified = verify_evidence.verify_revision(self, revision, item)
            else:
                verified = (
                    item.kind != "HISTORICAL_MARKET_DATA" and verify_evidence is not None
                    and verify_evidence(self.scope, item, revision.content.hypothesis_fingerprint())
                )
            if verified is not True:
                raise ValueError("RESEARCH_EVIDENCE_UNVERIFIED")

    @model_validator(mode="after")
    def check_history(self, info: ValidationInfo):
        context = info.context or {}
        if "scope" not in context:
            raise ValueError("RESEARCH_SCOPE_REQUIRED")
        self._require_scope(context["scope"])
        initial = self.revisions[0]
        if self.proposal_id != self._identity(self.scope, self.brief, self.origin, initial.content):
            raise ValueError("RESEARCH_PROPOSAL_ID_INVALID")
        if initial.author != ("AI_SUGGESTED" if self.origin == "AI_RESEARCHED" else "USER_AUTHORED"):
            raise ValueError("RESEARCH_ORIGIN_CONFLICT")
        parent = None
        for revision in self.revisions:
            if revision != _revision(self.proposal_id, parent.revision_id if parent else None,
                                     revision.author, revision.created_at, revision.content):
                raise ValueError("RESEARCH_REVISION_CHAIN_INVALID")
            if parent and (revision.created_at < parent.created_at or revision.content == parent.content):
                raise ValueError("RESEARCH_REVISION_CONFLICT")
            strategy = revision.content.strategy
            development = revision.content.development
            if development is not None and any(
                data.symbol is not None and self.brief.symbols and data.symbol not in self.brief.symbols
                for data in development.specification.data_requirements
            ):
                raise ValueError("RESEARCH_SPECIFICATION_SCOPE_CONFLICT")
            if strategy is not None and (
                strategy.trading_scope != self.scope.trading_scope
                or strategy.requested_mode != "advisory_only" or strategy.confirmation_policy != "NO_EXECUTION"
                or (self.brief.symbols and strategy.canonical_symbol not in self.brief.symbols)
                or (self.brief.account_scope and strategy.account_scope != self.brief.account_scope)
            ):
                raise ValueError("RESEARCH_STRATEGY_SCOPE_CONFLICT")
            if not context.get(_PINNED_READINESS_REPLAY):
                self._verify(revision, context.get("verify_evidence"))
            parent = revision
        positions = {revision.revision_id: i for i, revision in enumerate(self.revisions)}
        reviewed = set()
        for review in self.reviews:
            index = positions.get(review.revision_id)
            if index is None or review.revision_id in reviewed:
                raise ValueError("RESEARCH_REVIEW_CONFLICT")
            revision = self.revisions[index]
            if (
                review.reviewed_at < revision.created_at
                or (index + 1 < len(self.revisions) and review.reviewed_at > self.revisions[index + 1].created_at)
                or (review.decision == "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"
                    and revision.review_readiness() != "READY_FOR_REVIEW")
            ):
                raise ValueError("RESEARCH_REVIEW_INVALID")
            reviewed.add(review.revision_id)
        return self

    def revise(
        self, *, scope: ResearchScope, parent_revision_id: str, author: Author,
        content: ResearchContent, created_at: datetime, verify_evidence: EvidenceVerifier | None = None,
    ) -> ResearchProposal:
        self._require_scope(scope)
        revision = _revision(self.proposal_id, parent_revision_id, author, created_at, content)
        if any(prior.revision_id == revision.revision_id for prior in self.revisions):
            return self
        if parent_revision_id != self.head.revision_id:
            raise ValueError("RESEARCH_REVISION_CONFLICT")
        if content == self.head.content:
            return self
        return self._with_history(verify_evidence, revisions=(*self.revisions, revision))

    def review(self, *, scope: ResearchScope, revision_id: str, decision: Decision,
               reviewed_at: datetime, verify_evidence: EvidenceVerifier | None = None) -> ResearchProposal:
        self._require_scope(scope)
        if revision_id != self.head.revision_id:
            raise ValueError("RESEARCH_REVIEW_STALE")
        for existing in self.reviews:
            if existing.revision_id == revision_id:
                if existing.decision == decision:
                    return self
                raise ValueError("RESEARCH_REVIEW_CONFLICT")
        review = ResearchReview(revision_id=revision_id, decision=decision, reviewed_at=reviewed_at)
        return self._with_history(verify_evidence, reviews=(*self.reviews, review))

    def review_status(self, revision_id: str) -> str:
        if revision_id != self.head.revision_id:
            if any(item.revision_id == revision_id for item in self.revisions):
                return "SUPERSEDED"
            raise ValueError("RESEARCH_REVISION_NOT_FOUND")
        return next((item.decision for item in self.reviews if item.revision_id == revision_id),
                    self.head.review_readiness())

    def _with_history(self, verify_evidence, **changes) -> ResearchProposal:
        fields = {name: getattr(self, name) for name in type(self).model_fields}
        return type(self).model_validate(
            fields | changes, context={"scope": self.scope, "verify_evidence": verify_evidence},
        )

    def to_json(self) -> str:
        return canonical_bytes(self.model_dump(mode="json")).decode("utf-8")

    @classmethod
    def replay(cls, payload: str, *, scope: ResearchScope,
               verify_evidence: EvidenceVerifier | None = None) -> ResearchProposal:
        return cls.model_validate_json(payload, context={"scope": scope, "verify_evidence": verify_evidence})

    @classmethod
    def replay_pinned_for_readiness(cls, payload: bytes, *, scope: ResearchScope, snapshot_checksum: str) -> ResearchProposal:
        """Read recorded decisions from an independently pinned trusted export, not current data."""
        if checksum(payload) != snapshot_checksum:
            raise ValueError("RESEARCH_PROPOSAL_SNAPSHOT_STALE")
        try:
            return cls.model_validate_json(payload, context={"scope": scope, _PINNED_READINESS_REPLAY: True})
        except ValidationError as exc:
            error = exc.errors(include_input=False)[0].get("ctx", {}).get("error")
            reason = "RESEARCH_SCOPE_MISMATCH" if str(error) == "RESEARCH_SCOPE_MISMATCH" else "RESEARCH_PROPOSAL_SNAPSHOT_INVALID"
            raise ValueError(reason) from None
