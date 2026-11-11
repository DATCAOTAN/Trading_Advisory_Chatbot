# ChatGPT Project to Local Codex Issue Bridge

Development-only. This is NOT a trading/research/runtime authority. No listener
is installed or started by implementation or tests. Production Trading Core is
unchanged. Commands below are operator actions, not instructions to an agent
reading this document to run them automatically.

Implementation: [bridge](../../tools/codex_issue_bridge.py),
[offline tests](../../scripts/test_codex_issue_bridge.py).

## Supported Boundary

`owner Issue + codex-dev-task label -> PENDING/hash receipt -> owner approval
comment -> RUNNING -> dedicated Codex turn -> checked result -> PASS/BLOCKED/FAILED`

- Fixed repo `DATCAOTAN/Trading_Advisory_Chatbot`, human owner `DATCAOTAN`.
  Both repository owner ID and authenticated token identity are verified.
  Other authors, PRs, closed/locked/unlabelled Issues and edited approval
  comments are rejected. Issue body contents alone cannot authorize a command.
- Operations: `smoke`, `review`, `edit`. No raw commands, shell scripts,
  dependencies, test selectors, URLs, environment values or permissions accepted.
- Context is at most eight explicitly named UTF-8 code/doc files under src,
  scripts, tools, docs or AGENTS.md, with size/secret/path checks. Never name
  broker/account/private knowledge data as context. Context is sent to Codex's
  provider; repository access does not imply approval to disclose private files.
- Writes: at most ONE `.md`/`.py` under `docs/development/bridge_tasks/` or
  `scripts/dev_tasks/`; existing dirty/untracked targets are refused. No delete,
  rename, binary, mode/ACL, authority/config, source/runtime or Git-history edit.
  Wider development scope needs a separately reviewed code change, not an Issue.
- Model produces JSON, not a command or directly applied patch. Host validates
  target, before hash, current context, Python AST and whitespace. No generated
  code or task-selected tests execute. Reports explicitly say unit_tests=NOT_RUN.
- `PASS` means this bounded development operation/check passed, never full
  regression, live execution or deployment acceptance.

## Codex Session and Security

Uses installed Codex CLI **0.167.0**, native executable, `exec --ephemeral`,
read-only/unelevated sandbox, never approvals, no inherited user config/MCP,
disabled hooks/shell/apps/browser/computer/subagents and no Issue-controlled
process arguments. Worker sees only supplied context in a dedicated empty
`worker-cwd` outside the repository; nonempty or reparse-point workspaces are
refused. Per-turn schema/output files use a separate disposable directory, not
the process working directory. It is a dedicated session for this local repo's snapshots,
NOT the live Desktop directory or historical Desktop thread. Protected broker,
GitHub, API-key and proxy environment variables are not forwarded.

