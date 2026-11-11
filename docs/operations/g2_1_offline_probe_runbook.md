# G2.1 Offline Probe Runbook

Operator only. Build and inspect the ISO without Hyper-V privileges. Do not copy the repository, change the receipt, enable networking/integration/sharing, or mount a guest VHDX on Windows. F (forced power-off) and G (image recovery) are excluded. See the [A-H evidence matrix](../../TRADING_ADVISORY_CHATBOT_FULL_HANDOFF.md#132-g21-hyper-v-benign-acceptance-handoff).

## 1. Build and verify on Windows

From the repository in **Windows PowerShell 5.1**, build to a new local directory outside the repository and `D:\TradingAI_Sandbox`:

```powershell
$pin = '58a1d85bf79a90e732915257d8c50744e114a64054b6ec50ed103774feb9ab54'
$out = Join-Path $env:LOCALAPPDATA ('G21-Probes-' + [guid]::NewGuid().ToString('N'))
$probeMedia = & .\scripts\g2_1_probe_media.ps1 -OutputDirectory $out -ExpectedHarnessSha256 $pin
$probeMedia | Format-List
```

This pin is for the reviewed checkout's exact file bytes. If it differs, stop and review the source/line endings before using a new independently recorded pin. The built-in IMAPI2 builder creates a non-bootable ISO9660/Joliet image with exactly `g2_1_guest_probes.py` and one-line ASCII/LF `SHA256SUMS`. It reads both files back via Windows `tar.exe` and compares their hashes before publishing `g2_1_probes.iso`. Do not attach a `.partial` or any artifact without `MEDIA_VERIFIED`. The two payload bytes are reproducible; IMAPI image metadata can vary across builds. Pin the specific built ISO's hash and the manifest hash from the host result. Keep the output in an operator-controlled directory; do not edit or replace the ISO after verification.

## 2. Operator-only temporary DVD swap

In operator-owned **elevated Windows PowerShell**, set `$media` to the same `IsoPath`, `ManifestPath`, `SignaturePath`, and `DebianKeyringPath` used for provisioning. Set `$probeIso` and `$probeIsoSha256` from the `MEDIA_VERIFIED` output. Keep this session open through restoration, and record VM ID, original DVD path, controller/location and original ISO SHA-512 locally in case the session closes.

```powershell
$ErrorActionPreference = 'Stop'
$probeIso = Read-Host 'MEDIA_VERIFIED IsoPath (absolute path)'
$probeIsoSha256 = Read-Host 'MEDIA_VERIFIED IsoSha256'
$v, $gate = @(& .\scripts\g2_1_hyperv_worker.ps1 -Mode Verify @media)
$plan = & .\scripts\g2_1_hyperv_worker.ps1 -Mode Plan
if ($v.Status -cne 'VERIFIED_OFF' -or $v.VM -cne 'TradingAI-G2-Sandbox' -or
    $gate.BootRAMGate -ne $true -or $plan.DiskReady -ne $true) { throw 'STOP: host preflight' }
$vm = Get-VM -Id $v.Id
$dvd = @(Get-VMDvdDrive -VM $vm)
$originalIso = (Get-Item -LiteralPath $media.IsoPath).FullName
if ($vm.Name -cne $v.VM -or $vm.State -ne 'Off' -or $dvd.Count -ne 1 -or
    $dvd[0].Path -ine $originalIso -or (Get-FileHash -LiteralPath $probeIso -Algorithm SHA256).Hash -ine $probeIsoSha256) {
    throw 'STOP: wrong VM/DVD or probe ISO hash mismatch'
}
$controller = $dvd[0].ControllerNumber
$location = $dvd[0].ControllerLocation
$ownerNote = $vm.Notes # Keep local; do not include the ownership token in shared evidence.
Set-VMDvdDrive -VMDvdDrive $dvd[0] -Path $probeIso -Confirm
$current = @(Get-VMDvdDrive -VM (Get-VM -Id $v.Id))
if ($current.Count -ne 1 -or $current[0].ControllerNumber -ne $controller -or
    $current[0].ControllerLocation -ne $location -or $current[0].Path -ine $probeIso) { throw 'STOP: swap not verified' }
```

Use only the existing DVD device. Verify requires **exactly one DVD** at the original signed Debian ISO path and the receipt's SHA-512, in addition to the VM UUID/name/ownership note/location, Off state, owned disk, firmware and isolation settings. It is expected to reject the temporary ISO; **do not** change the receipt or treat that rejection as a waiver. The non-bootable data ISO has no installer. Immediately before a manual boot, rerun `-Mode Plan` and check `BootRAMGate=True` (at least 3 GiB free) and `DiskReady=True`. Use **Basic Session** and boot the existing Debian disk; stop if it does not boot or if the installer appears. Do not change firmware, Secure Boot, or boot order.

## 3. Verify guest identity and media, then run A-E and H

From the root Basic Session console, read `getent passwd g2worker`, `id g2worker`, and `passwd -S g2worker`. Require an existing dedicated account with nonzero UID/GID, private primary group and no supplementary groups, shell `/usr/sbin/nologin` or `/bin/false`, locked password (`L`) and no delegated administrative access. If absent or ambiguous, **stop before running**; do not create an account or install packages under this task. Check `python3 --version`, `findmnt -n -o FSTYPE /sys/fs/cgroup` (`cgroup2`), and that `/usr/bin/python3`, `/usr/bin/systemd-run`, `/usr/sbin/ip` are executable. Record `systemctl is-enabled ssh.service ssh.socket` and `systemctl is-active ssh.service ssh.socket`, and inspect mounts/devices for unexpected shares without displaying secrets. Unknown evidence remains inconclusive.

Use `lsblk -o NAME,TYPE,RO,FSTYPE,LABEL` to identify the `G21_PROBES` optical device. Use the following only if that device is `/dev/sr0`; otherwise replace that literal with the verified device. Use an empty unmounted `/mnt`. Type the **host-recorded** `ManifestSha256` at the prompt (not a value read from the disc):

```sh
(
  set -eu
  export LC_ALL=C
  read -r -p 'Host ManifestSha256: ' manifest_hash
  printf '%s\n' "$manifest_hash" | grep -Eq '^[0-9a-f]{64}$'
  ! mountpoint -q /mnt || exit 1
  test -z "$(find /mnt -mindepth 1 -maxdepth 1 -print -quit)"
  mount -t iso9660 -o ro,nodev,nosuid,noexec /dev/sr0 /mnt
  trap 'cd /; umount /mnt' EXIT
  findmnt -n -o SOURCE,FSTYPE,OPTIONS --mountpoint /mnt
  options=$(findmnt -n -o OPTIONS --mountpoint /mnt)
  for flag in ro nodev nosuid noexec; do
    case ",$options," in *",$flag,"*) ;; *) exit 1 ;; esac
  done
  cd /mnt
  test "$(find . -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)" = "$(printf '%s\n' SHA256SUMS g2_1_guest_probes.py)"
  test -f SHA256SUMS && test ! -L SHA256SUMS || exit 1
  test -f g2_1_guest_probes.py && test ! -L g2_1_guest_probes.py || exit 1
  printf '%s  SHA256SUMS\n' "$manifest_hash" | sha256sum --check --strict -
  sha256sum --check --strict SHA256SUMS
  rc=0
  /usr/bin/python3 -I -B /mnt/g2_1_guest_probes.py || rc=$?
  printf 'Harness exit=%s\n' "$rc"
  exit "$rc"
)
```

Any unexpected media entry, failed hash, bad mount, or prerequisite failure means **no harness run**. Record UTC, VM ID from the host, the three host SHA-256 values, mount/options and checksum results, plus the harness output and exit code. Copy only the evidence lines manually. `A_GUEST PASS` requires the kernel to reject the test connection; B remains `INCONCLUSIVE` without independent operator inventory. C/D require `EROFS`/`EACCES` respectively. E requires observed CPU throttling, fork rejection with `pids.events`, cgroup OOM kill, and the separate systemd timeout without completion. A contradiction can produce `FAIL`; missing or unexpected evidence is `INCONCLUSIVE`. Exit `1` means failed check; `2` means incomplete even if the guest checks pass. H must be scored separately: compare C's fixture hash against the handoff, record the signed installer Verify and host/guest media hashes, and leave installed-image provenance incomplete if not independently pinned. F/G are not executed by the harness.

E uses a 1.5s CPU loop at 25%, at most six fork attempts (children sleep 3s), and one 96 MiB allocation attempt after checking the cgroup's 64 MiB hard cap and zero swap. The resource unit has a 15s limit; the timer unit has a 2s limit. If the console is still responsive and a run stalls, interrupt the foreground command, list `systemctl list-units --all 'g2-probe-*.service'`, inspect the exact unit from this run, and `systemctl stop <exact-unit>.service` if it remains active. Do not rerun on a failure or stop unrelated units. Use normal guest shutdown (`systemctl poweroff`); if the guest cannot shut down cleanly, stop and ask the operator for recovery. No forced power-off of this VM is authorized here.

## 4. Restore the original ISO while Off

With the same recorded session values, verify the exact VM and DVD again. If the session closed, reconstruct the values from the recorded preflight and the protected ownership receipt, not from an assumed DVD path. If any state is unexpected, stop without changing it.

```powershell
$vm = Get-VM -Id $v.Id
$current = @(Get-VMDvdDrive -VM $vm)
if ($vm.Name -cne $v.VM -or $vm.Notes -cne $ownerNote -or $vm.State -ne 'Off' -or $current.Count -ne 1 -or
    $current[0].ControllerNumber -ne $controller -or $current[0].ControllerLocation -ne $location -or
    $current[0].Path -ine $probeIso -or (Get-FileHash -LiteralPath $originalIso -Algorithm SHA512).Hash -ine $v.IsoSha512) {
    throw 'STOP: unexpected VM/DVD/media state; do not restore blindly'
}
Set-VMDvdDrive -VMDvdDrive $current[0] -Path $originalIso -Confirm
& .\scripts\g2_1_hyperv_worker.ps1 -Mode Verify @media
```

Require `VERIFIED_OFF` for the original VM ID and signed ISO. Leave it Off. Do not use `Rollback`, which removes sandbox resources rather than restoring a DVD assignment. Do not proceed to G2.2.
