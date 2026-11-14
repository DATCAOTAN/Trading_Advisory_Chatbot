# Native Math Isolation Audit

Status: **INCONCLUSIVE**. Preparation/audit only; no native launch authority is
created here. Approval remains limited to package
`e05805d67cd2774599aa605b108f4833fdb9003753c4bec11efb20976f3cf9b5`, conditional
on proven isolation. G2.1 stays closed PARTIAL; G2.2 is unauthorized.

## Operator Audit

Open **Windows PowerShell as Administrator yourself**, then run exactly:

```powershell
powershell.exe -NoProfile -File "D:\GitHub\Trading_Advisory_Chatbot\scripts\audit_native_math_isolation.ps1"
```

No elevation is requested by the script. If execution policy prevents running
it, stop and report that policy; do not bypass it. Codex must not obtain an
Administrator token. The only write is a new, non-overwriting JSON report under
`data/research/mt5_tester/isolation_audit_<UTC>_<GUID>.json`. Reparse-point output
parents are refused. No credentials, profile contents, account IDs, process
command lines or firewall subject identities are collected.

The audit reads ActiveStore profiles, enabled outbound rules and application
filters; for relevant exact-path/Any/wildcard rules it records port/address,
service/interface/security filters, profile scope and enforcement status.
Errors retain operation, exception type, error ID and message. Inaccessible
policy is INCONCLUSIVE, never an empty-policy success. Partial rules are not
combined speculatively into full coverage. Even a full-path block is labelled
only `BLOCK_RULE_CANDIDATE`: policy interactions, bypass and runtime enforcement
remain distinct from configuration evidence.

## Intended Executables

Proposed portable directory, **not created**:
`D:\GitHub\Trading_Advisory_Chatbot\data\research\mt5_tester\numeric_e05805d67cd2`.

| Role | Exact intended file in that directory |
| --- | --- |
| Compiler | `MetaEditor64.exe` |
| Terminal/controller | `terminal64.exe` |
| Known local Tester agent | `metatester64.exe` |

Read-only source inventory found exactly these three vendor EXEs under the old
`s11b` directory, each version `5.0.0.6230`; their full file hashes are in the
audit report. Do not reuse the old account/cache/profile directories. Per-agent
data directories do not prove the path of the agent executable.

**This is not an exhaustive child-process guarantee.** Relocated/installed
agents, update/crash helpers and inherited Windows tools could execute at other
paths. No research process was launched to observe its process tree. Three
application rules cannot by themselves contain arbitrary descendants, prove
loopback denial or isolate the current user's broker/profile files. The audit
therefore deliberately does not issue overall PASS from path matches alone.

## Current Evidence

- Non-elevated smoke run succeeded as an audit: report verdict INCONCLUSIVE,
  native invocations zero. ActiveStore outbound/application inspection returned
  Access denied; Sandbox feature inspection required elevation. Those errors
  are preserved, not hidden.
- All three firewall profiles are enabled with default outbound Allow. Specific
  effective block rules remain unknown, not proven absent.
- Windows edition Professional, build 19045. The subsequent elevated audit
  `isolation_audit_20261109T195223227Z_689a035ddce9448fb268fcad591b23cb.json`
  succeeded with zero errors: Sandbox feature State=0 (DISM PowerShell enum
  Disabled), launcher absent. Access rights are no longer the blocker. Its
  hardcoded INCONCLUSIVE and conservative filter matching do not prove denial.
- A host trading terminal was observed separately under Program Files; it is
  not a fallback. It was not restarted or used by the audit.

## Safer Containment Candidate: Disposable Windows Sandbox

Preferred design if exact host policy cannot prove whole-tree denial: a fresh
Sandbox with networking disabled for the **whole guest**, not just three paths.
[Microsoft configuration reference](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)
documents network disabling and read-only mappings. Default Sandbox settings
are not suitable: networking and clipboard are enabled by default.

