"""Stand-ins for Slack, Duo and GitLab that record what the bot did."""

from bot.duo import DuoError, DuoReply


class FakeSlack:
    def __init__(self):
        self.messages = []  # every message, in the order it was posted
        self.thread = []  # what people wrote in the thread: {"ts", "text"}

    def post(self, channel, thread_ts, markdown, buttons=None):
        ts = f"m{len(self.messages) + 1}"
        self.messages.append({"ts": ts, "thread_ts": thread_ts, "text": markdown, "buttons": buttons})
        return ts

    def update(self, channel, ts, markdown, buttons=None):
        message = next(m for m in self.messages if m["ts"] == ts)
        message.update(text=markdown, buttons=buttons)

    def thread_messages(self, channel, thread_ts):
        return self.thread

    def texts(self):
        return [m["text"] for m in self.messages]

    def actions(self, index=-1):
        return [b["action_id"] for b in self.messages[index]["buttons"] or []]


class FakeDuo:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def run(self, goal, session_id=None):
        self.calls.append((goal, session_id))
        reply = self.replies.pop(0)
        if reply is None:
            raise DuoError("boom")
        return DuoReply(session_id="s1", text=reply)


class FakeGitLab:
    def __init__(self):
        self.created = []
        self.issue_state = "opened"
        self.issue_notes = []
        self.merge_requests = {}
        self.pipeline_list = []
        self.job_list = []

    def project(self):
        return {"web_url": "https://gitlab.example/group/app"}

    def create_issue(self, title, description):
        self.created.append({"title": title, "description": description})
        return {"iid": 7, "web_url": "https://gitlab.example/group/app/-/issues/7"}

    def issue(self, iid):
        return {"state": self.issue_state}

    def notes(self, iid):
        return self.issue_notes

    def related_merge_requests(self, iid):
        return [{"iid": iid} for iid in self.merge_requests]

    def merge_request(self, iid):
        return self.merge_requests[iid]

    def pipelines(self, sha, ref):
        return self.pipeline_list

    def jobs(self, pipeline_id):
        return self.job_list
