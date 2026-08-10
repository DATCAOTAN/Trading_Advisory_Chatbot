# Trading Chatbot Target Architecture

**Status:** LOCKED TARGET ARCHITECTURE  
**Purpose:** Canonical north-star architecture for the Trading Advisory Chatbot  
**Scope:** Semantic understanding, mode/policy resolution, strategy completion, deterministic proposal generation, mode-specific trade setup, recurring signal/re-entry semantics, Draft/Candidate lifecycle, confirmation/mandate authority, execution boundaries, post-entry lifecycle, position read models, conversational position management, provenance, recovery, and product acceptance.  

> This document defines the intended final product architecture. It does **not** claim that every component described here is already implemented.
>
> A new coding-agent session should be able to understand the intended final trading chatbot architecture from this document without access to the conversation in which it was designed.

>
> **Locked mode-UX clarification:** `human_confirmed_live` is **trade-centric**: every new trade instance requires a fresh deterministic Draft/Candidate and explicit per-trade confirmation. `autonomous_live` is **strategy/mandate-centric**: the user explicitly completes the strategy and confirms a bounded Standing Mandate; while that mandate remains valid, each new eligible signal creates a fresh internally generated Draft/Candidate with fresh evidence and recalculated Entry/SL/TP/Risk/Volume, without per-trade human confirmation. Mode never grants authority by itself, and autonomous recurring entry must obey an explicit deterministic re-entry/re-arm policy.

---

## 1. Authority and interpretation rules

Use this precedence when working on the repository:

```text
1. Explicit user instruction
2. AGENTS.md
3. Current approved sprint/task requirements
4. This locked target architecture
5. TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md
6. docs/engineering/SPRINT_CHANGELOG.md
7. General agent defaults
```

For **current implementation truth**:

```text
SOURCE + TESTS + GIT
    >
current-state documentation
    >
older architecture/history notes
```

Mandatory interpretation:

```text
LOCKED TARGET
= desired final architecture and behavior.

VERIFIED CURRENT
= behavior proven by current source/tests/Git.

PLANNED / REMAINING
= gap between current and target.
```

Never present target-only behavior as already implemented.

Do not change the locked target merely because current code is incomplete. If current source/tests prove a material incompatibility with this architecture, report the conflict before changing architecture.

---

## 2. Product objective

The final system is not merely:

```text
question -> answer
```

and not merely:

```text
signal -> place order -> stop
```

The intended product lifecycle is:

```text
UNDERSTAND
    -> COMPLETE
    -> ANALYZE
    -> PROPOSE
    -> REVIEW
    -> AUTHORIZE
    -> EXECUTE
    -> OBSERVE
    -> MANAGE
    -> EXPLAIN
    -> RECONCILE
    -> RETAIN HISTORY
```

The same chatbot should support:

```text
knowledge questions
market-data questions
technical-analysis questions
mixed macro + market questions
strategy questions
trade instructions
partial trade instructions
editable trading forms
human-confirmed workflows
autonomous-mandate workflows
position status queries
P/L queries
trade-history queries
trade provenance/explanations
position-management proposals
post-entry lifecycle observation
reconciliation and recovery
```

---

## 3. Core architectural principles

The architecture is governed by these principles:

```text
ONE universal semantic entry
ONE canonical semantic authority
NO domain reparses arbitrary raw language independently
SMALL compositional intent taxonomy
TYPED semantic artifacts
DETERMINISTIC context resolution
CAPABILITY routing instead of keyword routing
DETERMINISTIC policy/calculation/permission/execution
REUSE existing domain core
BROKER state is authoritative for broker truth
JOURNALS preserve durable provenance
FAIL CLOSED on uncertainty at authority boundaries
```

Additional product invariants:

```text
missing child != fabricated default
LLM suggestion != user-confirmed fact
requested mode != execution authority
Draft != order
Candidate != confirmation
confirmation != broker permission
Standing Mandate != unrestricted autonomy
LLM != broker state authority
UI != semantic authority
UI != execution authority
```

---

# PART I — UNIVERSAL SEMANTIC ARCHITECTURE

## 4. Universal ingress

Every meaningful user message passes through the same semantic entry.

```text
USER MESSAGE
    |
    v
UNIVERSAL INTENT / SEMANTIC GATE
    |
    +-----------------------------+
    |                             |
    v                             v
SOCIAL / TRASH              MEANINGFUL REQUEST
cheap bounded exit                |
                                  v
                      StructuredSemanticInterpreter
                                  |
                                  v
                         Pydantic v2 boundary
                                  |
                                  v
                      StructuredSemanticResult
                                  |
                                  v
                       ResolvedSemanticState
                                  |
                                  v
                              QueryPlan
```

No trading UI, market-data module, RAG component, execution module, or position-management component may independently become a second arbitrary-language semantic parser.

---

## 5. Structured semantic trust boundary

The untrusted structured LLM output crosses a Pydantic v2 trust boundary.

Target shape:

```text
Existing LLM provider
      |
      v
strict structured output
      |
      v
Pydantic v2 validation
      |
      v
StructuredSemanticResult
      |
      v
custom deterministic context resolver
      |
      v
ResolvedSemanticState
      |
      v
QueryPlan
```

Pydantic owns only schema/shape validation at the untrusted semantic boundary.

Pydantic does **not** become the architecture owner and does not require wholesale conversion of downstream domain models.

---

## 6. Canonical intent families

The target intent taxonomy remains small and compositional:

```text
SOCIAL
SYSTEM
OUT_OF_SCOPE
KNOWLEDGE
MARKET_DATA
ANALYSIS
STRATEGY
TRADE_LIFECYCLE
POSITION_MANAGEMENT
CONVERSATION
```

Intent means **user purpose**.

Do not turn every action, symbol, indicator, timeframe, missing field, or blocker into a new intent.

Examples:

```text
BUY / SELL
= action or direction, not primary intent.

RSI / EMA / MACD
= entities/parameters, not intents.

M1 / H1
= timeframe fields, not intents.

missing period
= unresolved field, not a new intent.

stale market data
= blocker/result, not intent.
```

---

## 7. Structured semantic artifact

Conceptual semantic artifact:

```text
StructuredSemanticResult
|
+-- primary_intent
+-- secondary_intents
+-- action
+-- direction
+-- subtype
+-- domain
+-- symbols
+-- indicators
+-- requested_data
+-- conditions
+-- context_references
+-- requested_mode
+-- account_scope
+-- explicit_fields
+-- unresolved_fields
+-- negated
+-- hypothetical
```

Example:

```text
User:
"hãy buy BTCUSD khi RSI14 M1 > 10"

StructuredSemanticResult
|
+-- primary_intent = POSITION_MANAGEMENT
+-- action         = OPEN_POSITION
+-- direction      = BUY
+-- symbols        = [BTCUSD]
+-- indicator
|    +-- RSI
|    +-- period = 14
|    +-- timeframe = M1
+-- condition
|    +-- subject = RSI
|    +-- operator = GREATER_THAN
|    +-- value = 10
+-- unresolved_fields = []
```

---

## 8. Semantic vs retrieval rewrite

Semantic interpretation and retrieval rewrite are separate responsibilities.

```text
raw message
    |
    v
semantic interpreter
    |
    v
Pydantic validated semantic artifact
    |
    v
ResolvedSemanticState
    |
    v
QueryPlan
    |
    +--> if retrieval required
            |
            v
      retrieval rewrite/query
```

Never parse retrieval rewrite output back into the canonical semantic meaning.

