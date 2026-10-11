import pytest

from bot.config import Settings
from bot.core import Bot, parse_draft
from bot.slack import link_references, normalize, split, to_mrkdwn
from bot.store import MemoryStore

from .fakes import FakeDuo, FakeGitLab, FakeSlack

TASK = {"channel": "D1", "thread_ts": "100.1", "user": "U1"}


@pytest.fixture
def make_bot():
    def build(replies=()):
        settings = Settings()
        settings.staging_url = "https://staging.example"
        return Bot(settings, MemoryStore(), FakeSlack(), FakeDuo(replies), FakeGitLab())

    return build


# ------------------------------------------------------------ formatting


def test_normalize_drops_comments_and_draws_checkboxes():
    text = normalize("<!-- hint -->\n- [x] done\n- [ ] open\n\n\n\nend")
    assert text == "- ✅ done\n- ⬜ open\n\nend"


def test_to_mrkdwn_converts_the_common_markdown():
    text = to_mrkdwn("## Title\n**bold** and [link](https://x.test/a)\n- item\na < b")
    assert text == "*Title*\n*bold* and <https://x.test/a|link>\n• item\na &lt; b"


def test_split_keeps_every_part_under_the_limit():
    parts = split("\n\n".join(["x" * 40] * 10), 100)
    assert all(len(part) <= 100 for part in parts)
    assert "".join(parts).count("x") == 400


def test_link_references_links_issues_and_merge_requests_only():
    text = link_references("closed with !9, see #7 and ## Heading", "https://g.test/p")
    assert "[!9](https://g.test/p/-/merge_requests/9)" in text
    assert "[#7](https://g.test/p/-/issues/7)" in text
    assert "## Heading" in text


def test_parse_draft_reads_title_and_description():
    title, description = parse_draft("TITLE: Thêm nút gửi lại mã\n\n## Bối cảnh\nNgười dùng…")
    assert title == "Thêm nút gửi lại mã"
    assert description.startswith("## Bối cảnh")


def test_parse_draft_without_marker_uses_the_first_line():
    title, description = parse_draft("# Thêm nút\nMô tả")
    assert (title, description) == ("Thêm nút", "Mô tả")


# ---------------------------------------------------------- conversation


def test_first_message_gets_the_rules_and_later_ones_reuse_the_session(make_bot):
    bot = make_bot(["Bạn muốn nút ở đâu?", "Rõ rồi."])
    bot.run({**TASK, "kind": "message", "text": "thêm nút gửi lại mã"})
    bot.run({**TASK, "kind": "message", "text": "ở trang nhập mã"})

    (first_goal, first_session), (second_goal, second_session) = bot.duo.calls
    assert "Chỉ đọc" in first_goal and first_goal.endswith("thêm nút gửi lại mã")
    assert first_session is None
    assert second_session == "s1" and second_goal.endswith("ở trang nhập mã")
    # Each answer replaces its own "thinking" message and offers to settle.
    assert bot.slack.texts() == ["Bạn muốn nút ở đâu?", "Rõ rồi."]
    assert bot.slack.actions() == ["draft"]


def test_duo_is_given_the_thread_messages_it_was_not_sent(make_bot):
    bot = make_bot(["Chào.", "Đã hiểu."])
    bot.slack.thread = [{"ts": "100.1", "text": "<@UBOT> hi"}]
    bot.run({**TASK, "kind": "message", "ts": "100.1", "text": "hi"})

    # Written without mentioning the bot, so Slack never delivered it.
    bot.slack.thread += [
        {"ts": "100.2", "text": "trên trang login thêm link đăng ký"},
        {"ts": "100.3", "text": "<@UBOT> review đi"},
    ]
    bot.run({**TASK, "kind": "message", "ts": "100.3", "text": "review đi"})

    first_goal, second_goal = (goal for goal, _ in bot.duo.calls)
    assert "chưa đọc" not in first_goal
    assert "- trên trang login thêm link đăng ký" in second_goal
    assert second_goal.endswith("Tin nhắn mới nhất:\nreview đi")
    assert "- hi" not in second_goal, "already seen in the first turn"


