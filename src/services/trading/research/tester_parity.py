"""Python reference vectors for the research-only MQL5 EA; no fill simulation."""
import csv
import io
import math
import platform
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_EVEN, ROUND_DOWN
from pathlib import Path
from typing import Sequence

from ..market.indicators import atr, rsi
from ..market.models import OHLCVBar
# Existing proposal package requires decision-first initialization; no service is run.
from ..decision import conversational_authorization as _draft_bootstrap
from ..proposal.editable_trade_draft import _floor_volume_to_cap, _round_tick, TradeDraftPolicy
from ..reasoning.strategy_evidence import StrategyRule, evaluate_strategy_rule


@dataclass(frozen=True)
class ParityCase:
    name: str
    bars: tuple[OHLCVBar, ...]
    entry: Decimal
    equity: Decimal = Decimal("10000")
    tick: Decimal = Decimal("0.001")
    tick_value: Decimal = Decimal("0.1")
    volume_min: Decimal = Decimal("0.01")
    volume_max: Decimal = Decimal("200")
    step: Decimal = Decimal("0.01")
    risk_cap: Decimal = Decimal("20")
    volume_cap: Decimal = Decimal("0.01")
    threshold: float = 10
    previous: float = 5
    active_entry: bool = False
    side: str = "BUY"


def validate_case(case: ParityCase) -> None:
    from .historical_dataset import utc
    values=(case.entry,case.equity,case.tick,case.tick_value,case.volume_min,
            case.volume_max,case.step,case.risk_cap,case.volume_cap)
    if (not case.name or case.side not in {"BUY","SELL"} or
            any(not Decimal(str(v)).is_finite() or v<=0 for v in values) or
            case.volume_max<case.volume_min or not 1<=len(case.bars)<=100 or
            not Decimal(str(case.threshold)).is_finite() or
            not Decimal(str(case.previous)).is_finite()):
        raise ValueError("PARITY_INPUT_INVALID")
    times=[utc(b.timestamp) for b in case.bars]
    if times!=sorted(set(times)):
        raise ValueError("PARITY_BAR_ORDER_INVALID")
    for bar in case.bars:
        if (any(not Decimal(str(v)).is_finite() or v<=0
                for v in (bar.open,bar.high,bar.low,bar.close)) or
                bar.high<max(bar.open,bar.close) or bar.low>min(bar.open,bar.close)):
            raise ValueError("PARITY_BAR_INVALID")


def reference(case: ParityCase) -> list:
    validate_case(case)
    # Pin the same default Decimal context as the production calculation.
    with localcontext() as context:
        context.prec=28
        context.rounding=ROUND_HALF_EVEN
        return _reference(case)


def _reference(case: ParityCase) -> list:
    policy = TradeDraftPolicy()
    calculated_rsi = rsi([b.close for b in case.bars],14)
    calculated_atr = atr(list(case.bars),14)
    stop = target = volume = actual_risk = Decimal("-1")
    valid = False
    if calculated_atr is not None and calculated_atr > 0:
        direction=Decimal(1 if case.side=="BUY" else -1)
        stop = _round_tick(case.entry-direction*Decimal(str(calculated_atr))*policy.default_atr_multiplier,case.tick)
        distance = direction*(case.entry-stop)
        if stop>0 and 0<distance<=case.entry*policy.maximum_stop_fraction:
            target = _round_tick(case.entry+direction*distance*policy.default_reward_risk_ratio,case.tick)
            per_lot=distance/case.tick*case.tick_value
            budget=min(case.equity*policy.default_demo_risk_fraction,case.risk_cap)
            volume=_floor_volume_to_cap(budget/per_lot,case.step,min(case.volume_cap,case.volume_max))
            if volume<case.volume_min or target<=0:
                volume=Decimal("-1")
            else:
                actual_risk=per_lot*volume
                valid=actual_risk<=case.risk_cap
    current=calculated_rsi if calculated_rsi is not None else -1
    values={"rsi":{"previous":case.previous,"current":current},"threshold":{"previous":case.threshold,"current":case.threshold}}
    level=evaluate_strategy_rule(StrategyRule("GREATER_THAN","rsi",constants=(case.threshold,)),values)["triggered"]
    edge=evaluate_strategy_rule(StrategyRule("CROSSES_ABOVE","rsi","threshold"),values)["triggered"]
    from .historical_dataset import utc
    return [case.name,int(utc(case.bars[-1].timestamp).timestamp()),current,
            calculated_atr if calculated_atr is not None else -1,
            float(stop),float(target),float(volume),float(actual_risk),
            int(level),int(edge),int(valid and level and not case.active_entry)]


def fixture_csv(cases: Sequence[ParityCase]) -> str:
    from .historical_dataset import utc
    policy=TradeDraftPolicy()
    output=io.StringIO(newline="")
    writer=csv.writer(output,lineterminator="\n")
    for case in cases:
        if not case.bars or len(case.bars)>100:
            raise ValueError("PARITY_BAR_COUNT_INVALID")
        validate_case(case)
        expected=reference(case)
        row=[case.name,len(case.bars)]
        for bar in case.bars:
            row.extend([int(utc(bar.timestamp).timestamp()),bar.close,bar.high,bar.low])
        row.extend([case.entry,case.equity,case.tick,case.tick_value,case.volume_min,
                    case.volume_max,case.step,policy.default_demo_risk_fraction,
                    case.risk_cap,case.volume_cap,policy.default_atr_multiplier,
                    policy.default_reward_risk_ratio,case.threshold,case.previous,expected[2],int(case.active_entry),case.side])
        writer.writerow(row)
    return output.getvalue()


