variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

resource "random_id" "suffix" {
  byte_length = 6
}

resource "google_apikeys_key" "api_key" {
  name         = "test-key-audit-${random_id.suffix.hex}"
  display_name = "Test API Key for Audit Mode"
  project      = var.google_project_id

  restrictions {
    api_targets {
      service = "translate.googleapis.com"
    }

    server_key_restrictions {
      allowed_ips = ["192.0.2.0/24"]
    }
  }
}
