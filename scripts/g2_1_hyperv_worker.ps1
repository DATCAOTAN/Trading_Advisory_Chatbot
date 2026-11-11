#Requires -Version 5.1
<#
.SYNOPSIS
Plan, provision OFF, verify, or roll back the dedicated G2.1 worker.
.DESCRIPTION
No download, boot, guest installation, or global host configuration. Run
Provision, Verify and Rollback from an operator-owned elevated PowerShell.
The public keyring must contain the Debian CD signing key from debian.org/CD/verify.
Media must be local and outside D:\TradingAI_Sandbox.
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param(
    [ValidateSet('Plan', 'Provision', 'Verify', 'Rollback')]
    [string]$Mode = 'Plan',
    [string]$IsoPath,
    [string]$ManifestPath,
    [string]$SignaturePath,
    [string]$DebianKeyringPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$vmName = 'TradingAI-G2-Sandbox'
$root = 'D:\TradingAI_Sandbox'
$diskPath = Join-Path $root 'worker.vhdx'
$receiptPath = Join-Path $root 'g2_1-owner.json'
$isoName = 'debian-13.7.0-amd64-DVD-1.iso'
$signer = 'DF9B9C49EAA9298432589D76DA87E80D6294BE9B'
$diskBytes = 8GB

function Get-PlainItem([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    for ($parent = $item; $null -ne $parent; ) {
        if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Reparse point refused: $($parent.FullName)"
        }
        if ($parent -is [IO.FileInfo]) { $parent = $parent.Directory }
        else { $parent = $parent.Parent }
    }
    return $item
}

function Test-InSandbox([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    return $full -ieq $root -or $full.StartsWith("$root\", [StringComparison]::OrdinalIgnoreCase)
}

function Assert-DebianSignature([string]$Manifest, [string]$Signature, [string]$Keyring) {
    # Use an installed verifier, never a binary from the supplied media.
    $verifier = Get-Command gpgv.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($verifier) { $exe = $verifier.Source }
    else {
        $exe = Join-Path $env:ProgramFiles 'Git\usr\bin\gpgv.exe'
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Trusted gpgv.exe not found.' }
    }
    # Git for Windows resolves --keyring using MSYS paths.
    $cygpath = Join-Path (Split-Path -Parent $exe) 'cygpath.exe'
    if (Test-Path -LiteralPath $cygpath -PathType Leaf) {
        $Keyring = & $cygpath -u -- $Keyring
        if ($LASTEXITCODE -ne 0 -or -not $Keyring) { throw 'Cannot resolve the verifier keyring path.' }
    }
    $result = & {
        # Windows PowerShell treats even redirected native stderr as an error.
        $ErrorActionPreference = 'Continue'
        $lines = @(& $exe --status-fd 1 --keyring $Keyring -- $Signature $Manifest 2>$null)
        [pscustomobject]@{ ExitCode = $LASTEXITCODE; Lines = $lines }
    }
    if ($result.ExitCode -ne 0 -or @($result.Lines | Where-Object { $_ -match '^\[GNUPG:\] (BADSIG|ERRSIG|EXPSIG|EXPKEYSIG|REVKEYSIG|KEYEXPIRED|SIGEXPIRED)\b' }).Count -or
        @($result.Lines | Where-Object { $_ -match "^\[GNUPG:\] VALIDSIG $signer " }).Count -ne 1) {
        throw 'Manifest signature is not valid under the pinned Debian CD signing key.'
    }
}

function Get-DebianMedia([switch]$KeepIsoLocked) {
    $paths = @($IsoPath, $ManifestPath, $SignaturePath, $DebianKeyringPath)
    if (@($paths | Where-Object { -not $_ }).Count) {
        throw 'Provide IsoPath, ManifestPath, SignaturePath and DebianKeyringPath together.'
    }
    $items = @(
        foreach ($path in $paths) {
            $item = Get-PlainItem $path
            if ($item -isnot [IO.FileInfo] -or $item.FullName -notmatch '^[A-Za-z]:\\' -or (Test-InSandbox $item.FullName)) {
                throw 'Media inputs must be local regular files outside the sandbox.'
            }
            $item
        }
    )
    if ($items[0].Name -cne $isoName -or $items[0].Length -ne 3992977408 -or
        $items[1].Name -cne 'SHA512SUMS' -or $items[2].Name -cne 'SHA512SUMS.sign') {
        throw "Wrong media: expected $isoName (3992977408 bytes), SHA512SUMS and SHA512SUMS.sign."
    }

    $locks = @()
    try {
        foreach ($item in $items) {
            $locks += [IO.File]::Open($item.FullName, 'Open', 'Read', 'Read')
        }
        Assert-DebianSignature $items[1].FullName $items[2].FullName $items[3].FullName
        $line = @(Get-Content -LiteralPath $items[1].FullName | Where-Object { $_ -cmatch ('^[a-fA-F0-9]{128} [ *]' + [regex]::Escape($isoName) + '$') })
        if ($line.Count -ne 1) { throw 'Signed manifest does not uniquely identify the selected ISO.' }
        $expected = $line[0].Substring(0, 128)
        $actual = (Get-FileHash -InputStream $locks[0] -Algorithm SHA512).Hash
        if ($actual -ine $expected) { throw 'ISO SHA-512 does not match the signed manifest.' }
        $isoLock = $null
        if ($KeepIsoLocked) {
            $isoLock = $locks[0]
            $locks[0] = $null
        }
        return [pscustomobject]@{ Path = $items[0].FullName; Sha512 = $actual; IsoLock = $isoLock }
    }
    finally {
        foreach ($lock in $locks) { if ($null -ne $lock) { $lock.Dispose() } }
    }
}

function Write-Receipt($Receipt) {
    $Receipt | ConvertTo-Json | Set-Content -LiteralPath $receiptPath -Encoding UTF8
}

function Read-Receipt {
    $file = Get-PlainItem $receiptPath
    if ($file -isnot [IO.FileInfo] -or $file.FullName -ine $receiptPath) { throw 'Invalid ownership receipt path.' }
    $receipt = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
    if ($receipt.Version -ne 1 -or $receipt.Token -cnotmatch '^[0-9a-f]{32}$') { throw 'Invalid ownership receipt.' }
    return $receipt
}

function Get-OwnerNote($Receipt) { return "G2.1 ownership: $($Receipt.Token)" }

function Assert-OwnedVM($VM, $Receipt) {
    if ($VM.Id -ne [guid]$Receipt.VmId -or $VM.Name -cne $vmName -or $VM.Notes -cne (Get-OwnerNote $Receipt) -or
        -not (Test-InSandbox $VM.ConfigurationLocation) -or $VM.State -ne 'Off') {
        throw 'VM ownership, location or OFF state could not be verified.'
    }
    $null = Get-PlainItem $VM.ConfigurationLocation
}

function Assert-OwnedDisk($Receipt) {
    $file = Get-PlainItem $diskPath
    if ($file -isnot [IO.FileInfo] -or $file.FullName -ine $diskPath) { throw 'Invalid owned disk path.' }
    $vhd = Get-VHD -Path $diskPath
    if (-not $Receipt.DiskId -or [guid]$Receipt.DiskId -eq [guid]::Empty -or $vhd.DiskIdentifier -ne [guid]$Receipt.DiskId -or
        $vhd.VhdFormat -ne 'VHDX' -or $vhd.VhdType -ne 'Dynamic' -or $vhd.ParentPath -or $vhd.Size -ne $diskBytes) {
        throw 'Disk identity or layout could not be verified.'
    }
    return $vhd
}

function Assert-ConfiguredVM($VM, $Receipt, $Media) {
    Assert-OwnedVM $VM $Receipt
    $memory = Get-VMMemory -VM $VM
    $drives = @(Get-VMHardDiskDrive -VM $VM)
    $dvds = @(Get-VMDvdDrive -VM $VM)
    $firmware = Get-VMFirmware -VM $VM
    if ($VM.Generation -ne 2 -or $VM.ProcessorCount -ne 1 -or $memory.DynamicMemoryEnabled -or
        $memory.Startup -ne 1GB -or $VM.AutomaticStartAction -ne 'Nothing' -or $VM.CheckpointType -ne 'Disabled' -or
        $VM.AutomaticCheckpointsEnabled -or
        @(Get-VMNetworkAdapter -VM $VM).Count -ne 0 -or
        @(Get-VMIntegrationService -VM $VM | Where-Object Enabled).Count -ne 0 -or
        @(Get-VMComPort -VM $VM | Where-Object Path).Count -ne 0 -or
        $drives.Count -ne 1 -or $drives[0].Path -ine $diskPath -or
        $dvds.Count -ne 1 -or $dvds[0].Path -ine $Media.Path -or
        $Receipt.IsoPath -ine $Media.Path -or $Receipt.IsoSha512 -ine $Media.Sha512 -or
        $firmware.SecureBoot -ne 'On' -or $firmware.SecureBootTemplate -ne 'MicrosoftUEFICertificateAuthority') {
        throw 'Sandbox configuration verification failed. Do not boot.'
    }
    $null = Assert-OwnedDisk $Receipt
    [pscustomobject]@{ Status = 'VERIFIED_OFF'; VM = $VM.Name; Id = $VM.Id; IsoSha512 = $Media.Sha512 }
}

function Assert-NoOtherDiskUsers([guid]$OwnerId) {
    foreach ($other in @(Get-VM | Where-Object Id -ne $OwnerId)) {
        $drives = @(Get-VMHardDiskDrive -VM $other)
        foreach ($snapshot in @(Get-VMSnapshot -VM $other)) {
            $drives += @(Get-VMHardDiskDrive -VMSnapshot $snapshot)
        }
        foreach ($drive in $drives) {
            $path = $drive.Path
            $seen = @{}
            while ($path) {
                $path = (Get-PlainItem $path).FullName
                if ($path -ieq $diskPath -or $seen.ContainsKey($path)) {
                    throw 'Another VM references the worker disk or its disk chain is ambiguous.'
                }
                $seen[$path] = $true
                $path = (Get-VHD -Path $path).ParentPath
            }
        }
    }
}

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$os = Get-CimInstance Win32_OperatingSystem
$volume = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='D:'"
$availableGiB = [math]::Round($os.FreePhysicalMemory / 1MB, 3)
$canBoot = $os.FreePhysicalMemory -ge (3 * 1MB)
$diskReady = $null -ne $volume -and $volume.DriveType -eq 3 -and $volume.FileSystem -eq 'NTFS' -and $volume.FreeSpace -ge (20GB)
$pathExists = Test-Path -LiteralPath $root

if ($Mode -eq 'Plan') {
    $nameState = 'UNKNOWN_NOT_ELEVATED'
    if ($admin) {
        $nameState = if (@(Get-VM | Where-Object Name -eq $vmName).Count) { 'IN_USE' } else { 'AVAILABLE' }
    }
    $mediaState = 'NOT_SUPPLIED'
    if ($IsoPath -or $ManifestPath -or $SignaturePath -or $DebianKeyringPath) {
        $media = Get-DebianMedia
        $mediaState = "VERIFIED_SHA512=$($media.Sha512)"
    }
    [pscustomobject]@{
        Mode = 'Plan'; Elevated = $admin; VM = $vmName; NameState = $nameState
        Root = $root; PathExists = $pathExists; DiskReady = $diskReady; Media = $mediaState
        AvailableRAMGiB = $availableGiB; BootRAMGate = $canBoot; BootAction = 'NONE'
        Planned = 'Gen2, 1 vCPU, 1 GiB static, 8 GiB dynamic VHDX, no NIC, no integrations, no auto-start'
    }
    return
}
if (-not $admin) { throw 'Run this mode in operator-owned PowerShell as Administrator.' }

switch ($Mode) {
    'Provision' {
        if ($pathExists -or @(Get-VM | Where-Object Name -eq $vmName).Count) { throw 'Sandbox path or VM name is already in use.' }
        if (-not $diskReady) { throw 'D: must be a fixed NTFS volume with at least 20 GiB available.' }
        $media = Get-DebianMedia -KeepIsoLocked
        try {
            if (-not $PSCmdlet.ShouldProcess($root, 'Create one dedicated Hyper-V VM in OFF state')) { return }
            if ((Test-Path -LiteralPath $root) -or @(Get-VM | Where-Object Name -eq $vmName).Count) {
                throw 'Sandbox path or VM name changed during preflight.'
            }
            $null = New-Item -Path $root -ItemType Directory
            $receipt = [pscustomobject]@{
                Version = 1; Token = [guid]::NewGuid().ToString('N'); VmId = ''; DiskId = ''
                IsoPath = $media.Path; IsoSha512 = $media.Sha512
            }
            Write-Receipt $receipt
            $vm = New-VM -Name $vmName -Path $root -Generation 2 -MemoryStartupBytes 1GB -NoVHD
            $receipt.VmId = $vm.Id.ToString()
            Write-Receipt $receipt
            Set-VM -VM $vm -Notes (Get-OwnerNote $receipt) -AutomaticStartAction Nothing -ProcessorCount 1 `
                -StaticMemory -MemoryStartupBytes 1GB -CheckpointType Disabled -AutomaticCheckpointsEnabled $false
            Get-VMNetworkAdapter -VM $vm | Remove-VMNetworkAdapter -Confirm:$false
            Get-VMIntegrationService -VM $vm | Where-Object Enabled | Disable-VMIntegrationService
            if (Test-Path -LiteralPath $diskPath) { throw 'Worker disk path unexpectedly exists.' }
            $null = New-VHD -Path $diskPath -Dynamic -SizeBytes $diskBytes
            $vhd = Get-VHD -Path $diskPath
            if (-not $vhd.DiskIdentifier -or $vhd.DiskIdentifier -eq [guid]::Empty) { throw 'No stable VHDX identifier.' }
            $receipt.DiskId = $vhd.DiskIdentifier.ToString()
            Write-Receipt $receipt
            Add-VMHardDiskDrive -VM $vm -Path $diskPath
            $dvd = Add-VMDvdDrive -VM $vm -Path $media.Path -Passthru
            Set-VMFirmware -VM $vm -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority -FirstBootDevice $dvd
            Assert-ConfiguredVM (Get-VM -Id $vm.Id) $receipt $media
        }
        catch {
            Write-Warning 'Provision did not complete. No automatic cleanup or boot. Review the ownership receipt before rollback.'
            throw
        }
        finally { $media.IsoLock.Dispose() }
    }
    'Verify' {
        $receipt = Read-Receipt
        $media = Get-DebianMedia
        Assert-ConfiguredVM (Get-VM -Id ([guid]$receipt.VmId)) $receipt $media
        [pscustomobject]@{ AvailableRAMGiB = $availableGiB; BootRAMGate = $canBoot; BootAction = 'NONE' }
    }
    'Rollback' {
        $receipt = Read-Receipt
        $id = [guid]$receipt.VmId
        if ($id -eq [guid]::Empty) { throw 'No recorded VM ID. Inspect partial resources manually; nothing was deleted.' }
        $vm = Get-VM | Where-Object Id -eq $id
        if ($vm) {
            Assert-OwnedVM $vm $receipt
            if (@(Get-VMSnapshot -VM $vm).Count -or @(Get-VMHardDiskDrive -VM $vm | Where-Object Path -ine $diskPath).Count) {
                throw 'Unexpected snapshots or disks. Nothing was deleted.'
            }
        }
        if (@(Get-VM | Where-Object { $_.Name -eq $vmName -and $_.Id -ne $id }).Count) {
            throw 'Sandbox name belongs to a different VM. Nothing was deleted.'
        }
        $hasDisk = Test-Path -LiteralPath $diskPath
        if ($hasDisk) {
            $null = Assert-OwnedDisk $receipt
            Assert-NoOtherDiskUsers $id
        }
        if (-not $PSCmdlet.ShouldProcess("$vmName / $id", 'Remove the recorded VM and its recorded disk only')) { return }
        if ((Read-Host "Confirm only this VM and disk; type ROLLBACK $id") -cne "ROLLBACK $id") {
            throw 'Rollback cancelled. Nothing was deleted.'
        }
        if ($vm) {
            $vm = Get-VM -Id $id
            Assert-OwnedVM $vm $receipt
            if (@(Get-VMSnapshot -VM $vm).Count -or @(Get-VMHardDiskDrive -VM $vm | Where-Object Path -ine $diskPath).Count) {
                throw 'Unexpected snapshots or disks after confirmation. Nothing was deleted.'
            }
            Remove-VM -VM $vm -Confirm:$false
        }
        if ($hasDisk) {
            Assert-NoOtherDiskUsers $id
            $vhd = Assert-OwnedDisk $receipt
            if ($vhd.Attached) { throw 'Disk still attached. Disk and receipt retained.' }
            Remove-Item -LiteralPath $diskPath
        }
        # Keep the receipt as evidence; never recursively remove the sandbox.
        [pscustomobject]@{ Status = 'ROLLED_BACK'; Id = $id; ReceiptRetained = $receiptPath }
    }
}