---

# PART II — CONTEXT RESOLUTION AND QUERYPLAN

## 9. Context precedence

The deterministic context resolver follows:

```text
CURRENT USER EXPLICIT
        >
VALID AUTHORITATIVE CONVERSATION CONTEXT
        >
USER-CONFIRMED SUGGESTION
        >
VALIDATED POLICY / SYSTEM DEFAULT
        >
UNRESOLVED
```

Rules:

```text
missing child does not erase siblings
current explicit value overrides inherited value
invalid/stale context cannot be inherited
LLM suggestion cannot silently become explicit context
operational defaults cannot masquerade as user semantics
```

---

## 10. ResolvedSemanticState

`ResolvedSemanticState` is the deterministic conversational state after applying precedence and context validity.

Responsibilities:

```text
preserve current explicit fields
inherit valid prior context only when allowed
record inherited provenance
retain unresolved children
reject conflicting or stale context
never grant execution authority
```

---

## 11. QueryPlan as internal semantic authority

After resolution:

```text
ResolvedSemanticState
        |
        v
QueryPlan
```

`QueryPlan` becomes the sole internal semantic authority for downstream planning.

Downstream modules should consume QueryPlan or typed projections derived from it rather than reparsing raw language.

---

# PART III — MODE, POLICY, AND AUTHORITY

## 12. Intent, action, mode, and authority are separate

```text
INTENT
= what the user is trying to accomplish.

ACTION
= what operation is being requested.

MODE
= operational policy governing how that action may proceed.

AUTHORITY
= whether the current action is actually permitted now.
```

Example:

```text
"hãy buy BTCUSD"

intent    = POSITION_MANAGEMENT / trade lifecycle purpose
action    = OPEN_POSITION
direction = BUY
mode      = human_confirmed_live

authority at Draft stage:
execution_allowed   = false
execution_authority = false
executable          = false
```

---

## 13. Mode resolution

Target deterministic mode semantics:

```text
INFORMATION / ANALYSIS
        |
        v
advisory_only
        |
        v
NO_EXECUTION


DIRECT TRADE COMMAND
BUY / SELL / OPEN / CLOSE / MANAGE
        |
        v
human_confirmed_live
        |
        v
CONFIRM_EVERY_TRADE


EXPLICIT AUTONOMOUS REQUEST
        |
        v
autonomous_live
        |
        v
STRATEGY + STANDING_MANDATE_SETUP
```

Representative cases:

```text
"RSI14 M1 BTCUSD hiện tại bao nhiêu?"
-> advisory_only

"phân tích BTCUSD"
-> advisory_only

"có nên buy BTCUSD không?"
-> advisory_only

"hãy buy BTCUSD"
-> human_confirmed_live

"buy BTCUSD khi RSI14 M1 > 10"
-> human_confirmed_live

"đóng position BTCUSD"
-> human_confirmed_live

"hãy tự động buy XAUUSD khi RSI14 M5 > 10"
-> autonomous_live through explicit strategy + Standing Mandate setup
```

Mode is derived from canonical typed semantics, not raw UI keyword parsing.

The UX/authority distinction is locked:

```text
human_confirmed_live
-> each NEW trade instance gets fresh evidence + fresh Draft/Candidate
-> USER CONFIRMS EACH TRADE

autonomous_live
-> user confirms strategy + bounded Standing Mandate setup/revision
-> each NEW eligible signal gets fresh evidence + fresh Draft/Candidate internally
-> NO per-trade user confirmation while action remains inside the valid mandate
```

For autonomous mode, the first user confirmation is **not** "permission for trade #1 that implicitly authorizes future trades." It is explicit confirmation of a bounded reusable strategy/mandate authority contract.

## 14. Mode never grants execution authority

At semantic, strategy-completion, Draft, Candidate-construction, or autonomous-evaluation stages:

```text
execution_allowed   = false
execution_authority = false
executable          = false
```

For `human_confirmed_live`:

```text
mode
+ fresh Draft/Candidate
+ exact per-trade human confirmation
+ deterministic final validation
= authority may proceed to the protected execution boundary
```

Every later trade instance requires a new Draft/Candidate and a new confirmation. A confirmation for trade N cannot authorize trade N+1.

For `autonomous_live`:

```text
mode
+ valid active Standing Mandate
+ exact strategy/symbol/action scope
+ fresh evidence
+ deterministic Candidate
+ mandate authorization
+ deterministic final validation
= authority may proceed to the protected execution boundary
```

No individual trade confirmation is required while the trade remains inside the already confirmed mandate, but the mandate must be revalidated for every trade instance and every management action.

Mode alone, LLM output alone, a previous trade confirmation, or a previous Draft never grants execution authority.

# PART IV — CAPABILITY ROUTING

## 15. Capability planning

QueryPlan drives existing capability planning:

```text
QueryPlan
    |
    v
ContextRequirementPlanner
    |
    v
ContextExecutionPlanner
    |
    v
CapabilityRegistry
    |
    v
Context Acquisition
```

No second capability planner is introduced.

---

## 16. Capability examples

```text
"RSI là gì?"
-> static knowledge / RAG
-> no market requirement

"RSI14 M1 BTCUSD hiện tại?"
-> market snapshot
-> OHLCV
-> technical snapshot
-> no knowledge retrieval unless required

"CPI ảnh hưởng vàng thế nào và RSI H1 hiện tại?"
-> macro / knowledge
-> economic context
-> market snapshot
-> OHLCV
-> technical snapshot
```

---

# PART V — TRADING PROJECTION

## 17. Trading projection

Trading semantics project deterministically from QueryPlan into existing trading-domain contracts.

```text
QueryPlan
    |
    v
Deterministic Trading Projection
    |
    v
ConversationalTradingRequest
    |
    v
ConversationalStrategyRequest
```

Arbitrary raw-language parsing is not allowed in the valid structured path.

Legacy raw parsers remain bounded fallback only until removed or further constrained.

---

## 18. Complete strategy example

```text
BUY BTCUSD
RSI14
M1
GREATER_THAN 10
```

Target projection:

```text
Action              OPEN_POSITION
Direction           BUY
Canonical symbol    BTCUSD
Broker symbol       BTCUSDm
Indicator           RSI
Period              14
Timeframe           M1
Condition           GREATER_THAN 10
Mode                human_confirmed_live
Confirmation        CONFIRM_EVERY_TRADE
Execution           NON_EXECUTABLE
```

---

# PART VI — PARTIAL SEMANTICS AND STRATEGY COMPLETION

## 19. Missing-field preservation

Example:

```text
User:
"hãy buy BTCUSD khi RSI > 10"
```

Known:

```text
BUY
BTCUSD
RSI
GREATER_THAN
10
human_confirmed_live
```

Missing:

```text
RSI period
timeframe
```

Required behavior:

```text
period    = UNRESOLVED
timeframe = UNRESOLVED
```

Forbidden behavior:

```text
RSI -> RSI14 automatically
missing timeframe -> M1,H1,H4 automatically
```

Operational monitoring profiles are not user semantic facts.

---

## 20. Strategy Completion architecture

Partial strategy semantics enter a completion experience rather than an invalid trading Draft.

```text
PARTIAL STRUCTURED STRATEGY
        |
        v
STRATEGY COMPLETION MODEL
        |
        v
EDITABLE COMPLETION FORM
        |
        +--> user edits semantic leaf values
        |
        +--> user accepts explicit suggestions
        |
        v
USER-CONFIRMED COMPLETE STRATEGY
```

