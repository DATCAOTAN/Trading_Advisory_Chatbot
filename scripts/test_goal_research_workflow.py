"""Offline application acceptance; synthetic provider/data, never live research evidence."""
import copy
import json
import threading
from types import SimpleNamespace

import pytest
from pymongo.errors import AutoReconnect

from scripts.test_goal_only_research_brief import goal_payload
from src.orchestrator import RAGOrchestrator
from src.services import history_service
from src.services.decision_context import DecisionContextBuilder
from src.services.history_service import HistoryService
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import resolve_structured_semantics
from src.services.semantic.structured_semantics import StructuredSemanticResult


OUTPUT = {"hypothesis": "Compare completed M1 high-low ranges across hourly blocks; equal medians would refute a session difference.",
          "timeframes": ["M1"], "limitations": ["Unverified hypothesis; no research or performance result."]}
ABSENT = object()


def message(payload=None, previous=None):
    state = resolve_structured_semantics(StructuredSemanticResult.from_payload(payload or goal_payload()), previous)
    plan = QueryPlanAssembler().assemble_resolved("", state)
    return {"role": "assistant", "intent": "RESEARCH_BRIEF", "content": "Canonical brief",
            "resolved_semantic_state": state.as_dict(), "research_brief": plan.constraints["research_brief"]}


class Collection:
    """Only the Mongo operations used here, with locked equality/exists CAS semantics."""
    def __init__(self):
        self.docs = {name: {"_id": name, "messages": [message()]} for name in ("A", "B")}
        self.lock = threading.RLock()
        self.writes = []

    def find_one(self, query, projection):
        with self.lock:
            return copy.deepcopy(self.docs.get(query["_id"]))

    def update_one(self, query, update, *, upsert):
        assert upsert is False
        with self.lock:
            doc = self.docs.get(query["_id"])
            if doc is None:
                return SimpleNamespace(modified_count=0)
            for path, condition in query.items():
                if path == "_id":
                    continue
                value = doc
                try:
                    for part in path.split("."):
                        value = value[int(part)] if isinstance(value, list) else value[part]
                except (KeyError, IndexError):
                    value = ABSENT
                if ("$eq" in condition and value != condition["$eq"]) or (
                    "$exists" in condition and (value is not ABSENT) != condition["$exists"]
                ):
                    return SimpleNamespace(modified_count=0)
            for path, value in update["$set"].items():
                target = doc
                parts = path.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = copy.deepcopy(value)
            self.writes.append(copy.deepcopy(query))
            return SimpleNamespace(modified_count=1)


class Provider:
    def __init__(self):
        self.calls = []
        self.output = json.dumps(OUTPUT)
        self.callback = lambda: None

    def complete(self, prompt, **options):
        self.calls.append((prompt, options))
        self.callback()
        return self.output


@pytest.fixture
def app(monkeypatch):
    collection = Collection()
    history = object.__new__(HistoryService)
    history.sessions_col = collection
    monkeypatch.setattr(history_service, "HistoryService", lambda: history)
    subject = RAGOrchestrator.__new__(RAGOrchestrator)
    subject.decision_context_builder = DecisionContextBuilder()
    subject.research_hypothesis_provider = Provider()
    monkeypatch.delenv("RESEARCH_READINESS_BINDING", raising=False)
    return subject, collection, history


def generate(subject, session="A"):
    return subject.generate_goal_research(session, subject.inspect_goal_research(session)["key"])


def test_goal_to_persistent_r1_revision_and_reload(app):
    subject, db, _ = app
    view = generate(subject)
    proposal = view["proposal"]
    assert proposal.origin == "AI_RESEARCHED" and proposal.head.author == "AI_SUGGESTED"
    assert proposal.head.content.hypothesis == OUTPUT["hypothesis"]
    assert proposal.review_status(proposal.head.revision_id) == "EVIDENCE_PENDING"
    assert not proposal.execution_allowed and not proposal.reviews
    assert proposal.brief.goal.horizon == "weekly"
    assert proposal.brief.goal.max_risk_per_trade_pct is None
    assert "canonical brief" in subject.research_hypothesis_provider.calls[0][0].lower()
    assert generate(subject)["proposal"] == proposal
    assert len(subject.research_hypothesis_provider.calls) == 1
    updated = subject.revise_goal_research("A", view["key"], proposal.head.revision_id, "Test a different hourly comparison.")
    assert updated["proposal"].revisions[0] == proposal.head
    assert updated["proposal"].head.author == "USER_AUTHORED"
    assert len(subject.inspect_goal_research("A")["proposal"].revisions) == 2
    assert db.docs["A"]["messages"][-1]["content"] == "Canonical brief"
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        subject.revise_goal_research("A", view["key"], proposal.head.revision_id, "Stale edit")


