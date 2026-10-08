variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

resource "google_data_loss_prevention_inspect_template" "c7n" {
  parent       = "projects/${var.google_project_id}/locations/us"
  display_name = "c7n-dlp-discovery-configs"

  inspect_config {
    info_types {
      name = "EMAIL_ADDRESS"
    }
  }
}

resource "google_data_loss_prevention_discovery_config" "c7n" {
  parent            = "projects/${var.google_project_id}/locations/us"
  location          = "us"
  display_name      = "c7n-dlp-discovery-configs"
  status            = "PAUSED"
  inspect_templates = [google_data_loss_prevention_inspect_template.c7n.id]

  targets {
    big_query_target {
      filter {
        other_tables {}
      }
    }
  }
}