The completion model owns **semantic strategy facts**, not concrete broker-sensitive trade parameters.

Typical completion fields include:

```text
indicator period
timeframe
condition/comparator
threshold
strategy-specific required semantic children
```

Completion fields must be editable **leaf fields**. A container path must not be presented as an editable scalar while a required child of that same container is also exposed.

Example:

```text
ALLOWED:
indicators[0].parameters.period
indicators[0].timeframe

NOT ALLOWED AS SIMULTANEOUS EDITABLE FIELDS:
indicators[0].parameters
indicators[0].parameters.period
```

Mode-specific continuation after strategy completion:

```text
human_confirmed_live
    -> Evidence
    -> deterministic Entry/SL/TP/Risk/Volume
    -> FULL EditableTradeDraft
    -> Candidate
    -> USER CONFIRM EACH TRADE

autonomous_live
    -> Autonomous Strategy + Standing Mandate Setup
    -> user confirms bounded strategy/mandate authority
    -> recurring signal loop
    -> fresh evidence + fresh Draft/Candidate PER eligible signal
    -> mandate authorization, no per-trade human confirmation
```

Strategy Completion is therefore never the final trade form and never the final autonomous authority contract.

## 21. Strategy Completion UI contract

For a partial trade instruction, the UI should expose recognized facts and only the missing semantic **leaf** fields.

Conceptual human-confirmed form:

```text
Trade Setup — Strategy Completion

Action
    BUY

Symbol
    BTCUSD / BTCUSDm

Indicator
    RSI

Period
    [14 suggested]
    [21]
    [Custom]

Timeframe
    [M1 suggested]
    [M5]
    [M15]
    [H1]
    [H4]
    [Custom]

Condition
    GREATER_THAN

Threshold
    10

Mode
    human_confirmed_live

Execution
    NON_EXECUTABLE

Entry
    WAITING_FOR_STRATEGY_COMPLETION

Stop Loss
    WAITING_FOR_STRATEGY_COMPLETION

Take Profit
    WAITING_FOR_STRATEGY_COMPLETION

Risk
    WAITING_FOR_STRATEGY_COMPLETION

Volume
    WAITING_FOR_STRATEGY_COMPLETION

[Apply Semantic Changes]
[Confirm Strategy Parameters]
```

This may be visually presented as a progressive trade builder, but the backend states remain separate:

```text
StrategyCompletionState
    !=
EditableTradeDraft
```

After all semantic prerequisites are complete in `human_confirmed_live`, the same UI may expand/transition into the full Draft containing fresh deterministic Entry/SL/TP/Risk/Volume.

For `autonomous_live`, partial semantics use the same leaf-level completion principles, but the next user-facing authority surface is **Autonomous Strategy + Standing Mandate Setup**, not a per-trade confirmation form.

No evidence calculation should be attempted while calculation-critical strategy prerequisites remain unresolved.

No Candidate should be created from a completion-only invalid state.

## 22. Suggestion semantics

The system may offer suggestions for missing semantic or policy fields, but suggestions must never silently become user facts or mutation authority.

LLM/system may suggest semantic fields such as:

```text
indicator period
timeframe
strategy explanation
```

For autonomous strategy/mandate setup, the system may also present bounded policy choices such as:

```text
stop policy
target policy
risk/sizing policy
re-entry/re-arm policy
management permissions
validity / trade-limit policy
```

However:

```text
LLM_SUGGESTION
    !=
USER_CONFIRMED_SUGGESTION
```

A suggestion cannot be consumed as authoritative user semantic input or mandate scope until accepted or explicitly edited by the user.

Concrete per-trade numeric values are a different category and must not be fabricated as semantic suggestions:

```text
Entry
SL
TP
risk amount
volume
```

Those values come from the existing deterministic evidence/proposal pipeline for each trade instance. They must be refreshed/recalculated rather than copied from a previous trade.

# PART VII — FIELD PROVENANCE

## 23. Canonical provenance classes

Fields should preserve source provenance whenever material to behavior:

```text
USER_EXPLICIT
USER_CONFIRMED_SUGGESTION
LLM_SUGGESTION
CONVERSATION_INHERITED
STRATEGY_POLICY
MARKET_CALCULATED
SYSTEM_CALCULATED
ACCOUNT_CALCULATED
```

Examples:

```text
BUY
source = USER_EXPLICIT

RSI
source = USER_EXPLICIT

period=14 after accepting a suggestion
source = USER_CONFIRMED_SUGGESTION

M1 after accepting suggestion
source = USER_CONFIRMED_SUGGESTION

SL
source = MARKET_CALCULATED / STRATEGY_POLICY

TP
source = SYSTEM_CALCULATED / STRATEGY_POLICY

volume
source = ACCOUNT_CALCULATED / SYSTEM_CALCULATED
```

---

# PART VIII — EVIDENCE ACQUISITION

## 24. Evidence gate

Only a sufficiently complete typed strategy may enter evidence acquisition.

```text
COMPLETE TYPED STRATEGY
        |
        v
Strategy Validation
        |
        v
StrategyDataPlan
        |
        v
Evidence Acquisition
```

Incomplete calculation prerequisites:

```text
-> evidence NOT_ATTEMPTED
-> precise unresolved blocker
-> no market/account/tick cascade caused solely by non-attempt
```

---

## 25. Market evidence

Target market evidence may include:

```text
bid
ask
spread
tick timestamp
point
tick size
tick value
minimum stop distance
volume minimum
volume maximum
volume step
contract size
OHLCV
completed-bar timestamps
freshness
history quality
ATR
swing high
swing low
technical indicator values
structure
volatility
```

---

## 26. Account and authority evidence

Target account/runtime evidence may include safe bounded forms of:

```text
account equity
free margin
account environment
account fingerprint
terminal capability
trade permission
operating mode
kill switches
mandate status
runtime safety status
```

Raw sensitive account identifiers must not become general logs or user-facing diagnostics.

---

# PART IX — DETERMINISTIC PROPOSAL ENGINE

## 27. Proposal ownership

LLM owns meaning and suggestions.

Deterministic backend owns authoritative broker-sensitive calculations.

```text
LLM
-> interpret
-> explain
-> suggest method

DETERMINISTIC CODE
-> calculate
-> validate
-> bind evidence
-> apply broker constraints
```

---

## 28. Entry calculation

Entry may be:

```text
USER_EXPLICIT
or
MARKET_CALCULATED
```

Market-calculated entry uses authoritative market evidence appropriate to direction/order type.

---

## 29. Stop-loss policies

Supported policy family:

```text
USER_EXPLICIT
ATR_MULTIPLE
RECENT_STRUCTURE
```

All resulting stop values remain deterministic and must satisfy broker and risk constraints.

---

## 30. Take-profit policies

Supported policy family:

```text
USER_EXPLICIT
REWARD_RISK_RATIO
RECENT_STRUCTURE
```

Target calculation remains deterministic.

---

## 31. Risk policy

Risk may come from:

```text
USER_EXPLICIT
CONFIGURED POLICY
DEMO DEFAULT
```

Risk policy must remain bounded and deterministically validated.

---

## 32. Volume / lot-size calculation

Volume may be:

```text
USER_EXPLICIT_VOLUME
or
ACCOUNT_RISK_FRACTION
```

Deterministic volume sizing consumes:

```text
account equity
risk fraction
entry price
stop distance
tick size
tick value
contract metadata
volume min/max/step
broker constraints
```

LLM-provided numeric volume is never execution authority by itself.

