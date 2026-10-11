# Slack bot

Lets the maintainer plan a change in Slack and watch it reach staging without
opening GitLab.

1. **Talk.** Write to the bot in Slack. It passes each message to GitLab Duo,
   which reads the code of this project and answers in the same thread.
2. **Settle.** Press **Chốt, viết issue**. Duo writes the issue from the
   conversation. Press **Tạo issue này** and the bot creates it on GitLab,
   assigned to the Duo Developer agent.
3. **Watch.** The agent works as described in [`AGENTS.md`](../AGENTS.md). The
   bot repeats what happens in the Slack thread: the plan, the merge request,
   its pipeline, the merge, the deploy to staging and the final report.

The bot itself decides nothing. Duo does the thinking, the Developer flow does
the work, the pipeline does the deploy. The bot connects them to Slack.

## How it works

```text
Slack ──events──▶ /slack/events ──▶ Cloud Tasks ──▶ /tasks/run ──▶ duo run (Duo CLI, headless)
      ◀─────────────── answer posted in the thread ◀──────────────┘
Slack ──button──▶ /slack/interactions ──▶ Cloud Tasks ──▶ /tasks/run ──▶ GitLab API: create issue
Cloud Scheduler ──every minute──▶ /tick ──▶ GitLab API: what is new? ──▶ Slack thread
```

- **Duo** is reached through the [GitLab Duo CLI](https://docs.gitlab.com/user/gitlab_duo_cli/)
  in headless mode. One Slack thread is one Duo session, so Duo remembers the
  conversation. Duo reads a shallow checkout of the default branch that the
  bot keeps inside its container.
- **Cloud Tasks** exists because Slack wants an answer within three seconds
  and a Duo turn takes ten to thirty.
- **Polling** exists because registering a GitLab webhook needs the Maintainer
  role, and this project is run with the Developer role.
- **Firestore** holds the Duo session of each thread, the issue draft and what
  has already been reported for each issue.

| File | Contents |
|---|---|
| `bot/main.py` | Web endpoints |
| `bot/core.py` | Conversation, issue creation and progress reporting |
| `bot/duo.py` | Runs the Duo CLI |
| `bot/gitlab.py` | GitLab REST calls |
| `bot/slack.py` | Posting to Slack and Markdown conversion |
| `bot/store.py` | Firestore, and an in-memory store for tests |
| `bot/tasks.py` | Cloud Tasks, and the check on internal callers |
| `slack-manifest.yaml` | Definition of the Slack app |
| `../infra/bot.tf` | Cloud Run service, queue, schedule, database and permissions |

## Set up

The order matters: the Cloud Run service does not start without its secrets.

1. **Slack app.** At <https://api.slack.com/apps> choose **Create New App** >
   **From a manifest**, pick the workspace and paste
   [`slack-manifest.yaml`](slack-manifest.yaml). Then **Install to Workspace**.
   Slack warns that the request URL is not verified yet. That is expected.
2. **GitLab token.** Create a personal access token with the `api` scope. The
   bot uses it to run Duo, to create issues and to read their progress.
3. **Secrets.** Store the three values in Secret Manager. Each command reads
   the value from the clipboard, so it never appears on screen:

   ```shell
   pbpaste | gcloud secrets create linkding-bot-slack-token --data-file=-            # Bot User OAuth Token, xoxb-…
   pbpaste | gcloud secrets create linkding-bot-slack-signing-secret --data-file=-   # Basic Information > Signing Secret
   pbpaste | gcloud secrets create linkding-bot-gitlab-token --data-file=-           # glpat-…
   ```

4. **Infrastructure.** Apply `infra/`, see [`infra/README.md`](../infra/README.md).
5. **Deploy.** Merge a change under `slackbot/` into the default branch. The
   `deploy-bot` job puts the image on Cloud Run.
6. **Verify the URL.** In the Slack app settings open **Event Subscriptions**
   and select **Retry** next to the request URL.
7. Write to the bot in a direct message, or mention it in a channel it has
   been added to. Its answer opens a thread. Inside that thread it reads every
   message, so no further mention is needed.

When `slack-manifest.yaml` changes, paste it again under **App Manifest** in
the Slack app settings and reinstall the app when Slack asks for it. New
permissions only take effect after the reinstall.

## Who may use it

The first person who writes to the bot becomes its owner, and nobody else is
served. To name the users instead, set `bot_slack_allowed_users` in
`infra/terraform.tfvars` to a list of Slack member IDs.

This matters because the bot acts on GitLab with the personal access token of
its maintainer. Requests are accepted only if Slack signed them, and the
internal endpoints only if Google signed them for the bot's own identity.

Duo runs with every tool approved, as headless mode requires. It is told to
read only, and its checkout is a throwaway copy that is reset before each turn.

## Develop

```shell
cd slackbot
uv venv && uv pip install -r requirements.txt pytest ruff
.venv/bin/pytest
.venv/bin/ruff check bot tests && .venv/bin/ruff format --check bot tests
```

The tests replace Slack, Duo and GitLab with fakes, so they need no account.
`BOT_LOCAL=1` makes the service keep state in memory and run tasks in threads.

`requirements.txt` is generated from `requirements.in`:

```shell
uv pip compile --python-version 3.13 requirements.in -o requirements.txt
```
