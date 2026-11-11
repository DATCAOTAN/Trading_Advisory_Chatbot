#Requires -Version 5.1
<# Read-only operator audit. Writes one new JSON report; never launches native tools. #>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-AuditEvidence($Label, [scriptblock]$Read, $Failures) {
    try { & $Read }
    catch {
        $Failures.Add([ordered]@{
            operation = $Label; status = 'INCONCLUSIVE'
            error_type = $_.Exception.GetType().FullName
            error_id = $_.FullyQualifiedErrorId; message = $_.Exception.Message
        })
    }
}

function Get-AuditField($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -ne $property) { return $property.Value }
    return $null
}

function Test-AnyFilter($Value) {
    return $null -ne $Value -and @($Value).Count -eq 1 -and [string]$Value -eq 'Any'
}

function Test-WholePathBlock($Rule, $Application, $Port, $Address, $Service, $Interface, $InterfaceType) {
    # Deliberately do not infer coverage by combining partial address/port/profile rules.
    return ([string]$Rule.Enabled -eq 'True' -and [string]$Rule.Direction -eq 'Outbound' -and
        [string]$Rule.Action -eq 'Block' -and [string]$Rule.Profile -eq 'Any' -and
        [string](Get-AuditField $Rule 'PrimaryStatus') -eq 'OK' -and
        (Test-AnyFilter (Get-AuditField $Application 'Package')) -and
        (Test-AnyFilter $Port.Protocol) -and (Test-AnyFilter $Port.LocalPort) -and
        (Test-AnyFilter $Port.RemotePort) -and (Test-AnyFilter $Address.LocalAddress) -and
        (Test-AnyFilter $Address.RemoteAddress) -and (Test-AnyFilter $Service.Service) -and
        (Test-AnyFilter $Interface.InterfaceAlias) -and (Test-AnyFilter $InterfaceType.InterfaceType))
}

