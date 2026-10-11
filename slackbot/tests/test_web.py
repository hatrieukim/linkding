import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

SECRET = "test-signing-secret"


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("BOT_LOCAL", "1")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SECRET)
    from bot import main
    from bot.config import Settings
    from bot.store import MemoryStore

    queued = []
    monkeypatch.setattr(main, "settings", Settings())
    monkeypatch.setattr(main, "_store", MemoryStore())
    monkeypatch.setattr(main.tasks, "enqueue", queued.append)
    return main.app.test_client(), queued


def signed(body: str, secret: str = SECRET) -> dict:
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"v0:{timestamp}:{body}".encode(), hashlib.sha256).hexdigest()
    return {"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": f"v0={digest}"}


def post_event(client, body: dict, **kwargs):
    raw = json.dumps(body)
    headers = signed(raw, **kwargs) | {"Content-Type": "application/json"}
    return client.post("/slack/events", data=raw, headers=headers)


def message(**event):
    base = {"type": "message", "channel_type": "im", "channel": "D1", "user": "U1", "ts": "100.1"}
    return {"type": "event_callback", "event_id": "E1", "event": base | event}


def test_health(web):
    client, _ = web
    assert client.get("/health").data == b"healthy\n"


def test_requests_not_signed_by_slack_are_rejected(web):
    client, queued = web
    assert post_event(client, message(text="hi"), secret="wrong").status_code == 401
    assert queued == []


def test_requests_without_slack_headers_are_rejected(web):
    client, queued = web
    assert client.post("/slack/events", json=message(text="hi")).status_code == 401
    assert client.post("/slack/interactions", data={"payload": "{}"}).status_code == 401
    assert queued == []


def test_url_verification_answers_the_challenge(web):
    client, _ = web
    response = post_event(client, {"type": "url_verification", "challenge": "abc"})
    assert response.get_json() == {"challenge": "abc"}


def test_a_direct_message_is_queued_once_even_when_slack_retries(web):
    client, queued = web
    post_event(client, message(text="<@UBOT> thêm nút"))
    post_event(client, message(text="<@UBOT> thêm nút"))
    assert queued == [
        {"kind": "message", "channel": "D1", "thread_ts": "100.1", "user": "U1", "text": "thêm nút"}
    ]


def test_a_reply_in_a_thread_keeps_the_thread(web):
    client, queued = web
    post_event(client, message(text="tiếp", ts="100.5", thread_ts="100.1"))
    assert queued[0]["thread_ts"] == "100.1"


def test_bot_messages_and_edits_are_ignored(web):
    client, queued = web
    post_event(client, message(text="x", bot_id="B1"))
    post_event(client, message(text="x", subtype="message_changed", event_id="E2"))
    assert queued == []


def test_a_button_click_is_queued_with_its_message(web):
    client, queued = web
    payload = {
        "type": "block_actions",
        "user": {"id": "U1"},
        "container": {"channel_id": "D1"},
        "message": {"ts": "100.9", "thread_ts": "100.1"},
        "actions": [{"action_id": "create"}],
    }
    raw = urlencode({"payload": json.dumps(payload)})
    headers = signed(raw) | {"Content-Type": "application/x-www-form-urlencoded"}
    assert client.post("/slack/interactions", data=raw, headers=headers).status_code == 200
    assert queued == [
        {"kind": "create", "channel": "D1", "thread_ts": "100.1", "message_ts": "100.9", "user": "U1"}
    ]


def test_internal_endpoints_reject_callers_without_a_google_token(web, monkeypatch):
    client, _ = web
    from bot import main

    monkeypatch.setattr(main.settings, "local", False)
    assert client.post("/tick").status_code == 403
    assert client.post("/tasks/run", json={"kind": "message"}).status_code == 403
