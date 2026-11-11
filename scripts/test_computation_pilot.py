import json
from dataclasses import replace
from datetime import timedelta

import pytest

from scripts.test_historical_research_dataset import START, bars
from scripts.test_research_evidence_verification import create, research, setup_source
from scripts.test_research_proposal import NOW
from src.services.trading.reasoning.strategy_evidence import INDICATOR_REGISTRY
from src.services.trading.research.computation_pilot import (
    ALGORITHM, INPUT_FIELDS, ISOLATION_GATE, MAX_SOURCE_BYTES, capture_source_reply,
    check_output_vectors, pilot_specification, prepare_pilot,
)
from src.services.trading.research.historical_dataset import checksum


def prepare(source, ref, spec=None):
    return prepare_pilot(
        spec or pilot_specification("XAUUSD", "M1"), source, create(research(ref)), ref, now=NOW,
    )


def test_verified_copy_and_inert_source_are_bound_without_launch(tmp_path):
    source, ref = setup_source(tmp_path)
    job = prepare(source, ref)
    assert job == prepare(source, ref)
    assert job.status == ISOLATION_GATE and ALGORITHM not in INDICATOR_REGISTRY
    assert job.coverage == "VERIFIED_FOR_DECLARED_SCOPE"
    assert job.manifest_checksum == source.manifest_checksum
    rows = json.loads(job.input_bytes)
    assert len(rows) == 60 and set(rows[0]) == set(INPUT_FIELDS)
    assert job.input_checksum == checksum(job.input_bytes)
    assert str(source.folder) not in job.codegen_prompt
    assert "4000.123" not in job.codegen_prompt and job.dataset_id not in job.codegen_prompt
    text = "raise RuntimeError('would fail if launched')"
    captured = capture_source_reply(job, json.dumps({"source": text}))
    assert captured.source_checksum == checksum(text.encode("utf-8"))
    assert captured.job_id == job.job_id and captured.input_checksum == job.input_checksum
    assert captured.specification_id == job.specification.specification_id
    assert captured.status == "GENERATED_UNVERIFIED"
    assert text not in repr(captured)


@pytest.mark.parametrize("reply", [
    "invalid", '{"source":""}', '{"source":true}', '{"source":"pass","tool_calls":[]}',
    '{"source":"pass","verified":true}', json.dumps({"source": "x" * (MAX_SOURCE_BYTES + 1)}),
])
def test_source_reply_has_strict_bounded_shape(tmp_path, reply):
    source, ref = setup_source(tmp_path)
    with pytest.raises(ValueError, match="G2_SOURCE_REPLY_INVALID"):
        capture_source_reply(prepare(source, ref), reply)


@pytest.mark.parametrize("window", [False, 0, 1, 31, 2.0, "5"])
def test_parameter_must_be_bounded_integer(window):
    with pytest.raises(ValueError, match="G2_WINDOW_INVALID"):
        pilot_specification("XAUUSD", "M1", window)


def test_r2_source_provenance_scope_coverage_and_warmup_fail_closed(tmp_path):
    source, ref = setup_source(tmp_path / "complete")
    with pytest.raises(ValueError, match="RESEARCH_SOURCE_PIN_MISMATCH"):
        prepare(replace(source, manifest_checksum="0" * 64), ref)
    with pytest.raises(ValueError, match="G2_DATA_REQUIREMENT_SCOPE_MISMATCH"):
        prepare(source, ref, pilot_specification("XAUUSD", "H1"))
    short = ref.model_copy(update={"window_end": START + timedelta(minutes=33)})
    with pytest.raises(ValueError, match="G2_LOOKBACK_OR_WARMUP_INSUFFICIENT"):
        prepare(source, short)
    limited, limited_ref = setup_source(tmp_path / "partial", rows=bars()[1:])
    with pytest.raises(ValueError, match="RESEARCH_COVERAGE_INSUFFICIENT"):
        prepare(limited, limited_ref)
    (source.folder / "data.jsonl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="DATASET_CHECKSUM_MISMATCH"):
        prepare(source, ref)


def vectors(rows, values):
    full = [{"time": row["time"], "value": value} for row, value in zip(rows, values)]
    return {"full": full, "replay": [dict(row) for row in full], "prefixes": tuple(
        [dict(row) for row in full[:i]] for i in range(1, len(full))
    )}


def test_oracle_warmup_zero_volume_flat_bars_and_nonconstant_vectors(tmp_path):
    rows = bars()
    # Close location is +1/3 for fixture bars. First windows have no usable volume.
    for row in rows[:5]:
        row["tick_volume"] = 0
    rows[5].update(high=4001, low=4001, open=4001, close=4001)
    source, ref = setup_source(tmp_path, rows=rows)
    job = prepare(source, ref)
    values = [None] * 5 + [0.0, 1/6, 2/9, 1/4, 4/15] + [1/3] * 50
    check_output_vectors(job, **vectors(rows, values))


@pytest.mark.parametrize("failure,code", [
    ("warmup", "G2_WARMUP_OR_MISSING_VALUE_INVALID"),
    ("nan", "G2_NUMERICAL_VERIFICATION_FAILED"),
    ("value", "G2_NUMERICAL_VERIFICATION_FAILED"),
    ("look_ahead", "G2_NUMERICAL_VERIFICATION_FAILED"),
    ("replay", "G2_REPLAY_OR_PREFIX_MISMATCH"),
    ("timestamp", "G2_OUTPUT_SHAPE_INVALID"),
    ("prefix_missing", "G2_PREFIX_EVIDENCE_MISSING"),
    ("input_changed", "G2_INPUT_CHECKSUM_MISMATCH"),
])
def test_claimed_output_never_promotes_and_must_match_oracle(tmp_path, failure, code):
    source, ref = setup_source(tmp_path)
    job = prepare(source, ref)
    claimed = vectors(bars(), [None] * 4 + [1/3] * 56)
    if failure == "warmup":
        claimed["full"][0]["value"] = 0
    elif failure in {"nan", "value"}:
        claimed["full"][5]["value"] = float("nan") if failure == "nan" else 0.4
    elif failure == "look_ahead":
        claimed["prefixes"][4][-1]["value"] = 0.4
    elif failure == "replay":
        claimed["replay"][5]["value"] += 1e-13
    elif failure == "timestamp":
        claimed["full"][5]["time"] += 60
    elif failure == "prefix_missing":
        claimed["prefixes"] = ()
    else:
        job = replace(job, input_bytes=b"[]")
    with pytest.raises(ValueError, match=code):
        check_output_vectors(job, **claimed)
    assert job.status == ISOLATION_GATE
