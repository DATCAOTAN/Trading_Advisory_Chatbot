# Data Storage and Cleanup

Evaluation governance uses local storage for safe review artifacts.

This page also classifies the trading workspace. A large or old file is not
automatically disposable. See the [project map](../PROJECT_CONTEXT_FOR_AI.md)
for the current production owners.

## Workspace Retention

| Path | Treatment |
| --- | --- |
| `src/`, `tools/`, `scripts/`, `src/metadata/` | Source, contracts, tests and operator CLIs. Check imports, dynamic references, fixtures and exports before deletion. |
| `docs/architecture/TRADING_CHATBOT_TARGET_ARCHITECTURE.md` | Locked product target; preserve. |
| Handoff, changelog, numbered architecture/demo notes | Current checkpoints and historical evidence; retain and distinguish current from historical claims. |
| `data/knowledge_repository/`, `data/knowledge_compiled/` | Knowledge sources, manifests and method/policy cards; preserve. |
| `data/qdrant_db/`, `data/knowledge_catalog/`, MongoDB/Redis volumes | Databases and durable/local state; no blanket cleanup. |
| `data/trading/execution_journal/`, `data/trading/protected_requests/` | Protected authority, idempotency, execution and recovery evidence; never delete to unblock trading. |
| `data/cache/embedding_cache.sqlite` | Reusable embedding cache, currently Git-tracked; preserve user changes and avoid paid re-embedding. |
| `data/research/mt5/` | Local historical research datasets/manifests; excluded from Git and Docker. Preserve provenance and checksums. |
| `.env`, local API-key files, `.agents/`, virtual environments | Local configuration, secrets, agent instructions and installed dependencies; preserve. |
| `Trading_Advisory_Chatbot.zip`, `logs/`, `tmp_debug_mt5_dry/` | Backup/diagnostics, potentially private; retain until a separate retention review. |
| `__pycache__/`, `*.pyc`, `.pytest_cache/` | Regenerable caches; safe to remove when no test process is using them. |

The 2026-11-01 housekeeping removed only the unreferenced root `diff.txt`
patch dump, duplicate `cmd_docker` command notes, and empty `log_terminal`.
Supported commands remain in the local runbook and Docker workflow. It also
removed regenerable code/test caches and the empty `tmp_preflight_diag/`.
No databases, protected journal records, backups, credentials, or dependencies
were deleted.

The follow-up source review removed 20 unreferenced exception-only modules,
the unused `src/services/trading/execution/receipt.py` alias, and two old root
experiments (`run_manual_test.py`, `test_reranker_manual.py`). Their collection
exclusions were removed from root `conftest.py`; hermetic provider guards remain.
Exception modules still exported by their packages were retained. Canonical
receipt models, supported manual MT5 CLIs, and existing regression cases remain.
The full default test collection passed with 3,771 tests and 156 subtests after
this deletion, using disabled execution defaults in the test process.
One legacy simulation test was also changed to inject a temporary journal after
the full suite exposed a local simulated-receipt append. The original local
journal was not truncated or rewritten; its one extra non-executed receipt was
retained. Later simulator verification left that journal unchanged.

## Docker Build Context

Git ignore rules do not control `COPY . .`. The `.dockerignore` additionally
excludes host key files, `.agents/`, the local ZIP, diagnostic folders,
`data/trading/`, `data/cache/`, and `data/knowledge_catalog/`.
Compose supplies local runtime data through the existing `./data:/app/data`
mount and supplies `.env` separately. These exclusions affect future builds;
they do not remove content from an already-built image. Never publish an old
image without reviewing its contents.

## Paths

- `data/evaluations/registry`: JSONL registry entries.
- `data/evaluations/versions`: dataset version manifests.
- `data/evaluations/reviews`: human review annotations, workflow states, annotated dataset versions, and exports.
- `data/evaluations/benchmarks`: golden cases and reports.
- `data/evaluations/quarantine`: quarantined corrupt or unsafe record excerpts with original hashes.
- `data/evaluations/diagnostics`: safe diagnostic reports.

