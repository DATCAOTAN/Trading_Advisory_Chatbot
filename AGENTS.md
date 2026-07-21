# Trading Advisory Chatbot - Agent Instructions

## Instruction priority

Follow instructions in this order:

1. Explicit user instruction
2. This `AGENTS.md`
3. Current sprint requirements
4. `TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md`
5. General agent defaults
6. Optional external skills or methodologies

External skills, generic workflows, and coding methodologies must not override repository-specific instructions.

## Required reading

Before sprint-level, architecture-changing, execution-related, or multi-module work:

1. Read `AGENTS.md`.
2. Read the relevant current-state sections of `TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md`.
3. Inspect the actual source files related to the task.
4. Treat documentation as context, not proof that the repository still matches it.
5. Report material code/documentation differences before implementation.

For small local fixes, inspect only the necessary files and avoid loading unrelated context.

## Session resume and context continuity

At the beginning of a new sprint, new agent session, or resumed task:

1. Read `AGENTS.md`.
2. Read the current-state and latest-sprint sections of `TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md`.
3. Read the latest relevant entries in `docs/engineering/SPRINT_CHANGELOG.md`.
4. Inspect `git status --short`, the latest relevant commits, and the actual source modules and tests affected by the task.
5. Identify the latest verified boundary, implemented but unverified work, uncommitted changes, current safety invariants, and the next approved task.
6. Before implementation, provide a concise context preflight containing the current verified state, relevant existing modules, behavior that must be preserved, documentation/code discrepancies, and intended files or responsibilities to change.
7. Do not rely on memory from a previous conversation or agent session.
8. Source code, tests, and current Git state override stale documentation.
9. Do not repeat implementation that already exists.
10. After sprint verification, update the handoff and changelog before reporting the sprint complete.

## Scope control

- Implement only the approved task or sprint scope.
- Do not refactor unrelated modules.
- Do not expand a small fix into an architecture rewrite.
- Do not add speculative future functionality.
- Do not reopen settled architecture decisions unless the current code proves they are invalid.
- Do not modify RAG, parser, embeddings, Qdrant, agent evaluation, or UI unless the task requires it.
- Prefer the shortest maintainable implementation that satisfies the acceptance criteria.
- Let the sprint define WHAT and the boundaries; decide HOW only inside that scope.

## Anti-overengineering rules

- Prefer modifying an existing appropriate module over creating a new package.
- Search the repository for an existing responsibility before adding a new abstraction.
- Reuse existing models, validators, stores, services, journals, and safety utilities where appropriate.
- Do not create an interface, abstract base class, factory, registry, plugin system, or generic framework for a single implementation.
- Do not generalize code until there are multiple concrete repeated use cases.
- Do not split a small feature mechanically into models, policy, builder, gate, validator, formatter, store, and service unless those files own distinct real responsibilities.
- Do not add configuration flags for behavior that does not require independent runtime configuration.
- Do not create a new execution boundary merely to approve or revalidate an already-approved boundary.
- Every new execution boundary must name the concrete failure mode that it prevents.
- Keep implementation size proportional to the current acceptance criteria.
- Do not perform broad cleanup during a focused implementation sprint.
- Delay generic refactors until runtime behavior demonstrates real duplication or coupling.

Before introducing a new abstraction, record briefly:

1. the concrete duplication, coupling, or failure mode it solves;
2. why an existing abstraction cannot solve it cleanly;
3. why it is required now rather than after runtime validation.

## Clean code rules

- Clean code must not be used as a reason to expand the approved task scope.
- Prefer straightforward, readable code over clever or overly generic code.
- Use names that describe the trading domain and runtime responsibility. Avoid vague names such as `data`, `obj`, `thing`, `result2`, `handler`, or `manager` when a precise domain name is available.
- Keep each function focused on one coherent responsibility. Do not combine validation, network I/O, state mutation, journaling, and presentation formatting in one function when they can be separated clearly.
- Do not split a coherent function merely to satisfy an arbitrary line-count limit.
- Prefer explicit inputs, outputs, and early returns over deeply nested conditions and hidden control flow.
- Make side effects visible. Network calls, configuration reads, journal writes, file writes, and external state mutations must not be hidden inside unrelated helpers or data-model methods.
- Prefer pure deterministic functions for validation, mapping, scoring, and policy decisions when practical.
- Validate untrusted data at system boundaries. Internal functions should consume already-validated typed objects rather than repeatedly validating the same artifact at every internal layer.
- Follow existing repository conventions for typing, dataclasses, enums, serialization, result objects, and errors. Do not introduce a competing style without a demonstrated need.
- Do not silently swallow exceptions. Catch only errors that can be handled meaningfully, preserve useful context, and return or raise an explicit domain-level failure.
- Avoid broad `except Exception` blocks unless they are located at a deliberate process boundary and convert the failure into an observable, logged, and safe state.
- Keep logs actionable and redacted. Logs should identify the failed operation, a safe correlation identifier, and the resulting state without exposing secrets or account information.
- Comments should explain why a non-obvious invariant, workaround, or safety decision exists. Do not add comments that merely restate the code.
- Avoid duplicated business rules where one authoritative implementation is practical. Intentional repeated enforcement is acceptable across independent trust boundaries, such as app-side and MT5 bridge-side safety validation.
- Preserve public contracts and backward compatibility unless the approved sprint explicitly changes them.
- Remove dead code only when it is inside the approved scope and its removal is verified. Do not perform unrelated cleanup during a focused sprint.
- Tests should verify observable behavior, state transitions, safety invariants, and failure modes rather than reproducing implementation details.
- A code-quality refactor must identify the concrete readability, maintainability, testability, or correctness problem it solves.
- Do not introduce interfaces, base classes, factories, registries, or helper layers solely to make the code appear more architecturally sophisticated.