---

# PART X — EDITABLE TRADE DRAFT

## 33. EditableTradeDraft

The proposal engine produces an editable, persisted, non-executable Draft.

```text
EditableTradeDraft
|
+-- symbol
+-- broker symbol
+-- direction
+-- action
+-- entry rule
+-- entry reference
+-- stop
+-- target
+-- risk
+-- sizing / volume
+-- mode
+-- confirmation policy
+-- account scope
+-- evidence references
+-- blockers
+-- warnings
+-- revision
|
+-- execution_authority = false
+-- executable = false
```

---

## 34. Draft UI

Target full form:

```text
Editable Trade Draft

Symbol
Direction
Indicator / Strategy Rule
Timeframe
Condition / Threshold

Entry mode
Entry value

Stop method
Stop value
ATR multiplier

Target method
Target value
Reward/Risk ratio

Risk fraction
Requested volume
Calculated volume

Mode
Confirmation policy
Evidence status
Blockers
Warnings

[Apply Changes]
[Create/Confirm Candidate]
```

Applying changes creates an immutable new Draft revision.

Changing a Draft does not itself create authority.

---

# PART XI — CANDIDATE LIFECYCLE

## 35. Draft to Candidate

```text
EditableTradeDraft Revision N
        |
        | explicit product action
        v
Candidate C(N)
```

Candidate is immutable and bound to the exact Draft revision/evidence/strategy identity required by current contracts.

Candidate remains non-executable by itself.

---

## 36. Candidate review

```text
Candidate
    |
    +--> Review
    |
    +--> Confirm
    |
    +--> Reject
```

No auto-confirmation from the LLM.

---

# PART XII — HUMAN-CONFIRMED MODE

## 37. human_confirmed_live opening lifecycle

`human_confirmed_live` is **trade-centric**. Every new trade instance requires a fresh proposal and a fresh explicit user confirmation.

```text
DIRECT TRADE COMMAND
or persistent human-confirmed strategy signal
        |
        v
human_confirmed_live
        |
        v
Strategy Completion if required
        |
        v
fresh Market / Account / Broker Evidence
        |
        v
fresh deterministic Entry / SL / TP / Risk / Volume
        |
        v
FULL EditableTradeDraft #N
        |
        v
Candidate #N
        |
        v
USER CONFIRM #N
        |
        v
Pre-Submit Validation
        |
        v
READY / BLOCKED
```

User confirmation binds to an exact Candidate and does not grant blanket future authority.

If a human-confirmed strategy remains active and later produces another eligible signal:

```text
new signal
-> refresh evidence
-> build Draft #N+1
-> build Candidate #N+1
-> show the FULL form/review again
-> USER CONFIRM #N+1
```

Trade parameters are never copied as authority from the previous trade. Entry/SL/TP/Risk/Volume are recomputed or revalidated from the new signal's current evidence.

`CONFIRM_EVERY_TRADE` therefore means exactly that: trade #1 confirmation cannot authorize trade #2.

# PART XIII — AUTONOMOUS MODE

## 38. autonomous_live opening lifecycle

`autonomous_live` is **strategy/mandate-centric**, not per-trade-confirmation-centric.

Initial setup:

```text
EXPLICIT AUTONOMOUS REQUEST
        |
        v
autonomous_live
        |
        v
Strategy Completion if required
        |
        v
Autonomous Strategy Setup
        |
        v
Standing Mandate Setup / Review
        |
        v
USER CONFIRMS STRATEGY + MANDATE
        |
        v
MANDATE ACTIVE
```

The initial user confirmation authorizes a **bounded reusable mandate**, not merely the first trade.

A mandate may define or bind policy methods instead of freezing one trade's numeric values. Examples:

```text
strategy identity
symbol / direction / allowed opening actions
stop policy
target policy
risk / sizing policy
re-entry / re-arm policy
position limits
trade/day limits
loss limits
management permissions
account/environment
validity / expiry
```

Recurring opening lifecycle while the mandate is active:

```text
completed bar / approved evaluation point
        |
        v
deterministic strategy signal evaluation
        |
        v
NEW ELIGIBLE SIGNAL?
      /         \
    NO           YES
    |             |
 NO_ACTION        v
             refresh evidence
                  |
                  v
       deterministic trade proposal
                  |
                  v
              Draft #N
                  |
                  v
            Candidate #N
                  |
                  v
       Standing Mandate Authorization
                  |
                  v
          Pre-Submit Validation
                  |
                  v
          READY / BLOCKED
```

No per-trade user confirmation is required for Candidate #N when the action remains inside the exact active mandate and every deterministic gate passes.

Every trade instance is fresh:

```text
Strategy            -> REUSED while valid
Standing Mandate    -> REUSED while valid
Market evidence     -> REFRESHED per trade
Account evidence    -> REFRESHED per trade
Broker constraints  -> REVALIDATED per trade
Draft                -> NEW per trade
Candidate            -> NEW per trade
Entry                -> RECALCULATED / revalidated per trade
SL                   -> RECALCULATED / revalidated per trade
TP                   -> RECALCULATED / revalidated per trade
Risk amount          -> RECALCULATED / revalidated per trade
Volume               -> RECALCULATED / revalidated per trade
```

Autonomous mode never means copying the first trade's Draft into future trades and never means unrestricted LLM autonomy.

## 39. Standing Mandate boundaries

A mandate may constrain:

```text
strategy identity
symbol universe
direction / allowed opening action types
stop policy
target policy
risk / sizing policy
re-entry / re-arm policy
position-count bounds
trade/day bounds
loss bounds
management permissions
expiration/freshness
account/environment context
```

Every autonomous opening or management action must still pass deterministic policy and runtime gates.

### Re-entry / re-arm contract

Recurring autonomous strategies must define a deterministic rule for when a previously triggered condition becomes eligible to trigger again.

A default safe target behavior for persistent level conditions is conceptually:

```text
condition FALSE
-> ARMED

condition transitions / becomes TRUE
-> TRIGGER ONCE
-> create at most one eligible trade instance

condition remains TRUE
-> NO NEW ENTRY from the same continuously-active signal

trade closes while condition remains TRUE
-> WAIT_FOR_REARM

condition becomes FALSE again
-> REARMED

next eligible FALSE -> TRUE event
-> next trade may be proposed
```

Example:

```text
RSI14 M5 > 10

08:00 RSI=8   -> ARMED
08:05 RSI=12  -> signal #1, trade #1 may be proposed
08:10 RSI=15  -> no new entry from the same active level
trade #1 closes
08:15 RSI=13  -> WAIT_FOR_REARM, still no new entry
08:20 RSI=9   -> REARMED
08:25 RSI=11  -> signal #2, fresh Draft/Candidate #2 may be proposed
```

The exact implementation may use edge/cross semantics or another explicit supported policy, but it must prevent accidental re-entry loops caused by a continuously true level condition.

If the required re-entry, stop, target, sizing, or management policy is unresolved or outside the current mandate:

```text
BLOCK
-> request explicit mandate setup/revision
-> user confirms the revised mandate
```

The system must never silently expand mandate scope.

# PART XIV — PRE-SUBMIT VALIDATION

## 40. Pre-submit gate

Before any submission-capable boundary:

```text
Candidate integrity
Confirmation or mandate integrity
Draft revision integrity
Strategy identity
Market freshness
Account fingerprint
Account environment
Mode integrity
Permission checks
Risk limits
Volume limits
Stop/target validity
Terminal capability
Kill switches
Bridge availability
Idempotency
```

