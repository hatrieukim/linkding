# Cloud Run can only run images from Google registries or Docker Hub, so the
# pipeline copies each image from the GitLab Container Registry into this one.
resource "google_artifact_registry_repository" "app" {
  repository_id = "linkding"
  location      = var.region
  format        = "DOCKER"
  description   = "linkding images deployed to Cloud Run"

  depends_on = [google_project_service.enabled]
}
