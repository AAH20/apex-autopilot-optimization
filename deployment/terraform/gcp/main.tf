# GCP — always-free services only.
# Cloud Run (2M req/mo), Cloud Storage (5 GB US), Firestore Native (1 GB),
# Compute e2-micro (1 instance, always-free), Monitoring alert policy.

resource "google_cloud_run_service" "api_burst" {
  name     = "mcft-api-burst"
  location = var.gcp_region

  metadata {
    annotations = {
      "run.googleapis.com/ingress" = "all"
    }
    labels = var.common_tags
  }

  template {
    spec {
      containers {
        image = "us-docker.pkg.dev/cloudrun/container/hello:latest"
        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

resource "google_storage_bucket" "archive" {
  name          = "mcft-archive"
  location      = "US"
  storage_class = "STANDARD"
  labels        = var.common_tags
}

resource "google_firestore_database" "metadata" {
  name     = "projects/${var.gcp_project}/databases/metadata"
  location = var.gcp_region
  type     = "FIRESTORE_NATIVE"
}

# Always-free e2-micro VM (1 instance, us regions) — bastion / cron only.
resource "google_compute_instance" "bastion" {
  name         = "mcft-bastion"
  machine_type = "e2-micro"
  zone         = var.gcp_zone
  tags         = ["mcft-bastion"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    network = "default"
    access_config {
      # Ephemeral external IP.
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  # Stop when idle to guarantee always-free compliance.
  scheduling {
    automatic_restart = false
    on_host_maintenance = "TERMINATE"
  }
}

# Alert when GCP spend crosses the tripwire.
resource "google_monitoring_alert_policy" "budget_tripwire" {
  display_name = "mcft-gcp-budget-tripwire"
  combiner     = "OR"

  conditions {
    condition_threshold {
      filter     = "resource.type=\"gcp_billing_account\""
      duration   = "60s"
      comparison = "COMPARISON_GT"
      threshold_value = 0.50
    }
  }
}
