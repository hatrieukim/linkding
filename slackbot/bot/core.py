"""What the bot does.

Three jobs:

1. Conversation. A message in Slack is passed to Duo and the answer is posted
   back in the same thread.
2. Issue. When the maintainer settles, Duo writes the issue, the maintainer
   confirms it, and the bot creates it assigned to the Developer agent.
3. Progress. Until the change is on staging, everything that happens to the
   issue on GitLab is repeated in the Slack thread.

The bot decides nothing about the code. Duo does the thinking, the Developer
flow on GitLab does the work.
"""

import logging
import re
import time

from .duo import DuoError
from .gitlab import SpamRejected
from .slack import button, link_references

log = logging.getLogger(__name__)

FIRST_TURN = """\
You are the planning assistant of this project. You are talking with the maintainer \
over Slack to clarify a feature or a bug before it is written up as an issue.

Rules for this conversation, which take priority over AGENTS.md:
- Read only. Do not edit files, do not run commands that change anything, do not create \
issues, merge requests, branches or commits. When the maintainer settles, the system creates the issue.
- Answer in English, in prose, with short sentences, at most about 150 words. The \
"Simple version" block is not needed.
- Read the code when needed, so that the answer matches the current state of the app. Do not \
name files or functions unless asked.
- If something is still unclear in a way that changes the approach, ask. At most two \
questions per turn, each with the option you recommend.
- Once the request is clear, summarise in a few sentences what will go into the issue, then \
remind the maintainer to press the "Settle, write the issue" button.

The maintainer's message:
"""

NEXT_TURN = "The maintainer's next message (same rules as before: read only, English, short):\n"

DRAFT_TURN = """\
The maintainer has settled. Based on the whole conversation, write the final issue. \
Still read only, do not create anything on GitLab.

Print exactly the format below and nothing else. Leave out any section that has no content.

TITLE: <title in English, at most 80 characters>

## Background
<why this change is needed>

## Desired outcome
<what the user will see and be able to do>

## Out of scope
<what was agreed not to do>

## Notes
<decisions and constraints agreed in the conversation>
"""

ISSUE_FOOTER = "\n\n---\n_This issue was written from a conversation in Slack._"

UNREAD = "Earlier messages in the thread that you have not read yet, oldest first:\n"

SPAM_REJECTED = """\
⚠️ GitLab refused to create this issue. Its spam filter suspects the content is spam. \
This is a false positive, but pressing again will be refused again, so do not retry. You have three options:

- Press **Create as private**, or write `create private`. A private issue is visible only to project \
members, and GitLab does not run the spam filter on those.
- Press **Keep discussing** and ask me for a shorter, plainer draft.
- Create the issue yourself on the GitLab website, then write `track #<issue number>` in this thread \
and I will report its progress.
"""

THINKING = "⏳ Reading the code and thinking…"
FOLLOW_COMMAND = re.compile(r"^(?:track|follow)\s+#?(\d+)$", re.IGNORECASE)
MAX_UNREAD = 20


def ts_key(ts: str) -> tuple:
    """Slack timestamps are strings like 1791732397.764479. Compare them exactly."""
    return tuple(int(part) for part in ts.split("."))


