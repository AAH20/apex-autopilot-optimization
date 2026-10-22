terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
  }
}

provider "aws" {
  alias  = "primary"
  region = var.aws_region
  # Always-free path only: default tags applied to every resource.
  default_tags {
    tags = merge(var.common_tags, {
      CloudProvider = "aws"
      ManagedBy     = "terraform"
    })
  }
}

provider "google" {
  alias  = "primary"
  project = var.gcp_project
  region  = var.gcp_region
  zone    = var.gcp_zone
  default_tags {
    tags = merge(var.common_tags, {
      CloudProvider = "gcp"
      ManagedBy     = "terraform"
    })
  }
}

provider "azurerm" {
  alias  = "primary"
  features {}
  # Subscription/resource group sourced from environment or var.
  subscription_id = var.azure_subscription_id
  default_tags {
    tags = merge(var.common_tags, {
      CloudProvider = "azure"
      ManagedBy     = "terraform"
    })
  }
}
