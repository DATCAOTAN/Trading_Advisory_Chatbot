from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

@dataclass
class CoverageRequirement:
    topic_role: str
    required: bool
    description: str
    retrieval_descriptors: List[str]
    compatible_evidence_types: List[str] = field(default_factory=list)

@dataclass
class CoverageRefinementRequest:
    task_id: str
    original_query: str
    canonical_query: str
    refined_query: str
    missing_topics: List[str]
    topic_descriptions: Dict[str, str]
    retrieval_descriptors: List[str]
    previous_evidence_ids: List[str]
    previous_chunk_ids: List[str]
    previous_parent_ids: List[str]
    provenance_constraints: Dict[str, Any]
    candidate_pool_size: int
    target_novel_items: int
    attempt: int
    reason: str

@dataclass
class RefinementNoveltyResult:
    previous_evidence_ids: List[str]
    returned_evidence_ids: List[str]
    new_evidence_ids: List[str]
    repeated_evidence_ids: List[str]
    novelty_ratio: float

@dataclass
class CoverageRefinementResult:
    task_id: str
    execution_status: str  # COMPLETED_IMPROVED, COMPLETED_NO_IMPROVEMENT, COMPLETED_STILL_DEGRADED, COMPLETED_NO_NOVEL_EVIDENCE, COMPLETED_NOVEL_BUT_NO_COVERAGE_GAIN, FAILED, SKIPPED
    before_coverage_ratio: float
    after_coverage_ratio: float
    before_missing_topics: List[str]
    after_missing_topics: List[str]
    candidate_count: int
    compatible_candidate_count: int
    previous_evidence_count: int
    new_evidence_count: int
    repeated_evidence_count: int
    novelty_ratio: float
    coverage_gain: float
    coverage_improved: bool

@dataclass
class AnswerContract:
    task_id: str
    required_topics: List[str]
    optional_topics: List[str]
    constraints: List[str] = field(default_factory=list)

@dataclass
class AnswerCoverageValidationResult:
    status: str  # PASS, WARN, FAIL
    covered_topics: List[str]
    missing_topics: List[str]
    coverage_ratio: float
    warnings: List[str] = field(default_factory=list)

@dataclass
class AnswerCompleteness:
    format_status: str
    evidence_status: str
    coverage_status: str
    contract_status: str
    overall_status: str
    reason: Optional[str] = None
