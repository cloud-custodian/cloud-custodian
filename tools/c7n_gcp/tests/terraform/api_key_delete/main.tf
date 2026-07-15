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
  name         = "test-key-${random_id.suffix.hex}"
  display_name = "Test API Key"
  project      = var.google_project_id

  # No restrictions — this key is intentionally unrestricted so the
  # policy can find and delete it.
}
