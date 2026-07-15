# Data Flow

## 1. Normal Answer Flow

```mermaid
flowchart TD
  A["User Query"] --> B["QueryPlan"]
  B --> C["ContextRequirements"]
  C --> D["ContextAcquisitionExecutor"]
  D --> E["EvidenceBundle"]
  E --> F["Agent Runtime"]
  F --> G["Compliance Gate"]
  G --> H["FinalAnswerArtifact"]
```

## 2. Multi-Intent Flow

```mermaid
flowchart TD
  A["User Query"] --> B["QueryPlan"]
  B --> C1["task_1: market or macro"]
  B --> C2["task_2: static or book"]
  C1 --> D1["Market evidence and allowed agents"]
  C2 --> D2["Static/book evidence only"]
  D1 --> E["Final answer with task-scoped refs"]
  D2 --> E
```

## 3. Agent Handoff Flow

```mermaid
flowchart TD
  A["AgentExecutionPlan"] --> B["MarketContextAgent"]
  B --> C["StrategyAgent"]
  C --> D["RiskAgent"]
  D --> E["StrategyRiskConsistencyAgent"]
  E --> F["AgentHandoffContext"]
  F --> G["Compact prompt enrichment"]
```

## 4. Evaluation Artifact Flow

```mermaid
flowchart TD
  A["FinalAnswerArtifact"] --> B["JournalReviewRecord"]
  B --> C["BacktestEvaluationRecord"]
  C --> D["PaperTradingEvaluationRecord"]
  D --> E["EvaluationRegistry"]
```

## 5. Dashboard / Review Flow

```mermaid
flowchart TD
  A["EvaluationRegistry"] --> B["EvaluationDashboard"]
  B --> C["Table and Detail"]
  B --> D["Chain View"]
  B --> E["Replay View"]
  B --> F["Safe Export"]
```

## 6. Persistence / Reload Flow

```mermaid
flowchart TD
  A["EvaluationRegistryEntry"] --> B["EvaluationPersistenceStore"]
  B --> C["JSONL registry store"]
  B --> D["DatasetVersionManifest"]
  C --> E["Reloadable Dashboard"]
```

## 7. Human Annotation Flow

```mermaid
flowchart TD
  A["EvaluationRegistryEntry"] --> B["HumanReviewAnnotation"]
  B --> C["ReviewWorkflowState"]
  C --> D["AnnotatedDatasetVersion"]
  D --> E["Supervised Review Export"]
```

## 8. Analytics Flow

```mermaid
flowchart TD
  A["Registry Entries"] --> C["ReviewAnalyticsEngine"]
  B["HumanReviewAnnotations"] --> C
  D["Dataset Versions"] --> C
  C --> E["QualityMetricsReport"]
  E --> F["Dashboard Analytics View"]
```

## 9. Benchmark Flow

```mermaid
flowchart TD
  A["GoldenBenchmarkCase"] --> B["GoldenBenchmarkRunner"]
  B --> C["GoldenBenchmarkResult"]
  C --> D["GoldenBenchmarkReport"]
```

## 10. Hardening / Recovery Flow

```mermaid
flowchart TD
  A["Runtime / persisted / benchmark / dashboard artifacts"] --> B["SystemHardeningService"]
  B --> C["IntegrityReport"]
  C --> D["RecoveryPlan"]
  D --> E["Safe Recovery / Quarantine / Diagnostic Export"]
```
