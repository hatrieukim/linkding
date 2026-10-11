# Passwords are generated here and stored in Secret Manager. They never appear
# in the repository or in GitLab CI/CD variables.
resource "random_password" "superuser" {
  for_each = local.environments

  length  = 24
  special = false
}

resource "google_secret_manager_secret" "db_password" {
  for_each = local.environments

  secret_id = "linkding-${each.key}-db-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "db_password" {
  for_each = local.environments

  secret      = google_secret_manager_secret.db_password[each.key].id
  secret_data = random_password.db[each.key].result
}

resource "google_secret_manager_secret" "superuser_password" {
  for_each = local.environments

  secret_id = "linkding-${each.key}-superuser-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "superuser_password" {
  for_each = local.environments

  secret      = google_secret_manager_secret.superuser_password[each.key].id
  secret_data = random_password.superuser[each.key].result
}

# Signs login sessions. Without a fixed key the app generates a new one on
# every start, which logs everyone out after each deploy or cold start.
resource "random_password" "secret_key" {
  for_each = local.environments

  length  = 64
  special = false
}

resource "google_secret_manager_secret" "secret_key" {
  for_each = local.environments

  secret_id = "linkding-${each.key}-secret-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "secret_key" {
  for_each = local.environments

  secret      = google_secret_manager_secret.secret_key[each.key].id
  secret_data = random_password.secret_key[each.key].result
}

