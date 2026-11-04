# Trading Advisory Chatbot

A Streamlit workspace for evidence-grounded financial research and controlled
MT5 DEMO trading. The product joins natural-language understanding, knowledge
retrieval, deterministic trade proposals, operator authorization, execution,
and broker lifecycle observation.

## Start Reading Here

- [Project map](docs/PROJECT_CONTEXT_FOR_AI.md): responsibilities, main paths,
  and where to resume development.
- [Locked target architecture](docs/architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md):
  intended product and authority boundaries; not a claim that every target is verified.
- [Current handoff](TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md): implementation and
  verification checkpoints. Read the latest sections first.
- [Changelog](docs/engineering/SPRINT_CHANGELOG.md): historical verification records.
- [Local runbook](docs/operations/local_runbook.md),
  [bridge setup](docs/operations/mt5_bridge_setup.md), and
  [Docker workflow](docs/operations/docker_workflow.md): supported operations.

Older numbered architecture notes and demo/CV documents describe the advisory
subsystem and earlier milestones. They do not override the locked target,
current source, tests, or latest handoff.

## Product Modes

| Mode | Proposal and authorization |
| --- | --- |
| `advisory_only` | Research and analysis; does not execute trades. |
| `human_confirmed_live` | An editable Draft becomes a protected Candidate; each trade needs exact confirmation, final validation, and separate controlled submission. |
| `autonomous_live` | A completed strategy and bounded Standing Mandate govern completed-bar evaluation, deterministic proposals, and independently checked execution. |

Mode selection alone grants no execution permission. Operating mode is bound
to the MT5 account; strategies, mandates, Candidate provenance, and Supervisor
ownership also carry conversation scope. Broker exposure and risk remain shared
across conversations.

## Main Flows

```text
Streamlit -> RAGOrchestrator
  -> StructuredSemanticInterpreter -> Pydantic v2 validation
  -> resolved semantics -> QueryPlan -> authoritative context acquisition
     -> knowledge/evidence -> grounded research answer
     -> position_state_read -> PositionReadModel -> redacted account/trade state
     -> typed strategy/request -> completion -> EditableTradeDraft

human-confirmed:
  Draft -> Candidate -> exact confirmation -> final validation -> pre-submit
  -> controlled adapter -> authenticated host bridge -> broker result

autonomous:
  completed bars -> strategy evaluation/re-arm -> deterministic Draft/Candidate
  -> policy -> Standing Mandate -> final validation -> pre-submit
  -> controlled adapter -> authenticated host bridge -> broker result

broker result -> protected journal -> lifecycle/reconciliation -> next decision
```

LLMs interpret language and supply bounded reasoning. Deterministic services
own prices, SL/TP, sizing, freshness, policy, permissions, and execution.
EvidenceBundle remains the grounding authority for research answers.

Only the host-side MT5 bridge imports `MetaTrader5`. The application under
`src/` uses HTTP and shares the existing isolated production `order_send`
call-site. The bridge independently checks authentication, DEMO account,
request integrity, permissions, broker capability, and idempotency.

## Verified Checkpoint

Implementation commit `88f175f` (2026-08-14) completed one human-confirmed DEMO
submission through the production UI and bridge. The protected broker result
was `RESULT_CONFIRMED` (retcode `10009`), with exactly one submission, no retry,
and lifecycle `POSITION_OPEN` / `UNIQUE_POSITION_MATCH`.

Retained verification at that checkpoint: **3,769 tests and 156 subtests passed**,
203 focused tests, and 11 documentation tests. These are historical results,
not evidence that a current terminal, account, feed, or Supervisor is healthy.
Consult the latest handoff for subsequent changes.

## Local Startup

From the repository root in Windows PowerShell:

1. Use the existing virtual environment. For a new environment, install
   `requirements.txt`; the Windows bridge additionally needs `MetaTrader5` in
   its host Python environment. Copy `.env.example` only for first-time setup;
   preserve an existing `.env` and configure the chosen providers privately.
2. Open MT5 and log into the intended DEMO account. Start the bridge in a
   separate PowerShell window:

   ```powershell
   .\venv\Scripts\python.exe -m tools.mt5_bridge.server
   ```

3. Start the existing Docker services without rebuilding:

   ```powershell
   docker compose up -d --no-build
   docker compose ps
   ```

4. Open [Streamlit](http://localhost:8501/) and check health:

   ```powershell
   Invoke-WebRequest http://127.0.0.1:8765/health
   Invoke-WebRequest http://localhost:8501/_stcore/health
   ```

Docker calls the bridge through `http://host.docker.internal:8765`. Authenticated
POST endpoints require the matching local bridge token; see the bridge setup
guide. Starting services does not grant trading authority.

For ordinary Python/UI changes use `docker-compose restart app`. Rebuild only
when Dockerfile, dependency, or image requirements change. MinerU is an optional
build component; routine restarts do not reinstall it. See the Docker workflow
for configuration reloads and first-time image creation.

For shutdown, stop running Supervisors through the UI, use `docker compose stop`,
and stop the host bridge with `Ctrl+C`. Stopping the application does not close
broker positions or cancel broker orders.

## Repository Map

| Path | Responsibility |
| --- | --- |
| `src/app.py`, `src/ui/` | Streamlit Advisory, Operations, Evaluation, Settings; service-owned controls. |
| `src/orchestrator.py`, `src/services/semantic/` | Semantic ingress, typed resolution, capability routing and context acquisition. |
| `src/services/knowledge/`, `src/services/evidence/`, `src/services/agents/` | Ingestion, retrieval, evidence grounding, reasoning and evaluation. |
| `src/services/trading/market/`, `src/services/trading/reasoning/`, `src/services/trading/scoring/` | Broker mapping, market evidence, features and analytical context. |
| `src/services/trading/proposal/`, `src/services/trading/decision/` | Immutable Drafts, Candidates, policy, trigger/re-arm and autonomous coordination. |
| `src/services/trading/execution/mt5_live_adapter_pre_submit/` | Mode/mandate authority, final validation, protected pre-submit, adapter, lifecycle and reconciliation. |
| `src/services/trading/position_read_model.py` | Authoritative redacted positions, P/L, history and provenance. |
| `tools/mt5_bridge/` | Windows host terminal access and the isolated broker mutation boundary. |
| `scripts/` | Tests, ingestion, deterministic acceptance and operational CLIs. |
| `data/` | Knowledge inputs/fixtures plus local databases and protected runtime state; not disposable clutter. |

The older execution packages remain referenced by compatibility contracts,
exports, tests, or diagnostic CLIs. A familiar name or an old sprint number is
not proof that a module can be deleted.

## Verification and Data Safety

Use the project Python explicitly. Start with documentation checks for
documentation-only changes:

```powershell
.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q
```

See [testing guide](docs/operations/testing_guide.md) for focused/full regression
and deterministic benchmarks. Execution-enabled local settings can conflict
with offline acceptance tests; use process-local disabled permissions and
engaged kill switches for offline verification. Do not run live operational
CLIs as part of ordinary regression.

Real accounts remain hard-blocked. The default is `execution_allowed=false`;
Candidate/confirmation/pre-submit artifacts do not themselves grant permission.
`RESULT_UNKNOWN` prohibits automatic retry and requires reconciliation.

Keep `.env`, credentials, broker identifiers, and protected journals private.
Docker build exclusions are independent from Git ignore rules. Consult
[storage and cleanup](docs/operations/data_storage_and_cleanup.md) before
removing caches, databases, history, or diagnostics.
