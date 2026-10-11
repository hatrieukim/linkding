"""Background work.

Slack wants an answer within three seconds, and a Duo turn takes longer. The
web endpoints therefore only queue a task. Cloud Tasks then calls this service
back on /tasks/run, and that request may take minutes.
"""

import json
import logging
import threading

log = logging.getLogger(__name__)


class Tasks:
    def __init__(self, settings, run):
        self._settings = settings
        self._run = run
        self._client = None

    def enqueue(self, task: dict) -> None:
        if self._settings.local:
            threading.Thread(target=self._run, args=(task,), daemon=True).start()
            return
        if self._client is None:
            from google.cloud import tasks_v2

            self._client = tasks_v2.CloudTasksClient()
        self._client.create_task(
            parent=self._settings.tasks_queue,
            task={
                "http_request": {
                    "http_method": "POST",
                    "url": f"{self._settings.service_url}/tasks/run",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(task).encode(),
                    "oidc_token": {
                        "service_account_email": self._settings.invoker_service_account,
                        "audience": self._settings.service_url,
                    },
                },
                "dispatch_deadline": {"seconds": 600},
            },
        )


def is_internal_call(settings, authorization: str) -> bool:
    """True if the request carries a Google-signed token of the invoker identity.

    The service is public because Slack must reach it, so the endpoints meant
    for Cloud Tasks and Cloud Scheduler check the caller themselves.
    """
    if settings.local:
        return True
    if not authorization.startswith("Bearer "):
        return False
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(
            authorization[len("Bearer ") :], google_requests.Request(), audience=settings.service_url
        )
    except ValueError as error:
        log.warning("rejected internal call: %s", error)
        return False
    return bool(claims.get("email_verified")) and claims.get("email") == settings.invoker_service_account
