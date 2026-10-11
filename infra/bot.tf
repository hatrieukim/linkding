# Slack bot: the maintainer discusses a change with GitLab Duo in Slack, the
# bot creates the issue and then repeats the progress of that issue in the
# same Slack thread. The code is in slackbot/.

locals {
  bot_url = "https://linkding-bot-${var.project_number}.${var.region}.run.app"

  # Created by hand, because their values come from Slack and GitLab.
  # See slackbot/README.md.
  bot_secrets = {
    GITLAB_TOKEN         = var.bot_gitlab_token_secret
    SLACK_BOT_TOKEN      = var.bot_slack_token_secret
    SLACK_SIGNING_SECRET = var.bot_slack_signing_secret
  }
}

resource "google_service_account" "bot" {
  account_id   = "linkding-bot"
  display_name = "linkding Slack bot"

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_iam_member" "bot" {
  for_each = local.bot_secrets

  secret_id = "projects/${var.project_id}/secrets/${each.value}"
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.bot.member
}

# Conversations and the issues being followed are kept in Firestore.
resource "google_firestore_database" "bot" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.enabled]
}

resource "google_project_iam_member" "bot_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = google_service_account.bot.member
}

# Slack expects an answer within three seconds and a Duo turn takes longer, so
# the bot queues the work here and Cloud Tasks calls it back.
resource "google_cloud_tasks_queue" "bot" {
  name     = "linkding-bot"
  location = var.region

  rate_limits {
    max_concurrent_dispatches = 4
  }

  # A failed turn is reported in Slack. Running it again would answer twice.
  retry_config {
    max_attempts = 1
  }

  depends_on = [google_project_service.enabled]
}

resource "google_cloud_tasks_queue_iam_member" "bot_enqueue" {
  name     = google_cloud_tasks_queue.bot.name
  location = var.region
  role     = "roles/cloudtasks.enqueuer"
  member   = google_service_account.bot.member
}

# The callbacks carry a token of the bot's own identity, which the bot checks.
# Asking for such a token requires permission to act as that identity.
resource "google_service_account_iam_member" "bot_act_as_self" {
  service_account_id = google_service_account.bot.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.bot.member
}

resource "google_cloud_run_v2_service" "bot" {
  name                = "linkding-bot"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account       = google_service_account.bot.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    # One request can be a whole Duo turn.
    timeout = "600s"

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.bot_bootstrap_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "SERVICE_URL"
        value = local.bot_url
      }
      env {
        name  = "TASKS_QUEUE"
        value = google_cloud_tasks_queue.bot.id
      }
      env {
        name  = "INVOKER_SERVICE_ACCOUNT"
        value = google_service_account.bot.email
      }
      env {
        name  = "GITLAB_PROJECT_ID"
        value = var.gitlab_project_id
      }
      env {
        name  = "GITLAB_AGENT_USERNAME"
        value = var.bot_agent_username
      }
      env {
        name  = "DUO_MODEL"
        value = var.bot_duo_model
      }
      env {
        name  = "STAGING_URL"
        value = local.service_urls["staging"]
      }
      env {
        name  = "SLACK_ALLOWED_USERS"
        value = join(",", var.bot_slack_allowed_users)
      }
      dynamic "env" {
        for_each = local.bot_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  # The pipeline owns which image is running, as for the app itself.
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
    google_secret_manager_secret_iam_member.bot,
    google_project_iam_member.bot_firestore,
  ]
}

# Slack has to reach the bot, so it is public. Requests from Slack are checked
# by signature, internal callbacks by their Google token.
resource "google_cloud_run_v2_service_iam_member" "bot_public" {
  name     = google_cloud_run_v2_service.bot.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Once a minute the bot looks for news on the issues it follows. A Developer
# role on GitLab cannot register webhooks, so the bot asks instead of being told.
resource "google_cloud_scheduler_job" "bot_tick" {
  name             = "linkding-bot-tick"
  region           = var.region
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"

  retry_config {
    retry_count = 0
  }

  http_target {
    uri         = "${local.bot_url}/tick"
    http_method = "POST"

    oidc_token {
      service_account_email = google_service_account.bot.email
      audience              = local.bot_url
    }
  }

  depends_on = [google_project_service.enabled, google_cloud_run_v2_service.bot]
}

# The pipeline may deploy new images of the bot, as it does for the app.
resource "google_cloud_run_v2_service_iam_member" "deployer_deploy_bot" {
  name     = google_cloud_run_v2_service.bot.name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deployer.member
}

resource "google_service_account_iam_member" "deployer_act_as_bot" {
  service_account_id = google_service_account.bot.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
