variable "aws_region" {
  description = "AWS region (always-free eligible)."
  type        = string
  default     = "us-east-1"
}

variable "gcp_project" {
  description = "GCP project id."
  type        = string
}

variable "gcp_region" {
  description = "GCP region (always-free eligible, e.g. us-central1)."
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "GCP zone for the always-free e2-micro VM."
  type        = string
  default     = "us-central1-a"
}

variable "azure_subscription_id" {
  description = "Azure subscription id (free-tier anchored)."
  type        = string
}

variable "azure_location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "common_tags" {
  description = "Tags applied to every resource (FinOps chargeback)."
  type        = map(string)
  default = {
    Environment = "free-tier"
    Project     = "multi-cloud-free-tier"
    Owner       = "platform"
    CostCenter  = "cc-000"
  }
}

variable "enable_custodian_autoremediation" {
  description = "Allow Cloud Custodian to auto-stop non-compliant resources."
  type        = bool
  default     = true
}

variable "budget_alert_email" {
  description = "Email for budget alerts."
  type        = string
  default     = "finops@example.com"
}