## Reuse-before-create check

Before creating a new execution package or major module:

1. Search for an existing module with the same responsibility.
2. Check whether the behavior fits an existing service.
3. Check whether existing models, validators, journal stores, or policy objects can be reused.
4. Check whether the new module would duplicate existing safety flags or serialization logic.
5. Prefer extending a coherent module over creating another approval layer.

If the task appears to require more than one new package or more than ten production files changed, stop and explain why the broader scope is necessary before continuing, unless the approved sprint explicitly requires that scope.

## Execution architecture rules

- Application code under `src/` must not import `MetaTrader5`.
- Only the host-side MT5 bridge may communicate directly with the MetaTrader5 package.
- The Docker application must communicate with the MT5 bridge through HTTP.
- Dashboard code must call services and must not contain direct execution logic.
- Intelligence Core artifacts must pass through Trading Execution Core before any execution path.
- LLM output must not itself grant execution permission.
- Deterministic policies, runtime state, kill switches, idempotency, and bridge-side checks must remain authoritative.
- Do not introduce autonomous execution implicitly.
- Do not introduce real-account execution implicitly.
- Preserve current execution safety invariants unless the approved sprint explicitly and narrowly changes them.
- The bridge must not trust app-side validation alone for any future write path.

## Verification rules

Do not mark work complete before required verification runs.

Use exactly one verification level:

- `IMPLEMENTED_NOT_VERIFIED`
- `STATIC_ONLY`
- `FOCUSED_PASS`
- `FOCUSED_AND_LIVE_PASS`
- `FULL_REGRESSION_PASS`

Rules:

- Never claim "all tests passed" unless the full regression actually ran.
- Focused PASS is not full-regression PASS.
- Record exact commands and exact result counts.
- For normal focused sprints, run the new focused tests and relevant neighboring tests.
- Do not run full regression unless explicitly requested, required by the sprint, preparing a major execution milestone, preparing a release or merge, or changing shared core behavior.
- Use Windows virtual-environment commands: `.\venv\Scripts\python.exe -m pytest ...`
- Do not use bare `pytest`.
- For Python or UI source changes, use `docker-compose restart app`.
- Do not rebuild Docker unless Dockerfile or dependency files changed.
- Sprint-specific verification requirements override generic verification defaults.

## Documentation rules

After sprint-level, architecture-changing, pipeline-changing, endpoint-changing, or safety-changing work:

1. Complete the required verification.
2. Append one concise entry to `docs/engineering/SPRINT_CHANGELOG.md`.
3. Update only affected current-state sections in `TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md`.
4. Do not rewrite historical changelog entries silently.
5. Do not duplicate full Git diff details in documentation.
6. Record exact verification level and exact test counts.
7. Separate implemented, verified, not verified, not implemented, and known limitations.
8. Keep each changelog entry concise, normally 15-30 lines.
9. Do not rewrite the full handoff after every sprint.

Documentation updates are not required for typo-only changes, formatting-only changes, variable renames, small internal fixes with no architecture or runtime impact, mechanical refactors with no public behavior change, or small tests that do not change system behavior.

## Security and privacy

Never write into source, logs, handoff, changelog, or final reports:

- API keys
- broker credentials
- MT5 passwords
- secrets from `.env`
- raw account identifiers
- unnecessary sensitive request payloads
- full raw market data
- full raw private knowledge documents

Ticket and deal identifiers may be retained only when required for controlled execution audit, broker-result correlation, reconciliation, duplicate detection, or failure recovery.

- Store only the minimum ticket/deal identifiers required by the runtime workflow.
- Exact ticket/deal identifiers may be stored in the protected internal execution journal when exact broker lookup or reconciliation requires them.
- Do not place raw ticket/deal identifiers in `AGENTS.md`, the architecture handoff, sprint changelog entries, public screenshots, general application logs, or user-facing diagnostic output.
- Use redacted, hashed, or shortened representations outside the protected internal reconciliation path.
- Do not combine ticket/deal identifiers with raw account identifiers, credentials, or secrets in documentation or general logs.
- Identifier retention must not be described as permission to execute an order.

Use redacted or hashed identifiers when required.

## Final report format

Every sprint-level completion report must contain:

- Implemented
- Verified
- Verification level
- Not verified
- Not implemented
- Known limitations
- Documentation updated
- Next recommended step

Do not describe planned behavior as implemented.