## What Should Not Be Stored

These stores should not contain raw prompts, hidden/system prompts, full final answers, full raw documents, secrets, account data, broker data, MT5 data, order data, or executable trading instruction details.

## Safe Cleanup

For local experiments, prefer archiving or moving generated evaluation exports and reports instead of deleting source stores. If cleanup is needed, inspect files first and keep a backup of registry and review data.

Do not delete Qdrant collections as part of evaluation cleanup.

Do not delete `.env` or secret-bearing files through documentation workflows.


## Historical MT5 Research Data (Sprint 11A)

The operator narrowed Sprint 11 to data foundation only. No simulator dependency,
trade replay, strategy optimization, performance claim or deployment was added.
The retrospective BacktestEvaluationAgent contract is unchanged.

Host-only read command (UTC interval is inclusive start, exclusive end):

```powershell
.\venv\Scripts\python.exe -m tools.mt5_bridge.export_research_history `
  --symbol XAUUSD --broker-symbol XAUUSDm --timeframe M1 `
  --start 2026-11-04T15:00:00Z --end 2026-11-04T16:00:00Z
```

The exporter reuses MT5Client initialization/account checks and the bounded
host _call_mt5 wrapper. It requires connected DEMO identity before acquisition
and the same account afterward. It never logs/stores account identifiers or
credentials, changes the selected symbol, starts a Supervisor, or calls execution.
The explicit canonical/broker mapping must agree with repository configuration.
It uses copy_rates_range, not the live recent-bar endpoint. Native API timestamps
are UTC; date ranges are limited to 366 days and acquired in seven-day chunks.
Endpoint overlap is removed only for identical rows from different chunks;
duplicates within a chunk, conflicting overlaps and non-monotonic rows fail closed.

Each content-addressed research_dataset_* directory contains:

- data.jsonl: deterministic UTF-8 JSON lines. Bars retain time (epoch seconds),
  open/high/low/close (unrounded source float64), tick_volume, spread (broker points)
  and real_volume. The shared OHLCVBar/market quality checker is reused, without
  applying live freshness rejection to historical data.
- manifest.json: schema/id, explicit request, source, DEMO environment only,
  acquisition/coverage timestamps, counts/field coverage, exporter version,
  Git revision plus exporter-source checksum, dataset/manifest SHA-256 checksums,
  current contract snapshot/digits, terminal history limit, quality and limitations.
  Current tick value/contract metadata is explicitly not certified historical metadata.

Re-exporting unchanged data/configuration/source reuses the original artifact
without overwriting or appending rows. Changed data/source yields a new identity.
Incomplete existing directories fail loading instead of being automatically repaired
or deleted. Preserve them for separate operator review.

Quality classes:

- VERIFIED: required fields/finite positive prices/OHLC/spread/volume/timestamp
  checks pass, at least the requested warmup count (default 35), and every expected
  completed bar in the declared interval/session policy is present.
- PARTIAL: coverage gaps, calendar mismatch, acquisition failure or unverified tick
  completeness. Must be explicitly excluded from primary results or used only in
  a separately labeled sensitivity analysis.
- INSUFFICIENT_HISTORY: fewer rows than warmup, including empty/truncated history.
- INVALID: malformed, duplicate/conflicting/non-monotonic/out-of-range timestamps,
  missing/extra fields, invalid prices/OHLC, negative spread/volume or invalid quotes.
  Persistence rejects INVALID input; no replacement values/interpolation are generated.

load_dataset verifies checksums, identity, record count and recomputed quality.
Its default require_verified=True rejects non-primary datasets. as_market_snapshot
adapts only VERIFIED bars for existing offline indicator functions; it creates no
Candidate or execution evidence. Warmup count is a data prerequisite, not proof
of sufficient history for train/validation/holdout, monthly returns or profitability.