def test_being_called_into_a_running_thread_brings_the_earlier_messages(make_bot):
    bot = make_bot(["Đã đọc."])
    bot.slack.thread = [
        {"ts": "100.1", "text": "nút lưu bị lệch trên mobile"},
        {"ts": "100.4", "text": "<@UBOT> tạo issue giúp"},
    ]
    bot.run({**TASK, "kind": "message", "ts": "100.4", "text": "tạo issue giúp"})
    assert "- nút lưu bị lệch trên mobile" in bot.duo.calls[0][0]


def test_other_people_in_a_thread_are_ignored_quietly(make_bot):
    bot = make_bot(["Chào."])
    bot.run({**TASK, "kind": "message", "text": "xin chào"})
    bot.run({**TASK, "kind": "message", "text": "tôi nghĩ khác", "user": "U2", "quiet": True})
    assert len(bot.duo.calls) == 1 and len(bot.slack.messages) == 1


def test_only_the_owner_is_served(make_bot):
    bot = make_bot(["Chào."])
    bot.run({**TASK, "kind": "message", "text": "xin chào"})
    bot.run({**TASK, "kind": "message", "text": "xin chào", "user": "U2"})

    assert len(bot.duo.calls) == 1
    assert "chỉ nhận yêu cầu từ maintainer" in bot.slack.texts()[-1]


def test_a_failed_turn_is_reported_and_the_thread_stays_usable(make_bot):
    bot = make_bot([None, "Lần này được."])
    bot.run({**TASK, "kind": "message", "text": "a"})
    bot.run({**TASK, "kind": "message", "text": "b"})

    assert "không trả lời được" in bot.slack.texts()[0]
    assert bot.slack.texts()[1] == "Lần này được."


def test_draft_then_create_makes_one_issue_and_starts_tracking(make_bot):
    bot = make_bot(["Rõ rồi.", "TITLE: Thêm nút gửi lại mã\n\n## Mong muốn\nCó nút."])
    bot.run({**TASK, "kind": "message", "text": "thêm nút"})
    bot.run({**TASK, "kind": "draft"})

    draft = bot.slack.messages[-1]
    assert "Bản nháp issue" in draft["text"] and bot.slack.actions() == ["create", "continue"]
    assert bot.gitlab.created == []

    click = {**TASK, "kind": "create", "message_ts": draft["ts"]}
    bot.run(click)
    bot.run(click)  # a double click

    assert len(bot.gitlab.created) == 1
    assert bot.gitlab.created[0]["title"] == "Thêm nút gửi lại mã"
    assert "Slack" in bot.gitlab.created[0]["description"]
    assert draft["buttons"] is None
    assert "issue #7" in bot.slack.texts()[-1]
    assert [track["iid"] for track in bot.store.active_tracks()] == [7]


def test_a_draft_refused_as_spam_can_be_created_as_a_private_issue(make_bot):
    bot = make_bot(["Rõ rồi.", "TITLE: Xem trang bằng iframe\n\n## Mong muốn\nCó lưới."])
    bot.gitlab.spam_filter = True
    bot.run({**TASK, "kind": "message", "text": "thêm kiểu xem lưới"})
    bot.run({**TASK, "kind": "draft"})
    draft = bot.slack.messages[-1]

    bot.run({**TASK, "kind": "create", "message_ts": draft["ts"]})
    assert bot.gitlab.created == [] and bot.store.active_tracks() == []
    assert "GitLab từ chối" in draft["text"]
    assert [b["action_id"] for b in draft["buttons"]] == ["create_private", "continue"]
    assert "bộ lọc spam" in bot.slack.texts()[-1].lower()

    bot.run({**TASK, "kind": "create_private", "message_ts": draft["ts"]})
    assert [issue["confidential"] for issue in bot.gitlab.created] == [True]
    assert "issue riêng tư #7" in bot.slack.texts()[-1]
    assert [track["iid"] for track in bot.store.active_tracks()] == [7]