function Invoke-NativeMathIsolationAudit {
    $root = Split-Path -Parent $PSScriptRoot
    $run = Join-Path $root 'data\research\mt5_tester\numeric_e05805d67cd2'
    $vendor = Join-Path $root 'data\research\mt5_tester\s11b'
    $failures = [Collections.Generic.List[object]]::new()
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $inventory = @('MetaEditor64.exe', 'terminal64.exe', 'metatester64.exe') | ForEach-Object {
        $name = $_
        $source = Join-Path $vendor $name
        $metadata = Read-AuditEvidence "vendor:$name" {
            $file = Get-Item -LiteralPath $source
            [ordered]@{ sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
                version = $file.VersionInfo.FileVersion }
        } $failures
        [pscustomobject]@{ role = $name; intended_path = (Join-Path $run $name)
            source_path = $source; source_metadata = $metadata }
    }
    $profiles = @(Read-AuditEvidence 'firewall:profiles:ActiveStore' {
        Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop |
            Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction,
                AllowLocalFirewallRules, AllowLocalIPsecRules, DisabledInterfaceAliases
    } $failures)
    $services = @(Read-AuditEvidence 'firewall:services' {
        Get-Service BFE, MpsSvc -ErrorAction Stop | Select-Object Name, Status
    } $failures)
    $rules = @(Read-AuditEvidence 'firewall:outbound:ActiveStore' {
        Get-NetFirewallRule -PolicyStore ActiveStore -Direction Outbound -Enabled True -ErrorAction Stop
    } $failures)
    $applications = @(Read-AuditEvidence 'firewall:applications:ActiveStore' {
        Get-NetFirewallApplicationFilter -PolicyStore ActiveStore -ErrorAction Stop
    } $failures)
    $relevant = [Collections.Generic.List[object]]::new()
    foreach ($rule in $rules) {
        $app = @(Read-AuditEvidence "application:$($rule.Name)" {
            $rule | Get-NetFirewallApplicationFilter -ErrorAction Stop
        } $failures)
        foreach ($filter in $app) {
            $program = [Environment]::ExpandEnvironmentVariables([string]$filter.Program)
            $paths = @($inventory | Where-Object {
                $program -eq 'Any' -or $program -ieq $_.intended_path -or
                    ($program.Contains('*') -and $_.intended_path -like $program)
            } | Select-Object -ExpandProperty intended_path)
            if ($paths.Count -eq 0) { continue }
            $port = Read-AuditEvidence "port:$($rule.Name)" { $rule | Get-NetFirewallPortFilter -ErrorAction Stop } $failures
            $address = Read-AuditEvidence "address:$($rule.Name)" { $rule | Get-NetFirewallAddressFilter -ErrorAction Stop } $failures
            $service = Read-AuditEvidence "service:$($rule.Name)" { $rule | Get-NetFirewallServiceFilter -ErrorAction Stop } $failures
            $interface = Read-AuditEvidence "interface:$($rule.Name)" { $rule | Get-NetFirewallInterfaceFilter -ErrorAction Stop } $failures
            $type = Read-AuditEvidence "interface_type:$($rule.Name)" { $rule | Get-NetFirewallInterfaceTypeFilter -ErrorAction Stop } $failures
            $security = Read-AuditEvidence "security:$($rule.Name)" { $rule | Get-NetFirewallSecurityFilter -ErrorAction Stop } $failures
            $whole = $false
            if ($port -and $address -and $service -and $interface -and $type) {
                $whole = Test-WholePathBlock $rule $filter $port $address $service $interface $type
            }
            $relevant.Add([ordered]@{
                name = $rule.Name; profiles = [string]$rule.Profile; action = [string]$rule.Action
                enabled = [string]$rule.Enabled; direction = [string]$rule.Direction
                enforcement = [string](Get-AuditField $rule 'EnforcementStatus')
                primary_status = [string](Get-AuditField $rule 'PrimaryStatus')
                policy_source_type = [string](Get-AuditField $rule 'PolicyStoreSourceType')
                program = $program; matching_paths = $paths
                application = $filter | Select-Object Program, Package
                ports = $port | Select-Object Protocol, LocalPort, RemotePort
                addresses = $address | Select-Object LocalAddress, RemoteAddress
                service = $service | Select-Object Service
                interface = $interface | Select-Object InterfaceAlias
                interface_type = $type | Select-Object InterfaceType
                security = $security | Select-Object Authentication, Encryption, OverrideBlockRules
                whole_path_block_candidate = ($whole -and ($program -eq 'Any' -or $paths -icontains $program))
            })
        }
    }
    $coverage = foreach ($entry in $inventory) {
        $candidates = @($relevant | Where-Object {
            $_.whole_path_block_candidate -and $_.matching_paths -icontains $entry.intended_path
        })
        [ordered]@{ path = $entry.intended_path
            status = $(if ($candidates.Count -gt 0) { 'BLOCK_RULE_CANDIDATE' } else { 'INCONCLUSIVE' })
            rule_names = @($candidates | ForEach-Object { $_.name }) }
    }
    $feature = Read-AuditEvidence 'sandbox:optional_feature' {
        Get-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -ErrorAction Stop |
            Select-Object FeatureName, State
    } $failures
    $windows = Read-AuditEvidence 'windows:edition' {
        Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' |
            Select-Object EditionID, CurrentBuildNumber, UBR
    } $failures
    $package = Join-Path $root 'data\research\mt5_tester\numeric_parity_preparation_e05805d67cd2774599aa605b108f4833fdb9003753c4bec11efb20976f3cf9b5.json'
    $pin = Read-AuditEvidence 'package:checksum' {
        $hash = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne 'e05805d67cd2774599aa605b108f4833fdb9003753c4bec11efb20976f3cf9b5') { throw 'Pinned package mismatch' }
        $hash
    } $failures
    $report = [ordered]@{
        schema = 'native-math-isolation-audit/v1'; observed_utc = [DateTime]::UtcNow.ToString('o')
        elevated = $elevated; verdict = 'INCONCLUSIVE'; native_invocations = 0
        package_sha256 = $pin; intended_run_directory = $run
        intended_directory_exists = (Test-Path -LiteralPath $run)
        executable_inventory = @($inventory); firewall_profiles = $profiles; firewall_services = $services
        enabled_outbound_rule_count = $rules.Count; active_application_filter_count = $applications.Count
        relevant_rules = @($relevant.ToArray()); known_path_coverage = @($coverage)
        whole_process_tree = 'NOT_PROVEN: unexpected helpers, relocated agents and inherited OS tools are not contained by this path inventory'
        credentials_isolation = 'NOT_PROVEN: no credential/profile content was read or copied; clean directory alone does not isolate host identity'
        caveats = @('Candidate rule matching is not WFP/runtime enforcement proof; authenticated bypass and policy interactions need review',
            'Host firewall inspection is not proof that loopback/host access is denied',
            'Do not launch tools or change policy based on a BLOCK_RULE_CANDIDATE label')
        windows = $windows; sandbox_feature = $feature
        sandbox_launcher_exists = (Test-Path -LiteralPath (Join-Path $env:windir 'System32\WindowsSandbox.exe'))
        offline_toolchain_compatibility = 'NOT_VERIFIED'; errors = @($failures.ToArray())
    }
    $directory = Join-Path $root 'data\research\mt5_tester'
    for ($parent = Get-Item -LiteralPath $directory; $null -ne $parent; $parent = $parent.Parent) {
        if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Report path through reparse point refused' }
    }
    $destination = Join-Path $directory ('isolation_audit_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '_' + [Guid]::NewGuid().ToString('N') + '.json')
    $stream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($report | ConvertTo-Json -Depth 12))
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
    [pscustomobject]@{ Verdict = $report.verdict; ReportPath = $destination; Errors = $failures.Count; NativeInvocations = 0 }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-NativeMathIsolationAudit }