Result:

```text
BLOCKED
or
READY
```

For repository acceptance and development, preserve explicit safety policy such as DEMO/NON_EXECUTABLE where required by the approved sprint.

---

# PART XV — EXECUTION BOUNDARY

## 41. Execution lifecycle

Conceptual lifecycle:

```text
READY
    |
    v
Protected Execution Request
    |
    v
Host Bridge Trust Boundary
    |
    v
Broker Submission
    |
    +--> RESULT_REJECTED
    |
    +--> RESULT_UNKNOWN
    |
    +--> RESULT_CONFIRMED
```

No automatic retry for unknown broker outcome unless a separate proven reconciliation contract explicitly permits it.

---

## 42. Execution trust boundaries

```text
Application src/
    X direct MetaTrader5 import

Application
    |
    v
HTTP bridge client
    |
    v
Host-side bridge
    |
    v
Independent bridge validation
    |
    v
MetaTrader5 / broker
```

The bridge never trusts app-side validation alone.

---

# PART XVI — POST-ENTRY POSITION LIFECYCLE

## 43. Trade does not end after submission

A confirmed broker result transitions into lifecycle supervision.

```text
BROKER_ACCEPTED
    |
    v
Lifecycle Supervisor
    |
    +--> ORDER_ACTIVE
    +--> POSITION_OPEN
    +--> POSITION_PARTIALLY_REDUCED
    +--> POSITION_CLOSED
    +--> BROKER_REJECTED
    +--> RECONCILIATION_REQUIRED
    +--> INCONSISTENT
```

Opening a position is the start of the post-entry lifecycle, not the end of the chatbot workflow.

---

## 44. Lifecycle Supervisor responsibilities

```text
periodic broker snapshot
execution-journal reconciliation
lifecycle-journal persistence
account-fingerprint validation
active-order discovery
active-position discovery
recent-deal discovery
discrepancy detection
state transitions
health/status reporting
fail-closed recovery state
```

Lifecycle Supervisor is deterministic infrastructure, not an LLM agent.

---

# PART XVII — POSITION READ MODEL

## 45. PositionReadModel

Post-entry conversational queries need a canonical read model.

```text
Broker Snapshot
+
Execution Journal
+
Lifecycle Journal
+
Draft/Candidate Provenance
+
Strategy Provenance
        |
        v
PositionReadModel
```

Target fields:

```text
open positions
pending orders
current P/L
realized P/L
entry price
current price
SL
TP
volume
open time
close time
lifecycle state
strategy reference
entry reason
exit reason
Draft reference
Candidate reference
confirmation / mandate reference
execution reference
```

The read model must consume authoritative runtime/journal data, not LLM memory.

---

# PART XVIII — CONVERSATIONAL POSITION QUERIES

## 46. Read-only query family

Representative user questions:

```text
"đang có lệnh nào mở?"
"BTCUSD đang lời hay lỗ?"
"lệnh này lời bao nhiêu?"
"SL TP hiện tại?"
"volume của lệnh này?"
"entry của lệnh này?"
"lệnh BTCUSD mở lúc nào?"
"lịch sử hôm nay?"
"lệnh nào vừa đóng?"
"tổng P/L hôm nay?"
"tại sao vào lệnh này?"
```

Flow:

```text
User message
    |
    v
Structured Semantic
    |
    v
POSITION_MANAGEMENT / MARKET_DATA / ANALYSIS
    |
    v
Read-only position capabilities
    |
    v
PositionReadModel
    |
    v
Answer
```

No confirmation is required because no broker mutation occurs.

---

# PART XIX — TRADE HISTORY

## 47. Historical read model

Closed trades remain queryable.

```text
POSITION_CLOSED
    |
    v
Historical Trade Record
```

History can be assembled from authoritative sources such as:

```text
execution journal
lifecycle journal
broker orders/deals history
Draft/Candidate provenance
management journal
```

---

# PART XX — TRADE PROVENANCE

## 48. Full provenance chain

```text
User Message
    |
    v
Structured Semantic Result
    |
    v
ResolvedSemanticState
    |
    v
QueryPlan
    |
    v
Strategy Identity
    |
    v
Evidence Bundle
    |
    v
Editable Draft Revision
    |
    v
Candidate
    |
    v
Human Confirmation
OR
Standing Mandate Authorization
    |
    v
Pre-Submit Artifact
    |
    v
Protected Execution Reference
    |
    v
Broker Order / Position
    |
    v
Lifecycle Observations
    |
    v
Management Actions
    |
    v
Final Close / Deal
    |
    v
Historical Trade Record
```

---

## 49. Explanation queries

Examples:

```text
"tại sao vào lệnh này?"
-> strategy + signal + evidence + Draft + Candidate + authorization

"tại sao SL thay đổi?"
-> previous protection + proposed protection + reason + evidence + authorization

"tại sao đóng lệnh?"
-> exit condition + lifecycle state + management decision + authorization
```

LLM may explain the retrieved provenance but may not invent missing provenance.

---

# PART XXI — HUMAN-CONFIRMED POSITION MANAGEMENT

## 50. Management operations

Target management operation family:

```text
CANCEL_PENDING_ORDER
MODIFY_POSITION_PROTECTION
PARTIAL_CLOSE
CLOSE_POSITION
```

No position-volume increase is implicitly allowed by a close/reduction workflow.

---

## 51. human_confirmed_live management flow

```text
POSITION_OPEN / ORDER_ACTIVE
        |
        v
User or analysis requests management
        |
        v
Management Proposal Form
        |
        v
USER CONFIRM
        |
        v
Deterministic Validation
        |
        v
Controlled Management Service
        |
        v
Host Bridge
        |
        v
Broker Mutation
        |
        v
Lifecycle Supervisor
        |
        v
Updated Position State
```

Every mutation is individually confirmed in `human_confirmed_live`.

---

## 52. Management form

Conceptual UI:

```text
Management Proposal

Target position/order
Current lifecycle state
Current volume
Current SL
Current TP

Requested / Proposed:
new SL
new TP
resulting volume
close amount

Reason
Evidence
Warnings
Blockers

[Edit]
[Confirm Management Action]
[Reject]
```

---

# PART XXII — AUTONOMOUS POSITION MANAGEMENT

## 53. Autonomous monitoring continues after entry

A trade instance does not consume or destroy the standing strategy/mandate. While the mandate remains valid, the system continues to supervise the current trade and, after the trade closes and the re-entry policy re-arms, may evaluate future independent signals.

Post-entry management:

```text
Standing Mandate
      |
      v
POSITION_OPEN
      |
      v
Lifecycle Supervisor
      |
      v
Strategy / Exit / Protection Evaluation
      |
      v
Autonomous Management Proposal
      |
      v
Mandate + Policy Validation
      |
      +--> BLOCKED
      |
      +--> ALLOWED
              |
              v
      Controlled Management
              |
              v
          Host Bridge
              |
              v
           Broker
              |
              v
      Lifecycle Supervisor
```

After closure:

```text
POSITION_CLOSED
      |
      v
preserve history / provenance
      |
      v
re-entry policy state
      |
      +--> WAIT_FOR_REARM
      |
      +--> ARMED when reset condition is satisfied
              |
              v
       next eligible signal
              |
              v
       fresh Draft/Candidate
```

There is no copy-forward of the previous trade's concrete Entry/SL/TP/Risk/Volume.

## 54. Autonomous management authority

LLM is never enough.

```text
LLM suggestion
      |
      X
cannot independently mutate broker
```