@pytest.mark.parametrize("objective", ["Nghien cuu bien do vang theo gio", "Study hourly gold ranges"])
def test_canonical_language_constraints_preserved(app, objective):
    subject, db, _ = app
    db.docs["A"]["messages"] = [message(goal_payload(research_goal={
        "objective": objective, "horizon": "weekly", "max_risk_per_trade_pct": 1, "max_drawdown_pct": 5,
    }))]
    proposal = generate(subject)["proposal"]
    assert proposal.brief.goal.objective == objective
    assert proposal.brief.goal.max_drawdown_pct == 5
    assert dict(proposal.brief.field_sources)["research_goal.max_risk_per_trade_pct"] == "USER_EXPLICIT"
    assert objective in subject.research_hypothesis_provider.calls[0][0]


@pytest.mark.parametrize("output", ["not JSON", "x" * 9000, json.dumps(OUTPUT | {"execution_allowed": True}),
    json.dumps(OUTPUT | {"evidence": []}), json.dumps(OUTPUT | {"hypothesis": ""}),
    json.dumps(OUTPUT | {"timeframes": ["M2"]}), json.dumps(OUTPUT | {"timeframes": ["H1 (one hour)"]}),
    json.dumps(OUTPUT | {"hypothesis": "x" * 501})])
def test_untrusted_provider_payload_cannot_create_proposal(app, output):
    subject, db, _ = app
    subject.research_hypothesis_provider.output = output
    result = generate(subject)
    assert result["status"] == "FAILED" and result["proposal"] is None
    assert result["reason"].startswith("RESEARCH_HYPOTHESIS_")
    generate(subject)
    assert len(subject.research_hypothesis_provider.calls) == 1
    assert "proposal" not in next(iter(db.docs["A"]["research_proposals"].values()))


def test_provider_unavailable_is_redacted_and_not_retried(app):
    subject, _, _ = app
    def fail():
        raise RuntimeError("private provider diagnostic")
    subject.research_hypothesis_provider.callback = fail
    result = generate(subject)
    assert result["reason"] == "RESEARCH_PROVIDER_UNAVAILABLE"
    assert "private provider diagnostic" not in repr(result)
    assert generate(subject)["status"] == "FAILED"
    assert len(subject.research_hypothesis_provider.calls) == 1


@pytest.mark.parametrize("state", ["FAILED", "GENERATING", "legacy"])
def test_explicit_recovery_reuses_brief_and_fences_old_attempt(app, state):
    subject, db, history = app
    view = subject.inspect_goal_research("A")
    old = {"status": "GENERATING" if state == "legacy" else state}
    if state != "legacy":
        old.update(generation_id="old", owner=history.research_generation_owner(), attempt=1)
    history.save_research_state("A", count=1, tail=db.docs["A"]["messages"][-1],
                               key=view["key"], expected=None, record=old)
    assert generate(subject)["status"] == old["status"]
    assert not subject.research_hypothesis_provider.calls
    token = subject.inspect_goal_research("A")["generation_token"]
    result = subject.generate_goal_research("A", view["key"], retry=True, expected_generation=token)
    assert result["status"] == "SAVED" and result["key"] == view["key"]
    assert len(subject.research_hypothesis_provider.calls) == 1
    assert len(db.docs["A"]["research_proposals"]) == 1
    assert not history.save_research_state("A", count=1, tail=db.docs["A"]["messages"][-1],
                                          key=view["key"], expected=old, record={"status": "FAILED"})


def test_recovery_cannot_overlap_an_active_provider_even_in_same_thread(app):
    subject, _, _ = app
    def try_recovery():
        view = subject.inspect_goal_research("A")
        with pytest.raises(ValueError, match="GENERATION_ACTIVE"):
            subject.generate_goal_research("A", view["key"], retry=True,
                                           expected_generation=view["generation_token"])
    subject.research_hypothesis_provider.callback = try_recovery
    assert generate(subject)["status"] == "SAVED"
    assert len(subject.research_hypothesis_provider.calls) == 1


def test_retry_token_and_owner_must_match(app):
    subject, db, history = app
    view = subject.inspect_goal_research("A")
    history.save_research_state("A", count=1, tail=db.docs["A"]["messages"][-1],
        key=view["key"], expected=None, record={"status": "GENERATING", "owner": "another-host"})
    with pytest.raises(ValueError, match="GENERATION_STALE"):
        subject.generate_goal_research("A", view["key"], retry=True, expected_generation="stale")
    token = subject.inspect_goal_research("A")["generation_token"]
    with pytest.raises(ValueError, match="REQUIRES_OWNER_INSTANCE"):
        subject.generate_goal_research("A", view["key"], retry=True, expected_generation=token)
    assert not subject.research_hypothesis_provider.calls


