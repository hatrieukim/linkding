"""Web endpoints of the Slack bot.

/slack/events        messages from Slack
/slack/interactions  button clicks from Slack
/tasks/run           background work, called by Cloud Tasks
/tick                progress check, called by Cloud Scheduler every minute
/health              liveness
"""

import json
import logging
import re
import threading

from flask import Flask, jsonify, request
from slack_sdk.signature import SignatureVerifier

from .config import Settings
from .tasks import Tasks, is_internal_call

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("bot")

app = Flask(__name__)
settings = Settings()

_store = None
_bot = None
_guard = threading.RLock()


def store():
    """The store is all the Slack endpoints need, so it is built on its own."""
    global _store
    with _guard:
        if _store is None:
            from .store import FirestoreStore, MemoryStore

            _store = MemoryStore() if settings.local else FirestoreStore()
    return _store


def bot():
    """Build the bot on first use, so the process starts without any credentials."""
    global _bot
    with _guard:
        if _bot is None:
            from .core import Bot
            from .duo import Duo
            from .gitlab import GitLab
            from .slack import Slack

            gitlab = GitLab(settings)
            project = gitlab.project()
            _bot = Bot(
                settings,
                store(),
                Slack(settings.slack_bot_token),
                Duo(settings, project["http_url_to_repo"], project["default_branch"]),
                gitlab,
            )
    return _bot


def run_task(task: dict) -> None:
    try:
        bot().run(task)
    except Exception:
        log.exception("task %s failed", task.get("kind"))
        try:
            bot().slack.post(
                task["channel"],
                task["thread_ts"],
                "⚠️ Có lỗi khi xử lý yêu cầu này. Chi tiết nằm trong log của bot.",
            )
        except Exception:
            log.exception("could not report the failure to Slack")


tasks = Tasks(settings, run_task)


def from_slack() -> bool:
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    # The verifier expects a numeric timestamp and fails on anything else.
    if not timestamp.isdigit() or not signature:
        return False
    return SignatureVerifier(settings.slack_signing_secret).is_valid(
        request.get_data(as_text=True), timestamp, signature
    )


@app.get("/health")
def health():
    return "healthy\n"


@app.post("/slack/events")
def slack_events():
    if not from_slack():
        return "invalid signature", 401
    body = request.get_json(force=True, silent=True) or {}
    if body.get("type") == "url_verification":
        return jsonify(challenge=body.get("challenge", ""))

    event = body.get("event", {})
    # Ignore edits, deletions, joins and everything written by bots, this one included.
    if event.get("type") not in ("message", "app_mention") or event.get("subtype") or event.get("bot_id"):
        return "", 200
    channel, ts = event.get("channel", ""), event.get("ts", "")
    thread_ts = event.get("thread_ts") or ts
    thread_key = f"{channel}_{thread_ts}"

    addressed = event["type"] == "app_mention" or event.get("channel_type") == "im"
    if not addressed:
        # In a channel the bot listens without being mentioned only inside
        # threads it is already part of.
        if not event.get("thread_ts") or store().get("threads", thread_key) is None:
            return "", 200
    # Slack sends an event again when the answer was slow, and sends a mention
    # inside such a thread twice: as a mention and as a message.
    if not store().claim("events", f"{channel}_{ts}"):
        return "", 200
    store().save("threads", thread_key, {"channel": channel})

    tasks.enqueue(
        {
            "kind": "message",
            "channel": channel,
            "thread_ts": thread_ts,
            "ts": ts,
            "user": event.get("user", ""),
            "text": re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip(),
            "quiet": not addressed,
        }
    )
    return "", 200


@app.post("/slack/interactions")
def slack_interactions():
    if not from_slack():
        return "invalid signature", 401
    payload = json.loads(request.form.get("payload", "{}"))
    actions = payload.get("actions") or [{}]
    kind = actions[0].get("action_id")
    message = payload.get("message", {})
    container = payload.get("container", {})
    if payload.get("type") != "block_actions" or kind not in ("draft", "create", "continue"):
        return "", 200
    tasks.enqueue(
        {
            "kind": kind,
            "channel": container.get("channel_id") or payload.get("channel", {}).get("id"),
            "thread_ts": message.get("thread_ts") or message.get("ts"),
            "message_ts": message.get("ts"),
            "user": payload.get("user", {}).get("id", ""),
        }
    )
    return "", 200


@app.post("/tasks/run")
def tasks_run():
    if not is_internal_call(settings, request.headers.get("Authorization", "")):
        return "forbidden", 403
    run_task(request.get_json(force=True))
    return "", 200


@app.post("/tick")
def tick():
    if not is_internal_call(settings, request.headers.get("Authorization", "")):
        return "forbidden", 403
    return jsonify(following=bot().tick())