Authority requires:

```text
Standing Mandate
+
Deterministic Policy
+
Current Lifecycle State
+
Current Broker Evidence
+
Account Binding
+
Risk Limits
+
Freshness
+
Kill Switch State
+
Bridge Validation
```

---

# PART XXIII — MANAGEMENT STATE ELIGIBILITY

## 55. State-to-operation mapping

```text
ORDER_ACTIVE
    |
    +--> CANCEL_PENDING_ORDER

POSITION_OPEN
    |
    +--> MODIFY_POSITION_PROTECTION
    +--> PARTIAL_CLOSE
    +--> CLOSE_POSITION

POSITION_PARTIALLY_REDUCED
    |
    +--> MODIFY_POSITION_PROTECTION
    +--> PARTIAL_CLOSE
    +--> CLOSE_POSITION

POSITION_CLOSED
    |
    v
NO FURTHER MUTATION
    |
    v
HISTORICAL QUERY ONLY
```

Any discrepant, stale, ambiguous, mismatched, or inconsistent lifecycle state fails closed.

---

# PART XXIV — FALLBACK ARCHITECTURE

## 56. Single-authority fallback rule

The invalid semantic path must never create a competing semantic authority.

Forbidden split-brain behavior:

```text
same raw user message
    |
    +--> general RAG interpretation
    |
    +--> independent UI raw trading parser
    |
    +--> conflicting Draft
```

Target:

```text
Structured Semantics
       |
       +---------------------------+
       |                           |
       v                           v
     VALID                       INVALID
       |                           |
       v                           v
AUTHORITATIVE PATH         BOUNDED FALLBACK ONLY
       |                           |
       |                      trade-like?
       |                       /      \
       |                     yes       no
       |                      |         |
       |                      v         v
       |                 Completion   General
       |                   State      Fallback
       |
       +--> COMPLETE
       |       |
       |       v
       |    Evidence
       |
       +--> PARTIAL
               |
               v
        Strategy Completion
```

---

## 57. Bounded fallback rules

When structured semantics is invalid/unavailable:

```text
legacy fallback may classify narrowly
legacy fallback may fail closed
legacy fallback may produce a completion/blocking state
legacy fallback must not fabricate missing strategy fields
legacy fallback must not become the general language-understanding authority
legacy fallback must not silently elevate execution authority
legacy fallback must not create a domain-invalid Draft merely because a raw parser found one keyword
```

---

# PART XXV — UI ARCHITECTURE

## 58. Thin UI principle

Target UI shape:

```text
tab_chatbot.py
raw input
    |
    v
orchestrator / universal ingress
    |
    v
semantic/domain result
    |
    v
presentation only
```

UI must not independently:

```text
parse arbitrary intent
resolve strategy semantics
invent missing parameters
resolve symbols as semantic authority
calculate SL/TP/volume business rules
decide mode as authority
grant permission
perform broker mutation
```

---

## 59. Dynamic form selection

The UI selects forms based on canonical typed state:

```text
KNOWLEDGE / ANALYSIS
-> answer view

PARTIAL TRADING STRATEGY
-> Strategy Completion Form

COMPLETE TRADING STRATEGY
-> Editable Trade Draft

CANDIDATE
-> Candidate Review Card

HUMAN MANAGEMENT REQUEST
-> Management Proposal Form

AUTONOMOUS MANDATE SETUP
-> Standing Mandate Form

POSITION QUERY
-> Position/History read view
```

---

# PART XXVI — OBSERVABILITY AND JOURNALING

## 60. Durable artifact families

The target system should retain the minimum durable artifacts needed for:

```text
semantic provenance
Draft provenance
Candidate provenance
confirmation / rejection
mandate authorization
pre-submit validation
execution correlation
lifecycle observation
management correlation
reconciliation
historical explanation
```

Sensitive details remain redacted or protected according to repository security rules.

---

## 61. Evaluation consistency

Evaluation/review artifacts should consume canonical runtime artifacts whenever possible.

They must not become execution authority.

A trade-like completion request should not be mislabeled as static explanation merely because a provider boundary failed upstream.

Avoid introducing another arbitrary raw-language detector solely for evaluation.

---

# PART XXVII — FAILURE AND RECOVERY

## 62. Fail-closed outcomes

Representative blockers/results:

```text
semantic invalid
semantic prerequisite unresolved
unsupported indicator
unsupported timeframe
market data stale
spread policy failure
account mismatch
account environment mismatch
permission denied
kill switch engaged
lifecycle state stale
broker target ambiguous
bridge unavailable
unknown broker outcome
journal corruption
reconciliation required
```

Failures are results/blockers, not semantic intents.

---

## 63. Unknown broker outcome

```text
SUBMISSION_STARTED
      |
      v
broker outcome unavailable
      |
      v
RESULT_UNKNOWN
      |
      v
RECONCILIATION_REQUIRED
```

Never blindly retry an unknown broker mutation.

---

# PART XXVIII — GLOBAL SAFETY INVARIANTS

## 64. Semantic safety

```text
LLM never grants execution authority
missing semantic values are not fabricated
valid siblings survive missing children
valid structured result is not overwritten by weaker fallback
```

---

## 65. Trading safety

```text
Draft != executable
Candidate != confirmation
confirmation != final broker permission
Standing Mandate != unrestricted autonomy
account context must bind correctly
freshness must be valid
risk/volume constraints remain deterministic
kill switches remain authoritative
idempotency remains enforced
```

---

## 66. Execution safety

```text
src/ does not directly own MetaTrader5 access
host bridge remains final broker trust boundary
bridge independently validates protected inputs
no automatic retry of unknown broker mutation
no implicit real-account activation
```

For development/acceptance, preserve approved DEMO/NON_EXECUTABLE restrictions and do not interpret this target document as permission to activate real-money execution.

---

# PART XXIX — THREE MODE END-TO-END ARCHITECTURE

## 67. advisory_only

```text
Understand
-> Resolve semantics
-> Plan capabilities
-> Acquire read-only evidence
-> Analyze
-> Explain
-> Query market/account/positions/history
-> NO broker mutation
```

---

## 68. human_confirmed_live

```text
Understand
-> Complete Strategy if needed
-> wait for / receive eligible trade opportunity
-> refresh Evidence
-> Deterministic Proposal
-> FULL Editable Draft #N
-> Candidate #N
-> User Confirm #N
-> Pre-Submit Gates
-> Controlled Execution Boundary
-> Lifecycle Supervisor
-> Position Read Model
-> Management Proposal
-> User Confirm each mutation
-> Controlled Management
-> Lifecycle Supervisor
-> History / Provenance
```

If another eligible trade opportunity appears later:

```text
NEW SIGNAL
-> NEW evidence
-> NEW Draft #N+1
-> NEW Candidate #N+1
-> SHOW FULL FORM AGAIN
-> NEW USER CONFIRMATION
```

No previous trade confirmation authorizes the next trade.

## 69. autonomous_live

```text
Understand explicit autonomous request
-> Complete Strategy if needed
-> Autonomous Strategy Setup
-> Standing Mandate Setup / Review
-> USER CONFIRMS STRATEGY + MANDATE ONCE
-> Mandate ACTIVE
-> completed-bar / approved evaluation loop
-> deterministic signal evaluation
-> re-entry/re-arm gate
-> fresh Evidence for each eligible signal
-> fresh Deterministic Proposal
-> fresh Draft #N
-> fresh Candidate #N
-> Mandate Authorization
-> Pre-Submit Gates
-> Controlled Execution Boundary
-> Lifecycle Supervisor
-> Strategy / Exit / Protection Monitoring
-> Autonomous Management Proposal
-> Mandate + Deterministic Policy Validation
-> Controlled Management
-> Lifecycle Supervisor
-> Position Closed / History / Provenance
-> re-entry state waits for reset
-> next eligible signal creates Draft/Candidate #N+1
```

