# G2.1 sandbox acceptance report

Date: 2026-11-09. **G2_1_PARTIAL; READY_FOR_G2_2 = NO.**

G2.1 is **closed as PARTIAL**, not eligible for formal full acceptance. Prior A/C/D/E/F runtime PASS is retained. G guest checks are **OPERATOR_ATTESTED** by the operator's explicit closeout directive: Debian booted after BootAfterG, the marker was absent, failed units were clean and root was rw. Independent machine-readable guest evidence was **not captured**; no guest output is fabricated and formal G PASS is not claimed. Normal guest-OS shutdown is independently recorded by the host. The existing non-destructive Closeout completed at **16:07:49Z**, exit code 0; both VMs remain Off. **B/H remain INCONCLUSIVE; READY_FOR_G2_2 = NO.** No further guest evidence gathering is scheduled.

| Probe | Verdict | Evidence and limit |
| --- | --- | --- |
| A: No network | PASS | Prior runtime PASS supplied by the operator; host inventory and current Stage3 Verify require zero NICs. Prior guest output was supplied in conversation, not recovered as a standalone file in this closeout. |
| B: No host resources or secrets | INCONCLUSIVE | Existing host inventory PASS; no NICs, enabled integrations, mapped COM ports or checkpoints. Independent Basic Session/no-other-sharing/guest-inventory attestation remains incomplete. |
| C: Input read-only | PASS | Prior runtime PASS supplied by the operator for the synthetic fixture; not repeated. |
| D: Non-privileged worker | PASS | Prior runtime PASS supplied by the operator for the bounded probe service; not a claim about future generated execution. |
| E: Resource limits | PASS | Prior runtime PASS supplied by the operator for CPU, RAM, process and wall-time enforcement; not repeated. |
| F: Forced stop/recovery | PASS | Exact-clone forced-off and BootAfterF receipts; operator confirms Debian reboot, marker persistence, zero failed units and root rw. Guest observations are supplied evidence, not observations made by this session. |
| G: Clean recovery | OPERATOR_ATTESTED | RestoreG/BootAfterG and normal shutdown are host-evidenced. The operator personally confirms the Debian, absent-marker, failed-unit and root-rw checks. Closeout recorded that attestation. Independent machine-readable guest evidence was not captured; formal independent acceptance remains unverified. |
| H: Provenance/checksums | INCONCLUSIVE | Signed-installer receipt, media/harness pins and baseline/restore byte identity are evidenced. Installed-image lineage remains unproven; the original's investigated boot incident does not change the sealed pin. |

## Evidence locations

