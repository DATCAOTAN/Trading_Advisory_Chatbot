#Requires -Version 5.1
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedHarnessSha256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
foreach ($excluded in @($repo, 'D:\TradingAI_Sandbox')) {
    if ($output -ieq $excluded -or $output.StartsWith("$excluded\", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Use a new local output directory outside the repository and sandbox.'
    }
}
if ($output -notmatch '^[A-Za-z]:\\' -or (Test-Path -LiteralPath $output) -or
    [IO.DriveInfo]::new([IO.Path]::GetPathRoot($output)).DriveType -ne 'Fixed') {
    throw 'Output must be a new path on a fixed local drive.'
}
for ($parent = Get-Item -LiteralPath (Split-Path -Parent $output); $null -ne $parent; $parent = $parent.Parent) {
    if ($parent -isnot [IO.DirectoryInfo] -or $parent.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Output parent must be an existing local directory without reparse points.'
    }
}

# IMAPI exposes its binary image as COM IStream, not a PowerShell/.NET stream.
if (-not ('G21IsoStream' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class G21IsoStream {
    [DllImport("shlwapi.dll")]
    [return: MarshalAs(UnmanagedType.Interface)]
    public static extern IStream SHCreateMemStream(byte[] data, uint length);

    public static void Save(object comImage, string path) {
        var image = (IStream)comImage;
        var bytes = new byte[65536];
        IntPtr count = Marshal.AllocCoTaskMem(sizeof(int));
        try {
            using (var file = new FileStream(path, FileMode.CreateNew)) {
                int n;
                while (true) {
                    Marshal.WriteInt32(count, 0);
                    image.Read(bytes, bytes.Length, count);
                    n = Marshal.ReadInt32(count);
                    if (n == 0) break;
                    file.Write(bytes, 0, n);
                    if (file.Length > 1024 * 1024) throw new IOException("Probe image exceeds 1 MiB.");
                }
            }
        } finally { Marshal.FreeCoTaskMem(count); }
    }
}
'@
}

$harness = 'g2_1_guest_probes.py'
$manifest = 'SHA256SUMS'
$source = Get-Item -LiteralPath (Join-Path $PSScriptRoot $harness) -Force
if ($source -isnot [IO.FileInfo] -or $source.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Harness must be the reviewed regular source file.'
}
$payload = [IO.File]::ReadAllBytes($source.FullName)
if ($payload.Length -eq 0 -or $payload.Length -gt 64KB) { throw 'Unexpected harness size.' }
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $harnessHash = [BitConverter]::ToString($sha.ComputeHash($payload)).Replace('-', '').ToLowerInvariant()
    $manifestBytes = [Text.Encoding]::ASCII.GetBytes("$harnessHash  $harness`n")
    $manifestHash = [BitConverter]::ToString($sha.ComputeHash($manifestBytes)).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
if ($harnessHash -ine $ExpectedHarnessSha256) { throw 'Harness SHA-256 does not match the independently reviewed pin.' }

$image = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$image.FileSystemsToCreate = 3 # ISO9660 + Joliet; no boot image configured.
$image.VolumeName = 'G21_PROBES'
$image.Root.AddFile($harness, [G21IsoStream]::SHCreateMemStream($payload, $payload.Length))
$image.Root.AddFile($manifest, [G21IsoStream]::SHCreateMemStream($manifestBytes, $manifestBytes.Length))
$null = New-Item -Path $output -ItemType Directory
$partial = Join-Path $output 'g2_1_probes.partial'
$iso = Join-Path $output 'g2_1_probes.iso'
$result = $image.CreateResultImage()
[G21IsoStream]::Save($result.ImageStream, $partial)

$tar = Join-Path $env:SystemRoot 'System32\tar.exe'
$entries = @(& $tar -tf $partial | Where-Object { $_ -cnotin @('.', './') } | ForEach-Object { $_ -creplace '^\./', '' })
if ($LASTEXITCODE -ne 0 -or $entries.Count -ne 2 -or $harness -cnotin $entries -or $manifest -cnotin $entries) {
    throw 'ISO file allowlist mismatch; do not attach the partial image.'
}
foreach ($entry in $harness, $manifest) {
    $start = [Diagnostics.ProcessStartInfo]::new($tar, ('-xOf "{0}" "{1}"' -f $partial, $entry))
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $process = [Diagnostics.Process]::Start($start)
    try {
        $actual = (Get-FileHash -InputStream $process.StandardOutput.BaseStream -Algorithm SHA256).Hash
        $process.WaitForExit()
        $expected = if ($entry -ceq $harness) { $harnessHash } else { $manifestHash }
        if ($process.ExitCode -ne 0 -or $actual -ine $expected) { throw "ISO read-back failed for $entry." }
    } finally { $process.Dispose() }
}

[IO.File]::Move($partial, $iso)
[pscustomobject]@{
    Status = 'MEDIA_VERIFIED'; IsoPath = $iso; IsoSha256 = (Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash
    ManifestSha256 = $manifestHash; HarnessSha256 = $harnessHash
}