No per-trade user confirmation is required while the action remains inside the active mandate.

The mandate is reusable; concrete trade parameters are not:

```text
strategy / mandate -> persist while valid
Entry / SL / TP / Risk / Volume -> refreshed/recalculated per trade
```

If the next action requires policy or authority not covered by the current mandate, fail closed and request an explicit mandate revision.

# PART XXX — FULL END-TO-END DIAGRAM

## 70. Canonical product flow

```text
USER
 |
 v
UNIVERSAL SEMANTIC ENTRY
 |
 v
STRUCTURED SEMANTIC LLM
 |
 v
PYDANTIC V2
 |
 v
RESOLVED SEMANTICS
 |
 v
QUERYPLAN
 |
 +---------------------------------------+
 |                                       |
 v                                       v
MODE / POLICY                        CAPABILITIES
 |                                       |
 |                              Requirement Planner
 |                                       |
 |                              Execution Planner
 |                                       |
 |                              Capability Registry
 |                                       |
 +-------------------+-------------------+
                     |
                     v
               DOMAIN PROJECTION
                     |
          +----------+----------+
          |                     |
          v                     v
      COMPLETE               PARTIAL
          |                     |
          |                     v
          |               STRATEGY COMPLETION
          |                     |
          |               user confirm/edit
          |                     |
          +----------+----------+
                     |
                     v
              COMPLETE STRATEGY
                     |
          +----------+-----------+
          |                      |
          v                      v
 human_confirmed_live        autonomous_live
          |                      |
          |                AUTONOMOUS STRATEGY
          |                 + MANDATE SETUP
          |                      |
          |                USER CONFIRMS
          |                BOUNDED MANDATE
          |                      |
          |                      v
          |                RECURRING SIGNAL LOOP
          |                      |
          |                re-entry / re-arm gate
          |                      |
          +----------+-----------+
                     |
                     v
              ELIGIBLE TRADE INSTANCE
                     |
                     v
               REFRESH EVIDENCE
                     |
                     v
         DETERMINISTIC PROPOSAL
          Entry / SL / TP / Risk / Volume
                     |
                     v
            FRESH EDITABLE DRAFT #N
                     |
                     v
              FRESH CANDIDATE #N
                     |
          +----------+-----------+
          |                      |
          v                      v
 HUMAN CONFIRM #N          MANDATE VALIDATION
          |                      |
          +----------+-----------+
                     |
                     v
                 PRE-SUBMIT
                     |
                     v
          CONTROLLED EXECUTION
                     |
                     v
              LIFECYCLE SUPERVISOR
                     |
                     v
                POSITION OPEN
                     |
             +-------+-------+
             |               |
             v               v
          READ MODEL      MANAGEMENT
             |               |
             |        +------+-------+
             |        |              |
             |        v              v
             |   HUMAN CONFIRM   MANDATE VALIDATION
             |        |              |
             |        +------+-------+
             |               |
             |               v
             |      CONTROLLED MANAGEMENT
             |               |
             +-------+-------+
                     |
                     v
              LIFECYCLE SUPERVISOR
                     |
                     v
               POSITION CLOSED
                     |
                     v
             HISTORY / PROVENANCE
                     |
          +----------+-----------+
          |                      |
          v                      v
 human strategy may         autonomous strategy
 await next signal          enters WAIT_FOR_REARM
 and show FULL form         then next eligible signal
 again                      creates NEW Draft/Candidate
```

The full product flow intentionally reuses the same deterministic evidence, proposal, Candidate, execution, lifecycle, read, and management boundaries in both modes. The difference is the authority model and recurring UX, not separate trading engines.

# PART XXXI — ACCEPTANCE BEHAVIOR FAMILIES

## 71. Product acceptance families

The architecture should support a representative acceptance set covering at least:

```text
1. Social greeting / bounded early exit
2. System-capability question
3. Static indicator explanation
4. Static strategy concept
5. Current market price
6. Current spread
7. Current technical indicator
8. Mixed macro + market analysis
9. Strategy analysis only
10. Direct BUY command -> human_confirmed_live
11. Direct SELL command -> human_confirmed_live
12. Direct CLOSE command -> human_confirmed_live
13. Direct MANAGE command -> human_confirmed_live
14. Explicit autonomous command -> autonomous_live
15. Partial strategy: missing indicator period
16. Partial strategy: missing timeframe
17. Partial strategy: both missing
18. Leaf-only completion fields; no editable parent container duplication
19. Complete strategy
20. User-confirmed suggestion
21. User edits suggested field
22. Conversation inheritance
23. Current user overrides inherited context
24. Unsupported symbol/timeframe/indicator
25. Stale market data
26. Provider unavailable / structured provider invalid
27. Bounded fallback with no split semantic authority
28. Deterministic Entry/Stop/Target/Risk/Volume proposal
29. Draft revision editing
30. Candidate creation and blocked-Draft gating
31. Candidate confirmation / rejection / mismatch
32. Pre-submit blocked by freshness/account/kill switch
33. Duplicate/idempotent opening request
34. Broker-result confirmed/rejected/unknown
35. RESULT_UNKNOWN -> reconciliation, no retry
36. Open-position query
37. Pending-order query
38. Current P/L / position detail / SL/TP query
39. Trade-history / why-entered / why-exited query
40. Cancel-pending management
41. Modify-protection management
42. Partial-close management
43. Full-close management
44. Human-confirmed management requires exact per-action confirmation
45. Human-confirmed recurring signal creates NEW full Draft/Candidate and asks again
46. Autonomous Strategy + Standing Mandate setup
47. Autonomous mode without valid mandate cannot mutate
48. Autonomous mandate validation by strategy/symbol/action/account/limits
49. Autonomous trade instance refreshes evidence and recalculates Entry/SL/TP/Risk/Volume
50. Autonomous trade #2 does not reuse trade #1 Draft values as authority
51. Autonomous continuously-true level condition does not re-enter repeatedly
52. Autonomous re-arm after reset allows the next independent signal
53. Mandate expiry/revocation blocks future openings
54. Mandate revision required for unresolved/out-of-scope stop/target/risk/re-entry policy
55. Autonomous post-entry protection management
56. Autonomous partial/full close management
57. Autonomous pending-order cancellation
58. Read-only queries remain read-only while autonomous mode is active
59. Ambiguous/stale target fails closed
60. Security/redaction + singular bridge mutation boundary + no implicit real-account activation
```

A final exact 60-question product acceptance suite may vary in wording, but must cover these bounded behavior families without sentence-specific patches.

For recurring autonomous acceptance, use deterministic fixtures rather than creating real broker trades merely to exercise re-entry.

## 72. Acceptance dimensions

Each acceptance case should be evaluated across relevant dimensions:

```text
SEMANTIC
CONTEXT
MODE
CAPABILITIES
DATA / EVIDENCE
ANSWER
UI / FORM
DOMAIN RESULT
AUTHORITY
NO FABRICATION
PROVENANCE
SAFETY
```

Do not call the product architecture closed solely because unit tests pass. Final closure requires representative end-to-end runtime/browser acceptance on the final implementation.

