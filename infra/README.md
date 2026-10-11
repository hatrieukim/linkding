# Infrastructure

Everything linkding needs on Google Cloud, described with [OpenTofu](https://opentofu.org/).

| File | Creates |
|---|---|
| `main.tf` | Enabled APIs, shared names |
| `registry.tf` | Artifact Registry repository for images |
| `database.tf` | One Cloud SQL PostgreSQL instance with a database and user per environment |
| `secrets.tf` | Generated database passwords, admin passwords and session keys in Secret Manager |
| `run.tf` | Two Cloud Run services, `linkding-staging` and `linkding-production`, and their runtime identities |
| `gitlab.tf` | Workload Identity Federation so GitLab CI/CD can deploy without a stored key |
| `budget.tf` | Optional monthly budget alert |

## Who changes what

OpenTofu owns the configuration of the services: environment variables, database connection, scaling and permissions. The GitLab pipeline owns which image is running. A deploy only replaces the image, and OpenTofu is told to ignore that field.

OpenTofu is applied from a maintainer's machine, not from CI. The pipeline only checks formatting and validity of these files. Its Google identity can push images and update the two services and nothing else.

## Access from GitLab

Google accepts an OIDC token from gitlab.com only if it comes from this project and from a job on the protected `master` branch. The token is exchanged for short-lived credentials of the `gitlab-deployer` service account. No Google credential is stored in GitLab.

## Registration e-mail

Visitors can create their own account. The app e-mails them a six digit code
through an SMTP server. The SMTP credentials belong to a mail account outside
this project, so they are not generated here. Create the two secrets once, by
hand, before applying:

```sh
printf '%s' 'sender@example.com' | gcloud secrets create linkding-smtp-user --data-file=-
gcloud secrets create linkding-smtp-password --data-file=-   # paste the password, then Ctrl-D
```

With Gmail, the user is the Gmail address and the password is an
[app password](https://myaccount.google.com/apppasswords), not the account
password. Set `enable_registration = false` to switch the feature off.

## Slack bot

`bot.tf` creates the service for the Slack bot in [`slackbot/`](../slackbot/README.md):
a Cloud Run service, a Cloud Tasks queue, a Cloud Scheduler job that calls the
bot every minute, a Firestore database and the permissions between them.

The bot needs three secrets that are created by hand before the first apply,
because their values come from Slack and GitLab: `linkding-bot-slack-token`,
`linkding-bot-slack-signing-secret` and `linkding-bot-gitlab-token`. The steps
are in [`slackbot/README.md`](../slackbot/README.md#set-up).

## Apply

Requires `gcloud` and `tofu`, and a Google Cloud project with billing enabled.

```sh
gcloud auth login
gcloud auth application-default login

cd infra
./bootstrap.sh <project-id>          # state bucket and base APIs, once
cp terraform.tfvars.example terraform.tfvars
tofu init
tofu plan
tofu apply
```

The first apply takes about 15 minutes, most of it waiting for the database instance.

The admin password of an environment:

```sh
gcloud secrets versions access latest --secret linkding-staging-superuser-password
```

## Known limits

- Files that linkding stores on disk (favicons, previews, uploaded assets) do not survive a new revision. Bookmarks are in PostgreSQL and do.
- Background tasks are disabled, because Cloud Run only provides CPU while a request is being served.
- Both database users live on the same instance. They are separated by credentials, not by network.
