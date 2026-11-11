import csv
import io
import json
import math
from hashlib import sha256
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from src.services.trading.market.models import OHLCVBar
from src.services.trading.research.tester_parity import (
    ParityCase,compare_results,fixture_csv,reference,load_fixture_csv,numeric_cases,
    numeric_reference,compare_numeric_results,prepare_numeric_package,
)


def parity_cases():
    start=datetime(2026,11,4,15,tzinfo=timezone.utc)
    def make(name,closes):
        records=tuple(OHLCVBar((start+timedelta(minutes=i)).isoformat(),v,v+.2,v-.2,v,10)
                      for i,v in enumerate(closes))
        return ParityCase(name,records,Decimal("104"))
    up=make("rising",[100+i*.1 for i in range(15)])
    return [up,make("falling",[102-i*.1 for i in range(15)]),make("flat",[100]*15),
            make("mixed",[100+(i%4)*.1 for i in range(30)]),
            replace(up,name="warmup14",bars=up.bars[:14]),
            replace(up,name="below_minimum",risk_cap=Decimal("0.01")),
            replace(up,name="volume_cap",volume_cap=Decimal("0.02")),
            replace(up,name="broker_cap",volume_cap=Decimal("1"),volume_max=Decimal("0.03")),
            replace(up,name="step",step=Decimal("0.03"),volume_min=Decimal("0.03"),volume_cap=Decimal("0.08")),
            replace(up,name="active",active_entry=True),
            replace(up,name="level_no_cross",previous=100),
            replace(up,name="half_tick",entry=Decimal("104.0005"))]


@pytest.mark.parametrize("case",parity_cases(),ids=lambda c:c.name)
def test_reference_vectors_use_production_formulas_and_fail_closed(case):
    row=reference(case)
    assert len(row)==11
    assert len(next(csv.reader(io.StringIO(fixture_csv([case])))))==2+4*len(case.bars)+17
    if case.name in {"warmup14","below_minimum","active","falling"}:
        assert row[-1]==0
    if row[-1]:
        assert Decimal(str(row[7]))<=case.risk_cap
        assert Decimal(str(row[6]))<=min(case.volume_cap,case.volume_max)


def test_compare_rejects_wrong_values_missing_duplicate_or_nonfinite_rows():
    cases=parity_cases()
    def encode(rows):
        out=io.StringIO(); csv.writer(out).writerows(rows); return out.getvalue()
    rows=[reference(c) for c in cases]
    assert compare_results(cases,encode(rows))["status"]=="PASS"
    assert compare_results(cases,encode(rows[:-1]))["status"]=="FAIL"
    assert compare_results(cases,encode([rows[0]]*len(rows)))["status"]=="FAIL"
    rows[0][6]=99
    assert compare_results(cases,encode(rows))["status"]=="FAIL"
    rows[0][6]="NaN"
    assert compare_results(cases,encode(rows))["status"]=="FAIL"


def test_ea_is_tester_only_default_nontrading_and_not_wilder_indicators():
    source=Path("tools/mt5_bridge/research/StrategyParity.mq5").read_text()
    initialization=source.split("int OnInit()",1)[1].split("void OnTick()",1)[0]
    assert initialization.index("!MQLInfoInteger(MQL_TESTER)")<initialization.index("RunFixtures()")
    assert "input bool SimulateOrders=false;" in source
    assert source.count("OrderSend(")==1
    assert "if(!MQLInfoInteger(MQL_TESTER)) return;\n   bool sent=OrderSend" in source
    assert "MQLInfoInteger(MQL_OPTIMIZATION)" in source
    assert "CopyRates(_Symbol,PERIOD_M1,1,15,bars)" in source
    assert "completed==last_completed" in source and "accepted++;" in source
    assert "iRSI(" not in source and "iATR(" not in source
    assert "#import" not in source and "WebRequest(" not in source