def load_fixture_csv(text: str) -> tuple[ParityCase, ...]:
    """Load retained v1 or side-aware v2 fixtures, never their expected RSI column."""
    from datetime import datetime, timezone
    cases=[]
    policy=TradeDraftPolicy()
    for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        try:
            n=int(row[1]); offset=2+4*n
            if not 1<=n<=100 or len(row) not in {offset+16,offset+17}:
                raise ValueError("shape")
            bars=[]
            for i in range(n):
                timestamp,close,high,low=row[2+4*i:6+4*i]
                bars.append(OHLCVBar(datetime.fromtimestamp(int(timestamp),timezone.utc).isoformat(),
                                    float(close),float(high),float(low),float(close),0))
            fields=row[offset:]
            if ([Decimal(fields[i]) for i in (7,10,11)]!=
                    [policy.default_demo_risk_fraction,policy.default_atr_multiplier,policy.default_reward_risk_ratio]
                    or fields[15] not in {"0","1"}):
                raise ValueError("policy")
            case=ParityCase(row[0],tuple(bars),*[Decimal(v) for v in fields[:7]],
                            risk_cap=Decimal(fields[8]),volume_cap=Decimal(fields[9]),
                            threshold=float(fields[12]),previous=float(fields[13]),
                            active_entry=fields[15]=="1",side=fields[16] if len(fields)==17 else "BUY")
            validate_case(case)
        except (ValueError,IndexError,InvalidOperation,OverflowError,OSError) as exc:
            raise ValueError("PARITY_FIXTURE_INVALID") from exc
        cases.append(case)
    if not cases or len({c.name for c in cases})!=len(cases):
        raise ValueError("PARITY_CASE_IDENTITIES_INVALID")
    return tuple(cases)


def compare_results(cases: Sequence[ParityCase], text: str) -> dict:
    if not cases or len({c.name for c in cases})!=len(cases):
        raise ValueError("PARITY_CASE_IDENTITIES_INVALID")
    expected={case.name:reference(case) for case in cases}
    actual=list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    failures=[]
    differences=[]
    if len(actual)!=len(expected) or len({r[0] for r in actual if r})!=len(expected):
        failures.append("CASE_COUNT_OR_DUPLICATE_MISMATCH")
    for row in actual:
        if not row or row[0] not in expected or len(row)!=11:
            failures.append("CASE_SCHEMA_MISMATCH")
            continue
        reference_row=expected[row[0]]
        for index,(left,right) in enumerate(zip(row[1:],reference_row[1:]),start=1):
            # Prices, volume and decisions must agree; indicator floats alone allow roundoff.
            tolerance=Decimal("0.000000001") if index in {2,3,7} else Decimal("0.000000000001")
            try:
                observed=Decimal(left)
                if len(left)>128 or (observed.is_finite() and abs(observed.adjusted())>64):
                    raise InvalidOperation
                with localcontext() as context:
                    context.prec=80
                    mismatch=not observed.is_finite() or abs(observed-Decimal(str(right)))>tolerance
            except InvalidOperation:
                mismatch=True
            if mismatch:
                failures.append(f"{row[0]}:COLUMN_{index}")
                differences.append({"case":row[0],"column":index,"expected":str(right),"observed":left})
    return {"status":"PASS" if not failures else "FAIL","cases":len(cases),"failures":failures,
            "differences":differences,"passing_ids":[c.name for c in cases
            if not any(f.startswith(c.name+":") for f in failures) and
            sum(bool(r) and r[0]==c.name and len(r)==11 for r in actual)==1]}


@dataclass(frozen=True)
class NumericCase:
    name: str
    operation: str
    left: str
    right: str = "1"


def numeric_cases() -> tuple[NumericCase, ...]:
    cases=[]
    for tick in ("0.001","0.25"):
        tie=Decimal(tick)*Decimal("100.5")
        for sign in (1,-1):
            value=float(sign*tie)
            for label,number in (("below",math.nextafter(value,-math.inf)),
                                 ("tie",sign*tie),("above",math.nextafter(value,math.inf))):
                cases.append(NumericCase(f"tick_{tick}_{sign}_{label}","TICK",str(number),tick))
    for step in ("0.01","0.03"):
        for label,value in (("below",str(math.nextafter(float(step),0))),
                            ("equal",step),("above",str(math.nextafter(float(step),math.inf)))):
            cases.append(NumericCase(f"step_{step}_{label}","FLOOR",value,step))
    cases.extend([
        NumericCase("historical_stop","ADD","4032.546","-4.76250000000002910"),
        NumericCase("historical_tick","TICK","4027.78349999999997090","0.001"),
        NumericCase("half_even_even","ADD","1.000000000000000000000000002","0.0000000000000000000000000005"),
        NumericCase("half_even_odd","ADD","1.000000000000000000000000003","0.0000000000000000000000000005"),
        NumericCase("recurring_division","DIV","1","3"),
        NumericCase("risk_product","MUL","476.3","0.01"),
        NumericCase("shortest_float","DOUBLE","3.1750000000000194"),
        NumericCase("shortest_tenth","DOUBLE","0.1"),
        NumericCase("zero_divisor","DIV","1","0"),
        NumericCase("nan","ADD","NaN"),NumericCase("infinity","TICK","Infinity"),
        NumericCase("malformed","ADD","not-a-number"),
    ])
    return tuple(cases)


