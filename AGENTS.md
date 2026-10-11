# AGENTS.md

Instructions for AI agents working in this repository. The first half describes
the project. The second half is the workflow an agent follows when it is given
an issue.

## Language

Everything you write for a person to read is in **Vietnamese**: comments on
issues and merge requests, merge request descriptions, questions, reports.
This applies to every agent and subagent working in this repository. Issues
are written in Vietnamese too.

Git and code stay in English, because this is a fork of an English project:
branch names, commit messages, merge request titles, identifiers, code
comments and documentation under `docs/`.

Keep technical terms that have no natural Vietnamese form as they are, for
example merge request, pipeline, commit, endpoint.

### The simple version comes first

The maintainer reads the top of every comment and often nothing else. So every
plan, report and merge request description opens with a block titled
`**Bản đơn giản, dễ hiểu**`, followed by a horizontal rule `---`, followed by
the detailed part.

Rules for the simple version:

- Prose, not a list. Short sentences.
- Between 100 and 200 words.
- Technical terms are allowed when they are needed. Do not name files or
  functions.
- It answers three questions, in this order: what the maintainer wants, what
  you will do or did, and what they will see that is different once it is done.

The detailed part below the rule is written in your normal style, with
headings, lists, file names and code where they help.

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

Run the test files that cover your change, not the whole suite. Do not count
on the pipeline to catch what you did not test: its test job may be switched
off.

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
- Your file tools cannot edit `.env.sample`. If a change needs a new line
  there, say so under `Việc cần bạn làm` in the final report with the exact
  text to add.

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
unsafe, post one comment in Vietnamese that explains the problem and asks a
specific question. Then stop. Do not guess.

### 2. Plan, on the issue

Before you change any file, post one comment on the issue in exactly this
shape:

```markdown
## Phân tích issue #<number>

**Bản đơn giản, dễ hiểu**

<100 to 200 words of prose>

---

### Phân tích

### Kế hoạch thực hiện

### Tiêu chí nghiệm thu
```

- `Phân tích`: what is being asked, where the relevant code is, and anything
  surprising you found.
- `Kế hoạch thực hiện`: a short numbered list of the changes you will make,
  naming files.
- `Tiêu chí nghiệm thu`: a checklist. Each item is a fact that someone can
  check without reading the code: an HTTP request and its response, something
  visible in the UI, a command and its output. Include at least one item that
  can be checked against the deployed application. Do not list process steps
  such as "merge request is opened".

Then continue with the next step. Do not wait for approval.

### 3. Implement

Create a branch named `<issue number>-<short-slug>` from the default branch.
Make the change and its tests. Each acceptance criterion that can be automated
is covered by a test.

### 4. Verify

Run the lint and format checks and the test files that cover your change. If a
check fails, fix the code, not the check.

### 5. Open the merge request

Push the branch and open a merge request to the default branch. It is **ready,
not a draft**. The title is in English. The description is in this shape:

```markdown
Closes #<number>

**Bản đơn giản, dễ hiểu**

<100 to 200 words of prose>

---

### Thay đổi

### Tiêu chí nghiệm thu

### Kiểm tra đã chạy
```

- `Thay đổi`: what changed and why, by file.
- `Tiêu chí nghiệm thu`: the checklist from the plan, ticked where a test or
  check you ran proves the item.
- `Kiểm tra đã chạy`: the commands you ran and their real results.

### 6. Enable auto-merge

The merge request merges by itself when its pipeline passes. You do not merge
it and you never push to the default branch.

1. Wait until the merge request has a pipeline: `glab mr view <iid> --output json`
   shows a `head_pipeline`.
2. Push one more commit with a push option that asks GitLab to merge when the
   pipeline succeeds:
   `git commit --allow-empty -m "Enable auto-merge"` and then
   `git push -o merge_request.auto_merge`.
3. Check that it took effect: `glab mr view <iid> --output json` shows
   `"merge_when_pipeline_succeeds": true`.

This is the only method that works with your credentials. `glab mr merge` and
the `/merge` quick action are both rejected with a 403. Do not try them.

### 7. See it through

Watch the pipeline until it finishes: `glab ci status --branch <branch>`.

If a job fails, read its log with `glab ci trace <job id>`, fix the cause and
push. After a push, check that auto-merge is still enabled and enable it again
if it is not. You may do this **twice**. If the pipeline is still failing after
the second fix, stop, and say so in the final comment.

### 8. Report, on the issue

Post one final comment on the issue in this shape:

```markdown
## Kết quả issue #<number>

**Bản đơn giản, dễ hiểu**

<100 to 200 words of prose>

---

### Thay đổi

### Tiêu chí nghiệm thu

### Kiểm tra đã chạy

### Merge request

### Việc cần bạn làm
```

- `Thay đổi`: what changed, in two or three sentences.
- `Tiêu chí nghiệm thu`: the checklist, each item marked as verified by a test,
  verified by hand, or not verified.
- `Kiểm tra đã chạy`: the checks you ran and their real results.
- `Merge request`: the link and its state: merged, waiting for its pipeline,
  or blocked, and why.
- `Việc cần bạn làm`: anything the maintainer has to do or decide. Write
  `Không có.` if there is nothing.

After the merge, the pipeline on the default branch deploys the change to
staging at https://linkding-staging-248896301327.asia-southeast1.run.app.
Production is deployed separately.

## Large requests

If an issue clearly needs more than one merge request, say so in the plan
comment, describe the slices, and implement only the first one. The rules for
splitting work into child issues will be added here by the maintainer.