def test_fixture_decisions_use_native_rsi_not_python_expected_input():
    source=Path("tools/mt5_bridge/research/StrategyParity.mq5").read_text()
    fixtures=source.split("int RunFixtures()",1)[1].split("int OnInit()",1)[0]
    assert "bool warm=Indicators(bars,n,rsi,atr);" in fixtures
    decisions=fixtures.split("FileWrite(output",1)[1].split("count++;",1)[0]
    assert "(int)(rsi>threshold)" in decisions
    assert "(int)(previous<=threshold && rsi>threshold)" in decisions
    assert "(int)(valid && rsi>threshold && !active)" in decisions
    assert "current" not in decisions
    assert "double previous=FileReadNumber(source);" in fixtures
    assert "FileReadNumber(source); // Consume legacy expected-RSI column" in fixtures


def test_empty_fixture_is_rejected():
    with pytest.raises(ValueError,match="BAR_COUNT"):
        fixture_csv([replace(parity_cases()[0],bars=())])


def test_half_tick_decimal_difference_is_not_hidden_by_price_tolerance():
    from src.services.trading.proposal.editable_trade_draft import _round_tick

    entry=Decimal("4032.546")
    atr_value=Decimal("3.1750000000000194")
    assert _round_tick(entry-atr_value*Decimal("1.5"),Decimal("0.001"))==Decimal("4027.783")
    assert float(entry)-float(atr_value)*1.5==4027.7835
    case=parity_cases()[0]
    row=reference(case)
    row[4]+=0.001
    out=io.StringIO(); csv.writer(out).writerow(row)
    assert compare_results([case],out.getvalue())["status"]=="FAIL"


RETAINED=Path("data/research/mt5_tester/s11b/MQL5/Files/s11b_parity.csv")
RETAINED_SHA="b83232054545190a93a9252ec884947bb23001a245c7a3b165d39e717e8c14f3"


@pytest.fixture
def retained_cases():
    if not RETAINED.is_file():
        pytest.skip("Retained local historical math evidence unavailable; no native PASS implied")
    assert sha256(RETAINED.read_bytes()).hexdigest()==RETAINED_SHA
    return load_fixture_csv(RETAINED.read_text())


@pytest.mark.parametrize("index",range(58))
def test_all_retained_vectors_keep_archived_python_contract(index,retained_cases):
    archive=json.loads(RETAINED.parents[2].joinpath("python_reference.json").read_text())
    expected={row[0]:row for row in archive["rows"]}
    case=retained_cases[index]
    assert reference(case)==expected[case.name]
    assert load_fixture_csv(fixture_csv([case]))==(case,)
    sell=reference(replace(case,side="SELL"))
    assert sell[2:4]==expected[case.name][2:4]
    if sell[-1]:
        assert sell[4]>float(case.entry)>sell[5]
        assert Decimal(str(sell[6]))<=min(case.volume_cap,case.volume_max)
        assert Decimal(str(sell[7]))<=case.risk_cap


def test_historical_native_evidence_is_rechecked_not_relabelled_current(retained_cases):
    old=Path("data/research/mt5_tester/s11b/Tester/Agent-127.0.0.1-3000/MQL5/Files/s11b_parity_result.csv")
    report=compare_results(retained_cases,old.read_text(encoding="utf-8-sig"))
    assert report["status"]=="FAIL"
    assert report["failures"]==["real_16:COLUMN_4","real_16:COLUMN_5","real_16:COLUMN_7"]
    assert len(report["passing_ids"])==57
    assert report["differences"][0]=={"case":"real_16","column":4,"expected":"4027.783","observed":"4027.784000000000"}


@pytest.mark.parametrize("side",["BUY","SELL"])
@pytest.mark.parametrize("entry",[Decimal(str(math.nextafter(104.0005,0))),Decimal("104.0005"),
                                  Decimal(str(math.nextafter(104.0005,math.inf)))])
