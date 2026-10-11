variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "project_number" {
  description = "Google Cloud project number. Used to build the stable Cloud Run URLs."
  type        = string
}

variable "region" {
  description = "Region for all resources."
  type        = string
  default     = "asia-southeast1"
}

variable "gitlab_project_id" {
  description = "Numeric ID of the GitLab project whose pipelines may deploy."
  type        = string
}

variable "gitlab_deploy_ref" {
  description = "Only pipelines on this protected branch may deploy."
  type        = string
  default     = "master"
}

variable "bootstrap_image" {
  description = "Image used when a Cloud Run service is first created. The pipeline replaces it on the first deploy."
  type        = string
  default     = "docker.io/sissbruecker/linkding:1.47.0"
}

variable "billing_account" {
  description = "Billing account ID for the budget alert. Leave empty to skip the budget."
  type        = string
  default     = ""
}

variable "budget_amount" {
  description = "Monthly budget, in the currency of the billing account."
  type        = number
  default     = 500000
}

variable "budget_currency" {
  description = "Currency of the billing account."
  type        = string
  default     = "VND"
}
