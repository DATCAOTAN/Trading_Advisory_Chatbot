# Agent Runtime

The Generic Agent Runtime adds task-scoped analytical context after evidence acquisition. Agents are helpers for reasoning, not sources of evidence authority.

## Runtime Structures

- AgentExecutionPlan: describes which agents should run for which task.
- AgentTaskEnvelope: carries task input to an agent.
- AgentRuntimeRegistry: registers available agent runtimes.
- AgentDispatcher: dispatches task envelopes to agents.
- AgentResultEnvelope: wraps agent output with metadata.
- AgentResultValidator: validates bounded agent output shape.
- AgentResultAggregator: combines safe agent outputs.
- AgentHandoffContext: passes compact agent context to final answer synthesis.
- AgentPromptEnrichment: enriches the prompt with compact analytical context.

## Analytical Agents

The current analytical agent stack is:

```text
MarketContextAgent
-> StrategyAgent
-> RiskAgent
-> StrategyRiskConsistencyAgent
```

- MarketContextAgent: summarizes market context and task-specific conditions.
- StrategyAgent: forms advisory thesis context from allowed inputs.
- RiskAgent: reviews risk considerations without account sizing.
- StrategyRiskConsistencyAgent: checks whether strategy and risk analysis are internally consistent.

## Scope Rules

Agent outputs are analysis context, not EvidenceItems. The EvidenceBundle remains the grounding authority for source-backed claims.

Static/book tasks must not receive market agents. Multi-intent routing should keep a book concept task separate from a market or macro task.

No agent can enable execution. Agents must not create BUY/SELL commands, entry price, stop-loss, take-profit, lot size, position size, account-risk percent, MT5 payloads, or broker orders.

## Compression and Handoff

Agent Stack Compression keeps handoff context compact for final synthesis. It preserves task IDs, intent families, source references, and agent references while avoiding raw prompts and unnecessary payload bloat.
