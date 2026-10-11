locals {
  # One Cloud Run service, one database and one set of secrets per environment.
  environments = toset(["staging", "production"])

  # Cloud Run gives every service this stable URL in addition to the hashed one.
  service_urls = {
    for env in local.environments :
    env => "https://linkding-${env}-${var.project_number}.${var.region}.run.app"
  }

  apis = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "sts.googleapis.com",
  ])
}

resource "google_project_service" "enabled" {
  for_each = local.apis

  service            = each.key
  disable_on_destroy = false
}