def test_typing_tao_rieng_tu_creates_the_private_issue_without_a_public_attempt(make_bot):
    bot = make_bot(["Rõ rồi.", "TITLE: A\n\nB"])
    bot.gitlab.spam_filter = True
    bot.run({**TASK, "kind": "message", "text": "thêm kiểu xem lưới"})
    bot.run({**TASK, "kind": "draft"})
    bot.run({**TASK, "kind": "message", "text": "Tạo riêng tư"})
    assert [issue["confidential"] for issue in bot.gitlab.created] == [True]
    assert "GitLab từ chối" not in " ".join(bot.slack.texts())


def test_an_issue_created_by_hand_can_be_followed_from_a_thread(make_bot):
    bot = make_bot()
    bot.run({**TASK, "kind": "message", "text": "theo dõi #12"})
    assert bot.duo.calls == []
    assert [track["iid"] for track in bot.store.active_tracks()] == [12]
    assert "issue #12" in bot.slack.texts()[-1]


def test_typing_chot_asks_for_the_draft(make_bot):
    bot = make_bot(["Rõ rồi.", "TITLE: A\n\nB"])
    bot.run({**TASK, "kind": "message", "text": "thêm nút"})
    bot.run({**TASK, "kind": "message", "text": "Chốt"})
    assert bot.slack.actions() == ["create", "continue"]


def test_draft_without_a_conversation_is_refused(make_bot):
    bot = make_bot()
    bot.run({**TASK, "kind": "draft"})
    assert "Chưa có gì để chốt" in bot.slack.texts()[-1]


# -------------------------------------------------------------- progress


def follow(bot):
    bot.store.save(
        "tracks",
        "7",
        {
            "iid": 7,
            "channel": "D1",
            "thread_ts": "100.1",
            "active": True,
            "created_at": 1e12,
            "last_note_id": 0,
            "seen": [],
        },
    )


def note(note_id, body, system=False):
    return {"id": note_id, "body": body, "system": system, "author": {"name": "Duo Developer"}}


def test_progress_is_reported_once_from_plan_to_staging(make_bot):
    bot = make_bot()
    follow(bot)
    gitlab, slack = bot.gitlab, bot.slack

    gitlab.issue_notes = [note(1, "## Phân tích issue #7\n\nKế hoạch…")]
    bot.tick()
    bot.tick()
    assert len(slack.messages) == 1 and "Phân tích issue" in slack.texts()[0]

    gitlab.merge_requests[9] = {
        "iid": 9,
        "title": "Add button",
        "state": "opened",
        "target_branch": "master",
        "web_url": "https://gitlab.example/group/app/-/merge_requests/9",
        "head_pipeline": {"id": 50, "status": "running", "web_url": "https://gitlab.example/p/50"},
    }
    bot.tick()
    bot.tick()
    assert ["đã mở" in t or "đang chạy" in t for t in slack.texts()[1:]] == [True, True]

    gitlab.merge_requests[9].update(state="merged", merge_commit_sha="abc")
    gitlab.issue_state = "closed"
    gitlab.issue_notes.append(note(2, "closed with merge request !9", system=True))
    gitlab.pipeline_list = [{"id": 51, "status": "running", "web_url": "https://gitlab.example/p/51"}]
    gitlab.job_list = [{"name": "deploy-staging", "status": "running"}]
    bot.tick()
    assert bot.store.active_tracks(), "still waiting for staging"
    assert "[!9](https://gitlab.example/group/app/-/merge_requests/9)" in slack.texts()[3]

    gitlab.job_list = [{"name": "deploy-staging", "status": "success"}]
    bot.tick()
    bot.tick()
    tail = slack.texts()[-2:]
    assert "https://staging.example" in tail[0] and "dừng theo dõi" in tail[1]
    assert bot.store.active_tracks() == []
    assert len(slack.messages) == len(set(slack.texts())), "nothing was said twice"


def test_an_issue_closed_without_a_merge_stops_tracking(make_bot):
    bot = make_bot()
    follow(bot)
    bot.gitlab.issue_state = "closed"
    bot.tick()
    assert bot.store.active_tracks() == []


def test_tracking_stops_after_the_time_limit(make_bot):
    bot = make_bot()
    follow(bot)
    bot.store.save("tracks", "7", {"created_at": 0})
    bot.tick()
    assert "dừng theo dõi" in bot.slack.texts()[-1] and bot.store.active_tracks() == []
