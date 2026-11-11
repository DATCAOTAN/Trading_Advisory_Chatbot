#Requires -Version 5.1
<# Run manually INSIDE the future guest only. No native tool/process launch. #>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-NativeInputHash([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Test-NativeInputManifest([string]$Directory, $Manifest) {
    $actual = @(Get-ChildItem -LiteralPath $Directory -Force -Recurse)
    if (@($actual | Where-Object { $_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }).Count) {
        throw 'Unexpected input directory or reparse point'
    }
    $expected = @($Manifest.files.PSObject.Properties.Name) + @('manifest.json')
    if (@(Compare-Object ($actual.Name | Sort-Object) ($expected | Sort-Object)).Count) {
        throw 'Input allowlist mismatch'
    }
    foreach ($property in $Manifest.files.PSObject.Properties) {
        if ([IO.Path]::GetFileName($property.Name) -ne $property.Name) { throw 'Non-flat manifest path' }
        $path = Join-Path $Directory $property.Name
        if ((Get-NativeInputHash $path) -ne $property.Value) {
            throw 'Input hash mismatch'
        }
    }
}

function Invoke-NativeGuestPreflight {
    if ($env:USERNAME -ne 'WDAGUtilityAccount' -or -not (Test-Path -LiteralPath 'C:\ResearchInput')) {
        throw 'Expected fresh Windows Sandbox guest; do not run on the host'
    }
    $directory = 'C:\ResearchInput'
    $manifest = Get-Content -LiteralPath "$directory\manifest.json" -Raw | ConvertFrom-Json
    Test-NativeInputManifest $directory $manifest
    $pin = 'e05805d67cd2774599aa605b108f4833fdb9003753c4bec11efb20976f3cf9b5'
    if ((Get-NativeInputHash "$directory\numeric_package.json") -ne $pin) {
        throw 'Approved package mismatch'
    }
    $package = Get-Content -LiteralPath "$directory\numeric_package.json" -Raw | ConvertFrom-Json
    foreach ($name in @('StrategyParity.mq5','ParityDecimal.mqh')) {
        $key = 'tools/mt5_bridge/research/' + $name
        $wanted = $package.source_sha256.PSObject.Properties[$key].Value
        if ((Get-NativeInputHash (Join-Path $directory $name)) -ne $wanted) {
            throw 'MQL pin mismatch'
        }
    }
    foreach ($name in @('s11b_parity.csv','s11b_numeric.csv')) {
        $wanted = $package.file_sha256.PSObject.Properties[$name].Value
        if ((Get-NativeInputHash (Join-Path $directory $name)) -ne $wanted) {
            throw 'Fixture pin mismatch'
        }
    }
    # Absence of an external interface is stronger evidence than no default route alone.
    $adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop)
    $active = @($adapters | Where-Object { $_.Status -eq 'Up' })
    $routes = @(Get-NetRoute -ErrorAction Stop | Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0','::/0') })
    $native = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('terminal64.exe','MetaEditor64.exe','metatester64.exe') })
    $profiles = @("$env:APPDATA\MetaQuotes", "$env:ProgramData\MetaQuotes") | Where-Object { Test-Path -LiteralPath $_ }
    $blockers = @()
    if ($active.Count -or $routes.Count) { $blockers += 'EXTERNAL_NETWORK_NOT_EXCLUDED' }
    if ($native.Count) { $blockers += 'NATIVE_PROCESS_ALREADY_PRESENT' }
    if (@($profiles).Count) { $blockers += 'FRESH_BROKER_PROFILE_ABSENCE_NOT_PROVEN' }
    $report = [ordered]@{
        status = 'INCONCLUSIVE'; input_hashes = 'PASS'; package_sha256 = $pin
        active_adapter_count = $active.Count; default_route_count = $routes.Count
        native_processes = @($native | Select-Object Name, ProcessId, ParentProcessId, ExecutablePath)
        blockers = $blockers; native_invocations = 0
        pending = @('Match manifest hash to host receipt', 'Verify host WSB networking/clipboard and sole read-only mapping',
                    'Benign CreateNew marker on input must fail with access denied; never modify source files',
                    'Approve result extraction before consuming the ONE Tester session')
    }
    $path = Join-Path $env:TEMP ('native_guest_preflight_' + [Guid]::NewGuid().ToString('N') + '.json')
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($report | ConvertTo-Json -Depth 6))
        $stream.Write($bytes,0,$bytes.Length)
    } finally { $stream.Dispose() }
    [pscustomobject]@{ Status = $report.status; ReportPath = $path; Blockers = $blockers }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-NativeGuestPreflight }