---

# PART XXXII — IMPLEMENTATION GUIDANCE

## 73. Reuse-before-create

Before adding a component:

```text
search existing responsibility
reuse existing service/model/store/journal/policy
extend coherent contract
avoid duplicate planners/parsers/authority layers
```

Likely existing responsibilities to reuse include semantic interpretation, QueryPlan, context requirement/execution planning, CapabilityRegistry, strategy evidence, Draft/Candidate lifecycle, confirmation, pre-submit validation, lifecycle supervision, and controlled management.

---

## 74. Do not over-engineer the target

The target architecture is comprehensive but does not imply one class/file per box.

Do not mechanically create:

```text
new framework
new agent graph
new generic workflow engine
new parser stack
new policy framework
new registry
new package tree
```

unless current source demonstrates a concrete need.

---

## 75. Framework boundary

Locked framework decision:

```text
Use Pydantic v2 at the untrusted semantic structured-output boundary.

Do NOT introduce LangGraph, LangChain, PydanticAI, Instructor,
OpenAI Agents SDK, or another agent framework as architecture owner.
```

Frameworks/helpers do not own product architecture.

---

# PART XXXIII — CURRENT VS TARGET WORK RULE

## 76. Required coding-agent workflow

When implementing against this target:

```text
1. Read AGENTS.md
2. Read this architecture
3. Read current handoff/changelog
4. Inspect Git state
5. Inspect current source/tests
6. Identify first actual target gap
7. Fix the smallest shared boundary
8. Test the bounded behavior family
9. Preserve safety and existing working behavior
10. Update handoff/changelog after verified sprint work
```

Never infer current implementation status solely from this document.

---

# PART XXXIV — FINAL LOCKED SUMMARY

## 77. Locked target in one view

```text
USER MESSAGE
    |
    v
UNIVERSAL SEMANTIC ENTRY
    |
    v
STRUCTURED SEMANTIC INTERPRETER
    |
    v
PYDANTIC V2 TRUST BOUNDARY
    |
    v
RESOLVED SEMANTIC STATE
    |
    v
QUERYPLAN
    |
    +--> MODE / POLICY
    |
    +--> CAPABILITY PLANNING
    |
    v
DOMAIN CORE
    |
    +--> KNOWLEDGE / ANALYSIS / MARKET READ
    |
    +--> TRADING PROJECTION
              |
              +--> PARTIAL -> STRATEGY COMPLETION FORM
              |
              +--> COMPLETE STRATEGY
                         |
                 +-------+--------+
                 |                |
                 v                v
        human_confirmed_live   autonomous_live
                 |                |
                 |          STRATEGY + MANDATE SETUP
                 |                |
                 |          USER CONFIRMS MANDATE
                 |                |
                 |          RECURRING SIGNAL LOOP
                 |                |
                 |          RE-ENTRY / RE-ARM GATE
                 |                |
                 +-------+--------+
                         |
                         v
                      EVIDENCE
                         |
                         v
               DETERMINISTIC PROPOSAL
               Entry / SL / TP / Risk / Volume
                         |
                         v
                    FRESH DRAFT #N
                         |
                         v
                  FRESH CANDIDATE #N
                         |
                  +------+-------+
                  |              |
                  v              v
          HUMAN CONFIRM #N   MANDATE VALIDATION
                  |              |
                  +------+-------+
                         |
                         v
                     PRE-SUBMIT
                         |
                         v
                CONTROLLED EXECUTION
                         |
                         v
                LIFECYCLE SUPERVISOR
                         |
                         v
                    POSITION STATE
                         |
                  +------+-------+
                  |              |
                  v              v
             READ MODEL      MANAGEMENT
                  |              |
                  |       +------+-------+
                  |       |              |
                  |       v              v
                  |  HUMAN CONFIRM   MANDATE VALIDATION
                  |       |              |
                  |       +------+-------+
                  |              |
                  |              v
                  |    CONTROLLED MANAGEMENT
                  |              |
                  +------+-------+
                         |
                         v
                LIFECYCLE SUPERVISOR
                         |
                         v
                  CLOSED / HISTORY
                         |
                         v
                     PROVENANCE
                         |
                  +------+-------+
                  |              |
                  v              v
             HUMAN MODE       AUTONOMOUS MODE
          next signal ->      WAIT_FOR_REARM ->
          NEW full Draft      next signal ->
          + USER CONFIRM      NEW Draft/Candidate
```

Locked responsibility split:

```text
LLM
-> meaning, interpretation, bounded suggestions, explanation

Pydantic
-> untrusted structured-output validation

ResolvedSemanticState
-> deterministic context precedence

QueryPlan
-> internal semantic authority

Capability planners/registry
-> required data and tools

Market/account services
-> runtime truth

Strategy/domain validation
-> domain validity

Strategy Completion
-> unresolved semantic leaf fields only

Autonomous Strategy + Standing Mandate Setup
-> user-confirmed reusable bounded strategy/policy authority

Proposal engine
-> deterministic fresh Entry/SL/TP/Risk/Volume for each trade instance

Draft
-> editable per-trade proposal; never reusable as authority for a later trade

Candidate
-> immutable per-trade candidate artifact

Human confirmation
-> exact per-trade/per-management-action authority in human_confirmed_live

Standing Mandate
-> bounded reusable authority in autonomous_live; revalidated for each action

Re-entry / re-arm policy
-> prevents repeated entries from one continuously-active signal and defines eligibility for the next independent trade

Pre-submit
-> deterministic final app-side gate

Lifecycle Supervisor
-> post-entry state observation/reconciliation

PositionReadModel
-> conversational state/history truth projection

Controlled Management
-> post-entry mutations

Host Bridge
-> final broker-mutation trust boundary

Broker
-> authoritative order/position/deal truth

Journals
-> durable provenance, reconciliation, and history
```

## 78. Non-negotiable invariants

```text
ONE canonical semantic authority
NO arbitrary UI semantic reparsing
NO fabricated missing semantic values
NO editable parent-container completion field when a child leaf is the actual unresolved requirement
NO LLM execution authority
NO Draft execution authority
NO Candidate self-confirmation
NO implicit autonomous authority
NO implicit real-account activation
NO blind retry after unknown broker mutation
NO broker truth from LLM memory
NO post-entry "fire and forget"

human_confirmed_live:
NO reuse of a previous trade confirmation for a new trade
NEW trade signal -> NEW evidence -> NEW Draft/Candidate -> NEW human confirmation

autonomous_live:
NO per-trade human confirmation inside a valid bounded mandate
NO reuse of previous trade's concrete Entry/SL/TP/Risk/Volume as authority
NEW eligible signal -> NEW evidence -> NEW Draft/Candidate -> mandate revalidation
NO repeated re-entry while one level condition remains continuously true unless an explicit supported policy says otherwise
NO mandate scope expansion without explicit user-confirmed mandate revision
```

The final product must remain conversational before, during, and after a trade lifecycle: it understands, proposes, obtains the required authority, observes resulting state, supports read-only position/history questions, supports bounded position management, preserves provenance, and remains fail-closed at every mutation boundary.

The two active trading modes intentionally share the same deterministic domain/execution infrastructure but differ in authority and recurring UX:

```text
human_confirmed_live
= trade-centric
= full fresh per-trade form/review
= confirm every trade

autonomous_live
= strategy/mandate-centric
= confirm strategy + bounded mandate setup/revision
= generate fresh per-trade proposals internally
= autonomous recurring entry/management only while every action stays inside mandate
```
