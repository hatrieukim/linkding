"""The few GitLab REST calls the bot needs."""

import requests


class SpamRejected(Exception):
    """GitLab's spam filter refused the content of a public issue."""


class GitLab:
    def __init__(self, settings):
        self._api = f"{settings.gitlab_url}/api/v4"
        self._project = f"{self._api}/projects/{settings.gitlab_project_id}"
        self._agent_username = settings.agent_username
        self._session = requests.Session()
        self._session.headers["PRIVATE-TOKEN"] = settings.gitlab_token
        self._project_info = None
        self._agent_id = None

    def _get(self, url: str, **params):
        response = self._session.get(url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def project(self) -> dict:
        if self._project_info is None:
            self._project_info = self._get(self._project)
        return self._project_info

    def agent_id(self) -> int:
        if self._agent_id is None:
            users = self._get(f"{self._api}/users", username=self._agent_username)
            if not users:
                raise RuntimeError(f"GitLab user {self._agent_username} not found")
            self._agent_id = users[0]["id"]
        return self._agent_id

    def create_issue(self, title: str, description: str, confidential: bool = False) -> dict:
        """Create an issue assigned to the agent, which starts the Developer flow."""
        response = self._session.post(
            f"{self._project}/issues",
            json={
                "title": title,
                "description": description,
                "assignee_ids": [self.agent_id()],
                "confidential": confidential,
            },
            timeout=20,
        )
        if response.status_code == 400 and "spam" in response.text.lower():
            raise SpamRejected()
        if not response.ok:
            # The body says why, which the status alone does not.
            raise RuntimeError(f"GitLab answered {response.status_code}: {response.text[:500]}")
        return response.json()

    def issue(self, iid: int) -> dict:
        return self._get(f"{self._project}/issues/{iid}")

    def notes(self, iid: int) -> list:
        return self._get(
            f"{self._project}/issues/{iid}/notes", sort="asc", order_by="created_at", per_page=100
        )

    def related_merge_requests(self, iid: int) -> list:
        return self._get(f"{self._project}/issues/{iid}/related_merge_requests")

    def merge_request(self, iid: int) -> dict:
        return self._get(f"{self._project}/merge_requests/{iid}")

    def pipelines(self, sha: str, ref: str) -> list:
        return self._get(f"{self._project}/pipelines", sha=sha, ref=ref)

    def jobs(self, pipeline_id: int) -> list:
        return self._get(f"{self._project}/pipelines/{pipeline_id}/jobs", per_page=100)
