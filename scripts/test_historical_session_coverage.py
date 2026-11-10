"""Synthetic contract tests; no market-performance evidence."""
from dataclasses import replace
from datetime import timedelta

import pytest

from scripts.test_historical_research_dataset import REQUEST, START, bars, save
from src.services.trading.research.historical_dataset import assess_quality, load_dataset, merge_chunks, utc
from src.services.trading.research.session_coverage import SessionEvidence, reassess_coverage


def evidence(start, end, state="QUOTING", historical=True):
    return SessionEvidence(start.isoformat(), end.isoformat(), state, "isolated-fixture", historical)


@pytest.mark.parametrize("windows", (((0, 60),), ((0, 20), (40, 60)), ((0, 1), (59, 60))))
def test_standard_multiple_sessions_and_boundaries(windows):
    records = [r for i, r in enumerate(bars()) if any(a <= i < b for a, b in windows)]
    sources = [evidence(START + timedelta(minutes=i), START + timedelta(minutes=i+1),
                        "QUOTING" if any(a <= i < b for a,b in windows) else "MARKET_CLOSED") for i in range(60)]
    result = reassess_coverage(records, replace(REQUEST, warmup_records=1), sources)
    assert result["coverage"] == "VERIFIED_BAR_SLOTS"
    assert all(i["classification"] == "CONFIRMED_MARKET_CLOSED" for i in result["intervals"])


@pytest.mark.parametrize("start,end", (
    ("2026-11-01T23:00:00Z", "2026-11-02T00:00:00Z"),  # Sunday / overnight
    ("2026-11-01T01:30:00-04:00", "2026-11-01T01:30:00-05:00"),  # DST repeated hour
    ("2026-10-31T23:30:00Z", "2026-11-01T00:30:00Z"),  # weekend / holiday closure
))
def test_explicit_utc_sessions_not_weekday_assumptions(start,end):
    request = replace(REQUEST, start=start, end=end, warmup_records=1)
    records = bars(60, utc(start))
    assert reassess_coverage(records, request, [SessionEvidence(start,end,"QUOTING","fixture",True)])["coverage"] == "VERIFIED_BAR_SLOTS"
    assert reassess_coverage([], request, [SessionEvidence(start,end,"MARKET_CLOSED","fixture",True)])["intervals"][0]["classification"] == "CONFIRMED_MARKET_CLOSED"


@pytest.mark.parametrize("state,historical,classification", (
    ("QUOTING",True,"SUSPECTED_HISTORY_GAP"),
    ("TRADING",True,"SESSION_HISTORY_UNAVAILABLE"),
    ("MARKET_CLOSED",False,"SESSION_HISTORY_UNAVAILABLE"),
    ("MARKET_CLOSED",True,"CONFIRMED_MARKET_CLOSED"),
    ("NO_QUOTES",True,"CONFIRMED_NO_QUOTE_INTERVAL"),
))
def test_missing_slots_require_independent_historical_quote_evidence(state,historical,classification):
    sources = [evidence(START, START + timedelta(hours=1), state, historical)]
    result = reassess_coverage(bars()[:30], REQUEST, sources)
    assert result["intervals"][-1]["classification"] == classification
    if not historical or state in {"QUOTING","TRADING"}:
        assert result["coverage"] == "PARTIAL"


def test_unknown_and_conflicting_evidence_never_promotes_coverage():
    assert reassess_coverage(bars()[:30], REQUEST)["intervals"][0]["classification"] == "SESSION_HISTORY_UNAVAILABLE"
    sources = [evidence(START,START+timedelta(hours=1),state) for state in ("MARKET_CLOSED","QUOTING")]
    assert reassess_coverage(bars(), REQUEST, sources)["coverage"] == "PARTIAL"
    with pytest.raises(ValueError):
        SessionEvidence(REQUEST.start,REQUEST.end,"GUESSED","",True)


def test_subminute_closure_does_not_excuse_whole_missing_bar():
    result = reassess_coverage(bars()[1:],REQUEST,[evidence(START,START+timedelta(seconds=30),"MARKET_CLOSED")])
    assert result["intervals"][0]["classification"] == "SESSION_HISTORY_UNAVAILABLE"


def test_ticks_distinct_same_millisecond_overlap_and_duplicates(tmp_path):
    timestamp = int(START.timestamp()*1000)
    first = dict(time=timestamp//1000,time_msc=timestamp,bid=10.,ask=11.,last=0,flags=134)
    second = dict(first,bid=10.1)
    later = dict(second,time_msc=timestamp+1)
    records=[first,second,later]
    assert merge_chunks([records[:2],records],"ticks") == (records,2)
    with pytest.raises(ValueError,match="CONFLICTING_CHUNK_OVERLAP"):
        merge_chunks([records[:2],[second,later]],"ticks")
    with pytest.raises(ValueError,match="DUPLICATE_TIMESTAMP"):
        merge_chunks([[first,first]],"ticks")
    with pytest.raises(ValueError,match="NON_MONOTONIC"):
        merge_chunks([[later,first]],"ticks")
    request=replace(REQUEST,kind="ticks",warmup_records=1)
    assert assess_quality(records,request,tick_groups=True)["status"] == "PARTIAL"
    assert assess_quality([first,first],request,tick_groups=True)["status"] == "INVALID"
    folder,_=save(tmp_path,records,request)
    assert load_dataset(folder,require_verified=False)[1]==records
    assert reassess_coverage([],request)["coverage"] == "PARTIAL"


def test_idempotent_reassessment_preserves_raw_and_manifest(tmp_path):
    folder,manifest=save(tmp_path)
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    result=reassess_coverage(bars(),REQUEST)
    assert result==reassess_coverage(bars(),REQUEST)
    assert load_dataset(folder)[0]==manifest
    assert before=={p.name:p.read_bytes() for p in folder.iterdir()}
    broken=bars(); broken[0]["high"]=1
    assert reassess_coverage(broken,REQUEST)["internal_consistency"]=="INVALID"


def test_v1_manifest_still_loads_with_original_quality(tmp_path,monkeypatch):
    from src.services.trading.research import historical_dataset as dataset

    original=dataset.assess_quality
    with monkeypatch.context() as legacy:
        legacy.setattr(dataset,"EXPORTER_VERSION","mt5-research-export/v1")
        legacy.setattr(dataset,"assess_quality",lambda rows,request,**kwargs: original(rows,request))
        request=replace(REQUEST,kind="ticks",warmup_records=1)
        timestamp=int(START.timestamp()*1000)
        row=dict(time=timestamp//1000,time_msc=timestamp,bid=10.,ask=11.,last=0,flags=134)
        folder,manifest=save(tmp_path,[row],request)
    assert load_dataset(folder,require_verified=False)[0]==manifest
