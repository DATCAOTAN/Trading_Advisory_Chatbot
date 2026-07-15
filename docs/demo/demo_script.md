# Demo Script

This script demonstrates the platform as an evidence-grounded advisory and review system. It should not be presented as a live trading bot.

## 1. Static Book Query

Ask:

```text
Al Brooks explains price action in what way?
```

Show that the answer uses static/book source references and does not trigger market agents for the book-only task.

## 2. Macro Report Query

Ask:

```text
Summarize the CPI report and key points.
```

Show macro/report source behavior and the advisory-only response boundary.

## 3. Market State Query

Ask:

```text
Analyze the current XAUUSD market state.
```

Show EvidenceBundle grounding, analytical agent context, compliance gate, and final answer artifact identity.

## 4. Multi-Intent Query

Ask:

```text
How does CPI affect XAUUSD, and what does Al Brooks say about price action?
```

Show two task scopes: market/macro and static/book. Confirm the book task does not inherit market symbol, market source refs, or market agents.

## 5. Safety Boundary Query

Ask a boundary request for a specific immediate order instruction.

Expected: the system must not output executable trading instructions. It should stay advisory and preserve `execution_allowed=false`.

## 6. Dashboard Review

Open Evaluation Dashboard. Show registry rows, detail panel, source refs, safety index, evaluation index, hashes, and chain view.

## 7. Persistence Reload

Use the persistence panel to save current evaluation records, load persisted records, and confirm the same request IDs and final answer hashes appear after reload.

## 8. Human Annotation

Add a safe annotation with bounded labels and a short redacted-safe note. Show workflow state and review history.

## 9. Analytics Report

Open Review Analytics. Show coverage, quality score, grounding issue rate, safety issue rate, task leakage rate, reason-code distribution, and dataset health label.

## 10. Golden Benchmark

Run:

```powershell
.\venv\Scripts\python.exe scripts\run_golden_benchmark.py --cases data\evaluations\benchmarks\golden_cases.v1.json --out data\evaluations\benchmarks\reports\latest.json
```

Show canonical cases passing and deliberate bad fixture behavior in tests.

## 11. Hardening Diagnostic

Open System Health / Recovery. Run validate-only health check and export a diagnostic report. Explain that recovery is non-destructive by default.
