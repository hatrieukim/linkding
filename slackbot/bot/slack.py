"""Posting to Slack, and turning GitLab Markdown into something Slack shows well."""

import logging
import re

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

log = logging.getLogger(__name__)

# Slack accepts 12,000 characters of Markdown per message and 3,000 per
# section block. Stay under both.
MARKDOWN_LIMIT = 11000
SECTION_LIMIT = 2900


def normalize(markdown: str) -> str:
    """Clean up GitLab Markdown that no Slack format understands."""
    text = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    text = re.sub(r"^(\s*)[-*] \[[xX]\] ", r"\1- ✅ ", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)[-*] \[ \] ", r"\1- ⬜ ", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def to_mrkdwn(markdown: str) -> str:
    """Convert Markdown to Slack's older mrkdwn dialect. Used as a fallback."""
    text = markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"^&gt; ", "> ", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"^#{1,6}\s+(.+?)\s*$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)[-*] ", r"\1• ", text, flags=re.MULTILINE)
    return re.sub(r"\*{2,}", "*", text)


def split(text: str, limit: int) -> list:
    """Split text into parts of at most `limit` characters, at paragraph or line ends."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def link_references(markdown: str, project_url: str) -> str:
    """Make `!9` and `#7` clickable, as they are on GitLab."""
    text = re.sub(r"(?<![\w/\[`])!(\d+)\b", rf"[!\1]({project_url}/-/merge_requests/\1)", markdown)
    return re.sub(r"(?<![\w/\[`#&])#(\d+)\b", rf"[#\1]({project_url}/-/issues/\1)", text)


def button(label: str, action: str, style: str | None = None) -> dict:
    element = {"type": "button", "action_id": action, "text": {"type": "plain_text", "text": label}}
    if style:
        element["style"] = style
    return element


class Slack:
    def __init__(self, token: str):
        self._client = WebClient(token=token)
        self._client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=3))
        # The `markdown` block renders standard Markdown. If the workspace
        # rejects it once, section blocks are used from then on.
        self._markdown_block = True

    def _blocks(self, part: str, buttons: list | None) -> list:
        if self._markdown_block:
            blocks = [{"type": "markdown", "text": part}]
        else:
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": piece}}
                for piece in split(to_mrkdwn(part), SECTION_LIMIT)
            ]
        if buttons:
            blocks.append({"type": "actions", "elements": buttons})
        return blocks

    def _send(self, method, part: str, buttons: list | None, **target) -> str:
        preview = re.sub(r"[*_`#>\[\]]", "", part)[:200]
        try:
            response = method(text=preview, blocks=self._blocks(part, buttons), **target)
        except SlackApiError as error:
            if not self._markdown_block:
                raise
            # Most likely the markdown block is not available here. Try the
            # older format once, and keep using it if that works.
            log.warning(
                "Slack refused a markdown block (%s), trying mrkdwn sections", error.response.get("error")
            )
            self._markdown_block = False
            try:
                response = method(text=preview, blocks=self._blocks(part, buttons), **target)
            except SlackApiError:
                self._markdown_block = True
                raise
        return response["ts"]

    def post(self, channel: str, thread_ts: str, markdown: str, buttons: list | None = None) -> str:
        """Post into a thread. Long text becomes several messages. Returns the last timestamp."""
        parts = split(normalize(markdown), MARKDOWN_LIMIT) or ["(trống)"]
        ts = ""
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            ts = self._send(
                self._client.chat_postMessage,
                part,
                buttons if last else None,
                channel=channel,
                thread_ts=thread_ts,
                unfurl_links=False,
                unfurl_media=False,
            )
        return ts

    def update(self, channel: str, ts: str, markdown: str, buttons: list | None = None) -> None:
        """Replace a message the bot posted earlier."""
        parts = split(normalize(markdown), MARKDOWN_LIMIT) or ["(trống)"]
        self._send(self._client.chat_update, parts[0], buttons, channel=channel, ts=ts)

    def thread_messages(self, channel: str, thread_ts: str) -> list:
        """Messages people wrote in a thread, oldest first. Bot messages are left out."""
        response = self._client.conversations_replies(channel=channel, ts=thread_ts, limit=200)
        return [
            {"ts": message["ts"], "text": message.get("text", "")}
            for message in response.get("messages", [])
            if not message.get("bot_id") and not message.get("subtype")
        ]