- Original host/image inventory: `%LOCALAPPDATA%\G21-Closeout-<local-session>\g2_1_host_image_baseline.json` (captured 12:55:20Z).
- Disposable clone receipts: `D:\TradingAI_G21_FG_Disposable\evidence\g2_1_clone_provision_receipt.json`, `stage3_boot_for_f.json`, `stage3_forced_off_f.json`, `stage3_boot_after_f.json`, `stage3_restore_g.json` (RestoreG captured 14:43:14Z), **`stage3_boot_after_g.json` (15:41:15.7316323Z)**. Closeout receipt: **`stage3_closeout.json` (16:07:49.0980135Z)**; operator-attested scope only.
- Current host audit: `D:\GitHub\Trading_Advisory_Chatbot\g21_host_audit_20261109.txt`. Stage3 Verify passed, including the original incident pin, Off states, identity, attachment and isolation checks. Supplemental restored-disk host-mount/attachment checks completed before a final two-VM display command failed because Get-VM -Id accepts one GUID. This log is not an unqualified overall audit PASS.
- Earlier boot-prompt transcript: `D:\GitHub\Trading_Advisory_Chatbot\g21_boot_after_g_20261109.txt`. That disconnected administrator process exited without a receipt; it was not left waiting or treated as successful. Host metadata/native stderr in a transcript is not guest acceptance evidence.
- Resume audit: `D:\GitHub\Trading_Advisory_Chatbot\g21_boot_after_g_resume_audit_20261109.txt`. At 15:38:16Z, both VMs were Off, only the restored disk was attached to the clone, and the unchanged Stage3 Verify and incident/hash gates passed. This fresh state check permitted continuation of the unexecuted BootAfterG stage; no completed stage was replayed.
- Successful approved boot log: `D:\GitHub\Trading_Advisory_Chatbot\g21_boot_after_g_approved_20261109.txt`. Records the unchanged scope-specific Read-Host gate accepting `BOOT_RESTORED_CLONE` via redirected stdin under prior explicit approval, exit code 0, receipt path, original Off and clone Running. No gate function was replaced or disabled. Post-boot state audit completed at 15:41:16Z.
- Final host/shutdown audit: `D:\GitHub\Trading_Advisory_Chatbot\g21_closeout_host_audit_20261109.txt`. Existing Stage3 Verify passed; exact-clone events 18500/18601 prove start/OS boot, and event **18508 at 15:53:26.2980266Z** explicitly says the VM "was shut down by the guest operating system." The initial audit summary incorrectly expected different English wording; the preserved event was reviewed and a reconciliation appended without overwriting the original result. Final reconciliation PASS: both VMs Off, source ownership/historical evidence hashes match, and sealed/restored disks are not host-mounted. No VM action was performed.
- Validated procedure: `%USERPROFILE%\Downloads\G2_1_FG_Stage3_Operator_IncidentPinned_RESEND.ps1`; SHA-256 `0AADB828635973FF71588BB4ABEB0D501409D2ADE28A683C1CFB39B3587C5CDC`; PowerShell 5.1 parser errors: **0**. Its older Stage3 sibling is not the selected procedure.
- Probe media: `%LOCALAPPDATA%\G21-Probes-<local-session>\g2_1_probes.iso`; SHA-256 `C3F5419C0101F14814CF459D195672A50A650A9A1F3A5D7BFF12D7C721253396`.
- Harness: `scripts/g2_1_guest_probes.py`; SHA-256 `58A1D85BF79A90E732915257D8C50744E114A64054B6EC50ED103774FEB9AB54`. Recorded guest manifest pin: `8E9D9CDC0A761F80DDEB5F92F04B4B7F98E8A7D171D0521D2856C53471684B91`.

## Protected disks and VM state

| Artifact | Observed state and evidence boundary |
| --- | --- |
| Original `TradingAI-G2-Sandbox`, `b1132943-5e1c-456c-ae97-a78f74e4bdd1` | **Off at 16:07:49Z**; sole disk `D:\TradingAI_Sandbox\worker.vhdx`; original signed Debian DVD; never started or modified by this session. Final Stage3 Verify preserved its incident hash and isolation contract. |
| Clone `TradingAI-G2-FG-Disposable`, `35446044-18f5-48b0-bb36-077e7b7dc4ce` | **Off at 16:07:49Z** after verified normal guest-OS shutdown; sole disk `D:\TradingAI_G21_FG_Disposable\runtime\worker.restored.vhdx`. Final guards verified expected ownership note/location, Gen2, static 1 GiB, one CPU, Secure Boot, no NIC/integrations/COM mapping/checkpoints/autostart. |
| Sealed `baseline\worker.sealed.vhdx` | Read-only; SHA-256 `F4295DF728800C82FA04BD0EEF3281888879C76CEF77525FC39A671264070284`. Unchanged. |
| Restored `runtime\worker.restored.vhdx` before boot | Same SHA-256 as sealed baseline. A successful boot may change these runtime bytes; never repin or overwrite the sealed baseline to match. |
| Original disk after investigated incident | SHA-256 `B17942FC468CF3D7B29142FD3F3DC74ABF2A20F86E6758569F7EF436DE5085D3`; 1,715,470,336 bytes; write UTC 13:31:09.1512635. Matches the incident-pinned procedure and host events; distinct from the sealed baseline. |
| Old `runtime\worker.runtime.vhdx` | Preserved; not overwritten, restored, attached for G or deleted by this session. |