The explicit UTC_WEEKDAYS_CONSERVATIVE_V1 calendar excludes Saturday/Sunday
missing slots, but does not guess weekday maintenance, holidays or DST. Actual
weekend bars cause a calendar mismatch rather than being discarded. CONTINUOUS_UTC_V1
expects every bar. Neither is certified broker session history. Investigate gaps
against authoritative historical schedules before broad primary research; do not
label all gaps missing broker data or infer closures solely from their pattern.

Optional --kind ticks captures time/time_msc, Bid/Ask/Last and flags through
copy_ticks_range/COPY_TICKS_ALL. Requests are limited to six hours and a million
rows per chunk. Ask below Bid is invalid; FX Last=0 is allowed. Exporter v2 retains
distinct simultaneous ticks; identical within-chunk duplicates and conflicting ordered
millisecond groups across chunks fail closed. No missing ticks are invented.
Exporter v1 manifests retain their original validator for immutable reload.
Tick datasets remain PARTIAL because completeness is not independently certified.
Non-VERIFIED export returns a nonzero status even when its diagnostic dataset is saved.

Official API contracts:
[copy_rates_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py),
[copy_ticks_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py).

Real read-only acceptance on 2026-11-05: one hour on 2026-11-04 15:00-16:00Z
returned 60/60 M1 bars, VERIFIED; an unchanged re-export retained the same dataset.
2026-10-26 to 2026-11-02 returned 6,829 bars, PARTIAL: 430 absent weekday slots
in five intervals plus Sunday bars incompatible with the declared calendar.
Their cause is not inferred from the data. A one-minute tick request returned
338 records, PARTIAL due to unverified completeness. No P/L simulation was run.

### Sprint 11A.1 session and coverage reassessment

`research/session_coverage.py` provides a read-only `mt5-session-coverage/v2`
assessment, separate from the immutable export manifest. Explicit aware start/end
instants normalize to UTC; callers must resolve a session's historical timezone/DST
before supplying intervals. There is no guessed server offset or automatic holiday
calendar. Separate internal consistency from market-history completeness.
Historical evidence must identify its source and distinguish MARKET_CLOSED,
NO_QUOTES, QUOTING and TRADING. Trading hours alone do not prove quoting hours;
current snapshots do not certify historical sessions. Only fully covered bar slots
can be excused by closure/no-quote evidence. Conflicting evidence stays UNRESOLVED.
Missing quoted slots are SUSPECTED_HISTORY_GAP, not proven data loss; unsupported
slots are SESSION_HISTORY_UNAVAILABLE. No raw data, manifest or primary-loader
eligibility is changed by reassessment.

The ignored local report `data/research/sprint_11a1_coverage_evidence.json` records
all original checksums, three assessments, each original gap and adjacent bars,
sources/limitations and read-only tick replay evidence. On 2026-11-05 all original
manifests/data reloaded strictly and remained byte-identical. The hour retains
VERIFIED bar slots; the week and ticks remain PARTIAL. The original 430 missing
weekday slots are four 62-minute intervals (Oct 26-29, 20:58-22:00 UTC) plus
182 minutes on Friday Oct 30 after 20:58 UTC. Without assuming weekend closure,
the last absent interval extends to Sunday Nov 1 at 23:01 UTC. There are 59 genuine
Sunday bars from 23:01 through 23:59; they are not discarded.