def numeric_reference(case: NumericCase) -> str:
    try:
        a,b=Decimal(case.left),Decimal(case.right)
        if not a.is_finite() or not b.is_finite():
            return "INVALID"
        with localcontext() as context:
            context.prec=28; context.rounding=ROUND_HALF_EVEN
            if case.operation=="TICK" and b>0:
                answer=_round_tick(a,b)
            elif case.operation=="FLOOR" and a>=0 and b>0:
                answer=(a/b).quantize(Decimal(1),rounding=ROUND_DOWN)*b
            elif case.operation=="MUL": answer=a*b
            elif case.operation=="DIV" and b!=0: answer=a/b
            elif case.operation=="ADD": answer=a+b
            elif case.operation=="DOUBLE": answer=Decimal(str(float(a)))
            else: return "INVALID"
            return str(answer)
    except InvalidOperation:
        return "INVALID"


def compare_numeric_results(cases: Sequence[NumericCase], text: str) -> dict:
    expected={c.name:numeric_reference(c) for c in cases}
    if not cases or len(expected)!=len(cases):
        raise ValueError("PARITY_CASE_IDENTITIES_INVALID")
    rows=list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    failures=[]; differences=[]
    if len(rows)!=len(expected) or len({r[0] for r in rows if r})!=len(expected):
        failures.append("CASE_COUNT_OR_DUPLICATE_MISMATCH")
    for row in rows:
        if len(row)!=2 or row[0] not in expected:
            failures.append("CASE_SCHEMA_MISMATCH"); continue
        wanted=expected[row[0]]
        try:
            valid=row[1]==wanted if wanted=="INVALID" else Decimal(row[1])==Decimal(wanted)
        except InvalidOperation: valid=False
        if not valid:
            failures.append(row[0]); differences.append({"case":row[0],"expected":wanted,"observed":row[1]})
    return {"status":"FAIL" if failures else "PASS","cases":len(cases),
            "failures":failures,"differences":differences}


def prepare_numeric_package(fixture: Path, expected_sha256: str, directory: Path) -> Path:
    """Prepare fixtures and pins only; never invoke a compiler, terminal or broker."""
    from .historical_dataset import canonical_bytes, checksum
    from .input_package import _publish
    original=fixture.read_bytes()
    if checksum(original)!=expected_sha256:
        raise ValueError("PARITY_FIXTURE_CHECKSUM_MISMATCH")
    original_cases=load_fixture_csv(original.decode("utf-8-sig"))
    if len(original_cases)!=58:
        raise ValueError("PARITY_RETAINED_VECTOR_COUNT_MISMATCH")
    from dataclasses import replace
    cases=(*original_cases,*(replace(c,name="sell_"+c.name,side="SELL") for c in original_cases))
    scalar=numeric_cases()
    out=io.StringIO(newline="")
    csv.writer(out,lineterminator="\n").writerows((c.name,c.operation,c.left,c.right) for c in scalar)
    files={"s11b_parity.csv":fixture_csv(cases),"s11b_numeric.csv":out.getvalue()}
    owners=[Path(__file__),Path(_round_tick.__code__.co_filename),
            Path(rsi.__code__.co_filename),Path(evaluate_strategy_rule.__code__.co_filename),
            Path("tools/mt5_bridge/research/StrategyParity.mq5"),
            Path("tools/mt5_bridge/research/ParityDecimal.mqh")]
    root=Path.cwd().resolve()
    payload={"schema":"research-numeric-parity-preparation/v2","classification":"MATH_ONLY_NOT_BACKTEST",
             "native_status":"NOT_VERIFIED","execution_allowed":False,"simulated_orders_allowed":False,
             "runtime":{"python":platform.python_version(),"implementation":platform.python_implementation()},
             "retained_fixture_sha256":expected_sha256,"retained_count":58,
             "proposal_count":len(cases),"numeric_count":len(scalar),
             "files":files,"file_sha256":{name:checksum(text.encode()) for name,text in files.items()},
             "source_sha256":{p.resolve().relative_to(root).as_posix():checksum(p.read_bytes()) for p in owners},
             "expected_rows":[reference(c) for c in cases],
             "numeric_expected":{c.name:numeric_reference(c) for c in scalar},
             "compiled_binary_sha256":None,"native_output_sha256":None,"native_toolchain":None}
    return _publish(directory,canonical_bytes(payload),prefix="numeric_parity_preparation")
