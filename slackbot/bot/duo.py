"""Talks to GitLab Duo through the Duo CLI in headless mode.

Each turn is one `duo run`. The CLI keeps the conversation on GitLab as a
session, so passing the session ID back continues where the last turn ended.

Duo answers questions about the code by reading a checkout of the project.
Headless mode approves every tool the agent wants to use, so the checkout is
a throwaway copy that is reset before every turn.
"""

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

REFRESH_SECONDS = 300


class DuoError(Exception):
    pass


@dataclass
class DuoReply:
    session_id: str
    text: str


class Duo:
    def __init__(self, settings, clone_url: str, default_branch: str):
        self._settings = settings
        self._clone_url = clone_url
        self._branch = default_branch
        self._refreshed_at = 0.0
        self._guard = threading.Lock()

    def _git(self, *args: str, cwd: str | None = None) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=120)

    def _prepare_workspace(self) -> str:
        path = self._settings.workspace_dir
        with self._guard:
            if not os.path.isdir(os.path.join(path, ".git")):
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                self._git("clone", "--depth", "1", "--branch", self._branch, self._clone_url, path)
                self._refreshed_at = time.time()
            else:
                # Undo anything a previous turn may have changed, and pick up
                # new commits every few minutes.
                target = "HEAD"
                if time.time() - self._refreshed_at > REFRESH_SECONDS:
                    self._git("fetch", "--depth", "1", "origin", self._branch, cwd=path)
                    self._refreshed_at = time.time()
                    target = "FETCH_HEAD"
                self._git("reset", "--hard", target, cwd=path)
                self._git("clean", "-fd", cwd=path)
        return path

    def run(self, goal: str, session_id: str | None = None) -> DuoReply:
        workspace = self._prepare_workspace()
        command = [self._settings.duo_bin, "run", "--output-format", "json", "--goal", goal]
        if self._settings.duo_model:
            command += ["--model", self._settings.duo_model]
        if session_id:
            command += ["--existing-session-id", str(session_id)]
        try:
            done = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self._settings.duo_timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise DuoError(f"Duo did not answer within {self._settings.duo_timeout} seconds") from error

        try:
            result = json.loads(done.stdout)
        except ValueError:
            result = {}
        text = (result.get("response") or "").strip()
        if done.returncode != 0 or not text:
            # The CLI log can be long and is only useful to the operator.
            log.error("duo run failed with exit code %s: %s", done.returncode, done.stderr[-2000:])
            raise DuoError(f"Duo CLI exited with code {done.returncode}")
        return DuoReply(session_id=str(result.get("sessionId") or session_id or ""), text=text)
