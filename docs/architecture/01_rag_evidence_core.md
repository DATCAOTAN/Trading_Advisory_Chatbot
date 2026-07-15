# RAG / Evidence Core

The RAG/Evidence Core is the authority layer for answer grounding. It decides what evidence is needed, what evidence is available, whether evidence is sufficient, and whether the answer can safely proceed.

## Main Concepts

- QueryPlan: decomposes the user request into task-scoped intents.
- ContextRequirements: states what each task needs from evidence or context.
- ContextAcquisitionExecutor: gathers the required context using configured project sources.
- EvidenceBundle: carries retrieved passages, source metadata, coverage, and sufficiency information.
- EvidenceSelector: selects evidence for the answer context.
- EvidenceSufficiency: evaluates whether evidence is enough for a task.
- EvidenceCoverage: checks whether required topics are covered.
- TopicEvidenceBinding: binds topics to supporting evidence.
- AnswerContract: describes what the answer is expected to satisfy.
- ResponseGate: controls whether the system can answer or must fail safely.
- ClaimEvidenceValidator: checks final answer claims against evidence.
- AnswerCompleteness: validates final answer structure and completeness.
- Controlled Failure Gate: prevents unsupported confident answers.

## Evidence Principles

Correct source is not the same as correct passage. A source may be relevant while the selected passage still does not support a specific claim.

Evidence availability is not the same as answer completeness. The system can have evidence but still fail completeness when the final answer misses required structure, source references, or task coverage.

Topic presence is not the same as support strength. A topic can appear in retrieved text without providing enough support for a conclusion.

No fabricated sources are allowed. Source references must come from preserved evidence metadata.

Static/book and market/macro tasks are separated. A book concept task should not inherit market symbols, market source refs, or market agent outputs from a sibling task.

## Controlled Failure

When evidence is missing or insufficient, the system should explain the limitation rather than invent a source or overstate certainty. Controlled failure behavior is part of the safety model, not a runtime defect.

## Boundaries

The RAG/Evidence Core does not place trades, produce order instructions, tune retrieval during evaluation governance, or convert agent analysis into EvidenceItems. EvidenceBundle remains the grounding authority.