def test_buy_sell_prices_use_production_tick_contract(side,entry):
    case=replace(parity_cases()[0],side=side,entry=entry)
    row=reference(case)
    from src.services.trading.market.indicators import atr
    from src.services.trading.proposal.editable_trade_draft import _round_tick
    direction=Decimal(1 if side=="BUY" else -1)
    stop=_round_tick(entry-direction*Decimal(str(atr(list(case.bars),14)))*Decimal("1.5"),case.tick)
    distance=direction*(entry-stop)
    assert Decimal(str(row[4]))==stop
    assert Decimal(str(row[5]))==_round_tick(entry+direction*distance*2,case.tick)
    assert row[6]==0.01 and row[-1]==1


@pytest.mark.parametrize("budget,cap,step,minimum,maximum,expected",[
    ("0.599999999999","0.01","0.01","0.01","200",-1),
    ("0.6","0.01","0.01","0.01","200",0.01),
    ("20","0.08","0.03","0.03","200",0.06),
    ("20","1","0.01","0.01","0.03",0.03),
])
def test_broker_limits_and_floor_never_raise_to_minimum(budget,cap,step,minimum,maximum,expected):
    case=replace(parity_cases()[0],risk_cap=Decimal(budget),volume_cap=Decimal(cap),
                 step=Decimal(step),volume_min=Decimal(minimum),volume_max=Decimal(maximum))
    row=reference(case)
    assert row[6]==expected
    if expected>0:
        assert Decimal(str(row[6]))%case.step==0
        assert Decimal(str(row[7]))<=case.risk_cap
    else:
        assert row[-1]==0


@pytest.mark.parametrize("field,value",[("entry",Decimal("NaN")),("equity",Decimal("Infinity")),
    ("step",Decimal(0)),("volume_min",Decimal(-1)),("tick",Decimal(0)),("side","HOLD"),
    ("previous",math.nan),("threshold",math.inf)])
def test_invalid_case_is_rejected_before_fixture_or_reference(field,value):
    case=replace(parity_cases()[0],**{field:value})
    with pytest.raises(ValueError): reference(case)
    with pytest.raises(ValueError): fixture_csv([case])


@pytest.mark.parametrize("value",["NaN","sNaN","Infinity","bad","", "1e999999999"])
def test_bad_native_cells_fail_with_vector_and_both_values(value):
    case=parity_cases()[0]; row=reference(case); row[4]=value
    out=io.StringIO(); csv.writer(out).writerow(row)
    report=compare_results([case],out.getvalue())
    assert report["status"]=="FAIL"
    assert report["differences"][0]=={"case":case.name,"column":4,"expected":"103.4","observed":value}


@pytest.mark.parametrize("case",numeric_cases(),ids=lambda c:c.name)
def test_scalar_decimal_oracles_and_serialization(case):
    expected=numeric_reference(case)
    out=io.StringIO(); csv.writer(out).writerow([case.name,expected])
    assert compare_numeric_results([case],out.getvalue())["status"]=="PASS"
    assert compare_numeric_results([case],f"{case.name},wrong\n")["status"]=="FAIL"
    if case.name=="historical_tick": assert Decimal(expected)==Decimal("4027.783")
    if case.name=="half_even_even": assert Decimal(expected)==Decimal("1.000000000000000000000000002")
    if case.name=="half_even_odd": assert Decimal(expected)==Decimal("1.000000000000000000000000004")


def test_decimal_context_is_pinned_and_does_not_escape():
    case=parity_cases()[0]; expected=reference(case)
    with localcontext() as context:
        context.prec=6
        assert reference(case)==expected
        assert context.prec==6


@pytest.mark.parametrize("problem",["duplicate_time","backwards","nonfinite","ohlc"])
def test_invalid_bar_evidence_cannot_reach_numeric_reference(problem):
    case=parity_cases()[0]; bars=list(case.bars)
    if problem=="duplicate_time": bars[-1]=replace(bars[-1],timestamp=bars[-2].timestamp)
    if problem=="backwards": bars.reverse()
    if problem=="nonfinite": bars[-1]=replace(bars[-1],high=math.inf)
    if problem=="ohlc": bars[-1]=replace(bars[-1],high=bars[-1].close-1)
    with pytest.raises(ValueError): reference(replace(case,bars=tuple(bars)))


