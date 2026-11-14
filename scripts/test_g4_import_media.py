"""Controlled fixtures only; these tests are not native execution evidence."""
import copy
import json
import os
import re
import shutil
from pathlib import Path
import subprocess

import pytest

from scripts import g4_prepare_import as media
from src.services.trading.research.historical_dataset import HistoricalDataRequest, canonical_bytes, checksum, persist_dataset


@pytest.fixture(scope="module")
def package():
    # Deliberately simple artificial quotes; never published as real market data.
    from datetime import datetime, timezone
    start = 1793800800
    bars = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"]
    for i in range(180):
        stamp = datetime.fromtimestamp(start + i * 60, timezone.utc).strftime("%Y.%m.%d\t%H:%M:%S")
        bars.append(stamp + "\t4000\t4001\t3999\t4000\t1\t0\t240\n")
    ticks = ["<DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>\n"]
    source = []
    for i in range(63156):
        ms = start * 1000 + i * 170
        stamp = datetime.fromtimestamp(ms // 1000, timezone.utc).strftime("%Y.%m.%d\t%H:%M:%S")
        ticks.append(stamp + f".{ms % 1000:03d}\t4000\t4000.24\t0\t0\n")
        source.append(json.dumps(dict(time=ms // 1000, time_msc=ms, bid=4000, ask=4000.24, last=0, flags=6)) + "\n")
    files = {"bars.tsv": "".join(bars), "ticks.tsv": "".join(ticks), "source_ticks.jsonl": "".join(source)}
    strategy = dict(purpose="CAPTURE_ONLY", execution_allowed=False, simulate_orders=False, financial_certification=False,
        tick_source={"data_sha256": checksum(files["source_ticks.jsonl"].encode())}, bar_count=180, tick_count=63156,
        signal_request={"inputs": [{"symbol": "XAUUSD"}]}, ticks_tsv_sha256=checksum(files["ticks.tsv"].encode()),
        bars_tsv_sha256=checksum(files["bars.tsv"].encode()))
    strategy["custom_symbol"] = "G4CAP_" + strategy["tick_source"]["data_sha256"][:12]
    capture = {"start": start + 35 * 60}
    strategy["capture_sha256"] = checksum(canonical_bytes(capture))
    return dict(strategy=strategy, strategy_sha256=checksum(canonical_bytes(strategy)), capture=capture,
        files=files, file_sha256={n: checksum(v.encode()) for n, v in files.items()})


def prepare(package):
    raw = canonical_bytes(package)
    return media.prepare(raw, checksum(raw))


def test_deterministic_allowlisted_media_and_missing_prestart(package):
    before = canonical_bytes(package)
    payload, manifest = prepare(package)
    assert prepare(package) == (payload, manifest)
    assert canonical_bytes(package) == before
    assert set(payload) == media.ALLOWLIST | {"manifest.json"}
    assert manifest["prestart"]["available_before_capture"] == 35
    assert manifest["prestart"]["missing"] == 65
    assert manifest["prestart"]["request"]["start"] == "2026-11-04T12:55:00+00:00"
    assert manifest["prestart"]["request"]["end"] == "2026-11-04T14:00:00+00:00"
    assert manifest["native_execution_authorized"] is False
    assert manifest["configuration_contract"]["required_quote_days"] == [3]
    assert manifest["configuration_contract"]["quote_days_mask"] == 8
    assert manifest["configuration_contract"]["financial_certification"] is False
    assert b"#define G4_QUOTE_DAYS_MASK 8" in payload["G4ImportPins.mqh"]
    assert all(checksum(payload[n]) == pin for n, pin in manifest["files"].items())


@pytest.mark.parametrize("mutation", ["pin", "authority", "file", "scope", "projection", "order"])
def test_reject_changed_input_and_invalid_bindings(package, mutation):
    changed = copy.deepcopy(package)
    if mutation == "pin":
        with pytest.raises(ValueError, match="PIN_MISMATCH"):
            media.prepare(canonical_bytes(changed), "0" * 64)
        return
    if mutation == "authority":
        changed["strategy"]["execution_allowed"] = True
    elif mutation == "file":
        changed["files"]["ticks.tsv"] += "altered"
    elif mutation == "scope":
        changed["strategy"]["custom_symbol"] = "broker_symbol"
        changed["strategy_sha256"] = checksum(canonical_bytes(changed["strategy"]))
    else:
        lines = changed["files"]["ticks.tsv"].splitlines(keepends=True)
        if mutation == "projection":
            lines[1] = lines[1].replace("4000.24", "4000.25")
        else:
            lines[1], lines[2] = lines[2], lines[1]
        changed["files"]["ticks.tsv"] = "".join(lines)
        changed["file_sha256"]["ticks.tsv"] = checksum(changed["files"]["ticks.tsv"].encode())
        changed["strategy"]["ticks_tsv_sha256"] = changed["file_sha256"]["ticks.tsv"]
        changed["strategy_sha256"] = checksum(canonical_bytes(changed["strategy"]))
    with pytest.raises(ValueError):
        prepare(changed)


def test_native_helper_safety_and_powershell_syntax():
    helper = media.RESEARCH_SOURCE.read_text()
    assert "#property service" in helper  # One-shot OnStart; no chart bootstrap dependency.
    assert "CustomTicksReplace" in helper and "CustomRatesReplace" in helper
    assert "AccountInfoInteger(ACCOUNT_LOGIN)!=0" in helper and "!ApproveImport" in helper
    assert "CopyTicksRange" in helper and "FLAGS_NOT_SOURCE_EQUALITY" in helper
    assert "OrderSend" not in helper and "CustomSymbolDelete" not in helper
    assert "while(" not in helper
    assert "if(observed_days!=G4_QUOTE_DAYS_MASK)" in helper
    assert helper.index("if(observed_days!=G4_QUOTE_DAYS_MASK)") < helper.index("bool created=CustomSymbolCreate")
    script = Path(__file__).with_name("g4_import_media.ps1")
    result = subprocess.run(["powershell", "-NoProfile", "-Command",
        "$e=$null; $t=$null; [void][Management.Automation.Language.Parser]::ParseFile('"
        + str(script) + "',[ref]$t,[ref]$e); if($e.Count){$e | ForEach-Object {$_.Message}; exit 1}"],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_build_readback_no_overwrite_and_unexpected_file(package, tmp_path):
    payload, _ = prepare(package)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name, content in payload.items():
        (inputs / name).write_bytes(content)
    iso = tmp_path / "fixture.iso"
    command = ["powershell", "-NoProfile", "-File", str(Path(__file__).with_name("g4_import_media.ps1")),
        "-InputDirectory", str(inputs), "-ManifestSha256", checksum(payload["manifest.json"]), "-OutputIso", str(iso)]
    # Codex's bundled pwsh paths shadow Windows PowerShell modules in child Python processes.
    env = dict(os.environ, PSModulePath=str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/Modules"))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
    assert completed.returncode == 0, completed.stderr
    before = checksum(iso.read_bytes())
    refused = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
    assert refused.returncode != 0 and "NEW_LOCAL_ISO_REQUIRED" in refused.stderr
    assert checksum(iso.read_bytes()) == before
    (inputs / "unexpected.exe").write_bytes(b"NOT AN EXECUTABLE: controlled fixture")
    refused = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
    assert refused.returncode != 0 and "MEDIA_ALLOWLIST_MISMATCH" in refused.stderr


def test_recovery_targets_pins_and_modes_without_native_execution(package):
    raw = canonical_bytes(package)
    pin = checksum(raw)
    config_files, config = media.prepare(raw, pin, recovery_mode="CONFIGURATION_ONLY")
    import_files, importing = media.prepare(raw, pin, recovery_mode="IMPORT")
    assert config["custom_symbol"] != importing["custom_symbol"] != package["strategy"]["custom_symbol"]
    assert len(config["custom_symbol"]) <= 31 and len(importing["custom_symbol"]) <= 31
    assert config["recovery"]["preserved_symbol"] == package["strategy"]["custom_symbol"]
    assert config["recovery"]["previous_importer_sha256"] == media.V8_IMPORTER_SHA256
    assert config["recovery"]["write_authorization"] == "REQUIRES_EXPLICIT_TARGET_APPROVAL"
    assert config["native_execution_authorized"] is False
    assert b"#define G4_CONFIGURATION_ONLY true" in config_files["G4ImportPins.mqh"]
    assert b"#define G4_CONFIGURATION_ONLY false" in import_files["G4ImportPins.mqh"]
    assert config["recovery"]["guest_subdirectory"] != importing["recovery"]["guest_subdirectory"]
    assert config["recovery"]["importer_source_sha256"] == checksum(media.RESEARCH_SOURCE.read_bytes())
    for payload, manifest in ((config_files, config), (import_files, importing)):
        folder = manifest["recovery"]["guest_subdirectory"]
        text = payload["README.txt"].decode()
        assert f"MQL5/Services/{folder}/G4Import.mq5" in text
        assert f"MQL5/Files/{folder}/roundtrip.csv" in text
        assert "ApproveImport defaults false" in text
    assert config["custom_symbol"][:6] == importing["custom_symbol"][:6] == "XAUUSD"
    assert config["metadata"]["calculation_mode"] == 0
    assert config["metadata"]["currency_base"] == config["metadata"]["currency_margin"] == "XAU"
    assert config["metadata"]["currency_profit"] == "USD"
    assert config["recovery"]["financial_fidelity"] == "NOT_CERTIFIED_CURRENT_SNAPSHOT_ONLY"
    for name in ("bars.tsv", "ticks.tsv", "source_ticks.jsonl"):
        assert config_files[name] == import_files[name] == package["files"][name].encode()
    assert media.prepare(raw, pin, recovery_mode="CONFIGURATION_ONLY") == (config_files, config)
    with pytest.raises(ValueError, match="RECOVERY_MODE_INVALID"):
        media.prepare(raw, pin, recovery_mode="AUTO_APPROVE")


def test_configuration_diagnostics_capture_error_before_logging_and_preserve_values():
    source = media.RESEARCH_SOURCE.read_text()
    configure = source.split("bool Configure()", 1)[1].split("bool Roundtrip", 1)[0]
    expected = [
        ("Integer", "SYMBOL_DIGITS", "3"), ("Integer", "SYMBOL_CHART_MODE", "SYMBOL_CHART_MODE_BID"),
        ("Integer", "SYMBOL_TRADE_MODE", "SYMBOL_TRADE_MODE_DISABLED"),
        ("Integer", "SYMBOL_TRADE_CALC_MODE", "SYMBOL_CALC_MODE_FOREX"),
        ("Double", "SYMBOL_POINT", "0.001"), ("Double", "SYMBOL_TRADE_TICK_SIZE", "0.001"),
        ("Double", "SYMBOL_TRADE_TICK_VALUE", "0.1"), ("Double", "SYMBOL_TRADE_CONTRACT_SIZE", "100"),
        ("Double", "SYMBOL_VOLUME_MAX", "200"), ("Double", "SYMBOL_VOLUME_STEP", "0.01"),
        ("Double", "SYMBOL_VOLUME_MIN", "0.01"),
        ("String", "SYMBOL_DESCRIPTION", '"G4 CAPTURE ONLY; CURRENT metadata; historical swap UNKNOWN"')]
    assert re.findall(r"(?:Set|Check)(Integer|Double|String)Property\((SYMBOL_\w+),([^\n]+?)\)\)", configure) == expected
    verifier = source.split("bool VerifyConfiguration()", 1)[1].split("bool Configure()", 1)[0]
    assert "CheckStringProperty(SYMBOL_CURRENCY_MARGIN,\"XAU\")) financial_ok=false" in verifier
    assert "CheckStringProperty" not in configure
    assert "if((G4_QUOTE_DAYS_MASK & (1<<day))==0) continue;" in configure
    for kind in ("Integer", "Double", "String"):
        assert re.search(r"ResetLastError\(\);\s*bool ok=CustomSymbolSet" + kind
            + r"\(G4_SYMBOL,property,value\);\s*int error=GetLastError\(\);", source)
        assert "api=CustomSymbolSet" + kind + " symbol=%s property=%s value=" in source
    assert re.search(r"ResetLastError\(\);\s*bool ok=CustomSymbolSetSessionQuote\(G4_SYMBOL,\(ENUM_DAY_OF_WEEK\)day,0,0,86400\);\s*int error=GetLastError\(\);", source)
    assert "day=%d session=0 from=0 to=86400 error=%d" in source
    assert source.index("if(G4_CONFIGURATION_ONLY) { Print(\"G4_CONFIGURATION_ONLY_COMPLETE") < source.index("int written_ticks=CustomTicksReplace")
    assert "if(!ApproveImport)" in source and "G4_CONFIG_TARGET_EXISTS_READ_ONLY" in source
    assert "int nb=CopyRates" in source and "int nt=CopyTicksRange" in source


def test_property_dependency_contract_does_not_invent_native_defaults():
    from decimal import Decimal
    source = media.RESEARCH_SOURCE.read_text()
    configure = source.split("bool Configure()", 1)[1].split("bool Roundtrip", 1)[0]
    volume_calls = re.findall(r"SetDoubleProperty\((SYMBOL_VOLUME_\w+),([0-9.]+)\)", configure)
    assert [name for name, _ in volume_calls] == ["SYMBOL_VOLUME_MAX", "SYMBOL_VOLUME_STEP", "SYMBOL_VOLUME_MIN"]
    values = {name: Decimal(value) for name, value in volume_calls}
    assert 0 < values["SYMBOL_VOLUME_STEP"] <= values["SYMBOL_VOLUME_MIN"] <= values["SYMBOL_VOLUME_MAX"]
    assert values["SYMBOL_VOLUME_MIN"] % values["SYMBOL_VOLUME_STEP"] == 0
    assert values["SYMBOL_VOLUME_MAX"] % values["SYMBOL_VOLUME_STEP"] == 0
    assert configure.index("SetIntegerProperty(SYMBOL_DIGITS") < configure.index("SetDoubleProperty(SYMBOL_POINT")
    assert "SetStringProperty(SYMBOL_CURRENCY" not in configure  # Ineffective for Forex; verify requested identity instead.
    assert source.index("LogCreationDefaults();") < source.index("if(!Configure())")
    assert source.index("bool selected=SymbolSelect") < source.index("LogCreationDefaults();")
    assert source.index("if(!VerifyConfiguration()) { Print(\"G4_IMPORT_STOP") < source.index("G4_CONFIGURATION_ONLY_COMPLETE")
    assert "CustomSymbolDelete" not in source and "OrderSend" not in source


def test_readback_requires_api_success_exact_values_and_source_sessions():
    source = media.RESEARCH_SOURCE.read_text()
    for kind in ("Integer", "Double", "String"):
        body = source.split("bool Check" + kind + "Property(", 1)[1].split("\n}", 1)[0]
        assert re.search(r"ResetLastError\(\);\s*bool ok=SymbolInfo" + kind
            + r"\(G4_SYMBOL,property,actual\);\s*int error=GetLastError\(\);", body)
        assert "bool match=ok && actual==expected;" in body and "return match;" in body
        assert "expected=" in body and "actual=" in body and "read_ok=%d match=%d error=%d" in body
    verify = source.split("bool VerifyConfiguration()", 1)[1].split("bool Configure()", 1)[0]
    assert "for(int day=0;day<7;day++)" in verify and "SymbolInfoSessionQuote" in verify
    assert "bool match=read && from==0 && to==86400;" in verify and "if(required && !match) ok=false;" in verify
    assert "if(ok) Print(\"G4_DATA_CONFIGURATION_READBACK_MATCH" in verify and "return ok;" in verify
    assert "financial_ok ? \"NOT_CERTIFIED\" : \"BLOCKED\"" in verify


@pytest.fixture(scope="module")
def configuration_stub_program(tmp_path_factory):
    """Execute the actual configuration functions with fake APIs, NOT a native MT5 acceptance."""
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("C++ compiler unavailable for offline MQL-compatible control-flow checks")
    source = media.RESEARCH_SOURCE.read_text()
    functions = source.split("bool SetIntegerProperty(", 1)[1].split("struct G4ReadbackComparison", 1)[0]
    properties = sorted(set(re.findall(r"\bSYMBOL_[A-Z_]+\b", functions)))
    constants = "enum {" + ",".join(properties) + "};\n"
    program = r'''
#include <cassert>
#include <map>
#include <string>
#include <sstream>
#include <vector>
using string=std::string;
using datetime=long long;
using ENUM_SYMBOL_INFO_INTEGER=int;
using ENUM_SYMBOL_INFO_DOUBLE=int;
using ENUM_SYMBOL_INFO_STRING=int;
using ENUM_DAY_OF_WEEK=int;
CONSTANTS
string G4_SYMBOL="OFFLINE_FIXTURE_ONLY";
int G4_QUOTE_DAYS_MASK=8, last_error=0, rejected=-1, unreadable=-1;
std::map<int,long> integers;
std::map<int,double> doubles;
std::map<int,string> strings;
std::map<int,std::pair<datetime,datetime>> sessions;
std::vector<int> setters;
std::ostringstream logs;
void ResetLastError(){last_error=0;}
int GetLastError(){return last_error;}
string EnumToString(int n){return std::to_string(n);}
template<class T, size_t N> int ArraySize(T (&)[N]){return N;}
template<class... T> void PrintFormat(const char* text,T... args){logs<<text; ((logs<<'|'<<args),...); logs<<'\n';}
void Print(const char* text){logs<<text<<'\n';}
template<class T> bool set(std::map<int,T>& m,int p,T v){
    setters.push_back(p); if(p==rejected){last_error=5308;return false;} m[p]=v;return true;}
template<class T> bool get(std::map<int,T>& m,int p,T& v){
    if(p==unreadable){last_error=4303;return false;} v=m[p];return true;}
bool CustomSymbolSetInteger(string,int p,long v){return set(integers,p,v);}
bool CustomSymbolSetDouble(string,int p,double v){return set(doubles,p,v);}
bool CustomSymbolSetString(string,int p,string v){return set(strings,p,v);}
bool SymbolInfoInteger(string,int p,long& v){return get(integers,p,v);}
bool SymbolInfoDouble(string,int p,double& v){return get(doubles,p,v);}
bool SymbolInfoString(string,int p,string& v){return get(strings,p,v);}
bool CustomSymbolSetSessionQuote(string,int day,int,datetime from,datetime to){
    if(rejected==100+day){last_error=5308;return false;} sessions[day]={from,to};return true;}
bool SymbolInfoSessionQuote(string,int day,int,datetime& from,datetime& to){
    if(!sessions.count(day)){last_error=4307;return false;}
    from=sessions[day].first;to=sessions[day].second;return true;}
bool SetIntegerProperty(FUNCTIONS
int main(int argc,char** argv){
    assert(argc==2); string scenario=argv[1];
    strings[SYMBOL_CURRENCY_BASE]="XAU"; strings[SYMBOL_CURRENCY_PROFIT]="USD";
    strings[SYMBOL_CURRENCY_MARGIN]="USD"; // Operator-observed V10 mismatch, not a new expected value.
    if(scenario=="setter_fail") rejected=SYMBOL_VOLUME_MIN;
    if(scenario=="description_setter_fail") rejected=SYMBOL_DESCRIPTION;
    if(scenario=="session_setter_fail") rejected=103;
    if(scenario=="required_weekends") G4_QUOTE_DAYS_MASK=65;
    if(scenario=="data_getter_fail") unreadable=SYMBOL_POINT;
    if(scenario=="financial_currency_getter_fail") unreadable=SYMBOL_CURRENCY_MARGIN;
    LogCreationDefaults();
    bool configured=Configure();
    if(rejected!=-1){assert(!configured);return 0;}
    assert(configured);
    assert(strings[SYMBOL_DESCRIPTION]!="");
    assert(sessions.size()==(scenario=="required_weekends" ? 2 : 1));
    if(scenario=="required_weekends"){assert(sessions.count(0)&&sessions.count(6));}
    if(scenario=="required_session_missing") sessions.clear();
    if(scenario=="required_session_wrong_bounds") sessions[3]={0,3600};
    if(scenario=="point_mismatch") doubles[SYMBOL_POINT]=0.01;
    if(scenario=="digits_mismatch") integers[SYMBOL_DIGITS]=2;
    if(scenario=="trade_enabled") integers[SYMBOL_TRADE_MODE]=999;
    if(scenario=="chart_mismatch") integers[SYMBOL_CHART_MODE]=999;
    if(scenario=="tick_size_mismatch") doubles[SYMBOL_TRADE_TICK_SIZE]=0.01;
    if(scenario=="description_missing") strings[SYMBOL_DESCRIPTION]="";
    if(scenario=="financial_getter_fail") unreadable=SYMBOL_TRADE_TICK_VALUE;
    if(scenario=="financial_all_match") strings[SYMBOL_CURRENCY_MARGIN]="XAU";
    auto preserved_strings=strings;
    auto preserved_setters=setters;
    bool expected=scenario=="v10_margin_and_absent_weekends" || scenario=="financial_getter_fail"
        || scenario=="financial_all_match" || scenario=="required_weekends" || scenario=="financial_currency_getter_fail";
    assert(VerifyConfiguration()==expected);
    assert(strings==preserved_strings && setters==preserved_setters);
    assert(logs.str().find("no financial/Tester acceptance")!=string::npos);
    assert(logs.str().find(scenario=="financial_all_match" ? "|NOT_CERTIFIED" : "|BLOCKED")!=string::npos);
}
'''.replace("CONSTANTS", constants).replace("FUNCTIONS", functions)
    directory = tmp_path_factory.mktemp("g4_configuration_stubs")
    fixture = directory / "configuration.cpp"
    fixture.write_text(program, encoding="ascii")
    binary = directory / "configuration.exe"
    compiled = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(fixture), "-o", str(binary)],
                              capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return binary


@pytest.mark.parametrize("scenario", [
    "v10_margin_and_absent_weekends", "financial_all_match", "financial_getter_fail", "required_weekends",
    "setter_fail", "description_setter_fail", "session_setter_fail", "required_session_missing",
    "required_session_wrong_bounds", "point_mismatch", "digits_mismatch", "trade_enabled", "chart_mismatch",
    "tick_size_mismatch", "description_missing", "data_getter_fail", "financial_currency_getter_fail",
])
def test_actual_configuration_control_flow_with_offline_api_stubs(configuration_stub_program, scenario):
    completed = subprocess.run([str(configuration_stub_program), scenario], capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0, scenario + completed.stdout + completed.stderr


@pytest.fixture(scope="module")
def history_comparison_program(tmp_path_factory):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("C++ compiler unavailable for actual-source offline history comparison")
    source = media.RESEARCH_SOURCE.read_text()
    comparison = "struct G4ReadbackComparison" + source.split("struct G4ReadbackComparison", 1)[1].split("bool Roundtrip(", 1)[0]
    # Only map MQL array-reference syntax to C++ vectors; retain the actual comparison logic.
    comparison = re.sub(r"(MqlRates|MqlTick) &(\w+)\[\]", r"std::vector<\1> &\2", comparison)
    program = r'''
#include <cassert>
#include <string>
#include <vector>
using datetime=long long;
const int G4_BARS=245,G4_TICKS=63156;
struct MqlRates { datetime time; double open=10,high=11,low=9,close=10; long tick_volume=1,real_volume=0; int spread=240; };
struct MqlTick { datetime time,time_msc; double bid=10,ask=10.2,last=0; int flags=2; long volume=0; double volume_real=0; };
template<class T> int ArraySize(std::vector<T>& a){return (int)a.size();}
template<class... T> void PrintFormat(const char*,T...){}
void Print(const char*){}
COMPARISON
int main(int argc,char** argv){
    assert(argc==2); std::string scenario=argv[1];
    std::vector<MqlRates> bars;
    for(int i=0;i<G4_BARS;i++) bars.push_back({1793796900LL+i*60});
    datetime boundary=bars.back().time+60;
    std::vector<MqlTick> ticks;
    for(int i=0;i<G4_TICKS;i++){
        datetime ms=i<G4_TICKS-394 ? 1793800800000LL+i*170LL : boundary*1000+(i-(G4_TICKS-394))*150LL;
        ticks.push_back({ms/1000,ms});
    }
    auto actual_bars=bars;
    if(scenario!="exact_source_only") actual_bars.push_back({boundary});
    auto actual_ticks=ticks;
    if(scenario=="wrong_extra_time") actual_bars.back().time+=60;
    if(scenario=="two_extra_bars") actual_bars.push_back({boundary+60});
    if(scenario=="missing_bar") actual_bars.erase(actual_bars.begin()+3);
    if(scenario=="reordered_bars") std::swap(actual_bars[0],actual_bars[1]);
    if(scenario=="duplicate_bar") actual_bars[1]=actual_bars[0];
    if(scenario=="missing_tick") actual_ticks.pop_back();
    if(scenario=="extra_tick") actual_ticks.push_back(actual_ticks.back());
    if(scenario=="reordered_ticks") std::swap(actual_ticks[0],actual_ticks[1]);
    if(scenario=="duplicate_tick") actual_ticks[1]=actual_ticks[0];
    if(scenario=="bar_time") actual_bars[100].time++;
    if(scenario=="bar_open") actual_bars[100].open++;
    if(scenario=="bar_high") actual_bars[100].high++;
    if(scenario=="bar_low") actual_bars[100].low++;
    if(scenario=="bar_close") actual_bars[100].close++;
    if(scenario=="bar_tick_volume") actual_bars[100].tick_volume++;
    if(scenario=="bar_real_volume") actual_bars[100].real_volume++;
    if(scenario=="bar_spread") actual_bars[100].spread++;
    if(scenario=="tick_time") actual_ticks[100].time++;
    if(scenario=="tick_time_msc") actual_ticks[100].time_msc++;
    if(scenario=="tick_bid") actual_ticks[100].bid++;
    if(scenario=="tick_ask") actual_ticks[100].ask++;
    if(scenario=="tick_last") actual_ticks[100].last++;
    if(scenario=="normalized_flags_volume"){actual_ticks[100].flags++;actual_ticks[100].volume++;}
    if(scenario=="no_source_boundary_ticks"){
        for(int i=G4_TICKS-394;i<G4_TICKS;i++){
            ticks[i].time_msc=(boundary-60)*1000+(i-(G4_TICKS-394))*150LL;
            ticks[i].time=ticks[i].time_msc/1000;
        }
        actual_ticks=ticks;
    }
    if(scenario=="another_tick_only_minute"){
        ticks.back().time+=60;ticks.back().time_msc+=60000;actual_ticks=ticks;
    }
    G4ReadbackComparison report;
    bool ok=CompareHistory(bars,ticks,actual_bars,actual_ticks,report);
    bool expected=scenario=="exact_source_only" || scenario=="source_plus_boundary" || scenario=="normalized_flags_volume";
    assert(ok==expected);
    if(ok){assert(report.boundary_ticks==394); assert(report.generated_bars==(scenario=="exact_source_only" ? 0 : 1));}
    if(scenario=="normalized_flags_volume"){assert(report.flag_changes==1 && report.volume_changes==1);}
}
'''.replace("COMPARISON", comparison)
    directory = tmp_path_factory.mktemp("g4_readback_stubs")
    fixture, binary = directory / "comparison.cpp", directory / "comparison.exe"
    fixture.write_text(program, encoding="ascii")
    compiled = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(fixture), "-o", str(binary)],
                              capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return binary


@pytest.mark.parametrize("scenario", [
    "exact_source_only", "source_plus_boundary", "normalized_flags_volume", "wrong_extra_time", "two_extra_bars",
    "missing_bar", "reordered_bars", "duplicate_bar", "missing_tick", "extra_tick", "reordered_ticks", "duplicate_tick",
    "no_source_boundary_ticks", "another_tick_only_minute",
    *["bar_" + field for field in ("time", "open", "high", "low", "close", "tick_volume", "real_volume", "spread")],
    *["tick_" + field for field in ("time", "time_msc", "bid", "ask", "last")],
])
def test_actual_history_comparison_offline(history_comparison_program, scenario):
    completed = subprocess.run([str(history_comparison_program), scenario], capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0, scenario + completed.stdout + completed.stderr


def boundary_package(package):
    # Controlled fixture: add a real-shaped boundary record, not evidence of native success.
    changed = copy.deepcopy(package)
    lines = changed["files"]["ticks.tsv"].splitlines(keepends=True)
    lines[-1] = "2026.11.04\t17:00:00.000\t4000\t4000.24\t0\t0\n"
    changed["files"]["ticks.tsv"] = "".join(lines)
    records = changed["files"]["source_ticks.jsonl"].splitlines(keepends=True)
    last = json.loads(records[-1])
    last.update(time=1793811600, time_msc=1793811600000)
    records[-1] = json.dumps(last) + "\n"
    changed["files"]["source_ticks.jsonl"] = "".join(records)
    changed["file_sha256"] = {n: checksum(v.encode()) for n, v in changed["files"].items()}
    changed["strategy"]["ticks_tsv_sha256"] = changed["file_sha256"]["ticks.tsv"]
    changed["strategy"]["tick_source"]["data_sha256"] = changed["file_sha256"]["source_ticks.jsonl"]
    changed["strategy"]["custom_symbol"] = "G4CAP_" + changed["strategy"]["tick_source"]["data_sha256"][:12]
    changed["strategy_sha256"] = checksum(canonical_bytes(changed["strategy"]))
    return changed


def test_prepare_verification_only_preserves_data_and_compiles_out_mutations(package, tmp_path):
    changed = boundary_package(package)
    raw = canonical_bytes(changed)
    payload, original = media.prepare(raw, checksum(raw), recovery_mode="IMPORT")
    for name, content in payload.items():
        (tmp_path / name).write_bytes(content)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    files, receipt = media.prepare_verification(tmp_path, checksum(payload["manifest.json"]))
    assert set(files) == {"G4Verify.mq5", "G4ImportPins.mqh", "verification_manifest.json"}
    assert receipt["allowed_tick_formed_bar_utc"] == "2026-11-04T17:00:00+00:00"
    assert receipt["boundary_source_ticks"] == 1
    assert receipt["data_mutation_allowed"] is False and receipt["financial_certification"] is False
    assert b"#define G4_VERIFICATION_ONLY" in files["G4ImportPins.mqh"]
    assert f'#define G4_SYMBOL "{original["custom_symbol"]}"'.encode() in files["G4ImportPins.mqh"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    with pytest.raises(ValueError, match="MANIFEST_PIN_MISMATCH"):
        media.prepare_verification(tmp_path, "0" * 64)
    (tmp_path / "ticks.tsv").write_bytes(b"changed")
    with pytest.raises(ValueError, match="MEDIA_PIN_MISMATCH"):
        media.prepare_verification(tmp_path, checksum(payload["manifest.json"]))
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("C++ preprocessor unavailable for read-only call-path check")
    source = "\n".join(line for line in files["G4Verify.mq5"].decode().splitlines()
                       if not line.startswith(("#property", "#include")))
    preprocessed = subprocess.run([compiler, "-E", "-P", "-x", "c++", "-DG4_VERIFICATION_ONLY", "-"],
                                 input=source, capture_output=True, text=True, timeout=10)
    assert preprocessed.returncode == 0, preprocessed.stderr
    start = preprocessed.stdout.split("void OnStart()", 1)[1]
    roundtrip = preprocessed.stdout.split("bool Roundtrip(", 1)[1].split("void OnStart()", 1)[0]
    for forbidden in ("CustomSymbol", "CustomRates", "CustomTicks", "SymbolSelect", "Configure()", "FileOpen", "FileWrite"):
        assert forbidden not in start + roundtrip
    assert "VerifyConfiguration()" in start and "CompareHistory(" in roundtrip


@pytest.fixture
def capture_import_case(package, tmp_path):
    import csv
    import io
    changed = boundary_package(package)
    strategy = changed["strategy"]
    changed["capture"].update(end=1793811600, split=1793808000,
        signals=[{"signal_time": 1793808120, "action": "ENTRY", "triggered": True}])
    strategy.update(schema_version="r1-native-capture/v1", capture_sha256=checksum(canonical_bytes(changed["capture"])),
                    source_sha256="", decimal_source_sha256="")
    for name in ("SignalReplay.mq5", "ParityDecimal.mqh"):
        changed["files"][name] = media.RESEARCH_SOURCE.with_name(name).read_text()
    strategy["source_sha256"] = checksum(changed["files"]["SignalReplay.mq5"].encode())
    strategy["decimal_source_sha256"] = checksum(changed["files"]["ParityDecimal.mqh"].encode())
    changed["strategy_sha256"] = checksum(canonical_bytes(strategy))
    capture = changed["capture"]
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows([
        ["SIGNAL_CAPTURE_V1", changed["strategy_sha256"], "CONTINUOUS", strategy["custom_symbol"], 60,
         capture["start"], capture["end"], capture["split"], 1], [1793808120, 0, "ENTRY", 1], ["END"]])
    changed["files"]["replay_schedule.csv"] = stream.getvalue()
    changed["files"]["SignalReplay.set"] = "ApprovedResearchReplay=false\nCaptureOnly=true\n"
    changed["files"]["capture.ini"] = ("[Tester]\nSymbol=" + strategy["custom_symbol"] +
        "\nExpert=SignalReplay.ex5\nModel=4\nUseLocal=1\nUseRemote=0\nUseCloud=0\nOptimization=0\nForwardMode=0\nReplaceReport=0\n")
    changed["file_sha256"] = {n: checksum(v.encode()) for n, v in changed["files"].items()}
    raw = canonical_bytes(changed)
    files, manifest = media.prepare(raw, checksum(raw), recovery_mode="IMPORT")
    # This fixture omits pre-start; the original source bars remain its own import bars.
    manifest["original_bars_tsv_sha256"] = strategy["bars_tsv_sha256"]
    files["manifest.json"] = canonical_bytes(manifest)
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    return raw, tmp_path, checksum(files["manifest.json"]), manifest


def test_capture_alias_binding_preserves_research_and_no_execution(capture_import_case):
    import csv
    import io
    raw, directory, manifest_pin, manifest = capture_import_case
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    original = json.loads(raw)
    bound = media.bind_capture_import(raw, checksum(raw), directory, manifest_pin)
    assert bound == media.bind_capture_import(raw, checksum(raw), directory, manifest_pin)
    assert bound["capture"] == original["capture"]
    assert bound["strategy"]["signal_request"] == original["strategy"]["signal_request"]
    assert bound["strategy"]["custom_symbol"] == manifest["custom_symbol"]
    assert bound["strategy"]["import_binding"]["native_execution_attested"] is False
    for name in ("bars.tsv", "ticks.tsv", "source_ticks.jsonl", "SignalReplay.mq5", "ParityDecimal.mqh", "SignalReplay.set"):
        assert bound["files"][name] == original["files"][name]
    old_rows = list(csv.reader(io.StringIO(original["files"]["replay_schedule.csv"])))
    rows = list(csv.reader(io.StringIO(bound["files"]["replay_schedule.csv"])))
    assert rows[1:] == old_rows[1:] and rows[0][1] == bound["strategy_sha256"]
    assert rows[0][3] == manifest["custom_symbol"]
    assert "UseCloud=0" in bound["files"]["capture.ini"] and "Model=4" in bound["files"]["capture.ini"]
    assert "Expert=G4Capture_" in bound["files"]["capture.ini"]
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.parametrize("mutation,reason", [
    ("package_pin", "PACKAGE_PIN"), ("manifest_pin", "MANIFEST_PIN"), ("data", "MEDIA_PIN"),
    ("schedule", "BINDING_INVALID"), ("authority", "BINDING_INVALID"),
    ("remote", "TESTER_CONFIG_INVALID"), ("enabled_default", "BINDING_INVALID"),
])
def test_capture_alias_binding_fails_closed(capture_import_case, mutation, reason):
    raw, directory, manifest_pin, _ = capture_import_case
    pin = checksum(raw)
    if mutation == "package_pin":
        pin = "0" * 64
    elif mutation == "manifest_pin":
        manifest_pin = "0" * 64
    elif mutation == "data":
        (directory / "ticks.tsv").write_bytes(b"changed")
    else:
        changed = json.loads(raw)
        if mutation == "schedule":
            changed["files"]["replay_schedule.csv"] += "extra\n"
        elif mutation == "remote":
            changed["files"]["capture.ini"] = changed["files"]["capture.ini"].replace("UseRemote=0", "UseRemote=1")
        elif mutation == "enabled_default":
            changed["files"]["SignalReplay.set"] = changed["files"]["SignalReplay.set"].replace("Replay=false", "Replay=true")
        else:
            changed["strategy"]["execution_allowed"] = True
        changed["file_sha256"] = {n: checksum(v.encode()) for n, v in changed["files"].items()}
        raw = canonical_bytes(changed)
        pin = checksum(raw)
        # Controlled fixture repinning reaches inner gates; never applied to real approval evidence.
        manifest = json.loads((directory / "manifest.json").read_bytes())
        manifest["capture_package_sha256"] = pin
        manifest_bytes = canonical_bytes(manifest)
        (directory / "manifest.json").write_bytes(manifest_bytes)
        manifest_pin = checksum(manifest_bytes)
    with pytest.raises(ValueError, match=reason):
        media.bind_capture_import(raw, pin, directory, manifest_pin)


def prestart_source(tmp_path, mutation=None):
    start, end = 1793796900, 1793800800
    if mutation == "overlap":
        end += 60
    request = HistoricalDataRequest("EURUSD" if mutation == "symbol" else "XAUUSD", "XAUUSDm",
        "M1", "2026-11-04T12:55:00Z", "2026-11-04T14:01:00Z" if mutation == "overlap" else "2026-11-04T14:00:00Z",
        warmup_records=1)
    rows = [dict(time=t, open=4000.123, high=4001.234, low=3999.001, close=4000.234,
        tick_volume=1, real_volume=0, spread=240) for t in range(start, end, 60)]
    if mutation == "gap":
        del rows[2]
    return persist_dataset(tmp_path, request, rows, contract={}, acquired_at="2026-11-13T00:00:00Z")


def test_245_bars_preserve_original_window_ticks_and_provenance(package, tmp_path):
    source, manifest = prestart_source(tmp_path)
    original = canonical_bytes(package)
    payload, result = media.prepare(original, checksum(original), prestart_folder=source,
        prestart_manifest_sha256=manifest["manifest_checksum"])
    assert result["bar_count"] == 245 and result["tick_count"] == 63156
    assert result["prestart"]["available_before_capture"] == 100
    assert result["prestart"]["missing"] == 0 and result["prestart"]["request"] is None
    assert result["prestart"]["source"]["data_sha256"] == manifest["data_checksum"]
    assert result["prestart"]["source"]["research_scope_expanded"] is False
    assert payload["bars.tsv"].endswith(package["files"]["bars.tsv"].split("\n", 1)[1].encode())
    assert payload["ticks.tsv"] == package["files"]["ticks.tsv"].encode()
    assert payload["source_ticks.jsonl"] == package["files"]["source_ticks.jsonl"].encode()
    assert canonical_bytes(package) == original
    assert b"#define G4_BARS 245" in payload["G4ImportPins.mqh"]
    assert media.prepare(original, checksum(original), prestart_folder=source,
        prestart_manifest_sha256=manifest["manifest_checksum"]) == (payload, result)


@pytest.mark.parametrize("mutation", ["pin", "gap", "overlap", "symbol", "data", "missing_pin"])
def test_prestart_rejects_invalid_scope_coverage_or_checksum(package, tmp_path, mutation):
    source, manifest = prestart_source(tmp_path, mutation)
    if mutation == "data":
        with (source / "data.jsonl").open("ab") as stream:
            stream.write(b"\n")
    pin = "0" * 64 if mutation == "pin" else manifest["manifest_checksum"]
    if mutation == "missing_pin":
        pin = None
    raw = canonical_bytes(package)
    with pytest.raises(ValueError):
        media.prepare(raw, checksum(raw), prestart_folder=source, prestart_manifest_sha256=pin)


@pytest.mark.parametrize("case,blocked", [
    ("empty", False), ("miniports", False), ("vm_nic", True),
    ("software_nic", True), ("unknown", True), ("enumeration_failure", True), ("metadata_missing", True),
    ("actual_inventory", False), ("actual_inventory_empty_component", False), ("actual_inventory_attached_nic", True),
    ("pseudo_up", True), ("pseudo_disconnected", True), ("pseudo_no_status", True),
    ("pseudo_name_only", True), ("renamed_vm_nic", True), ("conflicting_wan", True),
    ("exact_g3_inventory", False), ("exact_g3_plus_vm_nic", True),
    ("six_to_four", False), ("six_to_four_up", True),
    ("actual_six_to_four", False), ("fallback_unknown_name", True),
    ("fallback_component_conflict", True), ("fallback_description_conflict", True),
    ("fallback_hardware_true", True), ("fallback_hardware_not_bool", True),
    ("fallback_missing_hardware", True), ("fallback_missing_status", True),
    ("fallback_up", True), ("fallback_disconnected", True), ("fallback_wrong_case", True),
    ("fallback_missing_component", True), ("fallback_missing_description", True),
    ("actual_teredo", False), ("actual_iphttps", False), ("name_only_nulls", False),
    ("exact_g3_null_inventory", False), ("name_only_missing_name", True),
    ("actual_teredo_up", True), ("actual_iphttps_up", True),
    ("teredo_conflict", True), ("iphttps_missing_component", True),
])
def test_offline_guard_classifies_internal_miniports_fail_closed(case, blocked):
    script = Path(__file__).with_name("g4_import_media.ps1")
    program = r'''
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Get-CimInstance { param($ClassName,$ErrorAction)
    [pscustomobject]@{Manufacturer='Microsoft Corporation';Model='Virtual Machine'} }
function Get-NetAdapter { param([switch]$IncludeHidden,$ErrorAction)
    if(!$IncludeHidden -or $ErrorAction -ne 'Stop'){throw 'ENUMERATION_NOT_STRICT'}
    switch('CASE') {
        'empty' { return }
        'miniports' {
            $ids=@('ms_ndiswanip','ms_ndiswanipv6','ms_ndiswanbh','ms_pptpminiport',
                'ms_l2tpminiport','ms_agilevpnminiport','ms_sstpminiport','ms_pppoeminiport')
            for($i=0;$i -lt 12;$i++) { [pscustomobject]@{HardwareInterface=$false;ComponentID=$ids[$i%8]} }
        }
        {$_ -in @('actual_inventory','actual_inventory_empty_component','actual_inventory_attached_nic')} {
            # Operator-reported interface family/states, not a captured raw guest ComponentID export.
            $wan=@('IP','IPv6','Network Monitor','PPTP','L2TP','IKEv2','SSTP','PPPOE')
            foreach($kind in $wan) {
                $item=[pscustomobject]@{HardwareInterface=$false;InterfaceDescription="WAN Miniport ($kind)";Status='Disconnected'}
                if('CASE' -eq 'actual_inventory_empty_component') { $item | Add-Member -NotePropertyName ComponentID -NotePropertyValue '' }
                $item
            }
            foreach($driver in @('Teredo Tunneling Pseudo-Interface','Microsoft 6to4 Adapter',
                'Microsoft IP-HTTPS Platform Interface','Microsoft Kernel Debug Network Adapter')) {
                [pscustomobject]@{HardwareInterface=$false;InterfaceDescription=$driver;Status='Not Present'}
            }
            if('CASE' -eq 'actual_inventory_attached_nic') {
                [pscustomobject]@{HardwareInterface=$false;InterfaceDescription='Microsoft Hyper-V Network Adapter';ComponentID='vms_mp';Status='Not Present'}
            }
        }
        {$_ -in @('exact_g3_inventory','exact_g3_plus_vm_nic','exact_g3_null_inventory')} {
            $rows=@(
                @('WAN Miniport (IKEv2)','ms_agilevpnminiport','Disconnected'),
                @('WAN Miniport (PPPOE)','ms_pppoeminiport','Disconnected'),
                @('WAN Miniport (Network Monitor)','ms_ndiswanbh','Up'),
                @('WAN Miniport (IP)','ms_ndiswanip','Up'),
                @('WAN Miniport (PPTP)','ms_pptpminiport','Disconnected'),
                @('WAN Miniport (SSTP)','ms_sstpminiport','Disconnected'),
                @('WAN Miniport (IPv6)','ms_ndiswanipv6','Up'),
                @('WAN Miniport (L2TP)','ms_l2tpminiport','Disconnected'),
                @('Teredo Tunneling Pseudo-Interface','','Not Present'),
                @('Microsoft Kernel Debug Network Adapter','','Not Present'),
                @('Microsoft IP-HTTPS Platform Interface','','Not Present'),
                @('6to4 Adapter','','Not Present'))
            foreach($row in $rows) {
                $nameOnly=$row[0] -in @('Teredo Tunneling Pseudo-Interface','Microsoft IP-HTTPS Platform Interface','6to4 Adapter')
                [pscustomobject]@{HardwareInterface=$false;Name=$(if($row[0] -eq 'Microsoft Kernel Debug Network Adapter'){'Ethernet (Kernel Debugger)'}else{$row[0]});
                    InterfaceDescription=$(if($nameOnly){if('CASE' -eq 'exact_g3_null_inventory'){$null}else{''}}else{$row[0]});
                    ComponentID=$(if($nameOnly -and 'CASE' -eq 'exact_g3_null_inventory'){$null}else{$row[1]});Status=$row[2]}
            }
            if('CASE' -eq 'exact_g3_plus_vm_nic') {
                [pscustomobject]@{HardwareInterface=$true;InterfaceDescription='Microsoft Hyper-V Network Adapter';ComponentID='vms_mp';Status='Up'}
            }
        }
        {$_ -in @('actual_teredo','actual_iphttps','name_only_nulls','name_only_missing_name',
            'actual_teredo_up','actual_iphttps_up','teredo_conflict','iphttps_missing_component')} {
            $names=@('Teredo Tunneling Pseudo-Interface','Microsoft IP-HTTPS Platform Interface','6to4 Adapter')
            if('CASE' -in @('actual_teredo','actual_teredo_up','teredo_conflict')){ $names=@($names[0]) }
            if('CASE' -in @('actual_iphttps','actual_iphttps_up','iphttps_missing_component')){ $names=@($names[1]) }
            foreach($name in $names) {
                $item=[ordered]@{Name=$name;InterfaceDescription='';ComponentID='';Status='Not Present';HardwareInterface=$false}
                if('CASE' -eq 'name_only_nulls'){ $item.InterfaceDescription=$null; $item.ComponentID=$null }
                if('CASE' -eq 'name_only_missing_name'){ $item.Remove('Name') }
                if('CASE' -in @('actual_teredo_up','actual_iphttps_up')){ $item.Status='Up' }
                if('CASE' -eq 'teredo_conflict'){ $item.ComponentID='vms_mp' }
                if('CASE' -eq 'iphttps_missing_component'){ $item.Remove('ComponentID') }
                [pscustomobject]$item
            }
        }
        {$_ -in @('six_to_four','six_to_four_up')} {
            [pscustomobject]@{HardwareInterface=$false;InterfaceDescription='6to4 Adapter';ComponentID='';
                Status=$(if('CASE' -eq 'six_to_four'){'Not Present'}else{'Up'})}
        }
        {$_ -eq 'actual_six_to_four' -or $_ -like 'fallback_*'} {
            $adapter=[ordered]@{Name='6to4 Adapter';InterfaceDescription='';ComponentID='';Status='Not Present';HardwareInterface=$false}
            switch('CASE') {
                'fallback_unknown_name' { $adapter.Name='Unknown Adapter' }
                'fallback_component_conflict' { $adapter.ComponentID='vms_mp' }
                'fallback_description_conflict' { $adapter.InterfaceDescription='Microsoft Hyper-V Network Adapter' }
                'fallback_hardware_true' { $adapter.HardwareInterface=$true }
                'fallback_hardware_not_bool' { $adapter.HardwareInterface=0 }
                'fallback_missing_hardware' { $adapter.Remove('HardwareInterface') }
                'fallback_missing_status' { $adapter.Remove('Status') }
                'fallback_missing_component' { $adapter.Remove('ComponentID') }
                'fallback_missing_description' { $adapter.Remove('InterfaceDescription') }
                'fallback_up' { $adapter.Status='Up' }
                'fallback_disconnected' { $adapter.Status='Disconnected' }
                'fallback_wrong_case' { $adapter.Name='6TO4 ADAPTER' }
            }
            [pscustomobject]$adapter
        }
        'pseudo_up' { [pscustomobject]@{HardwareInterface=$false;InterfaceDescription='Teredo Tunneling Pseudo-Interface';Status='Up'} }
        'pseudo_disconnected' { [pscustomobject]@{HardwareInterface=$false;InterfaceDescription='Microsoft 6to4 Adapter';Status='Disconnected'} }
        'pseudo_no_status' { [pscustomobject]@{HardwareInterface=$false;InterfaceDescription='Microsoft IP-HTTPS Platform Interface'} }
        'pseudo_name_only' { [pscustomobject]@{HardwareInterface=$false;Name='Ethernet (Kernel Debugger)';Status='Not Present'} }
        'renamed_vm_nic' { [pscustomobject]@{HardwareInterface=$false;Name='Ethernet (Kernel Debugger)';InterfaceDescription='Microsoft Hyper-V Network Adapter';Status='Not Present'} }
        'conflicting_wan' { [pscustomobject]@{HardwareInterface=$false;ComponentID='ms_ndiswanip';InterfaceDescription='Microsoft Hyper-V Network Adapter'} }
        'vm_nic' { [pscustomobject]@{HardwareInterface=$true;ComponentID='vms_mp';Status='Disabled'} }
        'software_nic' { [pscustomobject]@{HardwareInterface=$false;ComponentID='vms_mp';Status='Disconnected'} }
        'unknown' { [pscustomobject]@{HardwareInterface=$false;ComponentID='unknown'} }
        'metadata_missing' { [pscustomobject]@{Name='WAN Miniport (IP)'} }
        'enumeration_failure' { Write-Error 'DENIED' }
    }
}
$e=$null; $t=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('SCRIPT',[ref]$t,[ref]$e)
$f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Assert-G4OfflineGuest'},$true)
. ([scriptblock]::Create($f.Extent.Text))
if('CASE' -in @('exact_g3_inventory','exact_g3_null_inventory')) {
    $inventory=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop)
    if($inventory.Count -ne 12 -or @($inventory | Where-Object {$_.HardwareInterface -isnot [bool]}).Count) {
        throw 'ACTUAL_INVENTORY_FIXTURE_COUNT_OR_TYPE_INVALID'
    }
}
try { Assert-G4OfflineGuest; Write-Output 'ALLOWED' } catch { Write-Output ('BLOCKED '+$_.Exception.Message) }
'''.replace("CASE", case).replace("SCRIPT", str(script))
    completed = subprocess.run(["powershell", "-NoProfile", "-Command", program], capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout.strip()
    assert output.startswith("BLOCKED ") if blocked else output == "ALLOWED"
    if case in {"exact_g3_plus_vm_nic", "six_to_four_up", "unknown", "metadata_missing"}:
        reason = json.loads(output.split(": ", 1)[1])
        assert reason["Reason"]
        if case == "exact_g3_plus_vm_nic":
            assert reason["InterfaceDescription"] == "Microsoft Hyper-V Network Adapter"
            assert reason["Reason"] == "HARDWARE_NIC_PRESENT"
        if case == "six_to_four_up":
            assert reason["InterfaceDescription"] == "6to4 Adapter"
            assert reason["Reason"] == "PSEUDO_INTERFACE_NOT_ABSENT"
    if case in {"actual_teredo_up", "actual_iphttps_up", "teredo_conflict", "iphttps_missing_component"}:
        reason = json.loads(output.split(": ", 1)[1])
        assert reason["Name"] in {"Teredo Tunneling Pseudo-Interface", "Microsoft IP-HTTPS Platform Interface"}
        assert reason["Reason"] == {"actual_teredo_up": "NAME_ONLY_STATUS_NOT_ABSENT",
            "actual_iphttps_up": "NAME_ONLY_STATUS_NOT_ABSENT", "teredo_conflict": "NAME_ONLY_IDENTITY_NOT_EMPTY",
            "iphttps_missing_component": "NAME_ONLY_IDENTITY_PROPERTY_MISSING"}[case]
