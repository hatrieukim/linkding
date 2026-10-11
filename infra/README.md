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
