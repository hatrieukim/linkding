# One small PostgreSQL instance shared by both environments. Each environment
# has its own database and its own user.
resource "google_sql_database_instance" "main" {
  name             = "linkding"
  region           = var.region
  database_version = "POSTGRES_16"

  # Guards against deleting the production data with a stray `tofu destroy`.
  deletion_protection = true

  settings {
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false

    backup_configuration {
      enabled = true
    }

    # Public IP with no authorised networks: the only way in is the Cloud SQL
    # connector, which requires IAM permission and encrypts the connection.
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "app" {
  for_each = local.environments

  name     = "linkding_${each.key}"
  instance = google_sql_database_instance.main.name
}

resource "random_password" "db" {
  for_each = local.environments

  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  for_each = local.environments

  name            = "linkding_${each.key}"
  instance        = google_sql_database_instance.main.name
  password        = random_password.db[each.key].result
  deletion_policy = "ABANDON"
}
