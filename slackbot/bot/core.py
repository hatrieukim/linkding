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
from .slack import button, link_references

log = logging.getLogger(__name__)

FIRST_TURN = """\
Bạn là trợ lý lập kế hoạch của dự án này. Bạn đang trò chuyện với maintainer \
qua Slack để làm rõ một tính năng hoặc một lỗi, trước khi nó được viết thành issue.

Luật của cuộc trò chuyện này, ưu tiên hơn AGENTS.md:
- Chỉ đọc. Không sửa file, không chạy lệnh làm thay đổi gì, không tạo issue, \
merge request, branch hay commit. Khi maintainer chốt, hệ thống sẽ tự tạo issue.
- Trả lời bằng tiếng Việt, văn xuôi, câu ngắn, tối đa khoảng 150 chữ. Không cần \
khối "Bản đơn giản, dễ hiểu".
- Đọc code khi cần, để câu trả lời đúng với hiện trạng của app. Không nêu tên \
file hay hàm, trừ khi được hỏi.
- Nếu còn điểm mơ hồ làm thay đổi cách làm thì hỏi lại. Mỗi lượt hỏi tối đa hai \
câu, mỗi câu kèm lựa chọn bạn đề xuất.
- Khi yêu cầu đã rõ, tóm tắt trong vài câu những gì sẽ được đưa vào issue, rồi \
nhắc maintainer bấm nút "Chốt, viết issue".

Tin nhắn của maintainer:
"""

NEXT_TURN = "Tin nhắn tiếp theo của maintainer (vẫn theo luật cũ: chỉ đọc, tiếng Việt, ngắn):\n"

DRAFT_TURN = """\
Maintainer đã chốt. Dựa trên toàn bộ cuộc trò chuyện, viết issue cuối cùng. \
Vẫn chỉ đọc, không tạo gì trên GitLab.

In ra đúng định dạng dưới đây và không thêm gì khác. Bỏ mục nào không có nội dung.

TITLE: <tiêu đề tiếng Việt, tối đa 80 ký tự>

## Bối cảnh
<vì sao cần thay đổi này>

## Mong muốn
<người dùng sẽ thấy gì, làm được gì>

## Ngoài phạm vi
<những gì đã thống nhất là không làm>

## Ghi chú
<quyết định và ràng buộc đã thống nhất trong cuộc trò chuyện>
"""

ISSUE_FOOTER = "\n\n---\n_Issue này được viết từ một cuộc trao đổi trên Slack._"

UNREAD = "Các tin nhắn trước đó trong thread mà bạn chưa đọc, cũ nhất trước:\n"

