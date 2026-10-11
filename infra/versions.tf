terraform {
  required_version = ">= 1.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # The bucket is created by bootstrap.sh. State holds generated passwords,
  # so the bucket is private and versioned.
  backend "gcs" {
    bucket = "linkding-transcend-tfstate"
    prefix = "linkding"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # Bill API calls made with personal credentials to this project. Some APIs,
  # such as Cloud Billing Budgets, refuse requests without a quota project.
  user_project_override = true
  billing_project       = var.project_id
}