Prepared [native_math_offline.wsb](native_math_offline.wsb) has Networking,
ClipboardRedirection, **vGPU** (case-sensitive element), audio/video/printer
redirection disabled, MemoryInMB=2048, one read-only mapping to C:\ResearchInput,
and no LogonCommand. No writable mapping or auto-launch. Do not open it yet.

The only mapped host directory is
`D:\GitHub\Trading_Advisory_Chatbot\data\research\mt5_tester\native_sandbox_e05805d67cd2\input`.
It now contains exactly 11 allowlisted files: three pinned vendor EXEs, two
pinned MQL sources, two pinned CSVs, unchanged numeric_package.json, math.ini,
guest_preflight.ps1 and manifest.json. No directories, reparse points, credentials,
profiles, `.env`, private journals, DLL copies or unrelated files were included.
Total about 249 MiB. Manifest SHA-256:
`f20b2dff06dd6f4c288a4a32bd91605089a17c46e7f585b671750b7659534651`.
WSB SHA-256: `67c43042588bced99e76e74c598f91eccfdc20aaa370e6dc092de82205f22f71`.
Guest must compare the manifest pin to this independent host receipt before use.
Use guest-local scratch C:\ResearchRun for later compilation, never the mapping.
Networking disabled must also be verified inside the actual guest; retaining
guest-internal loopback for terminal-to-local-agent communication is different
from host/LAN/Internet access and must be explicit in the approved boundary.

Sandbox is **not established on this host**. Enabling a Windows feature and any
required restart need separate operator approval/actions; none are performed.
See [Microsoft prerequisites/installation](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install).
Availability, resources and guest configuration must be checked before use.

## Offline Toolchain Compatibility

**NOT_VERIFIED for these binaries in Sandbox.** Vendor metadata/hashes and old
host math evidence do not establish startup, licensing/dependencies, compilation
or local-agent compatibility in a clean offline guest.

