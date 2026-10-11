# Keyless authentication for GitLab CI/CD. A pipeline presents a short-lived
# OIDC token signed by gitlab.com and Google exchanges it for credentials of
# the deployer service account. No Google key is stored in GitLab.
resource "google_iam_workload_identity_pool" "gitlab" {
  workload_identity_pool_id = "gitlab"
  display_name              = "GitLab CI/CD"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "gitlab" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.gitlab.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab-com"
  display_name                       = "gitlab.com"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.project_id" = "assertion.project_id"
    "attribute.ref"        = "assertion.ref"
  }

  # Tokens are accepted only from this one GitLab project, and only from jobs
  # running on its protected deploy branch.
  attribute_condition = join(" && ", [
    "assertion.project_id == \"${var.gitlab_project_id}\"",
    "assertion.ref_type == \"branch\"",
    "assertion.ref == \"${var.gitlab_deploy_ref}\"",
    "assertion.ref_protected == \"true\"",
  ])

  oidc {
    issuer_uri = "https://gitlab.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "gitlab-deployer"
  display_name = "GitLab CI/CD deployer"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account_iam_member" "deployer_from_gitlab" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gitlab.name}/attribute.project_id/${var.gitlab_project_id}"
}

# The deployer may push images, update the two services and start revisions
# that run as their runtime identities. It has no other access to the project.
resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  repository = google_artifact_registry_repository.app.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer.member
}

resource "google_cloud_run_v2_service_iam_member" "deployer_deploy" {
  for_each = local.environments

  name     = google_cloud_run_v2_service.app[each.key].name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deployer.member
}

resource "google_service_account_iam_member" "deployer_act_as_runtime" {
  for_each = local.environments

  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
