#Requires -Version 5.1
[CmdletBinding(DefaultParameterSetName='Build')]
param(
    [Parameter(Mandatory)][string]$InputDirectory,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ManifestSha256,
    [Parameter(Mandatory,ParameterSetName='Build')][string]$OutputIso,
    [Parameter(Mandatory,ParameterSetName='Guest')][switch]$StageGuest
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert-G4OfflineGuest {
    try {
        $system=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        $adapters=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop)
    } catch { throw 'GUEST_NETWORK_INSPECTION_INCONCLUSIVE' }
    if($system.Manufacturer -ne 'Microsoft Corporation' -or $system.Model -ne 'Virtual Machine') {
        throw 'OFFLINE_HYPERV_GUEST_REQUIRED'
    }
    # Prefer driver identity; only the confirmed absent Windows name-only family is exempt below.
    $wan=@{
        'ms_ndiswanip'='WAN Miniport (IP)'; 'ms_ndiswanipv6'='WAN Miniport (IPv6)'
        'ms_ndiswanbh'='WAN Miniport (Network Monitor)'; 'ms_pptpminiport'='WAN Miniport (PPTP)'
        'ms_l2tpminiport'='WAN Miniport (L2TP)'; 'ms_agilevpnminiport'='WAN Miniport (IKEv2)'
        'ms_sstpminiport'='WAN Miniport (SSTP)'; 'ms_pppoeminiport'='WAN Miniport (PPPOE)'
    }
    $absentPseudo=@('Teredo Tunneling Pseudo-Interface','Microsoft 6to4 Adapter','6to4 Adapter',
        'Microsoft IP-HTTPS Platform Interface','Microsoft Kernel Debug Network Adapter')
    $nameOnlyPseudo=@('Teredo Tunneling Pseudo-Interface','Microsoft IP-HTTPS Platform Interface','6to4 Adapter')
    foreach($adapter in $adapters) {
        if($null -eq $adapter) { throw 'GUEST_NETWORK_METADATA_MISSING: NULL_ADAPTER' }
        $hardware=$adapter.PSObject.Properties['HardwareInterface']
        $component=$adapter.PSObject.Properties['ComponentID']
        $description=$adapter.PSObject.Properties['InterfaceDescription']
        $status=$adapter.PSObject.Properties['Status']
        $nameProperty=$adapter.PSObject.Properties['Name']
        $id=if($null -ne $component){[string]$component.Value}else{''}
        $driver=if($null -ne $description){[string]$description.Value}else{''}
        $state=if($null -ne $status){[string]$status.Value}else{''}
        $name=if($null -ne $nameProperty){[string]$nameProperty.Value}else{''}
        if($null -eq $hardware -or $hardware.Value -isnot [bool]) { $reason='MISSING_OR_INVALID_HARDWARE_METADATA' }
        elseif($hardware.Value) { $reason='HARDWARE_NIC_PRESENT' }
        elseif($name -cin $nameOnlyPseudo) {
            if($null -eq $component -or $null -eq $description) { $reason='NAME_ONLY_IDENTITY_PROPERTY_MISSING' }
            elseif($id -or $driver) { $reason='NAME_ONLY_IDENTITY_NOT_EMPTY' }
            elseif($null -eq $status -or !$state) { $reason='NAME_ONLY_STATUS_MISSING' }
            elseif($state -cne 'Not Present') { $reason='NAME_ONLY_STATUS_NOT_ABSENT' }
            else { continue }
        }
        elseif($wan.ContainsKey($id) -and (!$driver -or $driver -eq $wan[$id])) { continue }
        elseif(!$id -and $driver -in $wan.Values) { continue }
        elseif($driver -in $absentPseudo) {
            # These interfaces can carry network traffic when present. Only Not Present is exempt.
            if($state -eq 'Not Present') { continue }
            $reason=if(!$state){'MISSING_PSEUDO_STATUS'}else{'PSEUDO_INTERFACE_NOT_ABSENT'}
        } elseif(!$id -and !$driver -and !$name) { $reason='ADAPTER_IDENTITY_MISSING' }
        else { $reason='UNRECOGNIZED_OR_CONFLICTING_ADAPTER_IDENTITY' }
        # Bounded identity/status fields only; no GUID, MAC or IP.
        $details=[ordered]@{Reason=$reason;Name=$name.Substring(0,[Math]::Min(160,$name.Length));
            InterfaceDescription=$driver.Substring(0,[Math]::Min(160,$driver.Length));
            ComponentID=$id.Substring(0,[Math]::Min(160,$id.Length));Status=$state.Substring(0,[Math]::Min(40,$state.Length))}
        throw ('GUEST_NETWORK_INTERFACE_PRESENT_OR_UNCLASSIFIED: '+($details | ConvertTo-Json -Compress))
    }
}
$expected=@('bars.tsv','ticks.tsv','source_ticks.jsonl','G4Import.mq5','G4ImportPins.mqh','README.txt','g4_import_media.ps1')
$root=Get-Item -LiteralPath $InputDirectory -Force
for($p=$root; $null -ne $p; $p=$p.Parent) {
    if($p.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE_PATH_REFUSED' }
}
$entries=@(Get-ChildItem -LiteralPath $root.FullName -Force)
if(!$root.PSIsContainer -or $entries.Count -ne 8 -or @($entries | Where-Object {
    $_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $_.Name -cnotin ($expected+@('manifest.json'))
}).Count) { throw 'MEDIA_ALLOWLIST_MISMATCH' }
$manifestPath=Join-Path $root.FullName 'manifest.json'
if((Get-FileHash -LiteralPath $manifestPath).Hash -ine $ManifestSha256) { throw 'MANIFEST_PIN_MISMATCH' }
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if($manifest.schema_version -cne 'g4-custom-import-media/v1' -or $manifest.native_execution_authorized -ne $false -or
    $manifest.shift_seconds -ne 0 -or $manifest.files.PSObject.Properties.Name.Count -ne 7) { throw 'WRONG_MEDIA_CONTRACT' }
foreach($name in $expected) {
    $path=Join-Path $root.FullName $name
    if((Get-Item -LiteralPath $path).Length -gt 12MB -or (Get-FileHash -LiteralPath $path).Hash -ine $manifest.files.$name) {
        throw "MEDIA_PIN_MISMATCH: $name"
    }
}
if($StageGuest) {
    Assert-G4OfflineGuest
    if([IO.DriveInfo]::new($root.PSDrive.Root).DriveType -ne 'CDRom') { throw 'READ_ONLY_DVD_REQUIRED' }
    if(Get-Process terminal64,MetaEditor64,metatester64 -ErrorAction SilentlyContinue) { throw 'CLOSE_GUEST_NATIVE_PROCESSES_FIRST' }
    $terminal=Join-Path $env:LOCALAPPDATA 'G3_MATH_A514_V3'
    if(!(Test-Path -LiteralPath (Join-Path $terminal 'terminal64.exe') -PathType Leaf)) { throw 'EXISTING_G3_TERMINAL_NOT_FOUND' }
    for($p=Get-Item -LiteralPath $terminal; $null -ne $p; $p=$p.Parent) {
        if($p.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE_PATH_REFUSED' }
    }
    $files=Join-Path $terminal 'MQL5\Files\G4Import'
    $services=Join-Path $terminal 'MQL5\Services'
    $servicesRoot=$services
    if($null -ne $manifest.PSObject.Properties['recovery']) {
        $recovery=$manifest.recovery
        if($recovery.guest_subdirectory -cnotmatch '^G4Import_[CR][a-f0-9]{8}$' -or
            $recovery.mode -cnotin @('CONFIGURATION_ONLY','IMPORT') -or
            $recovery.previous_importer_sha256 -cne '39ca5be17a0ab0c3f3827f98d0e38af91c18afcbb5883243f444137f725d86a3') {
            throw 'RECOVERY_STAGE_BINDING_INVALID'
        }
        $previous=Join-Path $services 'G4Import.mq5'
        $files=Join-Path $terminal ('MQL5\Files\'+$recovery.guest_subdirectory)
        $services=Join-Path $services $recovery.guest_subdirectory
    }
    foreach($directory in @((Join-Path $terminal 'MQL5'),(Join-Path $terminal 'MQL5\Files'),$servicesRoot,$services)) {
        if((Test-Path -LiteralPath $directory) -and ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'REPARSE_PATH_REFUSED'
        }
    }
    if($null -ne $manifest.PSObject.Properties['recovery']) {
        if(!(Test-Path -LiteralPath $previous -PathType Leaf) -or
            (Get-Item -LiteralPath $previous -Force).Attributes -band [IO.FileAttributes]::ReparsePoint -or
            (Get-FileHash -LiteralPath $previous).Hash -ine $recovery.previous_importer_sha256) {
            throw 'GUEST_V8_SOURCE_COMPARISON_FAILED_PRESERVE_EVIDENCE'
        }
        Write-Output 'GUEST_V8_SOURCE_SHA256_MATCH; previous source/profile untouched'
    }
    if((Test-Path -LiteralPath $files) -or (Test-Path -LiteralPath (Join-Path $services 'G4Import.mq5'))) {
        throw 'IMPORT_STAGE_ALREADY_EXISTS_PRESERVE_EVIDENCE'
    }
    $null=New-Item -ItemType Directory -Path $files
    if(!(Test-Path -LiteralPath $services)) { $null=New-Item -ItemType Directory -Path $services }
    foreach($name in @('bars.tsv','ticks.tsv','source_ticks.jsonl','manifest.json')) {
        [IO.File]::Copy((Join-Path $root.FullName $name),(Join-Path $files $name),$false)
    }
    foreach($name in @('G4Import.mq5','G4ImportPins.mqh')) {
        [IO.File]::Copy((Join-Path $root.FullName $name),(Join-Path $services $name),$false)
    }
    Write-Output "STAGED_ONLY: $terminal; no native executable invoked. Compile zero-errors/zero-warnings after separate approval."
    return
}
$iso=[IO.Path]::GetFullPath($OutputIso)
if($iso -notmatch '^[A-Za-z]:\\' -or (Test-Path -LiteralPath $iso) -or (Test-Path -LiteralPath "$iso.partial") -or
   [IO.DriveInfo]::new([IO.Path]::GetPathRoot($iso)).DriveType -ne 'Fixed') { throw 'NEW_LOCAL_ISO_REQUIRED' }
for($p=Get-Item -LiteralPath (Split-Path -Parent $iso); $null -ne $p; $p=$p.Parent) {
    if($p.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE_PATH_REFUSED' }
}
# Same bounded IMAPI IStream recipe as g2_1_probe_media.ps1; no disk mount or native terminal invocation.
if(-not ('G4IsoStream' -as [type])) {
Add-Type -TypeDefinition @'
using System; using System.IO; using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes;
public static class G4IsoStream {
 [DllImport("shlwapi.dll")][return: MarshalAs(UnmanagedType.Interface)]
 public static extern IStream SHCreateMemStream(byte[] data,uint length);
 public static void Save(object source,string path) {
  var stream=(IStream)source; var buffer=new byte[65536]; var count=Marshal.AllocCoTaskMem(4);
  try { using(var file=new FileStream(path,FileMode.CreateNew)) {
   while(true) { Marshal.WriteInt32(count,0); stream.Read(buffer,buffer.Length,count); int n=Marshal.ReadInt32(count);
    if(n==0) break; file.Write(buffer,0,n); if(file.Length>32*1024*1024) throw new IOException("ISO_TOO_LARGE"); }
  }} finally { Marshal.FreeCoTaskMem(count); }
 }
}
'@
}
$image=New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$image.FileSystemsToCreate=3
$image.VolumeName='G4_IMPORT_V1'
foreach($name in ($expected+@('manifest.json'))) {
    $bytes=[IO.File]::ReadAllBytes((Join-Path $root.FullName $name))
    $image.Root.AddFile($name,[G4IsoStream]::SHCreateMemStream($bytes,$bytes.Length))
}
$result=$image.CreateResultImage()
[G4IsoStream]::Save($result.ImageStream,"$iso.partial")
$tar=Join-Path $env:SystemRoot 'System32\tar.exe'
$actual=@(& $tar -tf "$iso.partial" | Where-Object { $_ -cnotin @('.','./') } | ForEach-Object { $_ -creplace '^\./','' })
if($LASTEXITCODE -ne 0 -or $actual.Count -ne 8 -or @($actual | Where-Object { $_ -cnotin ($expected+@('manifest.json')) }).Count) {
    throw 'ISO_READBACK_ALLOWLIST_MISMATCH'
}
foreach($name in $actual) {
    $start=[Diagnostics.ProcessStartInfo]::new($tar,('-xOf "{0}" "{1}"' -f "$iso.partial",$name))
    $start.UseShellExecute=$false; $start.RedirectStandardOutput=$true
    $process=[Diagnostics.Process]::Start($start)
    try {
        $pin=(Get-FileHash -InputStream $process.StandardOutput.BaseStream).Hash
        $process.WaitForExit()
        $expectedPin=if($name -ceq 'manifest.json') {$ManifestSha256} else {$manifest.files.$name}
        if($process.ExitCode -ne 0 -or $pin -ine $expectedPin) { throw "ISO_READBACK_PIN_MISMATCH: $name" }
    } finally { $process.Dispose() }
}
[IO.File]::Move("$iso.partial",$iso)
[pscustomobject]@{ Status='ISO_READBACK_VERIFIED_ONLY'; Path=$iso; SHA256=(Get-FileHash -LiteralPath $iso).Hash;
    Files=8; NativeInvocations=0; GuestRoundtrip='NOT_RUN' }