@pytest.mark.parametrize("mutation",["missing","duplicate","schema","unknown"])
def test_scalar_native_output_shape_must_match_exact_case_set(mutation):
    case=numeric_cases()[0]; row=[case.name,numeric_reference(case)]
    rows=[row]
    if mutation=="missing": rows=[]
    if mutation=="duplicate": rows=[row,row]
    if mutation=="schema": rows=[[case.name]]
    if mutation=="unknown": rows=[["other",row[1]]]
    out=io.StringIO(); csv.writer(out).writerows(rows)
    assert compare_numeric_results([case],out.getvalue())["status"]=="FAIL"


def test_prepared_package_is_deterministic_pinned_and_native_unverified(tmp_path,retained_cases):
    before=RETAINED.read_bytes()
    path=prepare_numeric_package(RETAINED,RETAINED_SHA,tmp_path)
    payload=path.read_bytes(); stamp=path.stat().st_mtime_ns
    assert prepare_numeric_package(RETAINED,RETAINED_SHA,tmp_path)==path
    assert path.read_bytes()==payload and path.stat().st_mtime_ns==stamp
    package=json.loads(payload)
    assert package["proposal_count"]==116 and package["retained_count"]==58
    assert package["native_status"]=="NOT_VERIFIED" and package["compiled_binary_sha256"] is None
    assert package["execution_allowed"] is False and package["simulated_orders_allowed"] is False
    assert len(load_fixture_csv(package["files"]["s11b_parity.csv"]))==116
    assert all(sha256(text.encode()).hexdigest()==package["file_sha256"][name]
               for name,text in package["files"].items())
    assert RETAINED.read_bytes()==before
    with pytest.raises(ValueError,match="CHECKSUM"):
        prepare_numeric_package(RETAINED,"0"*64,tmp_path)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError,match="MISMATCH"):
        prepare_numeric_package(RETAINED,RETAINED_SHA,tmp_path)


def test_native_decimal_and_math_only_source_contract():
    source=Path("tools/mt5_bridge/research/StrategyParity.mq5").read_text()
    decimal=Path("tools/mt5_bridge/research/ParityDecimal.mqh").read_text()
    init=source.split("int OnInit()",1)[1].split("void OnTick()",1)[0]
    assert "input bool MathOnly=true;" in source
    assert "if(MathOnly && SimulateOrders)" in init
    assert init.index("if(MathOnly)")<init.index("ledger=FileOpen")
    assert "if(!MQLInfoInteger(MQL_TESTER) || MathOnly) return;" in source
    assert "RunScalarFixtures()<=0" in init
    assert "MathRound(" not in source
    assert "StringToDouble(stop)" in source and "DFloat(atr)" in source
    assert "avg_gain=(gain+cg)/14,avg_loss=(loss+cl)/14" in source
    assert "next=total+x" in source
    assert "precision<=17" in decimal and "StringToDouble(text)==value" in decimal
    assert "int extra=StringLen(digits)-28" in decimal
    assert "DIntegral(DDiv(price,tick),true)" in decimal
    assert "DMul(DIntegral(DDiv(DMin(DDiv(budget,per_lot),cap),step),false),step)" in source


@pytest.mark.parametrize("mutation",["duplicate","missing","policy","timestamp","side"])
def test_retained_fixture_input_validation(mutation):
    text=fixture_csv([parity_cases()[0]])
    row=next(csv.reader(io.StringIO(text)))
    if mutation=="duplicate": text+=text
    elif mutation=="missing": text=""
    else:
        if mutation=="policy": row[-10]="0.5"
        if mutation=="timestamp": row[6]=row[2]
        if mutation=="side": row[-1]="OTHER"
        out=io.StringIO(); csv.writer(out).writerow(row); text=out.getvalue()
    with pytest.raises(ValueError): load_fixture_csv(text)
