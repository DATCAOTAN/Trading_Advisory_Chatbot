"""Development bridge tests; no provider, credential store, broker or real GitHub calls."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import socket
import ssl
from email.message import Message
import urllib.error
from types import SimpleNamespace
import uuid

import pytest

from tools import codex_issue_bridge as b


def task(operation="smoke", **fields):
    value = {"schema": "codex-dev-task/v1", "task_id": str(uuid.uuid4()), "state": "PENDING",
             "operation": operation, "instructions": "Return BRIDGE_SMOKE_OK without tools or changes.",
             "files": [], "write_path": None}
    value.update(fields)
    return value


def issue(value, number=1):
    return {"number": number, "state": "open", "locked": False, "user": {"id": 7, "login": b.OWNER},
            "labels": [{"name": b.LABEL}], "body": json.dumps(value)}


class FakeGitHub:
    def __init__(self, value):
        self.issue = issue(value); self.posts = []; self.notes = []; self.fail_post = False

    def owner(self): return 7

    def pages(self, path): return [deepcopy(self.issue)]

    def comments(self, number): return deepcopy(self.notes)

    def approve(self):
        value, pin = b.parse_task(self.issue, 7)
        self.notes.append({"user": {"id": 7, "login": b.OWNER}, "created_at": "t", "updated_at": "t",
                           "body": f"CODEX_BRIDGE_AUTHORIZE {value['task_id']} {pin}"})

    def request(self, method, path, payload=None):
        if method == "GET": return deepcopy(self.issue)
        self.posts.append(payload["body"])
        self.notes.append({"body": payload["body"], "user": {"id": 7, "login": b.OWNER}})
        if self.fail_post:
            raise b.Blocked("GITHUB_REQUEST_FAILED_NO_RETRY")
        return {"id": len(self.posts)}


class FakeWorker:
    def __init__(self, result=None):
        self.calls = 0; self.result = result; self.callback = None

    def run(self, value, context):
        self.calls += 1
        if self.callback: self.callback()
        if self.result: return deepcopy(self.result)
        return {"status": "PASS", "summary": "BRIDGE_SMOKE_OK", "edits": []}


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    state = tmp_path / "state"; state.mkdir()
    db = b.open_state(state)
    yield repo, state, db
    db.close()


@pytest.mark.parametrize("mutation", ["author", "label", "closed", "pr", "locked"])
def test_owner_and_label_authorization(mutation):
    candidate = issue(task())
    if mutation == "author": candidate["user"]["id"] = 99
    if mutation == "label": candidate["labels"] = []
    if mutation == "closed": candidate["state"] = "closed"
    if mutation == "pr": candidate["pull_request"] = {}
    if mutation == "locked": candidate["locked"] = True
    with pytest.raises(b.Blocked): b.parse_task(candidate, 7)


@pytest.mark.parametrize("changes", [{"state": "RUNNING"}, {"task_id": "bad"}, {"operation": "shell"},
    {"command": "git push"}, {"files": ["docs/a.md", "DOCS/a.md"]}, {"instructions": ""},
    {"write_path": "src/app.py"}])
def test_task_contract_is_not_an_arbitrary_command_channel(changes):
    with pytest.raises(b.Blocked): b.parse_task(issue(task(**changes)), 7)


@pytest.mark.parametrize("name", [".env", "data/executions.jsonl", "../outside", "docs/../.env", "C:/secret",
    "docs\\file.md", "docs//file.md", "docs/CON.md", "docs/file.md.", ".agents/rules/x", "docs/.env"])
def test_path_family_rejects_escape_and_protected_state(tmp_path, name):
    with pytest.raises(b.Blocked): b.plain_path(tmp_path, name)


@pytest.mark.parametrize("name", ["src/app.py", "scripts/run_autonomous_candidate_monitor.py", "tools/mt5_bridge/execution.py",
                                  "docs/operations/local_runbook.md", "docs/development/bridge_tasks/x.ps1"])
def test_write_allowlist_excludes_production_and_operations(tmp_path, name):
    with pytest.raises(b.Blocked): b.plain_path(tmp_path, name, write=True)


def test_labelled_issue_gets_pending_receipt_then_exact_owner_approval(setup):
    root, state, db = setup; value = task(); gh = FakeGitHub(value); worker = FakeWorker()
    bridge = b.Bridge(root, db, gh, worker)
    assert bridge.tick() == value["task_id"]
    assert worker.calls == 0 and '"state": "PENDING"' in gh.posts[0]
    assert "CODEX_BRIDGE_AUTHORIZE" in gh.posts[0]
    gh.approve(); bridge.tick(); bridge.tick()
    assert worker.calls == 1
    assert [json.loads(x.split("```json\n")[1].split("\n```")[0])["state"] for x in gh.posts] == ["PENDING", "RUNNING", "PASS"]
    assert db.execute("SELECT value FROM settings WHERE key='live_smoke_pass'").fetchone() == ("1",)
    assert not list(root.iterdir())


@pytest.mark.parametrize("problem", ["wrong_author", "edited", "wrong_hash"])
def test_approval_must_be_unedited_owner_and_exact_hash(setup, problem):
    root, _, db = setup; value = task(); gh = FakeGitHub(value); gh.approve()
    if problem == "wrong_author": gh.notes[0]["user"]["id"] = 9
    if problem == "edited": gh.notes[0]["updated_at"] = "later"
    if problem == "wrong_hash": gh.notes[0]["body"] += "changed"
    worker = FakeWorker(); b.Bridge(root, db, gh, worker).tick()
    assert worker.calls == 0


def test_task_edit_after_pending_is_terminal_not_new_execution(setup):
    root, _, db = setup; gh = FakeGitHub(task()); worker = FakeWorker(); bridge = b.Bridge(root, db, gh, worker)
    bridge.tick(); gh.issue["body"] = json.dumps(task()); gh.approve(); bridge.tick()
    assert worker.calls == 0
    assert db.execute("SELECT state FROM tasks").fetchone() == ("BLOCKED",)


def test_duplicate_id_on_another_issue_is_not_reexecuted(setup):
    root, _, db = setup; value = task(); gh = FakeGitHub(value); gh.approve(); worker = FakeWorker()
    bridge = b.Bridge(root, db, gh, worker); bridge.tick()
    gh.issue["number"] = 2; bridge.tick()
    assert worker.calls == 1


def test_post_timeout_reconciles_without_second_post_or_worker(setup):
    root, _, db = setup; gh = FakeGitHub(task()); gh.approve(); gh.fail_post = True
    worker = FakeWorker(); bridge = b.Bridge(root, db, gh, worker)
    with pytest.raises(b.Blocked): bridge.tick()
    assert worker.calls == 0 and len(gh.posts) == 1
    gh.fail_post = False; bridge.tick()
    assert worker.calls == 1 and len(gh.posts) == 3


def test_uncertain_comment_is_not_blindly_reposted(setup):
    root, _, db = setup; gh = FakeGitHub(task()); gh.fail_post = True
    bridge = b.Bridge(root, db, gh, FakeWorker())
    with pytest.raises(b.Blocked): bridge.tick()
    gh.notes.clear()
    with pytest.raises(b.Blocked, match="NO_REPOST"): bridge.tick()
    assert len(gh.posts) == 1


def test_crashed_running_task_is_blocked_and_never_restarted(setup):
    root, state, db = setup; value = task()
    db.execute("INSERT INTO tasks(task_id,issue,pin,state,operation) VALUES(?,1,'pin','RUNNING','smoke')", (value["task_id"],)); db.commit()
    other = b.open_state(state)
    try:
        assert other.execute("SELECT state FROM tasks").fetchone() == ("BLOCKED",)
        gh = FakeGitHub(value); gh.approve(); worker = FakeWorker()
        b.Bridge(root, other, gh, worker).tick(); assert worker.calls == 0
    finally: other.close()


@pytest.mark.parametrize("allow,smoke", [(False, True), (True, False), (False, False)])
def test_code_changes_require_two_local_gates(setup, allow, smoke):
    root, _, db = setup; value = task("edit", write_path="scripts/dev_tasks/demo.py")
    if smoke: db.execute("INSERT INTO settings VALUES('live_smoke_pass','1')"); db.commit()
    gh = FakeGitHub(value); gh.approve(); worker = FakeWorker()
    b.Bridge(root, db, gh, worker, allow_edits=allow).tick()
    assert worker.calls == 0 and not list(root.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows write handle/locking contract")
def test_single_development_edit_is_checked_backed_up_and_not_executed(setup, monkeypatch):
    root, state, db = setup; path = "scripts/dev_tasks/demo.py"
    value = task("edit", write_path=path); gh = FakeGitHub(value); gh.approve()
    db.execute("INSERT INTO settings VALUES('live_smoke_pass','1')"); db.commit()
    worker = FakeWorker({"status": "PASS", "summary": "Development file prepared; not executed", "edits": [
        {"path": path, "before_sha256": "absent", "content": "value = 1\n"}]})
    monkeypatch.setattr(b.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b""))
    bridge = b.Bridge(root, db, gh, worker, allow_edits=True); bridge.tick(); bridge.tick()
    assert worker.calls == 1 and (root/path).read_text() == "value = 1\n"
    assert (state/"backups"/(value["task_id"]+".before")).read_bytes() == b""
    assert '"unit_tests": "NOT_RUN"' in gh.posts[-1]


def test_context_change_or_authority_revocation_blocks_result(setup):
    root, _, db = setup; (root/"docs").mkdir(); f = root/"docs/a.md"; f.write_text("original")
    value = task("review", files=["docs/a.md"]); gh = FakeGitHub(value); gh.approve(); worker = FakeWorker()
    worker.callback = lambda: f.write_text("operator edit")
    b.Bridge(root, db, gh, worker).tick()
    assert f.read_text() == "operator edit"
    assert "WORKTREE_CHANGED_DURING_TASK" in gh.posts[-1]


@pytest.mark.parametrize("content", ["if :", "x = 1 \n", "password='not-a-real-secret'"])
def test_bad_or_sensitive_model_changes_are_never_written(tmp_path, content):
    value = task("edit", write_path="scripts/dev_tasks/demo.py"); context = b.snapshot(tmp_path, value)
    with pytest.raises(b.Blocked): b.validate_result(value, context,
        {"status": "PASS", "summary": "done", "edits": [{"path": value["write_path"], "before_sha256": "absent", "content": content}]})


def test_worker_has_no_broker_github_or_project_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_PASSWORD", "fixture-only"); monkeypatch.setenv("GH_TOKEN", "fixture-only")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only"); monkeypatch.setenv("HTTP_PROXY", "fixture-only")
    env = b.CodexWorker(Path("unused.exe"), tmp_path).environment()
    assert not {"MT5_PASSWORD", "GH_TOKEN", "OPENAI_API_KEY", "HTTP_PROXY"} & env.keys()


def test_codex_invocation_uses_stdin_no_shell_or_desktop_resume(tmp_path, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(command[command.index("--output-last-message")+1])
        output.write_text(json.dumps({"status": "PASS", "summary": "BRIDGE_SMOKE_OK", "edits": []}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(b.subprocess, "run", run)
    worker = b.CodexWorker(Path("codex.exe"), tmp_path/"home")
    assert worker.run(task(), {})["summary"] == "BRIDGE_SMOKE_OK"
    command, kwargs = calls[0]
    assert "--ignore-user-config" in command and "--ephemeral" in command and "--sandbox" in command
    assert 'windows.sandbox="unelevated"' in command and 'cli_auth_credentials_store="keyring"' in command
    assert "shell_tool" in command and "hooks" in command and "apps" in command
    assert "mcp_servers={}" in command and "resume" not in command and "--approve-for-me" not in command
    assert kwargs["shell"] is False and kwargs["timeout"] == 300 and command[-1] == "-"


def test_worker_timeout_does_not_retry(tmp_path, monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1); raise subprocess.TimeoutExpired("codex", 300)
    monkeypatch.setattr(b.subprocess, "run", fail)
    with pytest.raises(b.Blocked, match="TIMEOUT_NO_RETRY"):
        b.CodexWorker(Path("unused.exe"), tmp_path/"home").run(task(), {})
    assert len(calls) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows process lock")
def test_same_worktree_lock_rejects_concurrent_listener(tmp_path):
    with b.worktree_lock(tmp_path):
        with pytest.raises(b.Blocked, match="ALREADY_RUNNING"):
            with b.worktree_lock(tmp_path): pass


def test_github_transport_fixed_origin_and_no_mutation_endpoints():
    gh = b.GitHub("fixture-token")
    for method, path in [("POST", "/user"), ("DELETE", f"/repos/{b.REPOSITORY}/issues/1"),
                         ("GET", "https://example.invalid"), ("POST", f"/repos/{b.REPOSITORY}/git/refs")]:
        with pytest.raises(b.Blocked, match="ENDPOINT"): gh.request(method, path)


def test_github_request_and_response_contract_without_external_network():
    gh = b.GitHub("fixture-token"); recorded = []
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class Opener:
        def open(self, request, timeout):
            recorded.append(request)
            return Response(b'{"id":7}')
    gh.opener = Opener()
    assert gh.request("GET", "/user") == {"id": 7}
    assert recorded[0].full_url == "https://api.github.com/user"
    assert recorded[0].get_header("Authorization") == "Bearer fixture-token"
    with pytest.raises(b.Blocked, match="REDIRECT"):
        b.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.invalid")


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex")
def test_cross_process_mutex_rejects_second_process():
    import sys
    key = uuid.uuid4().hex
    code = ("from tools.codex_issue_bridge import named_worktree_lock; "
            f"lock=named_worktree_lock('{key}'); lock.__enter__()")
    with b.named_worktree_lock(key):
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=15)
        assert result.returncode != 0 and "BRIDGE_ALREADY_RUNNING_FOR_WORKTREE" in result.stderr


def test_label_revocation_after_worker_blocks_completion(setup):
    root, _, db = setup; gh = FakeGitHub(task()); gh.approve(); worker = FakeWorker()
    worker.callback = lambda: gh.issue.update(labels=[])
    b.Bridge(root, db, gh, worker).tick()
    assert worker.calls == 1 and "ISSUE_NOT_AUTHORIZED" in gh.posts[-1]
    assert db.execute("SELECT state FROM tasks").fetchone() == ("BLOCKED",)


def test_preexisting_dirty_target_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path/"docs/development/bridge_tasks/existing.md"
    path.parent.mkdir(parents=True); path.write_text("operator draft")
    value = task("edit", write_path="docs/development/bridge_tasks/existing.md")
    context = b.snapshot(tmp_path, value)
    monkeypatch.setattr(b.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b" M existing.md"))
    with pytest.raises(b.Blocked, match="PREEXISTING_LOCAL_CHANGES"):
        b.apply_one(tmp_path, value, context, {"path": value["write_path"],
            "before_sha256": context[value["write_path"]]["sha256"], "content": "replacement"}, tmp_path/"backups")
    assert path.read_text() == "operator draft"


def test_secret_redaction_does_not_echo_auth_material():
    assert "fixture_value" not in b.public_text("Bearer fixture_value")
    assert b.public_text("sha256: abc123") == "sha256: abc123"


def test_owner_identity_mismatch_is_rejected_before_poll():
    gh = b.GitHub("fixture-token")
    gh.request = lambda method, path, payload=None: {"id": 99, "login": "other"} if path == "/user" else {
        "full_name": b.REPOSITORY, "owner": {"id": 7, "type": "User"}}
    with pytest.raises(b.Blocked, match="OWNER_IDENTITY"):
        gh.owner()


def test_interrupted_uncertain_running_comment_finishes_as_blocked_without_retry(setup):
    root, state, db = setup; value = task(); gh = FakeGitHub(value)
    _, pin = b.parse_task(gh.issue, 7)
    body = f"<!-- codex-dev-bridge:{value['task_id']}:RUNNING -->\nold receipt"
    db.execute("INSERT INTO tasks(task_id,issue,pin,state,operation,result,comment,attempted,delivered) "
               "VALUES(?,1,?,'RUNNING','smoke',?,?,1,0)",
               (value["task_id"],pin,json.dumps({"write_intent":{"path":"scripts/dev_tasks/demo.py"}}),body)); db.commit()
    gh.notes.append({"body":body,"user":{"login":b.OWNER,"id":7}})
    other = b.open_state(state)
    try:
        worker=FakeWorker(); b.Bridge(root,other,gh,worker).tick()
        assert worker.calls==0 and len(gh.posts)==1
        assert "INTERRUPTED_TASK_NOT_RETRIED" in gh.posts[0]
        assert "scripts/dev_tasks/demo.py" in gh.posts[0]
        assert other.execute("SELECT state,delivered FROM tasks").fetchone()==("BLOCKED",1)
    finally: other.close()


def test_hardlinked_context_is_not_read(tmp_path):
    (tmp_path/"docs").mkdir(); original=tmp_path/"private.txt"; original.write_text("private fixture")
    os.link(original,tmp_path/"docs/alias.md")
    with pytest.raises(b.Blocked,match="LINKED"):
        b.plain_path(tmp_path,"docs/alias.md")


def test_lost_smoke_pass_response_unlocks_only_after_confirmed_delivery(setup):
    root,_,db=setup; gh=FakeGitHub(task()); gh.approve(); worker=FakeWorker()
    worker.callback=lambda: setattr(gh,"fail_post",True)
    bridge=b.Bridge(root,db,gh,worker)
    with pytest.raises(b.Blocked): bridge.tick()
    assert worker.calls==1 and db.execute("SELECT value FROM settings").fetchone() is None
    gh.fail_post=False; bridge.tick()
    assert worker.calls==1 and len(gh.posts)==3
    assert db.execute("SELECT value FROM settings WHERE key='live_smoke_pass'").fetchone()==("1",)


def test_blocked_smoke_does_not_unlock_edits(setup):
    root,_,db=setup; gh=FakeGitHub(task()); gh.approve()
    worker=FakeWorker({"status":"BLOCKED","summary":"BRIDGE_SMOKE_OK","edits":[]})
    b.Bridge(root,db,gh,worker).tick()
    assert db.execute("SELECT value FROM settings").fetchone() is None


@pytest.mark.parametrize("status,message,category,reason",[
    (401,"Bad credentials","AUTHENTICATION_FAILED","BAD_CREDENTIALS"),
    (403,"Resource not accessible by personal access token","PERMISSION_OR_POLICY_DENIED","TOKEN_PERMISSION_DENIED"),
    (404,"Not Found","RESOURCE_NOT_VISIBLE","NOT_FOUND_OR_NOT_AUTHORIZED"),
    (422,"Validation Failed","REQUEST_REJECTED","INVALID_REQUEST"),
    (429,"rate limit","RATE_LIMITED","RATE_LIMIT_EXCEEDED"),
    (503,"unavailable","SERVICE_FAILURE","GITHUB_SERVICE_ERROR"),
])
def test_http_errors_keep_safe_endpoint_status_and_reason(status,message,category,reason):
    gh=b.GitHub("fixture-token"); calls=[]
    class Opener:
        def open(self,request,timeout):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url,status,"untrusted reason",Message(),
                io.BytesIO(json.dumps({"message":message,"untrusted":"Bearer never-print-this"}).encode()))
    gh.opener=Opener()
    with pytest.raises(b.GitHubFailure) as caught:
        gh.request("GET",f"/repos/{b.REPOSITORY}")
    detail=caught.value.diagnostic
    assert detail["method"]=="GET" and detail["endpoint"]==f"/repos/{b.REPOSITORY}"
    assert (detail["http_status"],detail["category"],detail["reason"])==(status,category,reason)
    assert "never-print" not in json.dumps(detail) and "fixture-token" not in json.dumps(detail)
    assert len(calls)==1 and detail["retry_attempted"] is False


@pytest.mark.parametrize("cause,reason",[(socket.gaierror(-1,"private host omitted"),"DNS_ERROR"),
    (ssl.SSLError("private certificate text omitted"),"TLS_ERROR"),
    (TimeoutError("private timeout text omitted"),"TIMEOUT"),
    (ConnectionResetError("private peer omitted"),"CONNECTION_ERROR")])
def test_network_errors_are_not_reported_as_bad_credentials(cause,reason):
    gh=b.GitHub("fixture-token")
    class Opener:
        def open(self,*args,**kwargs): raise urllib.error.URLError(cause)
    gh.opener=Opener()
    with pytest.raises(b.GitHubFailure) as caught: gh.request("GET","/user")
    assert caught.value.diagnostic["http_status"] is None
    assert caught.value.diagnostic["reason"]==reason
    assert "private" not in json.dumps(caught.value.diagnostic)


def test_invalid_json_success_is_distinct_from_http_auth_failure():
    gh=b.GitHub("fixture-token")
    class Response(io.BytesIO):
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): self.close()
    class Opener:
        def open(self,*args,**kwargs): return Response(b"not json, private response omitted")
    gh.opener=Opener()
    with pytest.raises(b.GitHubFailure) as caught: gh.request("GET","/user")
    assert caught.value.diagnostic["category"]=="RESPONSE_PARSING_FAILED"
    assert caught.value.diagnostic["http_status"]==200
    assert "private" not in json.dumps(caught.value.diagnostic)


def test_request_format_errors_do_not_echo_header_values():
    gh=b.GitHub("fixture-token")
    class Opener:
        def open(self,*args,**kwargs): raise ValueError("Invalid header: Bearer fixture-token")
    gh.opener=Opener()
    with pytest.raises(b.GitHubFailure) as caught: gh.request("GET","/user")
    assert caught.value.diagnostic["category"]=="REQUEST_FORMAT_FAILED"
    assert "fixture-token" not in str(caught.value.diagnostic)


@pytest.mark.parametrize("token",["", "bad\r\nheader", "bad token", "nonascii\u200b", "paste\x16fixture"])
def test_malformed_credential_never_reaches_request_headers(token):
    with pytest.raises(b.Blocked,match="FORMAT_INVALID"): b.GitHub(token)


def test_403_rate_limit_is_not_misreported_as_missing_token_permission():
    headers=Message(); headers["X-RateLimit-Remaining"]="0"
    error=urllib.error.HTTPError("https://api.github.com/user",403,"ignored",headers,
                                io.BytesIO(b'{"message":"API rate limit exceeded"}'))
    assert b.http_failure("GET","/user",error).diagnostic["category"]=="RATE_LIMITED"


def test_read_only_check_does_not_execute_worker_or_publish_comments():
    gh=FakeGitHub(task()); result=b.check_github_access(gh)
    assert result["read_only_access"]=="PASS" and result["task_contract"]=="VALID"
    assert result["owner_hash_approval_present"] is False
    assert (result["worker_calls"],result["github_writes"],result["local_state_writes"])==(0,0,0)
    assert gh.posts==[]


def test_failed_credential_validation_does_not_overwrite_existing_vault(monkeypatch):
    import sys
    writes=[]
    monkeypatch.setattr(sys,"argv",["bridge","credential"])
    monkeypatch.setattr(b.getpass,"getpass",lambda *args:"fixture-token")
    monkeypatch.setattr(b.subprocess,"run",lambda *args,**kw:SimpleNamespace(returncode=0,stdout=f"https://github.com/{b.REPOSITORY}.git\n"))
    monkeypatch.setattr(b.ctypes,"windll",SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda:False)))
    monkeypatch.setattr(b,"WindowsVault",lambda:SimpleNamespace(write=writes.append))
    class Client:
        def __init__(self,token): pass
        def owner(self): raise b.GitHubFailure("GET",f"/repos/{b.REPOSITORY}","AUTHENTICATION_FAILED","BAD_CREDENTIALS",401)
    monkeypatch.setattr(b,"GitHub",Client)
    with pytest.raises(b.GitHubFailure): b.main()
    assert writes==[]


def test_check_command_short_circuits_before_worker_database_or_locks(monkeypatch,capsys,tmp_path):
    import sys
    gh=FakeGitHub(task())
    monkeypatch.setattr(sys,"argv",["bridge","check"])
    monkeypatch.setattr(b.subprocess,"run",lambda *args,**kw:SimpleNamespace(returncode=0,stdout=f"https://github.com/{b.REPOSITORY}.git\n"))
    monkeypatch.setattr(b.ctypes,"windll",SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda:False)))
    monkeypatch.setattr(b,"WindowsVault",lambda:SimpleNamespace(read=lambda:"fixture-token"))
    monkeypatch.setattr(b,"GitHub",lambda token:gh)
    monkeypatch.setattr(b,"locations",lambda root:tmp_path/"not-created")
    def forbidden(*args,**kwargs): raise AssertionError("Mutating path reached")
    monkeypatch.setattr(b,"CodexWorker",forbidden)
    monkeypatch.setattr(b,"open_state",forbidden)
    monkeypatch.setattr(b,"named_worktree_lock",forbidden)
    b.main()
    assert json.loads(capsys.readouterr().out)["worker_calls"]==0
    assert not (tmp_path/"not-created").exists() and gh.posts==[]


@pytest.mark.parametrize("failure",["timeout","service_error"])
def test_ambiguous_real_transport_write_is_not_retried(failure):
    gh=b.GitHub("fixture-token"); calls=[]
    class Opener:
        def open(self,request,timeout):
            calls.append(request.get_method())
            if failure=="timeout": raise TimeoutError("untrusted error omitted")
            raise urllib.error.HTTPError(request.full_url,503,"ignored",Message(),io.BytesIO(b"not json"))
    gh.opener=Opener()
    with pytest.raises(b.GitHubFailure) as caught:
        gh.request("POST",f"/repos/{b.REPOSITORY}/issues/1/comments",{"body":"fixture"})
    assert calls==["POST"]
    assert caught.value.diagnostic["write_outcome"]=="UNCONFIRMED_DO_NOT_REPOST"
    assert caught.value.diagnostic["retry_attempted"] is False


def test_control_v_is_rejected_before_credential_manager_write():
    vault=object.__new__(b.WindowsVault)
    with pytest.raises(b.Blocked,match="FORMAT_INVALID"):
        vault.write("\x16fixture")


@pytest.fixture
def credential_dialog(monkeypatch):
    import tkinter as tk
    from tkinter import ttk

    class Widget:
        def __init__(self, *args, **kwargs): self.options = kwargs
        def grid(self, *args, **kwargs): pass
        def configure(self, **kwargs): self.options.update(kwargs)
        def focus_set(self): pass

    for name in ("Frame", "Label", "Entry", "Button"):
        monkeypatch.setattr(ttk, name, Widget)
    root = SimpleNamespace(title=lambda *_: None, resizable=lambda *_: None,
        protocol=lambda *args: None, update_idletasks=lambda: None,
        destroy=lambda: None, clipboard_get=lambda: "fixture-token")
    interpreter = tk.Tcl()  # Real StringVar, no display, clipboard, network or vault access.
    real_var = tk.StringVar
    monkeypatch.setattr(tk, "StringVar", lambda master, **kwargs: real_var(interpreter, **kwargs))
    return b.CredentialDialog(root)


def test_gui_masks_input_and_pastes_without_keyboard(credential_dialog, monkeypatch):
    dialog = credential_dialog
    monkeypatch.setattr(b, "store_verified_credential", lambda *_: pytest.fail("Paste must not save"))
    dialog.paste()
    assert dialog.entry.options["show"] == "*"
    assert dialog.value.get() == "fixture-token"
    assert "fixture-token" not in dialog.feedback.get()


@pytest.mark.parametrize("value", ["", "\x16fixture", "token\n", " token", "token ", "\u200btoken", 123, "x" * 1201])
def test_gui_invalid_clipboard_keeps_existing_input(credential_dialog, value):
    dialog = credential_dialog
    dialog.value.set("previous")
    dialog.root.clipboard_get = lambda: value
    dialog.paste()
    assert dialog.value.get() == "previous"
    assert "Invalid clipboard" in dialog.feedback.get()


def test_gui_clipboard_unavailable_is_safe(credential_dialog):
    dialog = credential_dialog
    def unavailable(): raise dialog.tk.TclError("private clipboard content")
    dialog.root.clipboard_get = unavailable
    dialog.paste()
    assert dialog.value.get() == ""
    assert "private" not in dialog.feedback.get()


def test_gui_cancel_clears_input_without_storage(credential_dialog, monkeypatch):
    dialog = credential_dialog
    closed = []
    dialog.root.destroy = lambda: closed.append(True)
    monkeypatch.setattr(b, "store_verified_credential", lambda *_: pytest.fail("Cancel must not save"))
    dialog.value.set("fixture-token")
    dialog.cancel()
    assert closed == [True] and dialog.value.get() == ""


@pytest.mark.parametrize("token", ["", "\x16fixture", "token\r\n"])
def test_gui_invalid_manual_input_never_verifies_or_saves(credential_dialog, monkeypatch, token):
    monkeypatch.setattr(b, "store_verified_credential", lambda *_: pytest.fail("Invalid input"))
    credential_dialog.value.set(token)
    credential_dialog.save()
    assert "Invalid token format" in credential_dialog.feedback.get()


@pytest.mark.parametrize("failure", ["owner", "issues", "vault", None])
def test_gui_save_uses_shared_verification_before_storage(credential_dialog, monkeypatch, capsys, failure):
    calls = []
    def step(name):
        calls.append(name)
        if failure == name: raise RuntimeError("fixture-token PRIVATE")
    class Client:
        def __init__(self, token): assert token == "fixture-token"
        def owner(self): step("owner")
        def pages(self, path):
            assert path == f"/repos/{b.REPOSITORY}/issues?state=open&labels={b.LABEL}"
            step("issues")
    def write(token):
        assert token == "fixture-token"
        step("vault")
    monkeypatch.setattr(b, "GitHub", Client)
    monkeypatch.setattr(b, "WindowsVault", lambda: SimpleNamespace(write=write))
    dialog = credential_dialog
    dialog.value.set("fixture-token")
    dialog.save()
    assert calls == ["owner", "issues", "vault"][:{"owner": 1, "issues": 2, "vault": 3, None: 3}[failure]]
    if failure:
        assert "failed" in dialog.feedback.get()
        assert dialog.submit.options["state"] == "normal"
    else:
        assert "Saved in Windows Credential Manager" in dialog.feedback.get()
        assert dialog.value.get() == "" and dialog.entry.options["state"] == "disabled"
    assert "fixture-token" not in dialog.feedback.get()
    assert "PRIVATE" not in dialog.feedback.get()
    assert capsys.readouterr().out == ""


def test_gui_unexpected_callback_error_never_prints_secret(credential_dialog, capsys):
    credential_dialog.root.report_callback_exception(RuntimeError, RuntimeError("fixture-token"), None)
    assert "fixture-token" not in credential_dialog.feedback.get()
    assert capsys.readouterr().err == ""


def test_gui_cli_short_circuits_before_worker(monkeypatch):
    import sys
    calls = []
    monkeypatch.setattr(sys, "argv", ["bridge", "credential", "--gui"])
    monkeypatch.setattr(b.subprocess, "run", lambda *args, **kw: SimpleNamespace(returncode=0, stdout=f"https://github.com/{b.REPOSITORY}.git"))
    monkeypatch.setattr(b.ctypes, "windll", SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: False)))
    monkeypatch.setattr(b, "credential_gui", lambda: calls.append("gui"))
    monkeypatch.setattr(b.getpass, "getpass", lambda *_: pytest.fail("No console input"))
    monkeypatch.setattr(b, "CodexWorker", lambda *_: pytest.fail("No worker"))
    b.main()
    assert calls == ["gui"]


def test_gui_flag_is_not_available_to_listener(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "argv", ["bridge", "watch", "--gui"])
    with pytest.raises(SystemExit) as caught: b.main()
    assert caught.value.code == 2


def test_real_tk_dialog_has_masked_entry_and_dedicated_paste_button():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        dialog = b.CredentialDialog(root)
        assert dialog.entry.cget("show") == "*"
        frame = root.winfo_children()[0]
        buttons = {widget.cget("text"): widget for widget in frame.winfo_children()
                   if widget.winfo_class() == "TButton"}
        assert set(buttons) == {"Paste from Clipboard", "Verify and Save", "Cancel"}
        assert buttons["Paste from Clipboard"].cget("command")
        assert root.protocol("WM_DELETE_WINDOW")
        buttons["Cancel"].invoke()
    finally:
        try: root.destroy()
        except tk.TclError: pass


def test_github_uses_explicit_native_context_without_global_ssl_changes():
    import truststore
    original_factory = ssl._create_default_https_context
    original_context = ssl.SSLContext
    client = b.GitHub("fixture-token")
    handler = next(h for h in client.opener.handlers if isinstance(h, b.urllib.request.HTTPSHandler))
    assert isinstance(handler._context, truststore.SSLContext)
    assert handler._context.verify_mode == ssl.CERT_REQUIRED
    assert handler._context.check_hostname is True
    assert any(isinstance(h, b.NoRedirect) for h in client.opener.handlers)
    assert ssl._create_default_https_context is original_factory
    assert ssl.SSLContext is original_context


def test_windows_missing_native_tls_dependency_fails_closed(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "truststore", None)
    with pytest.raises(b.Blocked, match="WINDOWS_NATIVE_TLS_DEPENDENCY_REQUIRED"):
        b.GitHub("fixture-token")


def test_non_windows_uses_verified_standard_context(monkeypatch):
    monkeypatch.setattr(b, "os", SimpleNamespace(name="posix"))
    context = b.github_ssl_context()
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("certificate_failure", ["untrusted issuer", "hostname mismatch", "expired certificate"])
def test_certificate_validation_failures_remain_tls_errors_without_retry(method, certificate_failure):
    client = b.GitHub("fixture-token")
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.get_method())
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, certificate_failure + " fixture-token"))
    client.opener = Opener()
    path = f"/repos/{b.REPOSITORY}/issues/1/comments" if method == "POST" else "/user"
    with pytest.raises(b.GitHubFailure) as caught:
        client.request(method, path, {"body": "fixture"} if method == "POST" else None)
    detail = caught.value.diagnostic
    assert (detail["category"], detail["reason"], detail["http_status"]) == ("NETWORK_FAILED", "TLS_ERROR", None)
    assert calls == [method] and detail["retry_attempted"] is False
    assert detail["write_outcome"] == ("UNCONFIRMED_DO_NOT_REPOST" if method == "POST" else "NOT_APPLICABLE")
    assert "fixture-token" not in json.dumps(detail) and certificate_failure not in json.dumps(detail)


@pytest.mark.parametrize("restart", [False, True])
def test_absent_uncertain_receipt_never_reposts_or_changes_claim(setup, restart):
    root, state, db = setup
    value = task(); gh = FakeGitHub(value); gh.fail_post = True
    worker = FakeWorker(); bridge = b.Bridge(root, db, gh, worker)
    with pytest.raises(b.Blocked): bridge.tick()
    gh.notes.clear()  # A GET returning no comment is not proof of non-delivery.
    before = db.execute("SELECT * FROM tasks").fetchone()
    recovered = b.open_state(state) if restart else db
    try:
        bridge = b.Bridge(root, recovered, gh, worker)
        for _ in range(3):
            with pytest.raises(b.Blocked, match="COMMENT_DELIVERY_UNCERTAIN_NO_REPOST"):
                bridge.tick()
        assert recovered.execute("SELECT * FROM tasks").fetchone() == before
        assert len(gh.posts) == 1 and worker.calls == 0
        assert not recovered.execute("SELECT * FROM settings").fetchall()
    finally:
        if restart: recovered.close()


@pytest.mark.parametrize("restart", [False, True])
def test_delayed_exact_receipt_acknowledges_once_without_post_or_worker(setup, restart):
    root, state, db = setup
    value = task(); gh = FakeGitHub(value); gh.fail_post = True
    worker = FakeWorker(); bridge = b.Bridge(root, db, gh, worker)
    with pytest.raises(b.Blocked): bridge.tick()
    delayed = gh.notes.pop()
    with pytest.raises(b.Blocked, match="NO_REPOST"): bridge.tick()
    gh.notes.append(delayed)
    recovered = b.open_state(state) if restart else db
    try:
        bridge = b.Bridge(root, recovered, gh, worker)
        bridge.deliver(value["task_id"])
        bridge.deliver(value["task_id"])
        assert recovered.execute("SELECT state,attempted,delivered FROM tasks").fetchone() == ("PENDING", 1, 1)
        assert len(gh.posts) == 1 and worker.calls == 0
        assert not recovered.execute("SELECT * FROM settings").fetchall()
    finally:
        if restart: recovered.close()


@pytest.mark.parametrize("mismatch", ["body", "task_id", "state", "author"])
def test_reconciliation_requires_exact_receipt_identity_not_just_any_comment(setup, mismatch):
    root, _, db = setup
    value = task(); gh = FakeGitHub(value); gh.fail_post = True
    worker = FakeWorker(); bridge = b.Bridge(root, db, gh, worker)
    with pytest.raises(b.Blocked): bridge.tick()
    comment = gh.notes[0]
    if mismatch == "body": comment["body"] += "\nchanged"
    elif mismatch == "task_id": comment["body"] = comment["body"].replace(value["task_id"], str(uuid.uuid4()))
    elif mismatch == "state": comment["body"] = comment["body"].replace("PENDING", "RUNNING")
    else: comment["user"]["login"] = "another-owner"
    with pytest.raises(b.Blocked, match="NO_REPOST"): bridge.tick()
    assert len(gh.posts) == 1 and worker.calls == 0
    assert db.execute("SELECT delivered FROM tasks").fetchone() == (0,)


def test_post_403_is_permission_denial_but_restart_does_not_invent_rejection_evidence(setup):
    root, state, db = setup
    value = task(); gh = FakeGitHub(value); worker = FakeWorker()
    transport = b.GitHub("fixture-token")
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.get_method())
            raise urllib.error.HTTPError(request.full_url, 403, "omitted", Message(),
                io.BytesIO(b'{"message":"Resource not accessible by personal access token"}'))
    transport.opener = Opener()
    original_request = gh.request
    gh.request = lambda method, path, payload=None: transport.request(method, path, payload) if method == "POST" else original_request(method, path, payload)
    with pytest.raises(b.GitHubFailure) as caught: b.Bridge(root, db, gh, worker).tick()
    assert caught.value.diagnostic["http_status"] == 403
    assert caught.value.diagnostic["reason"] == "TOKEN_PERMISSION_DENIED"
    assert caught.value.diagnostic["task_id"] == value["task_id"]
    assert caught.value.diagnostic["stage"] == "COMMENT_POST"
    assert caught.value.diagnostic["issue"] == 1
    assert db.execute("SELECT state,attempted,delivered FROM tasks").fetchone() == ("PENDING", 1, 0)
    recovered = b.open_state(state)
    try:
        with pytest.raises(b.Blocked, match="NO_REPOST"):
            b.Bridge(root, recovered, gh, worker).tick()
        assert calls == ["POST"] and worker.calls == 0 and gh.notes == []
    finally: recovered.close()


class MultiIssueGitHub(FakeGitHub):
    def __init__(self, first, second):
        self.issues = {1: issue(first), 2: issue(second, 2)}
        self.notes = {1: [], 2: []}
        self.posts = []
        self.uncertain_issue = None

    def pages(self, path):
        return [deepcopy(i) for i in self.issues.values() if i["state"] == "open" and i["labels"]]

    def comments(self, number): return deepcopy(self.notes[number])

    def request(self, method, path, payload=None):
        number = int(path.split("/issues/")[1].split("/")[0])
        if method == "GET": return deepcopy(self.issues[number])
        self.posts.append((number, payload["body"]))
        if number == self.uncertain_issue:
            raise b.GitHubFailure("POST", path, "NETWORK_FAILED", "TIMEOUT")
        self.notes[number].append({"body": payload["body"], "user": {"id": 7, "login": b.OWNER}})
        return {"id": len(self.posts)}

    def approve(self, number):
        value, pin = b.parse_task(self.issues[number], 7)
        self.notes[number].append({"user": {"id": 7, "login": b.OWNER}, "created_at": "t", "updated_at": "t",
            "body": f"CODEX_BRIDGE_AUTHORIZE {value['task_id']} {pin}"})


@pytest.fixture
def two_issue_bridge(setup):
    root, state, db = setup
    first, second = task(), task()
    original = FakeGitHub(first); original.fail_post = True
    worker = FakeWorker()
    with pytest.raises(b.Blocked): b.Bridge(root, db, original, worker).tick()
    gh = MultiIssueGitHub(first, second)
    before = db.execute("SELECT * FROM tasks WHERE issue=1").fetchone()
    return root, state, db, first, second, gh, worker, before


@pytest.mark.parametrize("withdrawal", ["closed", "unlabelled", "both", "changed_binding"])
def test_withdrawn_uncertain_task_does_not_block_independent_pending_receipt(two_issue_bridge, withdrawal, capsys):
    root, _, db, first, second, gh, worker, before = two_issue_bridge
    if withdrawal in {"closed", "both"}: gh.issues[1]["state"] = "closed"
    if withdrawal in {"unlabelled", "both"}: gh.issues[1]["labels"] = []
    if withdrawal == "changed_binding": gh.issues[1]["body"] = json.dumps(task())
    bridge = b.Bridge(root, db, gh, worker)
    assert bridge.tick() == second["task_id"]
    bridge.tick()
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert db.execute("SELECT attempted,delivered FROM tasks WHERE issue=2").fetchone() == (1, 1)
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0
    diagnostic = json.loads(capsys.readouterr().out.splitlines()[0])
    assert diagnostic["task_id"] == first["task_id"] and diagnostic["issue"] == 1
    assert diagnostic["stage"] == "RECEIPT_TASK_ADMISSION" and diagnostic["journal_preserved"]
    assert diagnostic["operation_id"] == b.digest(before[6].encode())


def test_active_uncertain_task_is_skipped_but_its_approval_cannot_execute_it(two_issue_bridge, capsys):
    root, _, db, first, second, gh, worker, before = two_issue_bridge
    gh.approve(1)
    bridge = b.Bridge(root, db, gh, worker)
    assert bridge.tick() == second["task_id"]
    gh.approve(2)
    bridge.tick()
    with pytest.raises(b.CommentDeliveryUncertain): bridge.tick()
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert [number for number, _ in gh.posts] == [2, 2, 2] and worker.calls == 1
    diagnostic = json.loads(capsys.readouterr().out.splitlines()[0])
    assert diagnostic["error"] == "COMMENT_DELIVERY_UNCERTAIN_NO_REPOST"
    assert diagnostic["stage"] == "COMMENT_RECONCILIATION"
    assert diagnostic["task_id"] == first["task_id"] and diagnostic["operation"] == "smoke"
    assert not diagnostic["retry_attempted"]


def test_second_issue_uncertainty_is_preserved_independently(two_issue_bridge):
    root, _, db, first, second, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    gh.uncertain_issue = 2
    bridge = b.Bridge(root, db, gh, worker)
    with pytest.raises(b.GitHubFailure): bridge.tick()
    second_before = db.execute("SELECT * FROM tasks WHERE issue=2").fetchone()
    for _ in range(2):
        with pytest.raises(b.CommentDeliveryUncertain) as caught: bridge.tick()
        assert caught.value.diagnostic["task_id"] == second["task_id"]
        assert caught.value.diagnostic["issue"] == 2
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert db.execute("SELECT * FROM tasks WHERE issue=2").fetchone() == second_before
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0


def test_delayed_receipt_for_closed_task_is_preserved_until_reauthorized(two_issue_bridge):
    root, _, db, first, second, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    gh.notes[1].append({"body": before[6], "user": {"id": 7, "login": b.OWNER}})
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    gh.issues[1]["state"] = "open"
    bridge.tick(); bridge.tick()
    assert db.execute("SELECT attempted,delivered FROM tasks WHERE issue=1").fetchone() == (1, 1)
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0


def test_closed_unattempted_receipt_is_not_posted_during_crash_recovery(two_issue_bridge):
    root, state, db, first, second, gh, worker, _ = two_issue_bridge
    db.execute("UPDATE tasks SET attempted=0,state='RUNNING' WHERE issue=1"); db.commit()
    gh.issues[1]["state"] = "closed"
    recovered = b.open_state(state)
    try:
        before = recovered.execute("SELECT * FROM tasks WHERE issue=1").fetchone()
        assert before[3] == "BLOCKED" and before[7:] == (0, 0)
        b.Bridge(root, recovered, gh, worker).tick()
        assert recovered.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
        assert [number for number, _ in gh.posts] == [2] and worker.calls == 0
    finally: recovered.close()


def test_withdrawn_task_id_cannot_be_reused_on_new_issue(two_issue_bridge):
    root, _, db, first, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    gh.issues[2]["body"] = json.dumps(first)
    assert b.Bridge(root, db, gh, worker).tick() is None
    assert db.execute("SELECT * FROM tasks").fetchall() == [before]
    assert gh.posts == [] and worker.calls == 0


@pytest.mark.parametrize("response,expected_stage,exception_type,returncode", [
    ("nonzero", "WORKER_SUBPROCESS", None, 2),
    ("startup", "WORKER_SUBPROCESS", "FileNotFoundError", None),
    ("timeout", "WORKER_SUBPROCESS", "TimeoutExpired", None),
    ("missing", "WORKER_RESULT_FILE", None, 0),
    ("oversized", "WORKER_RESULT_FILE", None, 0),
    ("json", "WORKER_RESULT_PARSE", "JSONDecodeError", 0),
    ("encoding", "WORKER_RESULT_PARSE", "UnicodeDecodeError", 0),
])
def test_worker_failure_reports_exact_stage_without_raw_stderr(tmp_path, monkeypatch, response, expected_stage, exception_type, returncode):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        kwargs["stderr"].write(b"error: invalid schema; Bearer fixture-private-value\n")
        if response == "startup": raise FileNotFoundError(2, "private executable path")
        if response == "timeout": raise subprocess.TimeoutExpired(command, 1, stderr=b"private")
        output = Path(command[command.index("--output-last-message") + 1])
        if response == "oversized": output.write_bytes(b"x" * 100_001)
        elif response == "json": output.write_text("not JSON fixture-private-value")
        elif response == "encoding": output.write_bytes(b"\xff")
        return SimpleNamespace(returncode=2 if response == "nonzero" else 0)
    monkeypatch.setattr(b.subprocess, "run", run)
    with pytest.raises(b.CodexWorkerFailure) as caught:
        b.CodexWorker(Path("unused.exe"), tmp_path / "home").run(task(), {})
    detail = caught.value.diagnostic
    assert (detail["stage"], detail["exception_type"], detail["returncode"]) == (expected_stage, exception_type, returncode)
    assert detail["stderr_reasons"] == ["OUTPUT_SCHEMA_REJECTED"]
    assert detail["stderr_raw_omitted"] and not detail["retry_attempted"]
    assert "private" not in json.dumps(detail) and len(calls) == 1
    assert not list(tmp_path.glob("bridge-turn-*"))


@pytest.mark.parametrize("failure", ["home", "temporary", "schema"])
def test_worker_preparation_failures_are_not_generic_local_errors(tmp_path, monkeypatch, failure):
    home = tmp_path / "home"
    if failure == "home": home.write_text("existing user file")
    elif failure == "temporary":
        def fail(*args, **kwargs): raise PermissionError(13, "private directory")
        monkeypatch.setattr(b.tempfile, "TemporaryDirectory", fail)
    else:
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name == "result.schema.json": raise PermissionError(13, "private schema path")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", write)
    monkeypatch.setattr(b.subprocess, "run", lambda *args, **kwargs: pytest.fail("CLI must not start"))
    with pytest.raises(b.CodexWorkerFailure) as caught:
        b.CodexWorker(Path("unused.exe"), home).run(task(), {})
    assert caught.value.diagnostic["stage"] == {"home": "WORKER_HOME_PREPARATION", "temporary": "WORKER_TEMP_CREATION", "schema": "WORKER_SCHEMA_WRITE"}[failure]
    assert caught.value.diagnostic["returncode"] is None
    assert "private" not in json.dumps(caught.value.diagnostic)
    if failure == "home": assert home.read_text() == "existing user file"


@pytest.mark.parametrize("process_fails", [False, True])
def test_worker_cleanup_failure_does_not_hide_primary_failure(tmp_path, monkeypatch, process_fails):
    real_temporary = b.tempfile.TemporaryDirectory
    class Temporary(real_temporary):
        def cleanup(self):
            super().cleanup()
            raise PermissionError(13, "private cleanup path")
    monkeypatch.setattr(b.tempfile, "TemporaryDirectory", Temporary)
    def run(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"status": "PASS", "summary": "BRIDGE_SMOKE_OK", "edits": []}))
        return SimpleNamespace(returncode=1 if process_fails else 0)
    monkeypatch.setattr(b.subprocess, "run", run)
    with pytest.raises(b.CodexWorkerFailure) as caught:
        b.CodexWorker(Path("unused.exe"), tmp_path / "home").run(task(), {})
    detail = caught.value.diagnostic
    if process_fails:
        assert detail["stage"] == "WORKER_SUBPROCESS" and detail["returncode"] == 1
        assert detail["cleanup_failure"]["stage"] == "WORKER_TEMP_CLEANUP"
    else:
        assert detail["stage"] == "WORKER_TEMP_CLEANUP" and detail["returncode"] == 0
        assert detail["exception_type"] == "PermissionError"
    assert "private" not in json.dumps(detail)


def test_typed_worker_failure_is_persisted_and_failed_issue_is_not_retried(setup):
    root, _, db = setup
    value = task(); gh = FakeGitHub(value); gh.approve()
    class Worker(FakeWorker):
        def run(self, *args):
            self.calls += 1
            raise b.CodexWorkerFailure("WORKER_TEMP_CLEANUP", PermissionError(13, "private"), 0)
    worker = Worker(); bridge = b.Bridge(root, db, gh, worker)
    bridge.tick(); before = db.execute("SELECT * FROM tasks").fetchone()
    bridge.tick()
    assert worker.calls == 1 and db.execute("SELECT * FROM tasks").fetchone() == before
    report = json.loads(before[5])
    assert report["state"] == "FAILED" and report["stage"] == "WORKER_TEMP_CLEANUP"
    assert report["exception_type"] == "PermissionError" and report["returncode"] == 0
    assert report["worker_started"] and not report["write_attempted"]
    assert "LOCAL_FAILURE_NO_RETRY" not in gh.posts[-1] and "private" not in gh.posts[-1]


@pytest.mark.parametrize("result", [[], {"status": "PASS"}, {"status": "PASS", "summary": "BRIDGE_SMOKE_OK", "edits": [], "extra": 1},
    {"status": "PASS", "summary": "another result", "edits": []}])
def test_worker_json_result_must_still_satisfy_smoke_protocol(result):
    with pytest.raises(b.Blocked): b.validate_result(task(), {}, result)


def test_windows_cwd_handle_is_not_a_disposable_artifact_directory(tmp_path, monkeypatch):
    real_temporary = b.tempfile.TemporaryDirectory
    calls = []; cleanups = []; working_directories = []
    class Temporary(real_temporary):
        def cleanup(self):
            cleanups.append(1)
            if Path(self.name) in working_directories:
                error = PermissionError(13, "private locked directory")
                error.winerror = 32
                raise error
            super().cleanup()
    monkeypatch.setattr(b.tempfile, "TemporaryDirectory", Temporary)
    monkeypatch.setattr(b.time, "sleep", lambda *_: pytest.fail("No retry"))
    def run(command, **kwargs):
        calls.append(command)
        working_directories.append(Path(kwargs["cwd"]))
        output = Path(command[command.index("--output-last-message") + 1])
        assert output.parent != Path(kwargs["cwd"])
        assert Path(command[command.index("--cd") + 1]) == Path(kwargs["cwd"])
        output.write_text(json.dumps(
            {"status": "PASS", "summary": "BRIDGE_SMOKE_OK", "edits": []}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(b.subprocess, "run", run)
    worker = b.CodexWorker(Path("unused.exe"), tmp_path / "home")
    assert worker.run(task(), {})["summary"] == "BRIDGE_SMOKE_OK"
    assert len(calls) == 1 and len(cleanups) == 1
    assert not list(tmp_path.glob("bridge-turn-*"))
    assert (tmp_path / "worker-cwd").is_dir() and not list((tmp_path / "worker-cwd").iterdir())


def test_worker_refuses_preexisting_workspace_content(tmp_path, monkeypatch):
    work = tmp_path / "worker-cwd"; work.mkdir()
    (work / "AGENTS.md").write_text("untrusted instructions")
    monkeypatch.setattr(b.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("CLI must not start"))
    with pytest.raises(b.Blocked, match="CODEX_WORKSPACE_NOT_EMPTY"):
        b.CodexWorker(Path("unused.exe"), tmp_path / "home").run(task(), {})
    assert (work / "AGENTS.md").read_text() == "untrusted instructions"


def test_worker_stderr_identifier_digits_are_not_misreported_as_http_errors():
    detail = b.CodexWorkerFailure("WORKER_TEMP_CLEANUP", stderr="thread_401_403_identifier").diagnostic
    assert detail["stderr_present"] and detail["stderr_reasons"] == []
    assert "thread_401" not in json.dumps(detail)


def test_identical_deferred_logs_are_suppressed_but_every_poll_rechecks_admission(two_issue_bridge, capsys):
    root, _, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    first = json.loads(capsys.readouterr().out)
    assert first["error"] == "TASK_RECEIPT_DEFERRED"
    requests = []; polls = []
    request, pages = gh.request, gh.pages
    def get(method, path, payload=None):
        requests.append((method, path))
        return request(method, path, payload)
    def discover(path):
        polls.append(path)
        return pages(path)
    gh.request, gh.pages = get, discover
    for _ in range(3): bridge.tick()
    assert capsys.readouterr().out == ""
    assert requests.count(("GET", f"/repos/{b.REPOSITORY}/issues/1")) == 3
    assert len(polls) == 3
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0
    assert len(bridge._deferred_diagnostics) == 1


@pytest.mark.parametrize("change", ["task_id", "operation_id", "reason"])
def test_changed_deferred_identity_or_reason_is_logged_again(two_issue_bridge, capsys, change):
    root, _, db, _, _, gh, worker, _ = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    first = json.loads(capsys.readouterr().out)
    if change == "task_id":
        db.execute("UPDATE tasks SET task_id=? WHERE issue=1", (str(uuid.uuid4()),)); db.commit()
    elif change == "operation_id":
        db.execute("UPDATE tasks SET comment=comment || ? WHERE issue=1", ("\nchanged receipt",)); db.commit()
    else:
        gh.issues[1]["state"] = "open"
        gh.issues[1]["body"] = json.dumps(task())
    bridge.tick()
    changed = json.loads(capsys.readouterr().out)
    assert first[change] != changed[change]
    bridge.tick()
    assert capsys.readouterr().out == "" and len(bridge._deferred_diagnostics) == 1
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0


@pytest.mark.parametrize("change", ["state", "label", "locked"])
def test_meaningful_issue_changes_are_visible_even_when_deferral_reason_is_same(two_issue_bridge, capsys, change):
    root, _, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    if change == "state": gh.issues[1]["labels"] = []
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    first = json.loads(capsys.readouterr().out)
    if change == "state": gh.issues[1]["state"] = "open"
    elif change == "label": gh.issues[1]["labels"] = []
    else: gh.issues[1]["locked"] = True
    bridge.tick()
    changed = json.loads(capsys.readouterr().out)
    assert first["reason"] == changed["reason"] == "ISSUE_NOT_AUTHORIZED"
    field = {"state": "issue_state", "label": "task_label_present", "locked": "issue_locked"}[change]
    assert first[field] != changed[field]
    bridge.tick()
    assert capsys.readouterr().out == ""
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert worker.calls == 0


def test_deferred_state_reversion_is_not_suppressed_by_old_history(two_issue_bridge, capsys):
    root, _, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    first = json.loads(capsys.readouterr().out)
    labels = gh.issues[1]["labels"]
    gh.issues[1]["labels"] = []
    bridge.tick()
    assert json.loads(capsys.readouterr().out)["task_label_present"] is False
    gh.issues[1]["labels"] = labels
    bridge.tick()
    assert json.loads(capsys.readouterr().out) == first
    assert len(bridge._deferred_diagnostics) == 1
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before and worker.calls == 0


def test_suppressed_old_diagnostic_does_not_block_independent_approved_task(two_issue_bridge, capsys):
    root, _, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick(); capsys.readouterr()
    gh.approve(2)
    bridge.tick(); bridge.tick()
    assert capsys.readouterr().out == ""
    assert worker.calls == 1 and [number for number, _ in gh.posts] == [2, 2, 2]
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert db.execute("SELECT state,delivered FROM tasks WHERE issue=2").fetchone() == ("PASS", 1)


def test_new_bridge_after_restart_emits_first_observation_without_journal_changes(two_issue_bridge, capsys):
    root, state, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    first = json.loads(capsys.readouterr().out)
    bridge.tick()
    assert capsys.readouterr().out == ""
    recovered = b.open_state(state)
    try:
        restarted = b.Bridge(root, recovered, gh, worker)
        restarted.tick()
        assert json.loads(capsys.readouterr().out) == first
        restarted.tick()
        assert capsys.readouterr().out == ""
        assert recovered.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
        assert [number for number, _ in gh.posts] == [2] and worker.calls == 0
        assert not recovered.execute("SELECT * FROM settings").fetchall()
    finally: recovered.close()


def test_reconciliation_still_runs_and_recurring_deferral_is_logged(two_issue_bridge, capsys):
    root, _, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick()
    first = json.loads(capsys.readouterr().out)
    gh.issues[1]["state"] = "open"
    with pytest.raises(b.CommentDeliveryUncertain): bridge.tick()
    assert json.loads(capsys.readouterr().out)["error"] == "COMMENT_DELIVERY_UNCERTAIN_NO_REPOST"
    assert bridge._deferred_diagnostics == {}
    gh.issues[1]["state"] = "closed"
    bridge.tick()
    assert json.loads(capsys.readouterr().out) == first
    gh.issues[1]["state"] = "open"
    gh.notes[1].append({"body": before[6], "user": {"id": 7, "login": b.OWNER}})
    bridge.tick()
    assert bridge._deferred_diagnostics == {}
    assert db.execute("SELECT attempted,delivered FROM tasks WHERE issue=1").fetchone() == (1, 1)
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0


def test_new_api_error_is_never_hidden_by_deferred_log_cache(two_issue_bridge, capsys):
    root, _, db, _, _, gh, worker, before = two_issue_bridge
    gh.issues[1]["state"] = "closed"
    bridge = b.Bridge(root, db, gh, worker)
    bridge.tick(); capsys.readouterr()
    def fail(method, path, payload=None):
        raise b.GitHubFailure(method, path, "NETWORK_FAILED", "TLS_ERROR")
    gh.request = fail
    with pytest.raises(b.GitHubFailure) as caught: bridge.tick()
    assert caught.value.diagnostic["reason"] == "TLS_ERROR"
    assert caught.value.diagnostic["method"] == "GET"
    assert db.execute("SELECT * FROM tasks WHERE issue=1").fetchone() == before
    assert [number for number, _ in gh.posts] == [2] and worker.calls == 0