[Broker DST notice](https://get.exness.help/hc/en-us/articles/31342732737180-Trading-Hours-Update-End-of-US-Daylight-Saving-Time-01-Nov-2026)
is independent trading-schedule evidence: US DST ends Nov 1; daily/Friday closure
and Sunday reopening shift one hour. It is not certified quote-session history for
this exact server/suffix. Its close-only boundary differs from the first observed
quote bars. All five original intervals remain SESSION_HISTORY_UNAVAILABLE,
with low confidence in exact cause; no closure is inferred from absent data.
Historical holiday exceptions and server offsets remain unknown.

Installed MT5 Python 5.0.5735 exposes no session API. The documented
[SymbolInfoSessionQuote](https://www.mql5.com/en/docs/marketinformation/symbolinfosessionquote)
and SymbolInfoSessionTrade use weekday/session indices, not historical dates.
No MQL5 script/bridge endpoint was added: a current snapshot cannot resolve this
historical evidence gap. Native terminal quote-session snapshot was not acquired.

The 338 ticks pass UTC/millisecond, Bid/Ask, ordering and duplicate checks.
Two repeats return identical 338 rows; a 30-second overlap matches 147 original
rows. No simultaneous millisecond or identical duplicate occurs in this sample.
Flags 134 preserve BID/ASK bits plus an uninterpreted bit 128. These checks prove
repeatability, not full tick completeness. Interval remains [15:00,15:01) UTC.

### Sprint 11B engine assessment (decision only; no installation)

| Option | Execution/data fit | Costs, sizing, MTF | Maintenance/license considerations |
| --- | --- | --- | --- |
| backtesting.py | Sequential OHLC strategy; not native full Bid/Ask tick replay. Same-bar SL/TP ordering remains ambiguous. | Constant relative spread, commission callable, margin; explicit units-to-lots mapping needed. Reuse existing indicators with completed-bar resampling. Slippage/variable spread need declared assumptions, not claimed broker fidelity. | Smallest initial integration; pandas/numpy/Bokeh dependency surface. Active published changelog. AGPL-3.0; review pinned version/license before approval. |
| Backtrader | Event-driven feeds, tick/timeframe support and orders; feed support alone does not prove exact Bid/Ask execution. OHLC intrabar ambiguity still exists. | Commission schemes/multipliers, fixed/relative slippage, native multi-timeframe/replay. Contract/lot/quote fill rules require explicit adaptation and tests. | More broker/feed setup. Core largely self-contained; published 1.9.78.123 is old, target-Python compatibility untested. GPL-3.0. |
| vectorbt | Array/Numba portfolio simulation and order functions; good for parameter sweeps, not a native MT5 broker replay. | Fees/slippage/size controls; explicitly align completed MTF inputs and lot units. Stop ordering/quote semantics require deliberate modeling. | Larger dependency and compilation surface, more custom fidelity work. Apache-2.0 plus Commons Clause, not unrestricted Apache. |
| Repository reuse | Existing dataset integrity, market models, indicators and typed strategy semantics. BacktestEvaluationAgent is observation-only, not a fill engine. | Reuse pure calculations; no production adapter, authority, Candidate or broker mutation. | No new dependency for data checks; writing a new matcher is explicitly not recommended. |

Assessment sources: [backtesting.py API](https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html),
[MTF example](https://kernc.github.io/backtesting.py/doc/examples/Multiple%20Time%20Frames.html),
[Backtrader slippage](https://www.backtrader.com/docu/slippage/slippage/),
[Backtrader repository](https://github.com/mementum/backtrader),
[vectorbt portfolio](https://vectorbt.dev/api/portfolio/base/).
Licenses: [backtesting.py](https://github.com/kernc/backtesting.py/blob/master/LICENSE.md),
[Backtrader](https://github.com/mementum/backtrader/blob/master/LICENSE),
[vectorbt](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md).

Recommendation (engineering inference): separately approve a pinned backtesting.py
version for a minimal offline OHLC baseline only, after licensing review and data
coverage resolution. Use verified dataset -> existing deterministic indicator/
strategy functions -> library simulation -> reproducible result with data checksum,
version, contract mapping and cost/ambiguity assumptions. Preserve the repository's
simple-average RSI/ATR definitions; do not substitute a library's Wilder default.
Reject or separately label bars with indeterminate SL/TP order. For tick-accurate
Bid/Ask research, this recommendation is insufficient: reassess Backtrader fidelity
before implementation. None of the engines has been installed or compatibility-tested.
Pin engine/dependencies and deterministic inputs; repeated output alone is not market
fidelity. These datasets support pipeline smoke checks, not monthly returns,
holdout statistics, optimization or live-strategy promotion.


Quarantine files preserve original hashes and safe excerpts. They can be reviewed separately from the source JSONL.
