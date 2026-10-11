# Identity each Cloud Run service runs as. It can reach the database and read
# only the secrets of its own environment.
resource "google_service_account" "runtime" {
  for_each = local.environments

  account_id   = "linkding-${each.key}"
  display_name = "linkding ${each.key} runtime"

  depends_on = [google_project_service.enabled]
}

resource "google_project_iam_member" "runtime_sql" {
  for_each = local.environments

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.runtime[each.key].member
}

resource "google_secret_manager_secret_iam_member" "runtime_db_password" {
  for_each = local.environments

  secret_id = google_secret_manager_secret.db_password[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime[each.key].member
}

resource "google_secret_manager_secret_iam_member" "runtime_superuser_password" {
  for_each = local.environments

  secret_id = google_secret_manager_secret.superuser_password[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime[each.key].member
}

resource "google_secret_manager_secret_iam_member" "runtime_secret_key" {
  for_each = local.environments

  secret_id = google_secret_manager_secret.secret_key[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime[each.key].member
}

resource "google_cloud_run_v2_service" "app" {
  for_each = local.environments

  name                = "linkding-${each.key}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account       = google_service_account.runtime[each.key].email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    timeout               = "60s"

    # linkding keeps its session key and downloaded files on local disk, so it
    # must not run as more than one instance.
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.bootstrap_image

      ports {
        container_port = 9090
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "LD_SERVER_HOST"
        value = "0.0.0.0"
      }
      env {
        name  = "LD_DB_ENGINE"
        value = "postgres"
      }
      env {
        name  = "LD_DB_HOST"
        value = "/cloudsql/${google_sql_database_instance.main.connection_name}"
      }
      env {
        name  = "LD_DB_DATABASE"
        value = google_sql_database.app[each.key].name
      }
      env {
        name  = "LD_DB_USER"
        value = google_sql_user.app[each.key].name
      }
      env {
        name = "LD_DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password[each.key].secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "LD_SUPERUSER_NAME"
        value = "admin"
      }
      env {
        name = "LD_SUPERUSER_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.superuser_password[each.key].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "LD_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key[each.key].secret_id
            version = "latest"
          }
        }
      }
      # Cloud Run terminates HTTPS, so the app sees plain HTTP and would reject
      # form posts unless its public origin is trusted explicitly.
      env {
        name  = "LD_CSRF_TRUSTED_ORIGINS"
        value = local.service_urls[each.key]
      }
      # Cloud Run only gives CPU while a request is being served, so the
      # background worker would stall.
      env {
        name  = "LD_DISABLE_BACKGROUND_TASKS"
        value = "True"
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      # The container runs database migrations before it starts serving.
      startup_probe {
        initial_delay_seconds = 5
        period_seconds        = 5
        timeout_seconds       = 3
        failure_threshold     = 36
        http_get {
          path = "/health"
          port = 9090
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }

  # OpenTofu owns the configuration of the service. The pipeline owns which
  # image is running, so image changes made by a deploy are not reverted here.
  lifecycle {
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
      template[0].labels,
      template[0].revision,
    ]
  }

  depends_on = [
    google_project_iam_member.runtime_sql,
    google_secret_manager_secret_iam_member.runtime_db_password,
    google_secret_manager_secret_iam_member.runtime_superuser_password,
    google_secret_manager_secret_iam_member.runtime_secret_key,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_version.superuser_password,
    google_sql_user.app,
  ]
}

# The app has its own login, so the services are reachable without Google
# authentication.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = local.environments

  name     = google_cloud_run_v2_service.app[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
