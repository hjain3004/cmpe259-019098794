"""Offline checks for conversation isolation, honest presentation, and HTTP boundaries."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from cashbooks.demo.session import ChatTurnResult, ResolvedCitation, ToolTrace
from cashbooks.demo.web import DemoService, make_server, present_result
from cashbooks.contracts.common import Answerability


def test_live_provider_is_created_only_on_first_question(monkeypatch):
    from cashbooks.demo.rehearsal import rehearsal_llm
    created = []

    def fake_provider():
        created.append(True)
        provider = rehearsal_llm()
        provider.model = "test-live-adapter"
        return provider

    monkeypatch.setattr("cashbooks.llm.claude.ClaudeLLM", fake_provider)
    app = DemoService(mode="live")
    sid = app.create("C3")
    try:
        assert app.metadata()["mode"] == "live"
        assert created == []
        result = app.ask(sid, "Did I already pay invoice NS-1048?")
        assert result["ok"] and result["mode"] == "live"
        assert result["latency_ms"] is not None
        app.ask(sid, "What date was it paid?")
        assert len(created) == 1
    finally:
        app.discard(sid)


def test_rehearsal_followup_and_payment_boundary_do_not_match_history():
    app = DemoService()
    sid = app.create("C3")
    try:
        first = app.ask(sid, "Did I already pay invoice NS-1048?")
        assert first["ok"] and first["kind"] == "ANSWER"
        assert first["tools"][0]["name"] == "get_bill_status"
        followup = app.ask(sid, "What date was it paid?")
        assert "September 12" in followup["answer"]
        warning = app.ask(sid, "Did the payment details on BW-771 change?")
        assert warning["kind"] == "WARN"
        refused = app.ask(sid, "Pay it now.")
        assert refused["kind"] == "ABSTAIN"
        assert refused["tools"] == []
        assert refused["latency_ms"] is None
        assert len(app.sessions[sid].session.history) == 4
    finally:
        app.discard(sid)


def test_retrieval_context_does_not_choose_rehearsal_answer():
    app = DemoService()
    sid = app.create("C0")
    try:
        assert app.ask(sid, "Did the payment details on BW-771 change?")["kind"] == "WARN"
        assert app.ask(sid, "Pay it now.")["kind"] == "ABSTAIN"
    finally:
        app.discard(sid)


def test_browser_payload_has_no_raw_documents_or_tool_output():
    r = ChatTurnResult(config_name="C3", response=object(), answerability=Answerability.ANSWER,
                       answer="Account 123456789012", citations=[ResolvedCitation("span_inv_A_total", "Account 123456789012", "PRIVATE DOCUMENT CONTENT")],
                       tool_calls=[ToolTrace("get_bill_status", {"invoice_number":"123456789012"}, '{"raw_secret":"PRIVATE TOOL JSON"}')])
    data = json.dumps(present_result(r, "live"))
    assert "123456789012" not in data
    assert "PRIVATE DOCUMENT CONTENT" not in data
    assert "PRIVATE TOOL JSON" not in data
    assert "9012" in data


def test_invalid_response_is_not_kept_in_history():
    class InvalidSession:
        history = []
        def ask(self, q):
            self.history.append("broken response")
            return ChatTurnResult(config_name="C3", response=None, parse_error="private provider detail")
    session = InvalidSession()
    app = DemoService(session_factory=lambda _: session)
    sid = app.create("C3")
    result = app.ask(sid, "hello")
    assert not result["ok"] and result["kind"] == "ERROR"
    assert session.history == []
    assert "private provider detail" not in json.dumps(result)


def test_sessions_are_independent_and_busy_session_rejects_new_question():
    app = DemoService()
    a, b = app.create("C3"), app.create("C3")
    try:
        app.ask(a, "Did I already pay invoice NS-1048?")
        assert len(app.sessions[a].session.history) == 1
        assert app.sessions[b].session.history == []
        app.sessions[a].lock.acquire()
        try:
            with pytest.raises(ValueError, match="already running"):
                app.ask(a, "another")
            with pytest.raises(ValueError, match="Wait"):
                app.discard(a)
        finally:
            app.sessions[a].lock.release()
        with pytest.raises(ValueError):
            app.ask(a, " " * 3)
        with pytest.raises(ValueError):
            app.ask(a, "x" * 2001)
    finally:
        app.discard(a)
        app.discard(b)


@pytest.fixture
def http_app():
    app = DemoService()
    server = make_server(0, service=app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield app, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    for sid in list(app.sessions):
        app.discard(sid)


def request(url, body=None, **headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type":"application/json", **headers})
    return urllib.request.urlopen(req)


def test_http_is_local_token_protected_and_static_files_are_allowlisted(http_app):
    app, url = http_app
    meta = json.load(request(url+"/api/meta"))
    assert meta["mode"] == "rehearsal"
    for path in ["/code/.env", "/data/dev/cafe_01/ledger.json", "/../README.md"]:
        with pytest.raises(urllib.error.HTTPError) as e:
            request(url+path)
        assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        request(url+"/api/session", {"config":"C3"})
    assert e.value.code == 403
    headers = {"X-CashBooks-Token":meta["token"]}
    with pytest.raises(urllib.error.HTTPError) as e:
        request(url+"/api/session", {"config":"C3"}, **headers, Origin="https://example.com")
    assert e.value.code == 403
    sid = json.load(request(url+"/api/session", {"config":"C3"}, **headers))["session"]
    with pytest.raises(urllib.error.HTTPError):
        request(url+"/api/session", {"config":"unknown", "previous":sid}, **headers)
    assert sid in app.sessions
    answer = json.load(request(url+"/api/ask", {"session":sid,"question":"Did I already pay invoice NS-1048?"}, **headers))
    assert answer["ok"] and answer["sources"]


def test_provider_system_exit_becomes_a_safe_error(http_app):
    app, url = http_app
    class FailingSession:
        history = []
        def ask(self, _):
            raise SystemExit("sensitive provider diagnostic")
    app.session_factory = lambda _: FailingSession()
    sid = app.create("C3")
    with pytest.raises(urllib.error.HTTPError) as e:
        request(url+"/api/ask", {"session":sid,"question":"Hello"}, **{"X-CashBooks-Token":app.token})
    assert e.value.code == 503
    assert b"sensitive provider" not in e.value.read()
    assert json.load(request(url+"/api/meta"))["mode"] == "rehearsal"
