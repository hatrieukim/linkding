"""Settings, read once from environment variables."""

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    # Local mode keeps state in memory, runs tasks in threads and skips the
    # check that internal endpoints are called by Google. Never set in Cloud Run.
    local: bool = field(default_factory=lambda: _env("BOT_LOCAL") == "1")

    gitlab_url: str = field(default_factory=lambda: _env("GITLAB_URL", "https://gitlab.com"))
    gitlab_token: str = field(default_factory=lambda: _env("GITLAB_TOKEN"))
    gitlab_project_id: str = field(default_factory=lambda: _env("GITLAB_PROJECT_ID"))
    # The account that implements issues. Assigning an issue to it starts the
    # Developer flow.
    agent_username: str = field(default_factory=lambda: _env("GITLAB_AGENT_USERNAME"))

    slack_bot_token: str = field(default_factory=lambda: _env("SLACK_BOT_TOKEN"))
    slack_signing_secret: str = field(default_factory=lambda: _env("SLACK_SIGNING_SECRET"))
    # Comma separated Slack member IDs. Empty means: the first person who
    # writes to the bot becomes its owner and nobody else is served.
    allowed_users: tuple = field(
        default_factory=lambda: tuple(u for u in _env("SLACK_ALLOWED_USERS").split(",") if u)
    )

    # Public URL of this service, queue for background work and the identity
    # Cloud Tasks and Cloud Scheduler use when they call back.
    service_url: str = field(default_factory=lambda: _env("SERVICE_URL").rstrip("/"))
    tasks_queue: str = field(default_factory=lambda: _env("TASKS_QUEUE"))
    invoker_service_account: str = field(default_factory=lambda: _env("INVOKER_SERVICE_ACCOUNT"))

    duo_bin: str = field(default_factory=lambda: _env("DUO_BIN", "duo"))
    duo_model: str = field(default_factory=lambda: _env("DUO_MODEL"))
    duo_timeout: int = field(default_factory=lambda: int(_env("DUO_TIMEOUT", "280")))
    workspace_dir: str = field(default_factory=lambda: _env("WORKSPACE_DIR", "/tmp/workspace"))

    staging_url: str = field(default_factory=lambda: _env("STAGING_URL"))
    staging_job: str = field(default_factory=lambda: _env("STAGING_JOB", "deploy-staging"))
    # Stop following an issue after this many hours, whatever its state.
    track_hours: int = field(default_factory=lambda: int(_env("TRACK_HOURS", "6")))
