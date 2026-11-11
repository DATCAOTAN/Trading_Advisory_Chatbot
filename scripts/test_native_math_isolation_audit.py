"""Offline audit checks: no privileged queries, executable launch or firewall writes."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT=Path("scripts/audit_native_math_isolation.ps1").resolve()
POWERSHELL=shutil.which("powershell.exe")
pytestmark=pytest.mark.skipif(not POWERSHELL,reason="Windows PowerShell required")


def run_ps(body):
    completed=subprocess.run([POWERSHELL,"-NoProfile","-NonInteractive","-Command",
        f". '{str(SCRIPT).replace(chr(39),chr(39)*2)}'; " + body],
        capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,completed.stderr
    return completed.stdout.strip()


def test_audit_parses_and_contains_no_mutating_or_native_launch_commands():
    names=json.loads(run_ps("""
    $tokens=$null; $errors=$null
    $tree=[Management.Automation.Language.Parser]::ParseFile($PSCommandPath,[ref]$tokens,[ref]$errors)
    if($errors.Count){ throw ($errors | Out-String) }
    @($tree.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst]},$true) |
        ForEach-Object { $_.GetCommandName() }) | ConvertTo-Json -Compress
    """.replace("$PSCommandPath", "'"+str(SCRIPT)+"'")))
    forbidden=("New-Net","Set-Net","Remove-Net","Enable-","Disable-","Start-","Stop-",
               "Restart-","Invoke-Expression","Invoke-Command")
    assert not any(name and name.startswith(forbidden) for name in names)
    assert not any(name and name.lower().endswith(".exe") for name in names)
    source=SCRIPT.read_text()
    assert "[IO.FileMode]::CreateNew" in source
    assert "verdict = 'INCONCLUSIVE'" in source
    assert "Get-NetFirewallRule -PolicyStore ActiveStore" in source
    assert "Get-NetFirewallApplicationFilter -PolicyStore ActiveStore" in source


@pytest.mark.parametrize("mutation",["none","profile","direction","allow","disabled","port","address","package","service","interface"])
def test_partial_rules_never_become_full_path_block(mutation):
    patch={
        "none":"", "profile":"$r.Profile='Private'", "direction":"$r.Direction='Inbound'",
        "allow":"$r.Action='Allow'", "disabled":"$r.Enabled='False'",
        "port":"$p.RemotePort='443'", "address":"$a.RemoteAddress='Internet'",
        "package":"$app.Package='restricted'", "service":"$s.Service='specific'",
        "interface":"$i.InterfaceAlias='Ethernet'",
    }[mutation]
    result=run_ps("""
    $r=[pscustomobject]@{Enabled='True';Direction='Outbound';Action='Block';Profile='Any';PrimaryStatus='OK'}
    $app=[pscustomobject]@{Package='Any'}
    $p=[pscustomobject]@{Protocol='Any';LocalPort='Any';RemotePort='Any'}
    $a=[pscustomobject]@{LocalAddress='Any';RemoteAddress='Any'}
    $s=[pscustomobject]@{Service='Any'}
    $i=[pscustomobject]@{InterfaceAlias='Any'}
    $t=[pscustomobject]@{InterfaceType='Any'}
    """+patch+"; Test-WholePathBlock $r $app $p $a $s $i $t")
    assert result==("True" if mutation=="none" else "False")


def test_inaccessible_evidence_is_recorded_not_suppressed():
    record=json.loads(run_ps("""
    $failures=[Collections.Generic.List[object]]::new()
    $answer=Read-AuditEvidence 'denied-policy' {throw [UnauthorizedAccessException]::new('Denied')} $failures
    if($null -ne $answer){throw 'Unexpected successful evidence'}
    $failures.ToArray() | ConvertTo-Json -Compress
    """))
    assert record["operation"]=="denied-policy"
    assert record["status"]=="INCONCLUSIVE"
    assert "UnauthorizedAccessException" in record["error_type"]


def test_sandbox_configuration_has_only_readonly_input_and_no_autorun():
    from xml.etree import ElementTree as ET
    config=ET.parse("docs/operations/native_math_offline.wsb").getroot()
    for name in ("Networking","ClipboardRedirection","vGPU","AudioInput","VideoInput","PrinterRedirection"):
        assert config.findtext(name)=="Disable"
    mappings=config.findall("MappedFolders/MappedFolder")
    assert len(mappings)==1 and mappings[0].findtext("ReadOnly")=="true"
    assert mappings[0].findtext("SandboxFolder")==r"C:\ResearchInput"
    assert mappings[0].findtext("HostFolder").endswith(r"native_sandbox_e05805d67cd2\input")
    assert config.find("LogonCommand") is None
    guest=Path("scripts/native_math_guest_preflight.ps1").read_text()
    assert "[IO.FileMode]::CreateNew" in guest
    assert "status = 'INCONCLUSIVE'" in guest
    assert "Invoke-Expression" not in guest and "Start-Process" not in guest
    assert "NATIVE_PROCESS_ALREADY_PRESENT" in guest


@pytest.mark.parametrize("mutation",["none","tampered","extra","missing"])
def test_sandbox_guest_manifest_validation_is_fail_closed(tmp_path,mutation):
    from hashlib import sha256
    sample=b"benign fixture"
    (tmp_path/"sample.csv").write_bytes(sample)
    manifest={"files":{"sample.csv":sha256(sample).hexdigest()}}
    (tmp_path/"manifest.json").write_text(json.dumps(manifest))
    if mutation=="tampered": (tmp_path/"sample.csv").write_bytes(b"changed")
    if mutation=="extra": (tmp_path/"unexpected.txt").write_text("unexpected")
    if mutation=="missing": (tmp_path/"sample.csv").unlink()
    guest=str(Path("scripts/native_math_guest_preflight.ps1").resolve()).replace("'","''")
    directory=str(tmp_path).replace("'","''")
    result=run_ps(f". '{guest}'; $m=Get-Content -LiteralPath '{directory}\\manifest.json' -Raw | ConvertFrom-Json; "
                  f"try {{ Test-NativeInputManifest '{directory}' $m; 'PASS' }} catch {{ 'BLOCKED: '+$_.Exception.Message }}")
    if mutation=="none": assert result=="PASS"
    else: assert result.startswith("BLOCKED: ")


def test_sandbox_guest_script_parses_without_native_invocation():
    guest=str(Path("scripts/native_math_guest_preflight.ps1").resolve()).replace("'","''")
    result=run_ps(f"$tokens=$null; $errors=$null; [Management.Automation.Language.Parser]::ParseFile('{guest}',"
                  "[ref]$tokens,[ref]$errors) | Out-Null; if($errors.Count){throw ($errors | Out-String)}; 'PASS'")
    assert result=="PASS"