def test_os_generation_lock_releases_after_process_exit(app):
    import subprocess
    import sys
    import uuid
    subject, _, history = app
    key = uuid.uuid4().hex * 2
    code = (
        "import os,sys; from src.services.history_service import HistoryService; "
        "h=object.__new__(HistoryService); "
        f"lock=h.research_generation_lock('{key}'); lock.__enter__(); "
        "print('LOCKED',flush=True); sys.stdin.readline(); os._exit(0)"
    )
    child = subprocess.Popen([sys.executable, "-u", "-c", code], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "LOCKED"
        with pytest.raises(ValueError, match="GENERATION_ACTIVE"):
            with history.research_generation_lock(key):
                pytest.fail("Concurrent process acquired lock")
        child.communicate("EXIT\n", timeout=10)
        assert child.returncode == 0
        with history.research_generation_lock(key):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def test_generation_claim_prevents_concurrent_provider_calls(app):
    subject, _, _ = app
    nested = []
    subject.research_hypothesis_provider.callback = lambda: nested.append(generate(subject)["status"])
    assert generate(subject)["proposal"] is not None
    assert nested == ["GENERATING"] and len(subject.research_hypothesis_provider.calls) == 1


def test_simultaneous_requests_have_one_durable_generation_claim(app):
    from concurrent.futures import ThreadPoolExecutor
    subject, _, _ = app
    started, finish = threading.Event(), threading.Event()
    def pause():
        started.set()
        assert finish.wait(5)
    subject.research_hypothesis_provider.callback = pause
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(generate, subject)
        assert started.wait(5)
        try:
            assert pool.submit(generate, subject).result(timeout=5)["status"] == "GENERATING"
        finally:
            finish.set()
        assert first.result(timeout=5)["status"] == "SAVED"
    assert len(subject.research_hypothesis_provider.calls) == 1


def test_stale_display_and_repeated_legacy_goal_do_not_reuse_request(app):
    subject, db, _ = app
    tail = copy.deepcopy(db.docs["A"]["messages"][-1])
    first = generate(subject)
    repeated = copy.deepcopy(tail)
    repeated.pop("research_brief")
    db.docs["A"]["messages"].append(repeated)
    with pytest.raises(ValueError, match="BRIEF_STALE"):
        subject.inspect_goal_research("A", expected_tail=tail)
    assert subject.inspect_goal_research("A")["key"] != first["key"]
    assert subject.inspect_goal_research("A")["proposal"] is None


@pytest.mark.parametrize("change", ["deleted", "followup"])
def test_generation_cannot_save_after_context_changes(app, change):
    subject, db, _ = app
    def changed():
        if change == "deleted":
            del db.docs["A"]
        else:
            db.docs["A"]["messages"].append({"role": "user", "content": "A new request"})
    subject.research_hypothesis_provider.callback = changed
    with pytest.raises(ValueError, match="RESEARCH_BRIEF_STALE"):
        generate(subject)


def test_conversation_scope_and_goal_override_do_not_reuse_proposals(app):
    subject, db, _ = app
    first = generate(subject)
    other = generate(subject, "B")
    assert first["key"] != other["key"] and first["proposal"].scope != other["proposal"].scope
    assert first["proposal"].proposal_id != other["proposal"].proposal_id
    previous = subject._goal_research_context("A")[3].semantic_context
    from src.services.semantic.resolved_semantics import ResolvedSemanticState
    new = message(goal_payload(research_goal={"max_risk_per_trade_pct": 0.5},
        context_references=["previous_research_goal"], explicit_fields=["research_goal.max_risk_per_trade_pct"]),
        ResolvedSemanticState.from_dict(previous))
    db.docs["A"]["messages"].append(new)
    with pytest.raises(ValueError, match="BRIEF_STALE"):
        subject.generate_goal_research("A", first["key"])
    next_proposal = generate(subject)["proposal"]
    assert next_proposal.brief.goal.max_risk_per_trade_pct == 0.5
    assert next_proposal.brief.goal.horizon == "weekly"
    assert len(db.docs["A"]["research_proposals"]) == 2


@pytest.mark.parametrize("payload", [goal_payload(research_goal={}),
    goal_payload(unresolved_fields=["research_goal.objective"]), goal_payload(symbols=[])])
def test_missing_or_ambiguous_goal_stops_before_provider(app, payload):
    subject, db, _ = app
    db.docs["A"]["messages"] = [message(payload)]
    with pytest.raises(ValueError, match="CLARIFICATION_REQUIRED"):
        generate(subject)
    assert not subject.research_hypothesis_provider.calls


def test_storage_failure_and_stale_save_are_not_silent(app, monkeypatch):
    subject, db, history = app
    monkeypatch.setattr(db, "find_one", lambda *args: (_ for _ in ()).throw(AutoReconnect()))
    with pytest.raises(RuntimeError, match="RESEARCH_STORAGE_UNAVAILABLE"):
        subject.inspect_goal_research("A")
    with pytest.raises(ValueError, match="KEY_INVALID"):
        history.save_research_state("A", count=1, tail={}, key="bad.key", expected=None, record={})


def test_evidence_not_approved_never_grants_review_or_authority(app):
    subject, _, _ = app
    view = generate(subject)
    result = subject.attach_goal_research_evidence("A", view["key"], view["proposal"].head.revision_id)
    assert result["outcome"] == "EVIDENCE_PENDING"
    proposal = subject.inspect_goal_research("A")["proposal"]
    assert proposal.reviews == () and proposal.head.evidence_status() == "ABSENT"
    assert not proposal.execution_allowed


def test_provider_receives_the_existing_schema_and_supported_timeframe_tokens(app):
    from src.services.trading.market.timeframes import SUPPORTED_TIMEFRAMES
    subject, _, _ = app
    assert generate(subject)["status"] == "SAVED"
    prompt = subject.research_hypothesis_provider.calls[0][0]
    assert '"maxLength":500' in prompt and '"maxLength":240' in prompt
    assert all('"' + token + '"' in prompt for token in SUPPORTED_TIMEFRAMES)


def test_approved_source_is_independently_verified_for_new_revision(app, tmp_path, monkeypatch):
    from src.config import Config
    from dataclasses import replace
    from scripts.test_research_evidence_verification import setup_source
    from scripts.test_research_readiness import provision
    from scripts.test_research_proposal import NOW, ACCEPT
    from src.services.trading.research.proposal import ResearchContent, ResearchProposal
    from src.services.trading.research.evidence_verification import HistoricalEvidenceVerifier, HISTORICAL_EVALUATION_VERSION

    subject, _, _ = app
    root = tmp_path / "research"
    source, reference = setup_source(root / "mt5")
    _, _, _, plan, scope, _, _ = subject._goal_research_context("A")
    source = replace(source, scope=scope)
    owner = HistoricalEvidenceVerifier(scope, (source,))
    validated = reference.model_copy(update={"status": "VALIDATED", "data_quality": "VERIFIED",
                                              "evaluation_version": HISTORICAL_EVALUATION_VERSION})
    existing = ResearchProposal.from_plan(plan, scope=scope, origin="USER_DEFINED",
        content=ResearchContent(hypothesis="Fixture historical scope", timeframes=("M1",), evidence=(validated,)),
        created_at=NOW, verify_evidence=owner)
    existing = existing.review(scope=scope, revision_id=existing.head.revision_id, decision=ACCEPT,
                               reviewed_at=NOW, verify_evidence=owner)
    pin, path = provision(root, existing, source)
    monkeypatch.setenv("RESEARCH_READINESS_BINDING", json.dumps(pin))
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    original = {p: p.read_bytes() for p in (path, source.folder / "manifest.json", source.folder / "data.jsonl")}
    view = generate(subject)
    proof = subject.attach_goal_research_evidence("A", view["key"], view["proposal"].head.revision_id)
    assert proof["outcome"] == "VERIFIED_FOR_DECLARED_SCOPE"
    assert proof["claim_support"] == "NOT_ASSESSED"
    proposal = subject.inspect_goal_research("A")["proposal"]
    assert proposal.review_status(proposal.head.revision_id) == "EVIDENCE_PENDING"
    assert proposal.reviews == () and not proposal.execution_allowed
    assert all(p.read_bytes() == payload for p, payload in original.items())
    (source.folder / "data.jsonl").write_bytes(b"tampered fixture")
    proof = subject.attach_goal_research_evidence("A", view["key"], proposal.head.revision_id)
    assert proof["outcome"] == "EVIDENCE_PENDING" and proof["reason"] == "DATASET_CHECKSUM_MISMATCH"


def test_foreign_proposal_or_mutated_brief_is_not_reloaded(app):
    subject, db, _ = app
    a, b = generate(subject), generate(subject, "B")
    db.docs["B"]["research_proposals"][b["key"]] = copy.deepcopy(db.docs["A"]["research_proposals"][a["key"]])
    with pytest.raises(ValueError):
        subject.inspect_goal_research("B")
    db.docs["A"]["messages"][-1]["research_brief"]["goal"]["horizon"] = "changed"
    with pytest.raises(ValueError, match="BRIEF_CHANGED"):
        subject.inspect_goal_research("A")


def test_storage_cas_rejects_stale_counts_records_and_deleted_conversation(app):
    subject, db, history = app
    key = subject.inspect_goal_research("A")["key"]
    tail = db.docs["A"]["messages"][-1]
    assert not history.save_research_state("A", count=2, tail=tail, key=key, expected=None, record={})
    assert history.save_research_state("A", count=1, tail=tail, key=key, expected=None, record={"status": "GENERATING"})
    assert not history.save_research_state("A", count=1, tail=tail, key=key, expected=None, record={})
    assert not history.save_research_state("A", count=1, tail=tail, key=key, expected={"status": "SAVED"}, record={})
    del db.docs["A"]
    assert not history.save_research_state("A", count=1, tail=tail, key=key, expected=None, record={})


@pytest.mark.parametrize("recover", [False, True])
def test_streamlit_generate_edit_reload_and_conversation_isolation(app, recover):
    from streamlit.testing.v1 import AppTest
    subject, db, history = app
    if recover:
        view = subject.inspect_goal_research("A")
        history.save_research_state("A", count=1, tail=db.docs["A"]["messages"][-1],
            key=view["key"], expected=None, record={"status": "GENERATING"})
    test = AppTest.from_string('''
import streamlit as st
from src.ui.tab_chatbot import _render_goal_research
if st.button("Switch conversation"):
    st.session_state.current_session_id = "B"
    st.session_state.messages = st.session_state.other_messages
_render_goal_research(st.session_state.subject)
''')
    test.session_state.subject = subject
    test.session_state.current_session_id = "A"
    test.session_state.messages = copy.deepcopy(db.docs["A"]["messages"])
    test.session_state.other_messages = copy.deepcopy(db.docs["B"]["messages"])
    test.run()
    if recover:
        assert next(b for b in test.button if b.label == "Retry / recover hypothesis generation").disabled
        assert not subject.research_hypothesis_provider.calls
        test.checkbox[0].set_value(True).run()
        next(b for b in test.button if b.label == "Retry / recover hypothesis generation").click().run()
    else:
        next(b for b in test.button if b.label == "Generate testable hypothesis").click().run()
    assert not test.exception
    assert len(subject.research_hypothesis_provider.calls) == 1
    assert test.text_area[0].value == OUTPUT["hypothesis"]
    test.text_area[0].set_value("Compare a revised hourly hypothesis.")
    next(b for b in test.button if b.label == "Save hypothesis revision").click().run()
    test.run()
    assert not test.exception and test.text_area[0].value == "Compare a revised hourly hypothesis."
    assert len(subject.inspect_goal_research("A")["proposal"].revisions) == 2
    next(b for b in test.button if b.label == "Switch conversation").click().run()
    assert not test.exception and not test.text_area
    assert any(b.label == "Generate testable hypothesis" for b in test.button)


def test_real_app_url_restores_selected_conversation_and_rejects_deleted_ids(app, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ui import tab_dashboard, tab_evaluation_dashboard, tab_settings
    subject, db, history = app
    monkeypatch.setattr(history, "get_all_sessions", lambda: [{"_id": name, "title": name} for name in db.docs])
    monkeypatch.setattr(history, "load_history", lambda session: copy.deepcopy(db.docs[session]["messages"]))
    for tab in (tab_dashboard, tab_evaluation_dashboard, tab_settings):
        monkeypatch.setattr(tab, "render", lambda *_: None)
    page = AppTest.from_file("src/app.py")
    page.query_params["conversation"] = "B"
    page.session_state.orchestrator = subject
    page.run()
    assert not page.exception and page.session_state.current_session_id == "B"
    next(b for b in page.button if b.label == "A").click().run()
    assert page.session_state.current_session_id == "A"
    assert page.query_params["conversation"] in ("A", ["A"])
    refreshed = AppTest.from_file("src/app.py")
    refreshed.query_params["conversation"] = "A"
    refreshed.session_state.orchestrator = subject
    refreshed.run()
    assert not refreshed.exception and refreshed.session_state.current_session_id == "A"
    deleted = AppTest.from_file("src/app.py")
    deleted.query_params["conversation"] = "deleted"
    deleted.session_state.orchestrator = subject
    deleted.run()
    assert not deleted.exception and deleted.session_state.current_session_id == "A"