[Official app-server documentation](https://developers.openai.com/codex/app-server)
supports resuming a recorded thread, but this task has no proven safe ownership
handover of an active Desktop thread/worktree. The bridge intentionally does
not connect to the Desktop daemon, resume/fork its thread or reuse its approval
state. CLI flags were checked locally; actual authenticated Codex turn remains
a separate smoke requirement. No claim of VM-grade containment or G2.2 approval.

Windows named global mutex plus process-held file lock allow one bridge writer
per canonical worktree. Target uses an exclusive Windows write handle and hash
check, with a private before-image backup. Local SQLite claims survive restart;
interrupted RUNNING tasks become BLOCKED and are NEVER rerun automatically.
No journal deletion or ID reset is a recovery action.

Desktop does not participate in the bridge mutex: pause edits to the selected
files while bridge tasks run. Context changes cause BLOCKED; pre-existing dirty
files and unrelated files are not overwritten. Unsaved editor buffers cannot
be detected. An interrupted write requires manual inspection of before/after
hashes and its private backup; there is no destructive auto-rollback.

## Credentials and Permissions

ChatGPT's GitHub connector credentials are NOT available to this local process.
Local `gh` was not authenticated during implementation; no token was imported.

Create a fine-grained GitHub PAT for **this repository only**:

- Repository Issues: Read and write (label-filtered reads and result comments).
- Metadata: Read. No Contents write, Actions, administration, workflows or Git.
- Authenticate as DATCAOTAN. Organization-owner delegation/bot authors are not
  supported by v1. Set expiration; review/revoke the PAT normally.

[GitHub Issue API](https://docs.github.com/en/rest/issues/issues) and
[comment API](https://docs.github.com/en/rest/issues/comments) permissions apply.
The bridge cannot prove a token was not granted excess permissions; operator
must provision least privilege. It exposes only fixed GitHub GET endpoints and
POST Issue comments, refuses redirects and never forwards the token to Codex.

In a **non-Administrator** terminal at the repository root:

```powershell
.\venv\Scripts\python.exe -m pip install -r tools/requirements-codex-issue-bridge.txt
.\venv\Scripts\python.exe -m tools.codex_issue_bridge credential --gui
.\venv\Scripts\python.exe -m tools.codex_issue_bridge login
```

First command masks input, validates GitHub owner identity and repository/Issue
read access, then stores the PAT only in Windows Credential Manager. Invalid
credentials do not overwrite the old entry. No env/JSON/token file. Second explicitly opens Codex authentication with a
dedicated CODEX_HOME and mandatory OS keyring store, no file fallback. It does
not start a worker/listener. Existing Desktop project/auth files are not copied.
State/receipts/backups live under `%LOCALAPPDATA%\TradingAdvisoryCodexBridge\<repo-hash>`;
never publish that directory. CLI upgrades fail closed until reviewed.

### Read-Only Connection Diagnosis

```powershell
.\venv\Scripts\python.exe -m tools.codex_issue_bridge check
```

This command uses GET only: repository, authenticated owner, labelled Issue list,
Issue #1 and comments. No listener, Codex worker, comment/approval, lock/state
initialization or local database mutation occurs. A successful read check does
not prove Issues write permission or authorize the smoke task.

Failures report method, endpoint, HTTP status and fixed-vocabulary category/reason,
never the PAT, authorization headers or raw response/error bodies. HTTP 401 is
authentication rejection; 403 is permission/policy (or rate limit if evidenced);
404 means not found/not visible; 400/422 request rejection; 429 rate limit; 5xx
service failure. TLS/DNS/timeout/connection errors are separate from malformed
successful JSON responses. No automatic retry was added, including ambiguous POSTs.

On Windows the bridge uses a private `truststore.SSLContext` through urllib's
existing HTTPS handler, pinned in the host-only requirements above. Native
Windows certificate-chain validation and hostname verification remain required.
Missing truststore fails closed with `WINDOWS_NATIVE_TLS_DEPENDENCY_REQUIRED`.
There is no global SSL injection, unverified fallback, custom CA bundle or
Docker dependency change. See [truststore documentation](https://truststore.readthedocs.io/en/latest/).

TLS acceptance on 2026-11-10: public GitHub GET with this context returned 200;
one authenticated `check` passed owner/Issue reads with zero writes/worker calls.
Windows verified the Sectigo E36 -> Root E46 chain for `*.github.com`; no proxy
or CA override was detected in the inspected process. The earlier issuer error
did not reproduce even with standard Python SSL before the change, so missing
intermediate/cache state versus another historical cause is NOT PROVEN. A
successful read check still does not prove Issues write permission.

The observed first failure was GET `/repos/DATCAOTAN/Trading_Advisory_Chatbot`,
HTTP 401 Bad credentials. Credential Manager successfully read the stored value,
but it contained U+0016 (Ctrl+V), which the former whitespace-only validator
allowed. Opaque tokens are not silently stripped or normalized. The current
validator rejects control/non-ASCII/whitespace before storage or request.
`credential` previously meant storage succeeded, NOT authentication succeeded;
Codex `login` is unrelated to GitHub authentication.

Replace the invalid entry using `credential --gui` and an actual valid
fine-grained PAT. Click **Paste from Clipboard**, then **Verify and Save**.
The input stays masked; clipboard text is validated unchanged. Controls,
whitespace, non-text and oversized content are rejected, not trimmed.
Cancel/window close clears the input without storing it. The system clipboard
is not cleared automatically; manage its contents/history yourself. Verification
uses existing bounded synchronous HTTP requests; the dialog can be unresponsive
while they complete. Failures are sanitized and never retried automatically.
Plain `credential` remains the masked console fallback. Do not bypass the
validator, put the PAT in command arguments/environment, or share it in chat.
Replacement is operator-only; implementation did not alter the stored secret.

## Activate: Dry-Run First

After credential/login setup, ONE activation command:

```powershell
.\venv\Scripts\python.exe -m tools.codex_issue_bridge watch
```

Default is read-only dry-run. Poll interval 60 seconds (allowed 30-300), one new
task per poll, worker timeout 300 seconds, no bridge task retry. Codex's own bounded
transport retries remain its installed defaults under that deadline; no claim of
zero provider HTTP retries is made. Network or
uncertain-delivery failures stop the listener; no endless failure loop. Ctrl+C
stops it. No task scheduler, Windows service, Docker/WSL/app restart is installed.
For one bounded poll instead, use `once`. For local receipts use `status`.

## From the Existing ChatGPT Project

The conversation must have an actual GitHub tool/action that can **create and
comment on Issues**, not only search source. Repository read access alone does
not establish write capability. Do not substitute UI automation or share tokens
in chat if its connector is read-only.
Create the repository label `codex-dev-task` once using the owner's GitHub UI or
authorized connector. The bridge deliberately does not create labels or widen
its API allowlist to administer the repository.

Ask ChatGPT: create an owner-authored Issue in the exact repository, add label
`codex-dev-task`, and use this complete JSON body (generate a NEW UUIDv4):

```json
{
  "schema": "codex-dev-task/v1",
  "task_id": "db881292-7499-4ec0-8a65-05e54c189c54",
  "state": "PENDING",
  "operation": "smoke",
  "instructions": "Return BRIDGE_SMOKE_OK without tools or changes.",
  "files": [],
  "write_path": null
}
```

Then ask ChatGPT to read the bridge PENDING comment and post its exact
`approval_comment` value as ONE new owner-authored, unedited comment. The line is
`CODEX_BRIDGE_AUTHORIZE <task_id> <canonical-task-sha256>`. No manual copying by the
human is necessary: ChatGPT reads/writes the Issue through its GitHub tool.
If it cannot write, stop at that missing connector capability.

Read Issue comments for RUNNING then PASS with `BRIDGE_SMOKE_OK`, no changed files,
no executed tests and zero broker mutations. Only a fully delivered real smoke
PASS unlocks local edits. Offline fixture tests do NOT populate the real gate.
The bridge does not automatically wake/inject messages into a ChatGPT Project;
ask that conversation to read the Issue when needed.

For review, create a NEW Issue/UUID with operation=review, explicit files and
write_path=null, and repeat the owner hash approval. For modifications, first
stop dry-run watch, then the operator separately opts in using:

```powershell
.\venv\Scripts\python.exe -m tools.codex_issue_bridge watch --allow-edits
```

Create a new edit Issue with one allowed write_path and approved context. This
flag does not widen the write roots or permit execution/privileged commands.
Tasks blocked before the gate opened stay terminal; create a fresh reviewed
task rather than clearing state. Do not edit/reuse handled Issue bodies/IDs.

## Delivery and Recovery

Local receipt is claimed before worker execution; states mirror to structured
comments. HTTP posting is marked attempted BEFORE sending. If a response is
lost, the next operator run first looks for the identical comment; it does not
blindly repost or repeat the Codex task. If absent/ambiguous, that task remains
blocked with COMMENT_DELIVERY_UNCERTAIN_NO_REPOST; inspect its receipts manually.
This error is raised on the reconciliation GET branch, not a new POST. Even
repeated empty comment lists do not prove that an older request never took
effect. A delayed exact owner-authored body can acknowledge delivery without
reposting; a different task/state/body/author cannot. Do not manually recreate
the receipt, reset attempted/delivered, edit the task UUID or delete the journal.

The current task journal stores attempted/delivered flags, NOT the original
POST HTTP error/status/request ID or timestamp. After that diagnostic is lost,
the journal cannot distinguish a denied request from a lost response. A fresh
403 or successful GET does not establish the older attempt's outcome or prove
Issues Write permission. Require original operation-bound rejection evidence
or the matching published receipt; otherwise remain BLOCKED. No force-retry or
manual clear is supported. Merely rerunning `once` will preserve this block.
This block is task-scoped, not a global ban on independent tasks. Before any
pending receipt delivery, the bridge rechecks the Issue's owner/state/label,
canonical task ID and hash. Closed, unlabelled or changed tasks are deferred
without journal mutation or POST, emitting TASK_RECEIPT_DEFERRED. An active
uncertain task is also excluded from execution while unrelated authorized
tasks can proceed. If no independent work proceeds, its uncertainty is still
reported, not cleared. Reopening/relabeling cannot bypass the same receipt's
no-repost check. A delayed receipt on an inactive Issue remains untouched until
that task is admitted again; it can then be acknowledged without reposting.

Sanitized diagnostics include stage, task_id, Issue, operation and operation_id
(SHA-256 of the exact expected comment body), never arbitrary comment contents.
Within one listener instance, unchanged TASK_RECEIPT_DEFERRED observations are
printed once. The in-memory key is task_id/operation_id/reason/stage; changed
Issue state, lock or task-label presence also causes a new observation. The
cache retains only the latest poll's deferrals: state reversions or a deferral
recurring after admission/reconciliation are visible again, and a fresh process
starts empty. No cache is persisted in the journal. This suppresses output only;
every poll still fetches and checks pending receipt admission and performs normal
reconciliation/discovery. Other errors, including uncertain delivery, are not
silenced. Restart an existing watch with Ctrl+C, then the same plain watch
command; no --allow-edits is needed for this logging change.
New GitHub POST errors also carry this context; historical HTTP evidence is
not reconstructed or silently added to existing rows. One `once` still processes
at most one new task; completed tasks and duplicate task IDs remain protected.
Completed or failed tasks are not automatically retried. No push/commit/merge,
broker operation, research calculation, native Tester or host configuration is
part of recovery.

## Verification Status

Offline tests cover owner/hash/label gates, malformed tasks, path/sensitive-data
rejection, durable state, pending approval, duplicates, uncertain delivery,
timeouts, changed context, edit gating, exclusive writes/backups and process
locks. External GitHub/worker boundaries are fakes; these are not live E2E proof.
No persistent listener or authenticated Codex smoke was started during the task.
Local GitHub token and dedicated Codex login must be supplied by the operator;
full ChatGPT -> GitHub -> Codex -> GitHub acceptance remains NOT_VERIFIED.

Implementation verification: **60 bridge tests + 13 documentation tests = 73
passed**, no full regression. CLI 0.167.0 read-only feature validation confirmed
shell_tool/apps/hooks false; it made no provider call and started no listener.
An initial rejected built-in provider override was removed; installed Codex
transport retry defaults are not misreported as zero retries.

Task-isolation regression: **133 bridge + 13 documentation = 146 passed**.
Covers old closed/unlabelled/changed tasks, independent tasks, uncertainty on
either Issue, duplicate IDs, delayed visibility, 403 and restart recovery.
GET-only live diagnostics with an in-memory journal copy reached Issue #2's
first receipt boundary, blocked before network POST. Persistent Issue #1 row
and journal bytes remained unchanged; Issue #2 still has no persistent row.
This is not proof of Issues Write permission or successful worker execution.

Latest worker regression: **153 bridge + 13 documentation = 166 passed**.
Local Codex CLI 0.167.0 tool-free smoke returned exit 0 and BRIDGE_SMOKE_OK with
no edits or new scratch leftovers. This did not run/retry a GitHub task, post a
comment or populate the durable live_smoke_pass setting. Fresh GitHub E2E smoke
is still required; Issue #2 remains terminal FAILED.

Diagnosis reproduced a Windows sharing violation (PermissionError, errno 13,
WinError 32) when removing the CLI's temporary working directory AFTER exit 0
and JSON parsing. A short cleanup retry did not resolve it and is not shipped.
Separating stable empty cwd from disposable output fixes that reproduced path
without weakening sandbox/tool/auth gates or rerunning the worker. Old scratch
directories are preserved, not swept. The original Issue #2 traceback was not
recorded, and the process holding the Windows handle was not identified.

Worker failures now persist exact stage, exception type, return code, errno /
WinError and allowlisted stderr reason markers in the existing FAILED receipt.
Stages cover home/workspace/temp/schema preparation, subprocess, result file,
JSON parsing and cleanup. Raw stderr/task/context/credentials are never posted;
only a bounded 16 KB tail is inspected privately. A secondary cleanup failure
does not replace the original process failure. Missing/malformed/oversized
results, startup failures, timeout and persistent cleanup errors stay fail-closed.
There is no worker, provider-call or cleanup retry loop in the bridge.

Latest deferred-log regression: **165 bridge + 13 documentation = 178 passed**.
Verified offline with fake GitHub/worker and temporary SQLite: repeated events,
key/Issue-state changes, state reversion, per-poll admission, independent tasks,
delayed receipt reconciliation, errors and restart behavior. No live watch,
GitHub POST or actual Codex worker was run for this change. Existing real journal
and unknown Issue #1 outcome are preserved, not resolved by log suppression.
