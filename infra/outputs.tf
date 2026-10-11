output "service_urls" {
  description = "Public URL of each environment."
  value       = local.service_urls
}

output "artifact_registry" {
  description = "Registry path the pipeline pushes images to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}

output "workload_identity_provider" {
  description = "Audience of the OIDC token that GitLab CI/CD jobs must request."
  value       = "https://iam.googleapis.com/${google_iam_workload_identity_pool_provider.gitlab.name}"
}

output "deployer_service_account" {
  description = "Service account that GitLab CI/CD jobs impersonate."
  value       = google_service_account.deployer.email
}
