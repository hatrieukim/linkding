# AGENTS.md

Instructions for AI agents working in this repository. The first half describes
the project. The second half is the workflow an agent follows when it is given
an issue.

## Project

linkding is a self-hosted bookmark manager built with Django. This repository
is a fork that adds a GitLab CI/CD pipeline, Google Cloud infrastructure and
agent-driven delivery around the upstream application.

| Path | Contents |
|---|---|
| `bookmarks/` | The Django application: `models.py`, `views/`, `services/`, `api/`, `templates/`, `settings/` |
| `bookmarks/tests/` | Unit and integration tests, one `test_*.py` file per feature. Shared fixtures are in `helpers.py` (`BookmarkFactoryMixin`, `LinkdingApiTestCase`) |
| `bookmarks/tests_e2e/` | Browser tests. They are not run in CI. Do not rely on them |
| `bookmarks/frontend/`, `bookmarks/styles/` | JavaScript and CSS sources, bundled with esbuild |
| `bookmarks/migrations/` | Database migrations |
| `docs/` | User documentation. Options are documented in `docs/src/content/docs/options.md` |
| `docker/`, `bootstrap.sh`, `uwsgi.ini` | Container image and startup |
| `infra/` | Google Cloud infrastructure as OpenTofu code. Applied by a maintainer, never by a pipeline or an agent |
| `.gitlab-ci.yml` | The pipeline |

Python 3.13. Dependencies are managed with uv in `pyproject.toml` and `uv.lock`.

The app runs on SQLite by default and on PostgreSQL in staging and production.
Anything that touches the database must work on both.

## Commands

The environment is prepared before you start: dependencies are installed in
`.venv` and outbound network access is restricted. Always pass `--no-sync` so
that uv does not try to download anything.

| Purpose | Command |
|---|---|
| Lint | `uv run --no-sync ruff check bookmarks` |
| Format check | `uv run --no-sync ruff format --check bookmarks` |
| Apply formatting | `uv run --no-sync ruff format bookmarks` |
| One test file | `uv run --no-sync pytest bookmarks/tests/test_<name>.py` |
| One test | `uv run --no-sync pytest bookmarks/tests/test_<name>.py -k <test_name>` |
| Whole suite, about 5 minutes | `uv run --no-sync pytest -n auto` |
| New migration after a model change | `uv run --no-sync python manage.py makemigrations` |

Run the test files that cover your change, not the whole suite. The pipeline
runs everything.

If a command fails because the environment is missing something, say exactly
what failed. Do not report a check as passed unless you ran it and saw it pass.

## Conventions

- Follow the patterns already in the file you are changing. This is upstream
  code: keep changes small and do not refactor or reformat code you were not
  asked to change.
- Every behaviour change needs a test in `bookmarks/tests/`.
- Outbound HTTP requests go through `bookmarks/services/http_client.py`, never
  `requests` directly. The linter enforces this.
- A new configuration option is an environment variable named `LD_...`, read in
  `bookmarks/settings/base.py` or `prod.py`, listed in `.env.sample` and
  documented in `docs/src/content/docs/options.md`.
- Do not change `infra/`, `.gitlab-ci.yml`, `AGENTS.md` or anything under
  `.gitlab/` or `.agents/` unless the issue explicitly asks for it.
- Never commit secrets, and never print the value of a token or password.

## Delivery workflow

Follow these steps, in order, whenever you are assigned an issue or asked to
implement one. The maintainer does not review each step. They read the issue
afterwards, so the issue must tell the whole story.

### 1. Understand

Read the issue and all of its comments. Read the code the change will touch and
the tests that cover it. Work out what the user actually needs, which may be
less or more than the literal text.

If the issue cannot be implemented as written, because it is ambiguous in a way
that changes the design, contradicts existing behaviour, or asks for something
unsafe, post one comment that explains the problem and asks a specific
question. Then stop. Do not guess.

### 2. Plan, on the issue

Before you change any file, post one comment on the issue with exactly these
three sections:

- `## Analysis`: what is being asked, where the relevant code is, and anything
  surprising you found.
- `## Implementation plan`: a short numbered list of the changes you will make,
  naming files.
- `## Acceptance criteria`: a checklist. Each item is a fact that someone can
  check without reading the code: an HTTP request and its response, something
  visible in the UI, a command and its output. Include at least one item that
  can be checked against the deployed application. Do not list process steps
  such as "merge request is opened".

### 3. Implement

Create a branch named `<issue number>-<short-slug>` from the default branch.
Make the change and its tests. Each acceptance criterion that can be automated
is covered by a test.

### 4. Verify

Run the lint and format checks and the test files that cover your change. If a
check fails, fix the code, not the check.

### 5. Open the merge request

Push the branch and open a merge request to the default branch. It is **ready,
not a draft**. The description contains:

- `Closes #<issue number>`
- a short summary of the change
- the acceptance criteria as a checklist, ticked where a test or check you ran
  proves the item
- the commands you ran and their real results

### 6. Enable auto-merge

The merge request merges by itself when its pipeline passes. You do not merge
it and you never push to the default branch.

1. Wait until the merge request has a pipeline: `glab mr view <iid> --output json`
   shows a `head_pipeline`.
2. Ask GitLab to merge when the pipeline succeeds, with a quick action on the
   head commit:
   `glab api --method POST "projects/:id/merge_requests/<iid>/notes" -f body="/merge" -f merge_request_diff_head_sha="$(git rev-parse HEAD)"`
3. Check that it took effect: `glab mr view <iid> --output json` shows
   `"merge_when_pipeline_succeeds": true`.
4. If it did not, use a push option instead:
   `git commit --allow-empty -m "Enable auto-merge"` and then
   `git push -o merge_request.auto_merge`. Check again.

`glab mr merge` does not work with your credentials. Do not try it.

### 7. See it through

Watch the pipeline until it finishes: `glab ci status --branch <branch>`.

If a job fails, read its log with `glab ci trace <job id>`, fix the cause and
push. After a push, check that auto-merge is still enabled and enable it again
if it is not. You may do this **twice**. If the pipeline is still failing after
the second fix, stop, and say so in the final comment.

### 8. Report, on the issue

Post one final comment on the issue:

- what changed, in two or three sentences
- the acceptance criteria checklist, with each item marked as verified by a
  test, verified by hand, or not verified
- the checks you ran and their real results
- the merge request link and its state: merged, waiting for its pipeline, or
  blocked, and why
- anything the maintainer needs to do or decide

After the merge, the pipeline on the default branch deploys the change to
staging at https://linkding-staging-248896301327.asia-southeast1.run.app.
Production is deployed separately.

## Large requests

If an issue clearly needs more than one merge request, say so in the plan
comment, describe the slices, and implement only the first one. The rules for
splitting work into child issues will be added here by the maintainer.