THINKING = "⏳ Đang đọc code và suy nghĩ…"
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
            "Bot này chỉ nhận yêu cầu từ maintainer của dự án.",
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
                "Tôi đang trả lời tin trước. Tin này tôi sẽ đọc cùng với tin kế tiếp của bạn.",
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
                "⚠️ Duo không trả lời được lần này. Bạn nhắn lại giúp tôi.",
            )
            return None, placeholder
        finally:
            self.store.release_lock(f"thread_{key}")

    def on_message(self, task: dict) -> None:
        text = task.get("text", "").strip()
        if not text:
            return
        if text.lower().rstrip(".!") in ("chốt", "chot"):
            return self.on_draft(task)

        def goal(thread: dict) -> str:
            rules = NEXT_TURN if thread.get("session_id") else FIRST_TURN
            return rules + self._unread(task, thread) + text

        reply, placeholder = self._ask_duo(task, goal, THINKING)
        if reply:
            self.slack.update(
                task["channel"],
                placeholder,
                reply.text,
                [button("Chốt, viết issue", "draft", "primary")],
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
        return UNREAD + "\n".join(f"- {text}" for text in unread) + "\n\nTin nhắn mới nhất:\n"

    def on_draft(self, task: dict) -> None:
        key = self._key(task)
        channel, thread_ts = task["channel"], task["thread_ts"]
        if not (self.store.get("threads", key) or {}).get("session_id"):
            self.slack.post(channel, thread_ts, "Chưa có gì để chốt. Bạn kể tôi nghe bạn muốn gì trước đã.")
            return
        reply, placeholder = self._ask_duo(task, lambda thread: DRAFT_TURN, "⏳ Đang viết bản nháp issue…")
        if not reply:
            return
        title, description = parse_draft(reply.text)
        self.store.save("threads", key, {"draft": {"title": title, "description": description}})
        self.slack.update(
            channel,
            placeholder,
            f"**Bản nháp issue**\n\n**{title}**\n\n{description}",
            [button("Tạo issue này", "create", "primary"), button("Bàn tiếp", "continue")],
        )

    def on_continue(self, task: dict) -> None:
        draft = (self.store.get("threads", self._key(task)) or {}).get("draft")
        if draft and task.get("message_ts"):
            self.slack.update(
                task["channel"],
                task["message_ts"],
                f"**Bản nháp issue (chưa tạo)**\n\n**{draft['title']}**\n\n{draft['description']}",
            )
        self.slack.post(task["channel"], task["thread_ts"], "Được. Bạn muốn đổi gì, nhắn tiếp ở đây.")

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
                channel, thread_ts, "Không tìm thấy bản nháp. Bấm “Chốt, viết issue” lại giúp tôi."
            )
            return
        try:
            issue = self.gitlab.create_issue(draft["title"], draft["description"] + ISSUE_FOOTER)
        except Exception:
            self.store.release_lock(guard)
            raise
        iid = issue["iid"]
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
        self.store.save("threads", key, {"draft": None, "issue_iid": iid})
        if task.get("message_ts"):
            self.slack.update(
                channel,
                task["message_ts"],
                f"**Issue đã tạo**\n\n**{draft['title']}**\n\n{draft['description']}",
            )
        self.slack.post(
            channel,
            thread_ts,
            f"✅ Đã tạo [issue #{iid}]({issue['web_url']}) và giao cho agent. Tiến độ sẽ hiện ở thread này.",
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
                    say(f"💬 **{author}** viết trên issue #{iid}:\n\n{note['body']}")
                state["last_note_id"] = note["id"]

            deployed = False
            merged = False
            for related in self.gitlab.related_merge_requests(iid):
                mr = self.gitlab.merge_request(related["iid"])
                ref = f"[!{mr['iid']}]({mr['web_url']})"
                once(f"mr{mr['iid']}:opened", f"🔀 Merge request {ref} đã mở: {mr['title']}")
                if mr["state"] == "merged":
                    merged = True
                    once(f"mr{mr['iid']}:merged", f"✅ {ref} đã merge vào `{mr['target_branch']}`.")
                    deployed = self._report_deploy(mr, once) or deployed
                elif mr["state"] == "closed":
                    once(f"mr{mr['iid']}:closed", f"🚫 {ref} đã bị đóng mà không merge.")
                else:
                    self._report_pipeline(mr, ref, once)

            closed = self.gitlab.issue(iid)["state"] == "closed"
            expired = time.time() - track.get("created_at", 0) > self.settings.track_hours * 3600
            if closed and (deployed or not merged):
                say(f"🏁 Issue #{iid} đã đóng. Tôi dừng theo dõi ở đây.")
                state["active"] = False
            elif expired:
                say(f"⏹ Đã {self.settings.track_hours} giờ, tôi dừng theo dõi issue #{iid}.")
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
            once(f"pipe{pipeline['id']}:running", f"⏳ {link} của {ref} đang chạy.")
        elif status == "success":
            once(f"pipe{pipeline['id']}:success", f"✅ {link} của {ref} đã xanh.")
        elif status in ("failed", "canceled"):
            once(f"pipe{pipeline['id']}:{status}", f"❌ {link} của {ref} bị {status}.")

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
                f"🚀 Staging đã chạy bản mới: {self.settings.staging_url}\n"
                f"Muốn đưa lên production thì bấm `deploy-production` ở {link}.",
            )
            return True
        if (staging and staging["status"] in ("failed", "canceled")) or pipeline["status"] in (
            "failed",
            "canceled",
        ):
            once(f"deploy{pipeline['id']}:failed", f"❌ Deploy staging không thành công. Xem {link}.")
            return True
        if pipeline["status"] == "success" and not staging:
            return True
        once(
            f"deploy{pipeline['id']}:running",
            f"⏳ {link} trên `{mr['target_branch']}` đang build và deploy staging.",
        )
        return False