[MQL5 math-mode documentation](https://www.mql5.com/en/docs/runtime/testing)
states math calculations omit tick generation/history download and call
OnInit/OnTester/OnDeinit. This supports a no-market-feed design, not proof that
the installed terminal/editor needs no first-run bootstrap. Do not log in,
enable network, import a broker profile or switch models to make it start.

Remaining evidence before any approved native session:

1. Elevated host audit or actual guest-wide offline containment evidence.
2. Clean guest input inventory; no credentials/profile; all source/package pins.
3. Actual offline vendor-tool dependency/startup evidence within an explicitly
   authorized compatibility check. No such check was run here.
4. Exact settings MathOnly=true, SimulateOrders=false, Model=3, no optimization,
   remote/cloud agents, DLL or live-trading permissions.
5. An approved way to retrieve the resulting EX5/logs/CSVs without writable host
   mappings, network or shared clipboard. None is currently established; do not
   lose results by closing the disposable guest or silently add egress.

Overall isolation readiness remains **INCONCLUSIVE**. Safest candidate is the
offline disposable guest, but it is not yet a verified feasible run environment.
Stop before host feature changes or native invocation; do not compile/run the EA.

## Prepared Host and Guest Gates

Host inspection: x64 Windows 10 Pro 19045.3086, 12 logical CPUs, about 15.39 GiB
physical RAM and 75.55 GiB free on D:. HypervisorPresent and firmware
virtualization are true. WMI reports SLAT/VMMonitor flags false while a
hypervisor is running; this is not independent proof of absent or available
hardware support. Do not change BIOS/features to resolve it automatically.
Free RAM fluctuated between about 3.47 and 4.75 GiB. Recheck before launch;
recommend at least 4 GiB available for a planned 2-GiB guest plus host headroom
(a conservative operating recommendation, not a new Microsoft minimum).
No CBS/WU reboot-pending keys were present; enabling Sandbox can still require
a restart. No active app/terminal is stopped or restarted here.
Current read-only Win32_OptionalFeature inspection also reports InstallState=2
(Disabled), consistent with the elevated audit; no feature-change command ran.

Operator-only, AFTER accepting the feature change and checking prerequisites:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart
```

Run in the operator's own elevated Windows PowerShell. If RestartNeeded is true,
schedule a manual restart only when existing trading/runtime state is safe.
Do not launch the WSB until output transport and guest preflight are approved.

Static dependency inspection used installed objdump, not vendor execution.
All three binaries expose only Windows-system imports (UI/GDI, kernel, COM,
crypto, sockets, IP helper; editor additionally dbghelp, terminal CRYPT32/WINTRUST,
agent pdh). No separate VC runtime/vendor DLL import was listed. objdump warned
about a .cod2 section flag; packed/dynamic loading is not excluded. No extra
DLL/dependency was copied or installed. Guest presence of these OS libraries,
dynamic dependencies, startup/bootstrap and actual offline compatibility remain
unverified. Guest does not require Python for MQL compilation; host Python remains
the independent output comparator after controlled retrieval.

When a future guest launch is separately permitted, manually run only:

```powershell
powershell.exe -NoProfile -File C:\ResearchInput\guest_preflight.ps1
```

This is the staged copy of `scripts/native_math_guest_preflight.ps1`; no autorun.
It verifies allowlist/hashes/package/source/fixture pins, active adapters/default
routes, absence of pre-existing vendor processes and MetaQuotes profiles. It
creates only a guest-local report, never native tools. It remains INCONCLUSIVE
until WSB/mapping checks and the benign read-only marker probe are reviewed.
Guest-internal loopback is permitted for local agent IPC; host/LAN/Internet are
not. Observe all native descendants later inside the guest, including relocated
helpers; their network boundary must be the whole guest, not a path list.

## Result Extraction: Separate Approval Required

With network and clipboard disabled and input read-only, **no machine-readable
egress currently exists**. Do not consume the approved Tester session before
settling this; closing Sandbox destroys guest-local results.

Smallest practical proposal is one second mapping, requiring explicit approval:

- Exact host path: `D:\GitHub\Trading_Advisory_Chatbot\data\research\mt5_tester\native_sandbox_e05805d67cd2\outbox`.
- Guest path C:\ResearchOut; ReadOnly=false. NOT in the prepared WSB and NOT created.
- Dedicated empty directory, no inheritance/shared users/reparse points; operator
  identity and SYSTEM only on the host. Operator needs read/write access, guest
  receives write access via the projection. ACL setup itself requires approval;
  neither ACLs nor mapping were changed in this task.
- Allow only compile.log, terminal.log, tester.log, s11b_parity_result.csv,
  s11b_numeric_result.csv and receipt.json (binary/source/toolchain hashes).
  No EXE, EX5, script, HTML or arbitrary folder export. Host computes parity
  reports separately using existing comparators; never execute/open output by
  association, never use Explorer preview or an HTML report as trusted code.
- After all guest native processes terminate, operator exports that exact small
  allowlist once. Host rejects reparse points, subdirectories, unexpected names,
  more than 8 MiB total or 4 MiB per file, malformed encodings/schema/counts and
  source/fixture/binary receipt mismatches. These are admission limits, NOT an
  enforced disk quota; a writable mapping can still damage/fill its directory.
- Risks requiring consent: a guest-writable host boundary, disk exhaustion and
  malicious output. It must not point at source, credentials, journals or other
  user data. If those risks are unacceptable, keep the current input-only WSB
  and STOP; no clipboard/network fallback is permitted.

The single-session limit remains 58 original + 58 SELL + 30 numeric checks.
No preliminary Tester smoke run: even a failed attempt must be reported, not
retried automatically or reset by reopening a disposable guest. Record a trusted
host-side consumption receipt before the separately approved one session.
Prepared tooling is not proof of guest isolation, compatibility or native parity.

## G4 Data-Only Import into the Existing Offline G3 Guest

Use `scripts/g4_prepare_import.py` and `scripts/g4_import_media.ps1`; these
prepare/stage inert inputs, never start a VM or MT5. The existing G3 guest
must already be isolated, with zero host VM NICs, integration services disabled,
no broker account, disconnected terminal and trading disabled. This is not a
VM provisioning procedure or authorization to run Tester.

The V10 operator log proved that the margin getter expected XAU but returned
USD, stopping Configure before Description/session setters. Keep requested
metadata unchanged. Financial mismatches stay BLOCKED; even snapshot matches
are NOT_CERTIFIED historically. Only quote representation, Disabled trading,
Description provenance and source-day sessions gate the data roundtrip.
Source weekdays include pre-start bars and boundary ticks, not an inferred
broker calendar. The helper independently checks the pinned day mask.

Prepared private media (not committed):
- ISO: `data/research/mt5_tester/g4_import_once_e50d45c275df.iso`
- ISO SHA-256: `84198dd68edb96ad5ba457798e083cfc439c5e6999985ef06102ef7d7629d8bd`
- Manifest SHA-256: `454157554095b9828cdd8148a9444b197b53ba9c640a9673fab5229898c458ab`
- Source SHA-256: `e50d45c275df04ea43379b730c1d5a16d988995e71aa761d0d785a60ef1053e9`
- Target: `XAUUSD_G4Rf0386d9a`; folder: `G4Import_Rf0386d9a`.
- IMPORT mode; ApproveImport=false; native_execution_authorized=false.
- 245 M1 bars, 63,156 ticks; Shift 0, Wednesday quote session only.

The target identifier is new among preserved media; guest absence is NOT
verified from the host. SymbolExist must guard before writes. Existing symbols
are never deleted/reconfigured or overwritten (existing targets are read-only).
Require explicit approval for exactly this new target's configuration and
one import/readback attempt; stop on collision or failure, no automatic retry.

Operator staging, after host zero-NIC/integration checks and VM-Off DVD attach:
```powershell
& 'D:\g4_import_media.ps1' -InputDirectory 'D:\' -ManifestSha256 '454157554095b9828cdd8148a9444b197b53ba9c640a9673fab5229898c458ab' -StageGuest
```
Staging requires the verified read-only DVD, native processes closed and
preserved V8 source pin. Compile ONLY the staged
`MQL5/Services/G4Import_Rf0386d9a/G4Import.mq5` in the existing portable terminal
root. Record source/header/EX5 hashes and require zero errors/zero warnings.
After separate import authorization, use Navigator > Services >
G4Import_Rf0386d9a > G4Import, setting ApproveImport=true for that attempt only.
No Tester or broker-order permission is granted.

Acceptance requires API counts AND index-by-index equality: all 245 bar time,
OHLC, tick/real volume and spread fields; all 63,156 tick time/time_msc and
Bid/Ask/Last values, in original order. Extra/missing records fail. Tick flags
and volume changes are disclosed separately, not source-equality evidence.
Read the scoped Experts log and MQL5/Files/G4Import_Rf0386d9a/roundtrip.csv.
Data import PASS does not establish financial fidelity or Tester acceptance.
Native compilation/import/readback remain NOT_RUN at packaging time.

## G4_NATIVE_DATA_READBACK_PASS / Next Bounded Tester Capture (2026-11-15)

The operator reports the Experts checkpoint in the existing offline G3 guest:
G4_DATA_CONFIGURATION_READBACK_MATCH;
G4_VERIFY_GENERATED_BAR time=1793811600 source_ticks=394;
G4_VERIFY_DATA_MATCH source_bars=245 native_bars=246 ticks=63156.
Record G4_NATIVE_DATA_READBACK_PASS only for the verifier's equality scope:
all 245 source-bar fields and ordered tick time/time_msc/Bid/Ask/Last.
Generated-bar OHLC and tick flags/volume are not original-source equality.
This is operator-provided Experts observation, NOT a HOST-hashed raw log or
EX5 identity. No new screenshot was independently acquired in this task.
Raw logs and native binary hashes have not been transferred; no trusted
receipt or EX5 checksum is fabricated. Do not re-import or rerun the verifier.

### Gates

| Gate | Current evidence / remaining condition |
| --- | --- |
| Native data | Scoped operator-observed PASS above; HOST raw evidence pending |
| G3 math | 58 BUY + 58 SELL + 30 numeric PASS reported in-guest, including real_16; no new run or trusted receipt |
| Decimal source | Capture uses 5cddea29...c569465, identical to the existing G3 pinned library; not proof of a new EA binary |
| Replay | Approved artifacts contain 290 observations, 5 ENTRY/5 EXIT; capture compares replay, not independent native signal computation |
| Clock | Custom-symbol archive epoch identity; does not certify historical broker UTC offset or rollover |
| IS/OOS | Continuous 14:35-17:00 UTC, split 16:00 on 2026-11-04; diagnostic, not independent OOS holdout |
| Fills/costs | NOT evaluated by CAPTURE_ONLY; FULL_BACKTEST remains BLOCKED |
| Financial fidelity | Margin XAU/USD mismatch and historical contract/swap uncertainty remain; selected commission/slippage/deposit/leverage are assumptions, not broker facts |
| Lifecycle | Last signal-based entry at 16:58 may remain open; native SL/TP/exit lifecycle unknown; no forced close or realized P&L inferred |
| Report admission | Existing trusted receipt, binary/toolchain/run approval/raw report pins and FULL_BACKTEST gates remain mandatory; data PASS cannot admit a performance report |

### One prepared run, not authorized or executed

Existing capture package de82aefd...f96a91b targeted the old G4CAP alias.
`bind_capture_import` now binds it through the exact approved import manifest
45415755...8c458ab to XAUUSD_G4Rf0386d9a, retaining original revision/scope,
source bytes, schedule observations, timestamps and calculation versions.
It changes only transport alias/job binding and INI expert location; native
attestation remains false. No proposal/source approval or trading permission
is written. Private content-addressed package:
`data/research/results/native_capture_package_06e159f05ff4166f3f27761ff7216cfdf62530c5fe8ee37fd950240c22abd15c.json`.
SHA-256 equals its filename suffix; strategy SHA-256:
`153ef579bb13015869af5b81c4f97576f60d4196f3d4bd5b41411b5f865d4e53`.
It retains proposal_e0d7793097ab46a127a4ecf1439a0dbccb0e18426fd8a2b8441d715cc2cd3823 /
revision_593b5723e2b58a64f666c1be5c8b543b2fb28918feb73fe092e60890d73987bb;
this transport binding does not grant/reaffirm approval for a different head.
Native inputs only: `data/research/mt5_tester/g4_capture_153ef579bb13/`
contains SignalReplay.mq5, ParityDecimal.mqh, SignalReplay.set,
replay_schedule.csv and capture.ini; no market history needs re-import.
Read-only ISO `data/research/mt5_tester/g4_capture_153ef579bb13.iso`, SHA-256
`2c1a737b73030995fb54b8bb5285ea47feb6783dd7d090130eb6592548500727`,
contains exactly those five files; existing IMAPI builder reused, 5/5 entries
read-back/hash matched. It carries no execution authorization.

Source SHA-256: 4b935dcb71551b9359c2a1493111d01d315f7ed43cbd824728c62a98dc3f7e16.
Decimal SHA-256: 5cddea29b14501bc2fe1988448eae5f46de9b2cb9ce1962153c528bc5c569465.
Schedule SHA-256: 0b9ab4b1d85514604e8e18c3beeebcf9515b54edcea6d7b2ac2903fe212974ce.
INI SHA-256: ecaabd32e15f7012c1c17673d274033722c14fe0aef68aae49a6664ee7fbc4b9.
Prepared SET SHA-256: 2a054d5d2531dd693f63d5fcea2c0a230bcd0afb00ff991076763263947ef42b.
Prepared SET has ApprovedResearchReplay=false and CaptureOnly=true.
Expected capture is 52,073 ticks from 14:35 through the first tick at/after
17:00, plus all 290 observations and both boundaries. This is intentionally
not all 63,156 imported ticks. No fill, deal, cost, P&L or equity rows allowed.

Operator procedure, ONLY after a separate explicit approval of this exact
CAPTURE_ONLY run (not FULL_BACKTEST), at most one session and no auto retry:

1. Preserve G3 zero-NIC/all-six-services-disabled isolation and existing custom
   symbol/history. The approval must name the exact package/revision above;
   reject any revised scope or revoked source/research approval. Stage only
   the five pinned native inputs through existing
   read-only media. No VM/network/profile/broker changes, no new import.
2. Native processes must be closed. Create NEW
   MQL5/Experts/G4Capture_153ef579bb13; copy source/library there. Copy schedule
   to MQL5/Files/replay_schedule.csv and SET to MQL5/Profiles/Tester/SignalReplay.set
   only if absent. Stop rather than overwriting conflicting files. Stop if
   any existing replay_result.csv is found under the portable root's Tester
   agents; preserve it. Existing G3 runner's agent path is
   Tester/Agent-127.0.0.1-*/MQL5/Files. No other terminal/profile is permitted.
3. Verify existing toolchain against G3 manifest references (not a rerun of G3):
   MetaEditor64.exe cf2750bde55d98a1f3b4e56bcdd4f59300d0cff5caa6760985f7ef2c2cc12229;
   terminal64.exe bf3b5ad0ac2d5da6a4e1a813bf8fc830fde9f0837850cc85776a305bd16dd495;
   metatester64.exe 5033d9d45d669cebd735e8a6be20b54d74b75274f885c9a0e48e52d872104efb.
   Compile this exact SignalReplay source, require 0 errors/0 warnings, record
   new EX5 hash and toolchain/build identities; do not invent an expected EX5.
4. Preserve the prepared SET. After authorization only, change the GUEST
   runtime copy to ApprovedResearchReplay=true, CaptureOnly=true and record
   its actual SHA-256. This is run authorization, not live trading authority.
   Record package pin, compile log, EX5/toolchain pins and scope together.
5. Use the pinned capture.ini: Model=4, local agent only, remote/cloud off,
   optimization/forward off, ReplaceReport=0, no account login. Dates span
   Nov 4-Nov 5; the schedule enforces the exact intraday capture interval.
   In the existing G3 root, the one authorized launch is:
   `terminal64.exe /portable /config:<absolute path to capture.ini>`.
   Do not launch until all preceding gates and separate approval pass. Stop
   on unsupported settings, init failure or unexpected broker connection.
6. Reuse the existing runner's WaitForExit timeout pattern with a 180-second
   bound, NOT the g3_math_once script or math run. If exceeded, stop the
   GUEST research process only, retain partial outputs, do not retry. Preserve
   raw Tester/Experts/agent logs, replay_result.csv, report and hashes without
   rewriting them. No quarantine or new receipt system is introduced here.
7. After authorized output transfer, call existing normalize_capture with
   the exact new package and raw CSV. Require every timestamp/Bid/Ask, signal
   row and split/end marker to match. Missing/generated ticks, reordered or
   financial rows, incomplete output or mismatched pins mean INCONCLUSIVE.
   CAPTURE_COMPLETE plus normalized MATCH is non-financial replay evidence,
   not a financial result, independent strategy parity or trusted receipt.

Current authorization: NOT_GRANTED for Tester. No VM, MetaEditor, Tester,
verifier or import was executed. Next native operation is exactly this
capture-only pilot, after the bounded scope and remaining binary gates pass.
