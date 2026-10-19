# About this fork

This repository is a fork of [linkding](https://github.com/sissbruecker/linkding)
by Sascha Ißbrücker, a self-hosted bookmark manager released under the
[MIT license](LICENSE.txt). All credit for linkding itself goes to its author
and contributors. The upstream license and copyright notice are kept unchanged.

The fork was made for the GitLab Transcend hackathon (October 2026). It starts
from upstream commit `27b7303` ("Update CHANGELOG.md", 2026-09-13) on `master`,
with its full history. Everything after that commit was added by
[hatrieukim](https://github.com/hatrieukim) (GitLab: `botabun`) or by the
GitLab Duo Developer agent working on issues in the hackathon project.

The idea: a solo open source maintainer only reads requests and makes
decisions. GitLab takes a request from an issue to production, and leaves a
record at every step.

## What was added

**Pipeline** (`.gitlab-ci.yml`). Lint and tests, GitLab security scanners
(secret detection, SAST, IaC, dependency, container scanning and DAST), an
image build, an automatic deploy to staging on every merge to `master`, a
manual deploy to production that also creates a GitLab Release, and the build
and deploy of the Slack bot. Some verify and scanner jobs can be switched off
with variables at the top of the file to keep the pipeline fast.

**Infrastructure** (`infra/`). OpenTofu code for Google Cloud: Cloud Run
services for staging, production and the bot, Cloud SQL PostgreSQL, Artifact
Registry, Secret Manager and Workload Identity Federation so the pipeline
deploys without a stored Google key. See [infra/README.md](infra/README.md).

**Agent workflow** (`AGENTS.md`, `.gitlab/duo/agent-config.yml`,
`.gitlab/issue_templates/`). Instructions that make the Duo Developer agent
plan on the issue, implement on a branch, open a merge request, enable
auto-merge, watch the pipeline and report back on the issue.

**Slack bot** (`slackbot/`). A small separate service: the maintainer
discusses a change with GitLab Duo in Slack, settles it into an issue assigned
to the agent, and follows its progress to staging in the same thread. See
[slackbot/README.md](slackbot/README.md).

**App features**, most of them implemented by the Duo Developer agent from
issues:

- `LD_SECRET_KEY` to set the Django secret key from the environment
- self-service registration with an e-mail verification code
  (`LD_ENABLE_REGISTRATION`, `LD_EMAIL_*`, see `docs/src/content/docs/options.md`)
- an interactive onboarding guide for new users
- a show/hide toggle on password fields
- a grid view that embeds bookmarked pages at mobile width

## Running it

The app runs exactly like upstream linkding; see [README.md](README.md) and
the [upstream documentation](https://linkding.link/). The pipeline, the agent
workflow and the bot are written for GitLab CI/CD, GitLab Duo Agent Platform
and Google Cloud. They are kept here for reference and do not run on GitHub.
The project ID, project number, region and Cloud Run URLs in
`.gitlab-ci.yml`, `infra/`, `AGENTS.md`, `.gitlab/duo/agent-config.yml` and
`slackbot/slack-manifest.yaml` belong to the hackathon deployment; replace
them with your own to reuse the setup.

## License

MIT, as upstream. See [LICENSE.txt](LICENSE.txt).