The source owner receipt SHA-256 matches the provision receipt (`189AB84735EF22A56CA31C5E7D45D74F33C4329779284059C9EFDD203357D80F`). The historical host inventory JSON also matches its provision-receipt pin (`000EA6AB9E34621874B836FD4E8DD0AB423623E7696C053009801F18B9481C8E`). Neither match proves installed-image lineage.

## Final residual blockers and disposition

- **G evidence qualification:** `OPERATOR_ATTESTED`; independent machine-readable guest evidence not captured. This closes the operator workflow, not formal independent verification. No additional screenshots, boots or probes are requested.
- **B: INCONCLUSIVE:** independent Basic Session/no-other-sharing/resource-or-secret-exposure and reviewed guest-inventory attestation remains incomplete. Host isolation inventory alone is insufficient.
- **H: INCONCLUSIVE:** independent installed-image lineage linking the installed guest/baseline to authenticated installation history and accepted clean state remains incomplete. Media signatures/current hashes/byte copies do not prove that history. The original incident does not replace the sealed baseline.

The unchanged Stage3 Closeout explicitly accepts operator attestation. Its existing `MARKER_ABSENT_AFTER_G_VERIFIED` stdin gate was satisfied under the operator's explicit directive, after its deterministic Off/identity/hash/isolation checks. Receipt: `D:\TradingAI_G21_FG_Disposable\evidence\stage3_closeout.json`. Execution/evidence log: `D:\GitHub\Trading_Advisory_Chatbot\g21_operator_attested_closeout_20261109.txt`. No mandatory Closeout gate was bypassed. B/H and formal independent G proof are not supplied by this receipt. Full acceptance and G2.2 remain unauthorized.

## Next product milestone (proposed, not implemented)

**Read-only computational specification review and clarification response.** The current orchestrator returns only a status sentence, while QueryPlan already carries the typed specification, missing/conflicting fields, provenance and data assessments. Extend that existing response to show the objective, formula/parameters, data requirements and precise clarification needs, keeping suggestions distinct from user facts. Reuse `QueryPlanAssembler._computational_plan`, the existing computational branch in `src/orchestrator.py`, and `scripts/test_computational_specification.py`; no new service or semantic call is needed.

Dependencies: existing G1 semantic/resolution contracts only. G2.1 full acceptance, G2.2, a worker, provider code generation and broker access are not dependencies. Keep data assessments NOT_CHECKED and execution_allowed=False. Smallest slice: one response formatter at the existing orchestrator boundary plus compact complete/incomplete/conflicting/suggested-input tests. This is a proposal, not a delivered capability or execution authorization.

## Changes and verification

- Reused validated procedures; no production code or procedure edits, VM provisioning, F repeat, RestoreG repeat, baseline replacement, disk deletion, networking, SSH, integrations, sharing, generated trading code or MT5 orders.
- Administrator access and BootAfterG were explicitly approved. Direct tool elevation alone lacked Hyper-V permission; UAC launch was used. The existing exact-phrase gate was satisfied through standard input after approval; no terminal UI commands or authentication dialogs were automated. Only the clone was started, once.
- Existing staged/unstaged/untracked work was preserved; no reset, stash, clean, commit or push.
- Verification level: **FOCUSED_PASS**, limited to document checks, host Stage3 Verify and normal-shutdown reconciliation; not full G2.1 acceptance. `.\venv\Scripts\python.exe -m pytest scripts/test_documentation_integrity.py -q -p no:cacheprovider --tb=short`: **13 passed**. PowerShell parser: **0 errors**. No full regression or application restart needed for this evidence/documentation-only scope.
- Not independently verified: G guest observations, B attestation and installed-image lineage. Implemented/completed: existing operator-attested Closeout, normal-shutdown reconciliation and final Off checks. G2.1 remains PARTIAL.
- Not implemented: G2.2 and generated execution. No authority is granted by a checksum, hypervisor Running state or this report.
- Documentation: final report, affected G2.1 handoff and changelog updated. Next step: implement the proposed read-only specification review slice; no further G2.1 evidence work unless a concrete safety-critical dependency requires it. Both VMs, all VHDXs and prior evidence remain preserved.