def parse_draft(text: str) -> tuple:
    """Split Duo's answer into an issue title and description."""
    text = re.sub(r"^```\w*\n|\n```\s*$", "", text.strip())
    match = re.search(r"^\s*\**TITLE:\**\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if match:
        title = match.group(1)
        description = text[match.end() :]
    else:
        title, _, description = text.partition("\n")
    title = title.strip().strip("*#` ").strip()
    return title[:200], description.strip()


class Bot:
    def __init__(self, settings, store, slack, duo, gitlab):
        self.settings = settings
        self.store = store
        self.slack = slack
        self.duo = duo
        self.gitlab = gitlab

    # ------------------------------------------------------------ dispatch

    def run(self, task: dict) -> None:
        """Run one piece of background work queued by the web endpoints."""
        kind = task.get("kind")
        handler = {
            "message": self.on_message,
            "draft": self.on_draft,
            "create": self.on_create,
            "create_private": self.on_create,
            "continue": self.on_continue,
        }.get(kind)
        if handler is None:
            log.warning("unknown task kind %r", kind)
            return
        if not self._allowed(task):
            return
        handler(task)

    def _allowed(self, task: dict) -> bool:
        user = task.get("user", "")
        allowed = self.settings.allowed_users or (self.store.owner(user),)
        if user in allowed:
            return True
        # Other people talking in a thread are not talking to the bot.
        if task.get("quiet"):
            return False
        self.slack.post(
            task["channel"],
            task["thread_ts"],
            "This bot only takes requests from the project maintainer.",
        )
        return False

    @staticmethod
    def _key(task: dict) -> str:
        return f"{task['channel']}_{task['thread_ts']}"

    # -------------------------------------------------------- conversation

    def _ask_duo(self, task: dict, goal: str, waiting: str, lock_ttl: int = 330):
        """Run one Duo turn for a thread. Returns (reply, placeholder ts) or (None, ts)."""
        key = self._key(task)
        channel, thread_ts = task["channel"], task["thread_ts"]
        if not self.store.acquire_lock(f"thread_{key}", lock_ttl):
            self.slack.post(
                channel,
                thread_ts,
                "I am still answering your previous message. I will read this one together with your next.",
            )
            return None, None
        placeholder = self.slack.post(channel, thread_ts, waiting)
        try:
            thread = self.store.get("threads", key) or {}
            reply = self.duo.run(goal(thread), thread.get("session_id"))
            seen = {"last_ts": task["ts"]} if task.get("ts") else {}
            self.store.save("threads", key, {"session_id": reply.session_id, **seen})
            return reply, placeholder
        except DuoError as error:
            log.error("Duo turn failed for %s: %s", key, error)
            self.slack.update(
                channel,
                placeholder,
                "⚠️ Duo could not answer this time. Please send your message again.",
            )
            return None, placeholder
        finally:
            self.store.release_lock(f"thread_{key}")

    def on_message(self, task: dict) -> None:
        text = task.get("text", "").strip()
        if not text:
            return
        if text.lower().rstrip(".!") in ("settle", "draft"):
            return self.on_draft(task)
        if text.lower().rstrip(".!") in ("create private", "private"):
            return self.on_create({**task, "kind": "create_private"})
        follow = FOLLOW_COMMAND.match(text)
        if follow:
            return self.on_follow(task, int(follow.group(1)))

        def goal(thread: dict) -> str:
            rules = NEXT_TURN if thread.get("session_id") else FIRST_TURN
            return rules + self._unread(task, thread) + text

        reply, placeholder = self._ask_duo(task, goal, THINKING)
        if reply:
            self.slack.update(
                task["channel"],
                placeholder,
                reply.text,
                [button("Settle, write the issue", "draft", "primary")],
            )

    def _unread(self, task: dict, thread: dict) -> str:
        """Thread messages Duo has not been given yet.

        Slack only sends the bot what is addressed to it. When the bot is
        called into a discussion that is already going on, or a message was
        skipped because the bot was busy, Duo would otherwise miss part of
        the conversation.
        """
        if not task.get("ts"):
            return ""
        try:
            messages = self.slack.thread_messages(task["channel"], task["thread_ts"])
        except Exception as error:
            log.warning("could not read the thread: %s", error)
            return ""
        after = ts_key(thread["last_ts"]) if thread.get("last_ts") else (0,)
        unread = [
            re.sub(r"<@[A-Z0-9]+>", "", message["text"]).strip()[:1500]
            for message in messages
            if after < ts_key(message["ts"]) < ts_key(task["ts"])
        ]
        unread = [text for text in unread if text][-MAX_UNREAD:]
        if not unread:
            return ""
        return UNREAD + "\n".join(f"- {text}" for text in unread) + "\n\nLatest message:\n"

    def on_draft(self, task: dict) -> None:
        key = self._key(task)
        channel, thread_ts = task["channel"], task["thread_ts"]
        if not (self.store.get("threads", key) or {}).get("session_id"):
            self.slack.post(
                channel, thread_ts, "There is nothing to settle yet. Tell me what you want first."
            )
            return
        reply, placeholder = self._ask_duo(task, lambda thread: DRAFT_TURN, "⏳ Writing the issue draft…")
        if not reply:
            return
        title, description = parse_draft(reply.text)
        self.store.save("threads", key, {"draft": {"title": title, "description": description}})
        self.slack.update(
            channel,
            placeholder,
            f"**Issue draft**\n\n**{title}**\n\n{description}",
            [button("Create this issue", "create", "primary"), button("Keep discussing", "continue")],
        )

    def on_continue(self, task: dict) -> None:
        draft = (self.store.get("threads", self._key(task)) or {}).get("draft")
        if draft and task.get("message_ts"):
            self.slack.update(
                task["channel"],
                task["message_ts"],
                f"**Issue draft (not created)**\n\n**{draft['title']}**\n\n{draft['description']}",
            )
        self.slack.post(task["channel"], task["thread_ts"], "Sure. Tell me here what you want to change.")

    def on_create(self, task: dict) -> None:
        key = self._key(task)
        channel, thread_ts = task["channel"], task["thread_ts"]
        # A second click on the same button must not create a second issue.
        guard = f"create_{key}_{task.get('message_ts', '')}"
        if not self.store.acquire_lock(guard, 24 * 3600):
            return
        draft = (self.store.get("threads", key) or {}).get("draft")
        if not draft:
            self.store.release_lock(guard)
            self.slack.post(
                channel, thread_ts, "No draft found. Please press “Settle, write the issue” again."
            )
            return
        private = task["kind"] == "create_private"
        body = f"**{draft['title']}**\n\n{draft['description']}"
        try:
            issue = self.gitlab.create_issue(draft["title"], draft["description"] + ISSUE_FOOTER, private)
        except SpamRejected:
            self.store.release_lock(guard)
            if task.get("message_ts"):
                self.slack.update(
                    channel,
                    task["message_ts"],
                    f"**Issue draft (refused by GitLab)**\n\n{body}",
                    [
                        button("Create as private", "create_private", "primary"),
                        button("Keep discussing", "continue"),
                    ],
                )
            self.slack.post(channel, thread_ts, SPAM_REJECTED)
            return
        except Exception:
            self.store.release_lock(guard)
            raise
        iid = issue["iid"]
        self._follow(iid, channel, thread_ts)
        self.store.save("threads", key, {"draft": None, "issue_iid": iid})
        if task.get("message_ts"):
            self.slack.update(channel, task["message_ts"], f"**Issue created**\n\n{body}")
        kind = "private issue" if private else "issue"
        self.slack.post(
            channel,
            thread_ts,
            f"✅ Created [{kind} #{iid}]({issue['web_url']}) and assigned it to the agent. "
            "Progress will show up in this thread.",
        )

    def on_follow(self, task: dict, iid: int) -> None:
        """Report in this thread on an issue that was created outside the bot."""
        channel, thread_ts = task["channel"], task["thread_ts"]
        try:
            self.gitlab.issue(iid)
        except Exception:
            self.slack.post(channel, thread_ts, f"I cannot find issue #{iid} in the project.")
            return
        self._follow(iid, channel, thread_ts)
        self.slack.post(
            channel, thread_ts, f"Sure. I will report the progress of issue #{iid} in this thread."
        )

    def _follow(self, iid: int, channel: str, thread_ts: str) -> None:
        self.store.save(
            "tracks",
            str(iid),
            {
                "iid": iid,
                "channel": channel,
                "thread_ts": thread_ts,
                "active": True,
                "created_at": time.time(),
                "last_note_id": 0,
                "seen": [],
            },
        )

    # ------------------------------------------------------------ progress

    def tick(self) -> int:
        """Report what is new on every issue being followed. Called once a minute."""
        if not self.store.acquire_lock("tick", 110):
            return 0
        try:
            tracks = self.store.active_tracks()
            for track in tracks:
                try:
                    self._advance(track)
                except Exception:
                    log.exception("could not report on issue %s", track.get("iid"))
            return len(tracks)
        finally:
            self.store.release_lock("tick")

    def _advance(self, track: dict) -> None:
        iid = track["iid"]
        channel, thread_ts = track["channel"], track["thread_ts"]
        seen = list(track.get("seen", []))
        project_url = self.gitlab.project()["web_url"]
        state = {"last_note_id": track.get("last_note_id", 0), "active": True}

        def say(markdown: str) -> None:
            self.slack.post(channel, thread_ts, link_references(markdown, project_url))

        def once(key: str, markdown: str) -> None:
            if key not in seen:
                say(markdown)
                seen.append(key)

        try:
            for note in self.gitlab.notes(iid):
                if note["id"] <= state["last_note_id"]:
                    continue
                author = note["author"]["name"]
                if note.get("system"):
                    say(f"🔹 **{author}** {note['body']}")
                else:
                    say(f"💬 **{author}** wrote on issue #{iid}:\n\n{note['body']}")
                state["last_note_id"] = note["id"]

            deployed = False
            merged = False
            for related in self.gitlab.related_merge_requests(iid):
                mr = self.gitlab.merge_request(related["iid"])
                ref = f"[!{mr['iid']}]({mr['web_url']})"
                once(f"mr{mr['iid']}:opened", f"🔀 Merge request {ref} opened: {mr['title']}")
                if mr["state"] == "merged":
                    merged = True
                    once(f"mr{mr['iid']}:merged", f"✅ {ref} merged into `{mr['target_branch']}`.")
                    deployed = self._report_deploy(mr, once) or deployed
                elif mr["state"] == "closed":
                    once(f"mr{mr['iid']}:closed", f"🚫 {ref} was closed without merging.")
                else:
                    self._report_pipeline(mr, ref, once)

            closed = self.gitlab.issue(iid)["state"] == "closed"
            expired = time.time() - track.get("created_at", 0) > self.settings.track_hours * 3600
            if closed and (deployed or not merged):
                say(f"🏁 Issue #{iid} is closed. I stop tracking it here.")
                state["active"] = False
            elif expired:
                say(f"⏹ {self.settings.track_hours} hours have passed, I stop tracking issue #{iid}.")
                state["active"] = False
        finally:
            # Saved even when a call failed, so that nothing is reported twice.
            self.store.save("tracks", str(iid), {**state, "seen": seen})

    @staticmethod
    def _report_pipeline(mr: dict, ref: str, once) -> None:
        pipeline = mr.get("head_pipeline")
        if not pipeline:
            return
        status = pipeline["status"]
        link = f"[pipeline]({pipeline['web_url']})"
        if status == "running":
            once(f"pipe{pipeline['id']}:running", f"⏳ {link} of {ref} is running.")
        elif status == "success":
            once(f"pipe{pipeline['id']}:success", f"✅ {link} of {ref} passed.")
        elif status in ("failed", "canceled"):
            once(f"pipe{pipeline['id']}:{status}", f"❌ {link} of {ref} {status}.")

    def _report_deploy(self, mr: dict, once) -> bool:
        """Follow the default-branch pipeline of a merged MR. True once staging is settled."""
        sha = mr.get("merge_commit_sha") or mr.get("squash_commit_sha") or mr.get("sha")
        pipelines = self.gitlab.pipelines(sha, mr["target_branch"]) if sha else []
        if not pipelines:
            return False
        pipeline = pipelines[0]
        link = f"[pipeline]({pipeline['web_url']})"
        jobs = self.gitlab.jobs(pipeline["id"])
        staging = next((job for job in jobs if job["name"] == self.settings.staging_job), None)
        if staging and staging["status"] == "success":
            once(
                f"deploy{pipeline['id']}:success",
                f"🚀 Staging runs the new version: {self.settings.staging_url}\n"
                f"To release it to production, press `deploy-production` in {link}.",
            )
            return True
        if (staging and staging["status"] in ("failed", "canceled")) or pipeline["status"] in (
            "failed",
            "canceled",
        ):
            once(f"deploy{pipeline['id']}:failed", f"❌ The staging deploy failed. See {link}.")
            return True
        if pipeline["status"] == "success" and not staging:
            return True
        once(
            f"deploy{pipeline['id']}:running",
            f"⏳ {link} on `{mr['target_branch']}` is building and deploying to staging.",
        )
        return False
